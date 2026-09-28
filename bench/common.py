"""Shared helpers: paths, data loading, ground truth, CPU layout, page cache, host metadata."""
import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time

import numpy as np

ROOT = os.environ.get("BENCH_ROOT", os.path.expanduser("~/rag_bench"))
DATA_DIR = os.environ.get("BENCH_DATA", os.path.join(ROOT, "data"))
CACHE_DIR = os.environ.get("BENCH_CACHE", os.path.join(ROOT, "cache"))


def now_ns():
    # CLOCK_MONOTONIC is shared by all processes on the node, so worker timestamps are comparable
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def normalize(x):
    n = np.linalg.norm(x, axis=1, keepdims=True)
    n[n == 0] = 1
    return (x / n).astype(np.float32)


def load_vectors(n, dim, synthetic=0, seed=42):
    """Returns (base, queries, tag). Truncated dims are re-normalized (Matryoshka style)."""
    if synthetic:
        # clustered data, so HNSW recall behaves roughly like real embeddings
        rng = np.random.default_rng(seed)
        centers = rng.standard_normal((max(n // 500, 8), dim)).astype(np.float32)
        pick = rng.integers(0, len(centers), n + 1000)
        pts = centers[pick] + 0.35 * rng.standard_normal((n + 1000, dim)).astype(np.float32)
        pts = normalize(pts)
        return pts[:n], pts[n:], f"synth{seed}"

    full = np.load(os.path.join(DATA_DIR, "embeddings_1m.npy"), mmap_mode="r")
    if n > len(full):
        sys.exit(f"asked for {n} vectors but embeddings_1m.npy has {len(full)}")
    base = np.ascontiguousarray(full[:n, :dim], dtype=np.float32)
    queries = np.load(os.path.join(DATA_DIR, "queries.npy"))[:, :dim].astype(np.float32)
    if dim < full.shape[1]:
        base, queries = normalize(base), normalize(queries)
    return base, queries, "msmarco"


def ground_truth(base, queries, k, tag):
    """Exact top-k by inner product (vectors are unit length, so this equals cosine). Cached on disk."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"gt_{tag}_n{len(base)}_d{base.shape[1]}_q{len(queries)}_k{k}.npy")
    if os.path.exists(path):
        return np.load(path)
    log(f"computing ground truth, cached at {path}")
    gt = np.empty((len(queries), k), dtype=np.int64)
    for s in range(0, len(queries), 64):
        sims = queries[s:s + 64] @ base.T
        idx = np.argpartition(-sims, k, axis=1)[:, :k]
        order = np.argsort(-np.take_along_axis(sims, idx, 1), axis=1)
        gt[s:s + 64] = np.take_along_axis(idx, order, 1)
    np.save(path, gt)
    return gt


def summarize(lat_ns):
    ms = np.asarray(lat_ns, dtype=np.float64) / 1e6
    if len(ms) == 0:
        return {"count": 0}
    p = np.percentile(ms, [50, 90, 95, 99, 99.9])
    return {
        "count": int(len(ms)),
        "mean_ms": round(float(ms.mean()), 4),
        "std_ms": round(float(ms.std()), 4),
        "p50_ms": round(float(p[0]), 4),
        "p90_ms": round(float(p[1]), 4),
        "p95_ms": round(float(p[2]), 4),
        "p99_ms": round(float(p[3]), 4),
        "p999_ms": round(float(p[4]), 4),
        "max_ms": round(float(ms.max()), 4),
    }


# CPU layout

def parse_cpus(spec):
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


def fmt_cpus(cpus):
    return ",".join(str(c) for c in sorted(cpus))


def numa_nodes():
    nodes = []
    base = "/sys/devices/system/node"
    if os.path.isdir(base):
        for d in sorted(os.listdir(base)):
            if d.startswith("node") and d[4:].isdigit():
                with open(os.path.join(base, d, "cpulist")) as f:
                    nodes.append(parse_cpus(f.read().strip()))
    return nodes


def pick_cores(server_spec, client_spec):
    """Works inside whatever cpuset Slurm gave the job (20 cores on barbun, not a full node).
    'auto:8' puts the server on the first 8 allowed cores of the first NUMA node that has any.
    Client 'auto' takes the allowed cores on the other NUMA node if there are at least 12 of
    them (keeps client and server off each other's L3), otherwise every remaining core."""
    allowed = sorted(os.sched_getaffinity(0))
    nodes = [[c for c in nd if c in allowed] for nd in numa_nodes()] or [allowed]
    nodes = [nd for nd in nodes if nd]
    if server_spec.startswith("auto"):
        k = int(server_spec.split(":")[1]) if ":" in server_spec else 8
        server = nodes[0][:k]
    else:
        server = parse_cpus(server_spec)
    if client_spec == "auto":
        other = [c for nd in nodes if not set(nd) & set(server) for c in nd]
        client = other if len(other) >= 12 else [c for c in allowed if c not in server]
    else:
        client = parse_cpus(client_spec)
    if not client:
        sys.exit(f"no cores left for the client (allowed {allowed}, server {server})")
    if set(server) & set(client):
        sys.exit(f"server cores {server} overlap client cores {client}")
    return server, client


# Page cache handling for memory-limited runs

def evict_page_cache(path):
    """Drops the clean page-cache pages of every file under path. Works without root
    (fsync + POSIX_FADV_DONTNEED), which is what we need on a shared cluster."""
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            p = os.path.join(root, name)
            try:
                fd = os.open(p, os.O_RDONLY)
            except OSError:
                continue
            try:
                os.fsync(fd)
                os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
                total += os.fstat(fd).st_size
            except OSError:
                pass
            finally:
                os.close(fd)
    return total


def resident_bytes(path):
    """Bytes of path currently in page cache, via util-linux fincore. None if fincore is missing."""
    if not shutil.which("fincore"):
        return None
    files = [os.path.join(r, f) for r, _, fs in os.walk(path) for f in fs]
    total = 0
    for i in range(0, len(files), 500):
        out = subprocess.run(["fincore", "-b", "-n", "-o", "RES"] + files[i:i + 500],
                             capture_output=True, text=True).stdout
        total += sum(int(x) for x in out.split() if x.isdigit())
    return total


def dir_size(path):
    """Allocated bytes on disk. Qdrant preallocates sparse files, so apparent size overstates it."""
    total = 0
    for r, _, fs in os.walk(path):
        for f in fs:
            try:
                total += os.lstat(os.path.join(r, f)).st_blocks * 512
            except OSError:
                pass
    return total


# Metadata

def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception as e:  # tool missing or not permitted, just note it
        return f"unavailable: {e}"


def sha256(path, limit_mb=2048):
    if not path or not os.path.isfile(path) or os.path.getsize(path) > limit_mb * 2**20:
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def host_info():
    cpu_model = None
    for line in (_read("/proc/cpuinfo") or "").splitlines():
        if line.startswith("model name"):
            cpu_model = line.split(":", 1)[1].strip()
            break
    mem_kb = None
    for line in (_read("/proc/meminfo") or "").splitlines():
        if line.startswith("MemTotal"):
            mem_kb = int(line.split()[1])
    slurm = {k: v for k, v in os.environ.items() if k.startswith("SLURM_") and k in (
        "SLURM_JOB_ID", "SLURM_JOB_PARTITION", "SLURM_JOB_NODELIST", "SLURM_CPUS_ON_NODE",
        "SLURM_MEM_PER_NODE", "SLURM_ARRAY_TASK_ID")}
    return {
        "hostname": socket.gethostname(),
        "kernel": platform.release(),
        "os": _read("/etc/os-release"),
        "cpu_model": cpu_model,
        "logical_cpus": os.cpu_count(),
        "numa_nodes": numa_nodes(),
        "mem_total_gb": round(mem_kb / 2**20, 1) if mem_kb else None,
        "governor": _read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"),
        "lscpu": _run(["lscpu"]),
        "python": sys.version,
        "slurm": slurm,
        # barbun jobs get 20 of 40 cores, so another job may share the node. Recorded for the
        # threats-to-validity section.
        "loadavg": _read("/proc/loadavg"),
        "node_jobs": _run(["squeue", "-h", "-w", socket.gethostname(), "-o", "%i %u %C %j"])
        if "SLURM_JOB_ID" in os.environ else None,
        "time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def save_json(obj, path):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2, default=str)
    os.replace(tmp, path)
