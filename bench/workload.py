"""Latency sweep (one client) and closed-loop concurrency (N client processes) plus telemetry."""
import collections
import multiprocessing as mp
import os
import shutil
import signal
import subprocess
import threading
import time

import numpy as np
import psutil

from common import log, now_ns, summarize
from engines import make_query_fn
from features import (open_loop_summary, pad_ids, perf_record_cmd, poisson_arrivals)


def recall_hits(ids, gt_row):
    return len(set(ids) & set(gt_row.tolist()))


def proc_counters(pids, proc_root="/proc"):
    """Page faults, bytes read from storage and resident memory summed over processes.

    Processes that have exited are skipped. The stat file is split after the last ")" because
    the command name may contain spaces and parentheses."""
    from pathlib import Path
    root = Path(proc_root)
    total = {"minor_faults": 0, "major_faults": 0, "read_bytes": 0, "rss_kb": 0, "rss_file_kb": 0}
    for pid in pids:
        try:
            fields = (root / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
            total["minor_faults"] += int(fields[7])
            total["major_faults"] += int(fields[9])
            for line in (root / str(pid) / "io").read_text().splitlines():
                if line.startswith("read_bytes:"):
                    total["read_bytes"] += int(line.split()[1])
            for line in (root / str(pid) / "status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    total["rss_kb"] += int(line.split()[1])
                elif line.startswith("RssFile:"):
                    total["rss_file_kb"] += int(line.split()[1])
        except (OSError, IndexError, ValueError):
            continue
    return total


def cgroup_memory_bytes(pid, sys_root="/sys/fs/cgroup"):
    """memory.current of the cgroup a process belongs to, or None where it cannot be read."""
    try:
        with open(f"/proc/{pid}/cgroup") as f:
            relative = next(line.strip().split("::", 1)[1] for line in f if line.startswith("0::"))
        with open(os.path.join(sys_root, relative.lstrip("/"), "memory.current")) as f:
            return int(f.read().strip())
    except (OSError, StopIteration, IndexError, ValueError):
        return None


def pass_order(n, seed, index):
    """Query order of one pass: a permutation fixed by (seed, pass index), so repetitions with
    different seeds differ and a pass can be reproduced."""
    return np.random.default_rng([seed, index]).permutation(n)


def memory_passes(query_fn, queries, gt, k, passes, order_seed, counters_fn, stats_begin, stats_end):
    """Cold-start and steady-state passes over the whole query set, one client.

    Pass 0 follows a server restart with an evicted page cache and has no warm-up, so it
    measures the cold start. Later passes measure the steady state. Every pass visits every
    query once in its own random order, so the measurement is not a fixed subset of the graph."""
    rows, raw = [], {}
    for index in range(passes):
        order = pass_order(len(queries), order_seed, index)
        lat = np.empty(len(order), dtype=np.int64)
        hits = 0
        before = counters_fn()
        stats_begin()
        wall0 = now_ns()
        for slot, j in enumerate(order):
            t0 = now_ns()
            ids = query_fn(queries[j])
            lat[slot] = now_ns() - t0
            hits += recall_hits(ids, gt[j])
        wall_s = (now_ns() - wall0) / 1e9
        stats = stats_end()
        after = counters_fn()
        row = {
            "pass": index, "phase": "cold" if index == 0 else "steady",
            "recall_at_k": round(hits / (k * len(order)), 5),
            "wall_s": round(wall_s, 3), "throughput_qps": round(len(order) / wall_s, 3) if wall_s else None,
            "major_faults": after["major_faults"] - before["major_faults"],
            "minor_faults": after["minor_faults"] - before["minor_faults"],
            "read_bytes": after["read_bytes"] - before["read_bytes"],
            "rss_kb": after["rss_kb"], **summarize(lat), **stats,
        }
        rows.append(row)
        raw[f"mem_pass{index}_lat"] = lat
        raw[f"mem_pass{index}_order"] = order
    return rows, raw


def latency_sweep(server, protocols, efs, reps, queries, warm, gt, k, store_ids=False, perf_record_dir=None):
    """Sequential queries, one persistent connection per (protocol, ef). Each (protocol, ef)
    gets its own untimed warm-up pass over a separate query set before the measured reps.

    store_ids keeps the returned row numbers (n_queries x k, -1 padded) for rep 0 of every
    (protocol, ef); perf_record_dir samples the server's user-space cycles during that same rep."""
    out, raw = [], {}
    for proto in protocols:
        for ef in efs:
            q = make_query_fn(server.query_spec(ef, proto, k))
            plan = server.plan(ef, queries[0], k) if hasattr(server, "plan") else None
            if plan and not all(p["uses_index"] for p in plan.values()):
                log(f"  WARNING {server.name} ef={ef}: plan without the ANN index: {plan}")
            for v in warm:
                q(v)
            for rep in range(reps):
                lat = np.empty(len(queries), dtype=np.int64)
                per_query_hits = np.empty(len(queries), dtype=np.int16)
                returned = np.full((len(queries), k), -1, dtype=np.int64) if store_ids and rep == 0 else None
                perf_rec = (start_perf_record(server.pids(), os.path.join(
                    perf_record_dir, f"perfrec_{proto}_ef{ef}.data")) if perf_record_dir and rep == 0 else None)
                hits = 0
                server.stats_begin(proto)
                cpu0_srv = server.cpu_seconds()
                cpu0_client = _cpu([os.getpid()])
                for i, v in enumerate(queries):
                    t0 = now_ns()
                    ids = q(v)
                    lat[i] = now_ns() - t0
                    if returned is not None:
                        returned[i] = pad_ids(ids, k)
                    per_query_hits[i] = recall_hits(ids, gt[i])
                    hits += per_query_hits[i]
                cpu1_srv = server.cpu_seconds()
                cpu1_client = _cpu([os.getpid()])
                srv = server.stats_end(proto)
                if perf_rec is not None:
                    stop_perf_record(perf_rec)
                row = {"proto": proto, "ef": ef, "rep": rep, "recall_at_k": round(hits / (k * len(queries)), 5),
                       "server_cpu_ms_per_query": round(
                           (cpu1_srv - cpu0_srv) * 1000 / max(len(queries), 1), 6
                       ),
                       "client_cpu_ms_per_query": round(
                           (cpu1_client - cpu0_client) * 1000 / max(len(queries), 1), 6
                       ),
                       **summarize(lat), **srv}
                if plan:
                    row["plan"] = plan
                if perf_rec is not None:
                    row["perf_record_file"] = f"perfrec_{proto}_ef{ef}.data"
                out.append(row)
                if returned is not None:
                    raw[f"ids_{proto}_ef{ef}_rep{rep}"] = returned
                raw[f"lat_{proto}_ef{ef}_rep{rep}"] = lat
                # Neighbors found per query (0..k): the per-query recall distribution, not only its mean.
                raw[f"hits_{proto}_ef{ef}_rep{rep}"] = per_query_hits
                log(f"  {server.name}/{proto} ef={ef} rep={rep}: mean={row['mean_ms']}ms "
                    f"p99={row['p99_ms']}ms recall={row['recall_at_k']} server={srv.get('server_mean_ms')}ms")
    return out, raw


def _worker(spec, queries, gt, offset, ready, go, stop, results):
    # Pin nothing here: the parent already restricted affinity to the client cores.
    try:
        q = make_query_fn(spec)
        q(queries[offset % len(queries)])  # connect and warm the connection before timing
    except Exception as e:
        ready.put(("err", repr(e)))
        return
    ready.put(("ok", os.getpid()))
    go.wait()
    starts, lats, hits = [], [], []
    i = offset
    k = spec["k"]
    while not stop.is_set():
        j = i % len(queries)
        t0 = now_ns()
        ids = q(queries[j])
        t1 = now_ns()
        starts.append(t0)
        lats.append(t1 - t0)
        hits.append(recall_hits(ids, gt[j]))
        i += 1
    results.put((np.array(starts, dtype=np.int64), np.array(lats, dtype=np.int64),
                 np.array(hits, dtype=np.int16), k))


class WaitEventSampler(threading.Thread):
    """Samples pg_stat_activity wait events of active client backends every 10 ms. This is the
    no-root substitute for eBPF lock tracing: LWLock, BufferMapping, IO:DataFileRead, etc."""

    def __init__(self, server, period=0.01):
        super().__init__(daemon=True)
        self.server, self.period = server, period
        self.counts = collections.Counter()
        self.samples = 0
        self.halt = threading.Event()

    def run(self):
        with self.server.admin() as conn:
            sql = ("SELECT coalesce(wait_event_type, 'CPU'), coalesce(wait_event, 'running') "
                   "FROM pg_stat_activity WHERE backend_type = 'client backend' "
                   "AND state = 'active' AND pid <> pg_backend_pid()")
            while not self.halt.is_set():
                for t, e in conn.execute(sql).fetchall():
                    self.counts[f"{t}:{e}"] += 1
                self.samples += 1
                time.sleep(self.period)

    def result(self):
        total = sum(self.counts.values()) or 1
        return {"samples": self.samples, "active_backend_observations": sum(self.counts.values()),
                "share": {k: round(v / total, 4) for k, v in self.counts.most_common(15)}}


# ARF has perf_event_paranoid=2, so only user-space counts are meaningful. Context switches come from
# /proc instead (see _ctx), since perf reports them as 0 at that level.
PERF_EVENTS = (
    "task-clock,page-faults,cycles:u,instructions:u,cache-references:u,cache-misses:u,"
    "branches:u,branch-misses:u"
)


def start_perf(pids, path):
    if not shutil.which("perf") or not pids:
        return None
    return subprocess.Popen(["perf", "stat", "-x", ",", "-o", path, "-e", PERF_EVENTS,
                             "-p", ",".join(map(str, pids))],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def stop_perf(proc, path):
    if proc is None:
        return None
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(20)
    except subprocess.TimeoutExpired:
        proc.kill()
    res = {}
    try:
        for line in open(path):
            parts = line.strip().split(",")
            if len(parts) >= 3 and not line.startswith("#"):
                try:
                    res[parts[2]] = float(parts[0])
                except ValueError:
                    res[parts[2]] = parts[0]  # "<not supported>" or "<not counted>"
    except OSError:
        return {"error": "perf produced no output (perf_event_paranoid?)"}
    return res


def start_perf_record(pids, path):
    """Sampling profile of the server processes (user space), or None where perf is missing."""
    if not shutil.which("perf") or not pids:
        return None
    return subprocess.Popen(perf_record_cmd(pids, path), stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)


def stop_perf_record(proc):
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(60)
    except subprocess.TimeoutExpired:
        proc.kill()


def perf_per_query(perf, query_count):
    """Normalize supported numeric perf totals and derive ratios without inventing gaps."""
    if not perf or query_count <= 0:
        return None
    numeric = {key: value for key, value in perf.items() if isinstance(value, (int, float))}
    out = {
        "query_count": int(query_count),
        "events_per_query": {key: round(value / query_count, 6) for key, value in numeric.items()},
    }
    cycles = next((value for key, value in numeric.items() if key.split(":")[0] == "cycles"), None)
    instructions = next((value for key, value in numeric.items() if key.split(":")[0] == "instructions"), None)
    refs = next((value for key, value in numeric.items() if key.split(":")[0] == "cache-references"), None)
    misses = next((value for key, value in numeric.items() if key.split(":")[0] == "cache-misses"), None)
    branches = next((value for key, value in numeric.items() if key.split(":")[0] == "branches"), None)
    branch_misses = next((value for key, value in numeric.items() if key.split(":")[0] == "branch-misses"), None)
    if cycles:
        out["instructions_per_cycle"] = round(instructions / cycles, 6) if instructions is not None else None
    if refs:
        out["cache_miss_ratio"] = round(misses / refs, 6) if misses is not None else None
    if branches:
        out["branch_miss_ratio"] = round(branch_misses / branches, 6) if branch_misses is not None else None
    return out


def concurrency_run(server, proto, ef, clients, duration, warmup, queries, gt, k, perf_path=None):
    """Closed loop: `clients` processes, each with its own connection, issue queries back to back.
    Only queries that start inside the measurement window count, after `warmup` seconds."""
    ctx = mp.get_context("spawn")
    ready, results = ctx.Queue(), ctx.Queue()
    go, stop = ctx.Event(), ctx.Event()
    spec = server.query_spec(ef, proto, k)
    procs = [ctx.Process(target=_worker, args=(spec, queries, gt, w * len(queries) // clients,
                                                ready, go, stop, results), daemon=True)
             for w in range(clients)]
    for p in procs:
        p.start()
    worker_pids = []
    for _ in procs:
        status, info = ready.get(timeout=300)
        if status != "ok":
            stop.set()
            go.set()
            raise RuntimeError(f"client worker failed: {info}")
        worker_pids.append(info)

    go.set()
    t_go = now_ns()
    time.sleep(warmup)

    sampler = None
    if server.name == "pg":
        sampler = WaitEventSampler(server)
        sampler.start()
    srv_pids = server.pids()
    perf = start_perf(srv_pids, perf_path) if perf_path else None
    server.stats_begin(proto)
    cpu0_srv = server.cpu_seconds()
    cpu0_cli = _cpu(worker_pids)
    ctx0 = _ctx(srv_pids)
    w0 = now_ns()
    time.sleep(duration)
    w1 = now_ns()
    cpu1_srv = server.cpu_seconds()
    cpu1_cli = _cpu(worker_pids)
    ctx1 = _ctx(srv_pids)
    srv = server.stats_end(proto)
    perf_res = stop_perf(perf, perf_path) if perf else None
    if sampler:
        sampler.halt.set()
        sampler.join(5)
    stop.set()

    starts, lats, hits = [], [], []
    for _ in procs:
        s, l, h, _k = results.get(timeout=120)
        starts.append(s)
        lats.append(l)
        hits.append(h)
    for p in procs:
        p.join(30)
    s, l, h = np.concatenate(starts), np.concatenate(lats), np.concatenate(hits)
    in_win = (s >= w0) & (s < w1)
    done_in_win = ((s + l) >= w0) & ((s + l) < w1)
    wall = (w1 - w0) / 1e9
    row = {
        "proto": proto, "ef": ef, "clients": clients, "window_s": round(wall, 3),
        "throughput_qps": round(int(done_in_win.sum()) / wall, 2),
        "recall_at_k": round(float(h[in_win].sum()) / (k * max(int(in_win.sum()), 1)), 5),
        **summarize(l[in_win]),
        "server_cores_busy": round((cpu1_srv - cpu0_srv) / wall, 3),
        "server_cpu_ms_per_query": round(
            (cpu1_srv - cpu0_srv) * 1000 / max(int(done_in_win.sum()), 1), 6
        ),
        "server_cores_allotted": len(server.cores),
        "client_cores_busy": round((cpu1_cli - cpu0_cli) / wall, 3),
        "client_cpu_ms_per_query": round(
            (cpu1_cli - cpu0_cli) * 1000 / max(int(done_in_win.sum()), 1), 6
        ),
        "client_cores_allotted": len(os.sched_getaffinity(0)),
        "server_ctx_switches_per_query": {
            "voluntary": round((ctx1[0] - ctx0[0]) / max(int(done_in_win.sum()), 1), 3),
            "involuntary": round((ctx1[1] - ctx0[1]) / max(int(done_in_win.sum()), 1), 3)},
        "warmup_s": warmup, **srv,
    }
    if sampler:
        row["pg_wait_events"] = sampler.result()
    if perf_res is not None:
        row["perf"] = perf_res
        row["perf_derived"] = perf_per_query(perf_res, int(done_in_win.sum()))
    log(f"  {server.name}/{proto} C={clients}: {row['throughput_qps']} qps mean={row['mean_ms']}ms "
        f"p99={row['p99_ms']}ms srv_cores={row['server_cores_busy']} cli_cores={row['client_cores_busy']}")
    raw = {f"conc_{proto}_ef{ef}_c{clients}_lat": l[in_win], f"conc_{proto}_ef{ef}_c{clients}_start": s[in_win] - t_go}
    return row, raw


def _ctx(pids):
    vol = inv = 0
    for p in pids:
        try:
            c = psutil.Process(p).num_ctx_switches()
            vol, inv = vol + c.voluntary, inv + c.involuntary
        except psutil.Error:
            pass
    return vol, inv


def _cpu(pids):
    total = 0.0
    for p in pids:
        try:
            t = psutil.Process(p).cpu_times()
            total += t.user + t.system
        except psutil.Error:
            pass
    return total


def _open_loop_worker(spec, queries, gt, jobs, t_zero, go, ready, results):
    """Sends each of its planned queries at its planned time (monotonic ns from t_zero) and never
    waits for an earlier reply of another worker. One worker handles one query at a time, so the
    pool size bounds the in-flight queries; a saturated server shows as send lag."""
    try:
        q = make_query_fn(spec)
        q(queries[0])
    except Exception as e:
        ready.put(("err", repr(e)))
        return
    ready.put(("ok", os.getpid()))
    go.wait()
    t_zero = t_zero.value
    planned, started, finished, hits = [], [], [], []
    for at, j in jobs:
        delay = (t_zero + at - now_ns()) / 1e9
        if delay > 0:
            time.sleep(delay)
        t0 = now_ns()
        ids = q(queries[j])
        t1 = now_ns()
        planned.append(t_zero + at)
        started.append(t0)
        finished.append(t1)
        hits.append(recall_hits(ids, gt[j]))
    results.put((np.array(planned, dtype=np.int64), np.array(started, dtype=np.int64),
                 np.array(finished, dtype=np.int64), np.array(hits, dtype=np.int16)))


def open_loop_run(server, proto, ef, rate, duration, workers, queries, gt, k, seed):
    """Open loop: Poisson arrivals at `rate` per second for `duration` seconds, served by a pool
    of `workers` client processes. Latency is measured from the planned send time."""
    ctx = mp.get_context("spawn")
    ready, results = ctx.Queue(), ctx.Queue()
    arrivals = poisson_arrivals(rate, duration, seed)
    qidx = np.random.default_rng([seed, 1]).integers(0, len(queries), size=len(arrivals))
    t_zero, go = ctx.Value("q", 0), ctx.Event()
    spec = server.query_spec(ef, proto, k)
    chunks = [list(zip(arrivals[w::workers].tolist(), qidx[w::workers].tolist())) for w in range(workers)]
    procs = [ctx.Process(target=_open_loop_worker, args=(spec, queries, gt, chunks[w], t_zero, go, ready, results),
                         daemon=True) for w in range(workers)]
    for p in procs:
        p.start()
    pids = []
    for _ in procs:
        status, info = ready.get(timeout=300)
        if status != "ok":
            raise RuntimeError(f"open-loop worker failed: {info}")
        pids.append(info)
    srv_pids = server.pids()
    server.stats_begin(proto)
    cpu0 = server.cpu_seconds()
    t_zero.value = now_ns() + 500_000_000  # workers sleep until this instant
    go.set()
    parts = [results.get(timeout=duration + 600) for _ in procs]
    cpu1 = server.cpu_seconds()
    srv = server.stats_end(proto)
    for p in procs:
        p.join(30)
    planned, started, finished, hits = (np.concatenate([x[i] for x in parts]) for i in range(4))
    row = {"proto": proto, "ef": ef, "workers": workers, "seed": seed,
           **open_loop_summary(planned - t_zero.value, started - t_zero.value, finished - t_zero.value,
                               hits, k, rate, duration),
           "server_cpu_ms_per_query": round((cpu1 - cpu0) * 1000 / max(len(planned), 1), 6),
           "server_cores_busy": round((cpu1 - cpu0) / ((max(finished) - t_zero.value) / 1e9), 3), **srv}
    log(f"  {server.name}/{proto} open-loop {rate}/s: achieved={row['achieved_qps']} mean={row['mean_ms']}ms "
        f"p99={row['p99_ms']}ms lag_max={row['max_send_lag_ms']}ms")
    return row, {f"open_{proto}_ef{ef}_r{rate}_lat": finished - planned,
                 f"open_{proto}_ef{ef}_r{rate}_planned": planned - t_zero.value}
