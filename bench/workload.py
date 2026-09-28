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


def recall_hits(ids, gt_row):
    return len(set(ids) & set(gt_row.tolist()))


def latency_sweep(server, protocols, efs, reps, queries, warm, gt, k):
    """Sequential queries, one persistent connection per (protocol, ef). Each (protocol, ef)
    gets its own untimed warm-up pass over a separate query set before the measured reps."""
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
                hits = 0
                server.stats_begin(proto)
                for i, v in enumerate(queries):
                    t0 = now_ns()
                    ids = q(v)
                    lat[i] = now_ns() - t0
                    hits += recall_hits(ids, gt[i])
                srv = server.stats_end(proto)
                row = {"proto": proto, "ef": ef, "rep": rep, "recall_at_k": round(hits / (k * len(queries)), 5),
                       **summarize(lat), **srv}
                if plan:
                    row["plan"] = plan
                out.append(row)
                raw[f"lat_{proto}_ef{ef}_rep{rep}"] = lat
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
PERF_EVENTS = "task-clock,page-faults,cycles:u,instructions:u,cache-misses:u"


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
        "server_cores_allotted": len(server.cores),
        "client_cores_busy": round((cpu1_cli - cpu0_cli) / wall, 3),
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
