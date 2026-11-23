"""Server lifecycle, index build, query functions and server-side stats for pgvector and Qdrant.

Two launch modes, picked by BENCH_MODE:
  apptainer  servers run from .sif images (ARF / TRUBA)
  local      servers run from native binaries (dev machine, CI)
A memory limit is applied by starting the server as its own Slurm step (srun --mem), so the
kernel cgroup caps the server's RSS plus its page cache. That only exists in apptainer mode.
"""
import json
import os
import shutil
import signal
import subprocess
import time
import urllib.request

import psutil

from common import dir_size, fmt_cpus, log, sha256
from features import (conn_mode_flags, pg_copy_value, pooler_cmd, pg_create_index_sql, pg_create_table_sql, pg_plan_prepare_sql, pg_query_sql,
                      pg_txn_settings, pg_vector_type, pgbouncer_ini, pooled_dsn, qdrant_quantization,
                      txn_query)

MODE = os.environ.get("BENCH_MODE", "apptainer")
PG_SIF = os.environ.get("PG_SIF")
QDRANT_SIF = os.environ.get("QDRANT_SIF")
PG_BIN = os.environ.get("PG_BIN", "/usr/lib/postgresql/16/bin")
QDRANT_BIN = os.environ.get("QDRANT_BIN", "qdrant")
COLL = "items"
UPLOAD_BATCH = 512
DEFAULT_QDRANT_INDEXING_THRESHOLD_KB = 20000

# pgvector accepts hnsw.ef_search from 1 to 1000. Outside that range the server only logs a
# WARNING and keeps the previous value (40 by default), so a plain SET would silently measure a
# different ef than the one recorded.
PG_EF_SEARCH_MAX = 1000


def port_in_use(port, host="127.0.0.1"):
    """True when binding host:port fails because another socket holds it.

    Binding is what the server itself does, so this agrees with its failure. Connecting to the
    port instead can look free when the owner's accept queue is full. SO_REUSEADDR matches what
    PostgreSQL and Qdrant set, so connections in TIME_WAIT do not count as the port being used."""
    import errno
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, int(port)))
        except OSError as error:
            return error.errno == errno.EADDRINUSE
        return False


def wait_for_free_ports(ports, timeout_s=120.0, poll_s=1.0):
    """Waits until none of the ports has a listener, and returns the seconds waited.

    The cluster nodes run one job after another, and the server of the previous job can still
    hold its port for a moment after that job ends. Two benchmark runs failed that way
    (PostgreSQL on 55432, Qdrant gRPC on 56334) although they only needed a few seconds."""
    start = time.monotonic()
    while True:
        busy = [p for p in ports if port_in_use(p)]
        if not busy:
            return round(time.monotonic() - start, 2) if time.monotonic() - start > poll_s else 0.0
        if time.monotonic() - start > timeout_s:
            raise RuntimeError(f"port(s) {busy} still in use after {timeout_s:.0f}s; "
                               "a server from an earlier job is probably still running on this node")
        time.sleep(poll_s)


def set_ef_search(conn, ef):
    """Sets hnsw.ef_search and confirms the server took the value."""
    ef = int(ef)
    conn.execute(f"SET hnsw.ef_search = {ef}")
    applied = conn.execute("SHOW hnsw.ef_search").fetchone()[0]
    if str(applied) != str(ef):
        raise RuntimeError(
            f"hnsw.ef_search = {ef} was not applied (server reports {applied}); pgvector accepts "
            f"1..{PG_EF_SEARCH_MAX} and otherwise keeps the previous value")

# PostgreSQL write-path counters. Each query is best effort because the views differ
# between major versions, and a counter that is unavailable is left out, never zero.
_PG_ACTIVITY_QUERIES = (
    ("SELECT wal_records, wal_fpi, wal_bytes FROM pg_stat_wal",
     ("wal_records", "wal_fpi", "wal_bytes")),
    ("SELECT num_timed, num_requested, write_time, sync_time, buffers_written FROM pg_stat_checkpointer",
     ("checkpoints_timed", "checkpoints_requested", "checkpoint_write_ms", "checkpoint_sync_ms",
      "checkpoint_buffers")),
    ("SELECT checkpoints_timed, checkpoints_req, checkpoint_write_time, checkpoint_sync_time, "
     "buffers_checkpoint FROM pg_stat_bgwriter",
     ("checkpoints_timed", "checkpoints_requested", "checkpoint_write_ms", "checkpoint_sync_ms",
      "checkpoint_buffers")),
    # PostgreSQL 18 reports write_bytes; 16 and 17 report writes in units of op_bytes.
    ("SELECT COALESCE(sum(write_bytes), 0)::bigint FROM pg_stat_io", ("io_write_bytes",)),
    ("SELECT COALESCE(sum(writes * op_bytes), 0)::bigint FROM pg_stat_io", ("io_write_bytes",)),
)


def pg_activity_snapshot(conn):
    """Cumulative WAL, checkpoint and write counters, for deltas around a build phase."""
    try:
        conn.execute("SELECT pg_stat_force_next_flush()")
    except Exception:  # noqa: BLE001 - PostgreSQL before 15 has no such function
        pass
    out = {}
    for sql, names in _PG_ACTIVITY_QUERIES:
        if names[0] in out:  # the bgwriter fallback is only for versions without the checkpointer view
            continue
        try:
            row = conn.execute(sql).fetchone()
        except Exception:  # noqa: BLE001
            continue
        if row is None:
            continue
        for name, value in zip(names, row):
            out[name] = float(value) if isinstance(value, float) else int(value)
    return out


def pg_activity_delta(before, after):
    return {key: after[key] - before[key] for key in after if key in before}


def explain_summary(plan):
    """Node types, total cost and index use of an EXPLAIN (FORMAT JSON) plan tree."""
    nodes, stack = [], [plan]
    while stack:
        node = stack.pop(0)
        nodes.append(node["Node Type"])
        stack.extend(node.get("Plans", []))
    return {"nodes": "/".join(nodes), "cost": plan["Total Cost"], "uses_index": "Index Scan" in nodes}


def plan_grid_rows(conn, efs, vector_literal, k=10, vector_type="vector", dim=None):
    """Plans for the benchmark query at each ef, without executing it.

    For every ef this records the planner's own choice, the best index plan (sequential scans
    disabled) and the best scan plan (index scans disabled). The ratio of the two costs shows
    how close the planner is to switching. The planner switches are restored afterwards."""
    conn.execute(pg_plan_prepare_sql(vector_type, dim, k))
    conn.execute("SET plan_cache_mode = force_custom_plan")
    rows = []
    try:
        for ef in efs:
            set_ef_search(conn, ef)
            entry = {"ef": int(ef)}
            for label, switches in (("default", ()), ("forced_index", (("enable_seqscan", "off"),)),
                                    ("forced_scan", (("enable_indexscan", "off"), ("enable_bitmapscan", "off")))):
                for name, value in switches:
                    conn.execute(f"SET {name} = {value}")
                try:
                    explained = conn.execute(f"EXPLAIN (FORMAT JSON) EXECUTE bq('{vector_literal}')").fetchone()[0][0]
                    entry[label] = explain_summary(explained["Plan"])
                finally:
                    for name, _ in switches:
                        conn.execute(f"RESET {name}")
            scan_cost = entry["forced_scan"]["cost"]
            entry["index_to_scan_cost_ratio"] = (entry["forced_index"]["cost"] / scan_cost) if scan_cost else None
            rows.append(entry)
    finally:
        conn.execute("RESET hnsw.ef_search")
    return rows


class Server:
    name = "?"

    def __init__(self, work, cores, args):
        self.work = os.path.join(work, self.name)
        self.cores = cores
        self.args = args
        self.proc = None
        self.logf = None
        self.started_at = 0.0
        self.mem_limit = None
        self.log_dir = self.work

    def _launch(self, cmd, env=None, cwd=None, mem_limit=None):
        argv = []
        if mem_limit:
            if MODE != "apptainer" or "SLURM_JOB_ID" not in os.environ:
                raise RuntimeError("memory limits need a Slurm job (srun step cgroup)")
            argv += ["srun", "--overlap", "-N1", "-n1", f"-c{os.environ['SLURM_CPUS_ON_NODE']}",
                     f"--mem={mem_limit}", "--cpu-bind=none", "--quiet"]
        argv += ["taskset", "-c", fmt_cpus(self.cores)] + cmd
        self.logf = open(os.path.join(self.log_dir, f"{self.name}_server_{int(time.time())}.log"), "w")
        log(f"{self.name}: launching {' '.join(argv[:12])} ...")
        self.started_at = time.time()
        self.mem_limit = mem_limit
        self.proc = subprocess.Popen(argv, stdout=self.logf, stderr=subprocess.STDOUT,
                                     env=env, cwd=cwd, start_new_session=True)

    def _wait_ready(self, check, timeout=300):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.proc.poll() is not None:
                raise RuntimeError(f"{self.name} exited early, see {self.logf.name}")
            try:
                if check():
                    log(f"{self.name}: ready after {time.time() - t0:.1f}s")
                    return
            except Exception:
                pass
            time.sleep(0.5)
        raise RuntimeError(f"{self.name} not ready after {timeout}s")

    def _kill_group(self, sig, wait):
        if not self.proc or self.proc.poll() is not None:
            return True
        try:
            os.killpg(self.proc.pid, sig)
        except ProcessLookupError:
            return True
        try:
            self.proc.wait(wait)
            return True
        except subprocess.TimeoutExpired:
            return False

    def cpu_seconds(self):
        total = 0.0
        for p in self.pids():
            try:
                t = psutil.Process(p).cpu_times()
                total += t.user + t.system
            except psutil.Error:
                pass
        return total


class Pg(Server):
    name = "pg"

    def __init__(self, work, cores, args):
        super().__init__(work, cores, args)
        self.data = os.path.join(self.work, "pgdata")
        self.port = int(os.environ.get("PG_PORT", "55432"))
        self.dsn = f"host=127.0.0.1 port={self.port} dbname=postgres user=postgres"
        self.vector_type = getattr(args, "pg_vector_type", "vector")
        self.dim = None  # set by build()
        self.pooler = None
        self.conn_mode = "direct"
        self.pooler_image = None
        self.pooler_port = int(os.environ.get("PGBOUNCER_PORT", "56432"))

    def _cmd(self, binary, *a):
        if MODE == "apptainer":
            return ["apptainer", "exec", "--cleanenv", "--bind", self.work, PG_SIF, binary, *a]
        return [os.path.join(PG_BIN, binary), *a]

    def settings(self):
        a, ncores = self.args, len(self.cores)
        return {
            "listen_addresses": "127.0.0.1",
            "port": self.port,
            "unix_socket_directories": self.work,
            "max_connections": 300,
            "shared_buffers": a.pg_shared_buffers,
            "effective_cache_size": a.pg_effective_cache,
            "maintenance_work_mem": a.pg_maintenance_mem,
            "max_worker_processes": ncores + 8,
            "max_parallel_workers": ncores,
            "max_parallel_maintenance_workers": max(ncores - 1, 0),
            "max_wal_size": "16GB",
            "checkpoint_timeout": "30min",
            "jit": "off",
            "track_io_timing": "on",
            "shared_preload_libraries": "pg_stat_statements",
            "pg_stat_statements.max": 1000,
            "logging_collector": "off",
        }

    def init(self):
        os.makedirs(self.work, exist_ok=True)
        if os.path.exists(self.data):
            shutil.rmtree(self.data)
        subprocess.run(self._cmd("initdb", "-D", self.data, "-U", "postgres", "--auth=trust",
                                 "-E", "UTF8", "--locale=C"),
                       check=True, stdout=subprocess.DEVNULL)

    def start(self, mem_limit=None):
        flags = []
        for k, v in self.settings().items():
            flags += ["-c", f"{k}={v}"]
        waited = wait_for_free_ports([self.port])
        if waited:
            log(f"pg: port {self.port} was busy for {waited:.1f}s")
        self._launch(self._cmd("postgres", "-D", self.data, *flags), mem_limit=mem_limit)
        self._wait_ready(lambda: self.admin().close() is None)

    def stop(self):
        self.stop_pooler()
        if not self.proc or self.proc.poll() is not None:
            return
        subprocess.run(self._cmd("pg_ctl", "stop", "-D", self.data, "-m", "fast", "-w", "-t", "600"),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not self._kill_group(signal.SIGTERM, 60):
            self._kill_group(signal.SIGKILL, 30)
        log("pg: stopped")

    def query_dsn(self):
        """Where benchmark clients connect: PgBouncer when a pooler runs, else the server."""
        return pooled_dsn(self.dsn, self.pooler_port) if conn_mode_flags(self.conn_mode)["use_pooler"] else self.dsn

    def set_conn_mode(self, mode):
        """direct: session SET, straight to PostgreSQL. direct_txn: a transaction per query. pooled: the
        same, through PgBouncer (started on first use)."""
        if conn_mode_flags(mode)["use_pooler"] and not self.pooler:
            self.start_pooler()
        self.conn_mode = mode

    def pooler_pids(self):
        """The pooler runs inside the Apptainer wrapper, so its CPU is that of the wrapper's descendants."""
        if not self.pooler or self.pooler.poll() is not None:
            return []
        try:
            return [self.pooler.pid] + [c.pid for c in psutil.Process(self.pooler.pid).children(recursive=True)]
        except psutil.Error:
            return []

    def pooler_cpu_seconds(self):
        total = 0.0
        for pid in self.pooler_pids():
            try:
                t = psutil.Process(pid).cpu_times()
                total += t.user + t.system
            except psutil.Error:
                pass
        return total

    def start_pooler(self):
        """PgBouncer (transaction pooling) in front of the server, pinned to the server cores so
        its CPU counts as server cost. Binary from PGBOUNCER_BIN, or PGBOUNCER_SIF with apptainer."""
        a = self.args
        os.makedirs(self.work, exist_ok=True)
        auth = os.path.join(self.work, "pgbouncer_users.txt")
        with open(auth, "w") as f:
            f.write('"postgres" ""\n')
        ini = os.path.join(self.work, "pgbouncer.ini")
        with open(ini, "w") as f:
            f.write(pgbouncer_ini(self.pooler_port, self.port, a.pg_pooler_pool_size,
                                  a.pg_pooler_max_client_conn, auth, self.work))
        sif = os.environ.get("PGBOUNCER_SIF")
        cmd = pooler_cmd(sif, os.environ.get("PGBOUNCER_BIN"), ini, self.work)
        self.pooler_image = sif
        waited = wait_for_free_ports([self.pooler_port])
        if waited:
            log(f"pgbouncer: port {self.pooler_port} was busy for {waited:.1f}s")
        self.logf_pooler = open(os.path.join(self.log_dir, f"pgbouncer_{int(time.time())}.log"), "w")
        self.pooler = subprocess.Popen(["taskset", "-c", fmt_cpus(self.cores)] + cmd,
                                       stdout=self.logf_pooler, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        t0 = time.time()
        while time.time() - t0 < 60:
            if self.pooler.poll() is not None:
                self.pooler = None
                raise RuntimeError("pgbouncer exited early, see the pgbouncer log")
            if port_in_use(self.pooler_port):
                log(f"pgbouncer: ready after {time.time() - t0:.1f}s")
                return
            time.sleep(0.2)
        raise RuntimeError("pgbouncer not ready after 60s")

    def pooler_info(self):
        """Which pooler ran: image, its checksum and the version it reports."""
        out = {"image": self.pooler_image, "image_sha256": sha256(self.pooler_image) if self.pooler_image else None,
               "pool_mode": "transaction", "pool_size": self.args.pg_pooler_pool_size,
               "max_client_conn": self.args.pg_pooler_max_client_conn, "pinned_cores": list(self.cores)}
        try:
            cmd = pooler_cmd(self.pooler_image, os.environ.get("PGBOUNCER_BIN"), "--version", self.work)[:-1] + ["--version"]
            out["version"] = subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.splitlines()[0]
        except (OSError, IndexError, subprocess.SubprocessError):
            out["version"] = None
        return out

    def stop_pooler(self):
        if self.pooler and self.pooler.poll() is None:
            try:
                os.killpg(self.pooler.pid, signal.SIGTERM)
                self.pooler.wait(30)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                os.killpg(self.pooler.pid, signal.SIGKILL)
        self.pooler = None

    def admin(self):
        import psycopg
        from pgvector.psycopg import register_vector
        conn = psycopg.connect(self.dsn, autocommit=True, connect_timeout=5)
        try:
            register_vector(conn)
        except Exception:
            pass  # extension not created yet
        return conn

    def pids(self):
        try:
            with open(os.path.join(self.data, "postmaster.pid")) as f:
                pm = int(f.readline())
            p = psutil.Process(pm)
            return [pm] + [c.pid for c in p.children(recursive=True)] + self.pooler_pids()
        except (OSError, ValueError, psutil.Error):
            return []

    def build(self, base, m, efc):
        dim, n = base.shape[1], len(base)
        self.dim = dim
        notices = []
        with self.admin() as conn:
            conn.add_notice_handler(lambda d: notices.append(d.message_primary))
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
            conn.execute("DROP TABLE IF EXISTS items")
            unlogged = bool(getattr(self.args, "pg_unlogged", False))
            conn.execute(pg_create_table_sql(self.vector_type, dim, unlogged))
        # fresh connection so register_vector sees the new type
        with self.admin() as conn:
            conn.add_notice_handler(lambda d: notices.append(d.message_primary))
            log(f"pg: COPY {n} x {dim}")
            activity = {"start": pg_activity_snapshot(conn)}
            t0 = time.perf_counter()
            with conn.cursor() as cur:
                with cur.copy("COPY items (id, embedding) FROM STDIN WITH (FORMAT BINARY)") as cp:
                    cp.set_types(["int8", pg_vector_type(self.vector_type, dim)["copy_type"]])
                    for i in range(n):
                        cp.write_row((i, pg_copy_value(self.vector_type, base[i])))
            load_s = time.perf_counter() - t0
            activity["after_copy"] = pg_activity_snapshot(conn)
            # PostgreSQL sizes parallel index-build workers from the heap, and with TOASTed
            # vectors the heap is tiny (~1.5% of the data), so it would plan few or no workers.
            workers = max(len(self.cores) - 1, 0)
            conn.execute(f"ALTER TABLE items SET (parallel_workers = {workers})")
            log(f"pg: load {load_s:.1f}s, building HNSW m={m} ef_construction={efc} ({workers} workers)")
            t0 = time.perf_counter()
            conn.execute(pg_create_index_sql(self.vector_type, m, efc))
            index_s = time.perf_counter() - t0
            activity["after_index"] = pg_activity_snapshot(conn)
            log(f"pg: index {index_s:.1f}s")
            t0 = time.perf_counter()
            conn.execute("VACUUM (ANALYZE) items")
            conn.execute("CHECKPOINT")
            vacuum_s = time.perf_counter() - t0
            activity["after_checkpoint"] = pg_activity_snapshot(conn)
            sizes = conn.execute(
                "SELECT pg_relation_size('items'), pg_total_relation_size('items'), "
                "pg_relation_size('items_hnsw'), "
                "pg_relation_size((SELECT reltoastrelid FROM pg_class WHERE relname = 'items'))").fetchone()
            storage = conn.execute("SELECT attstorage FROM pg_attribute WHERE attrelid='items'::regclass "
                                   "AND attname='embedding'").fetchone()[0]
        return {
            "load_s": round(load_s, 2), "index_s": round(index_s, 2),
            "total_s": round(load_s + index_s, 2), "vacuum_checkpoint_s": round(vacuum_s, 2),
            "heap_bytes": sizes[0], "table_total_bytes": sizes[1], "index_bytes": sizes[2],
            "toast_bytes": sizes[3], "parallel_workers": workers,
            "embedding_attstorage": storage, "notices": notices,
            "table_unlogged": unlogged, "vector_type": self.vector_type,
            "write_activity": {
                "copy": pg_activity_delta(activity["start"], activity["after_copy"]),
                "index": pg_activity_delta(activity["after_copy"], activity["after_index"]),
                "vacuum_checkpoint": pg_activity_delta(activity["after_index"], activity["after_checkpoint"]),
            },
            "method": ("single-stream binary COPY into an UNLOGGED table, then CREATE INDEX (parallel maintenance workers)"
                       if unlogged else
                       "single-stream binary COPY, then CREATE INDEX (parallel maintenance workers)"),
        }

    def info(self):
        with self.admin() as conn:
            ver = conn.execute("SELECT version()").fetchone()[0]
            ext = conn.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()
            # The hnsw.* settings exist only once the extension library is loaded in the session.
            conn.execute("SELECT '[1,2]'::vector")
            rows = conn.execute("SELECT name, setting, unit FROM pg_settings WHERE name = ANY(%s)",
                                (list(self.settings().keys()) + ["huge_pages", "work_mem",
                                                                 "random_page_cost", "wal_level",
                                                                 "hnsw.ef_search", "hnsw.iterative_scan",
                                                                 "hnsw.max_scan_tuples",
                                                                 "hnsw.scan_mem_multiplier"],)).fetchall()
        return {"version": ver, "pgvector": ext[0] if ext else None, "vector_type": self.vector_type,
                "pooler": ({"kind": "pgbouncer", "pool_mode": "transaction",
                            "pool_size": self.args.pg_pooler_pool_size,
                            "max_client_conn": self.args.pg_pooler_max_client_conn}
                           if self.pooler else None), "conn_modes": getattr(self.args, "pg_conn_modes", ["direct"]),
                "settings": {r[0]: f"{r[1]}{r[2] or ''}" for r in rows}, "image": PG_SIF}

    def query_spec(self, ef, proto="pg", k=10):
        return {"engine": "pg", "dsn": self.query_dsn(), "ef": ef, "k": k, "proto": "pg",
                "force_index": self.args.pg_planner == "force-index",
                "vector_type": self.vector_type, "dim": self.dim,
                "per_query_txn": conn_mode_flags(self.conn_mode)["per_query_txn"]}

    def plan(self, ef, vec, k=10):
        """Plan nodes for the benchmark query at this ef, as a custom and as a generic plan
        (psycopg switches to a server-side prepared statement after 5 executions)."""
        lit = "[" + ",".join(f"{x:.7g}" for x in vec.tolist()) + "]"
        out = {}
        with self.admin() as conn:
            set_ef_search(conn, ef)
            if self.args.pg_planner == "force-index":
                conn.execute("SET enable_seqscan = off")
            conn.execute(pg_plan_prepare_sql(self.vector_type, self.dim, k))
            for mode in ("custom", "generic"):
                conn.execute(f"SET plan_cache_mode = force_{mode}_plan")
                p = conn.execute(f"EXPLAIN (FORMAT JSON) EXECUTE bq('{lit}')").fetchone()[0][0]["Plan"]
                nodes, stack = [], [p]
                while stack:
                    node = stack.pop(0)
                    nodes.append(node["Node Type"])
                    stack.extend(node.get("Plans", []))
                out[mode] = {"nodes": "/".join(nodes), "cost": p["Total Cost"],
                             "uses_index": "Index Scan" in nodes}
        return out

    def plan_grid(self, efs, vec, k=10):
        """Plan-only measurement for the planner exposure study: table, TOAST and index sizes
        in pages plus the plan grid. Nothing in it runs a query."""
        lit = "[" + ",".join(f"{x:.7g}" for x in vec.tolist()) + "]"
        with self.admin() as conn:
            conn.execute("ANALYZE items")
            sizes = conn.execute(
                "SELECT c.relpages, c.reltuples, COALESCE(t.relpages, 0), i.relpages "
                "FROM pg_class c LEFT JOIN pg_class t ON t.oid = c.reltoastrelid, pg_class i "
                "WHERE c.relname = 'items' AND i.relname = 'items_hnsw'").fetchone()
            settings = dict(conn.execute(
                "SELECT name, setting FROM pg_settings WHERE name IN ('random_page_cost', 'seq_page_cost', "
                "'cpu_tuple_cost', 'effective_cache_size', 'max_parallel_workers_per_gather', "
                "'parallel_setup_cost', 'parallel_tuple_cost', 'min_parallel_table_scan_size')").fetchall())
            rows = plan_grid_rows(conn, efs, lit, k, self.vector_type, self.dim)
        return {"table_pages": {"heap": sizes[0], "heap_tuples": sizes[1], "toast": sizes[2], "index": sizes[3]},
                "planner_settings": settings, "grid": rows}

    def stats_begin(self, proto):
        with self.admin() as conn:
            conn.execute("SELECT pg_stat_statements_reset()")

    def stats_end(self, proto):
        with self.admin() as conn:
            cur = conn.execute("SELECT * FROM pg_stat_statements WHERE query LIKE %s",
                               ("%ORDER BY embedding%",))
            cols = [c.name for c in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        if not rows:
            return {}
        keep = ("calls", "total_exec_time", "mean_exec_time", "stddev_exec_time", "shared_blks_hit",
                "shared_blks_read", "blk_read_time", "shared_blk_read_time", "temp_blks_read")
        agg = {k: sum(float(r[k] or 0) for r in rows) for k in keep if k in rows[0]}
        calls = agg.get("calls", 0) or 1
        hits, reads = agg.get("shared_blks_hit", 0), agg.get("shared_blks_read", 0)
        return {
            "server_calls": int(agg.get("calls", 0)),
            "server_mean_ms": round(agg.get("total_exec_time", 0) / calls, 4),
            "buffer_hit_ratio": round(hits / (hits + reads), 5) if hits + reads else None,
            "blks_hit_per_query": round(hits / calls, 1),
            "blks_read_per_query": round(reads / calls, 2),
            "read_time_ms_per_query": round((agg.get("blk_read_time", 0) +
                                             agg.get("shared_blk_read_time", 0)) / calls, 4),
        }


def qdrant_segment_summary(collections_telemetry):
    """Summarize level-10 telemetry without equating empty appendable segments to graphs."""
    segments = []
    for collection in (collections_telemetry or {}).get("collections", []):
        for shard in collection.get("shards", []):
            local = shard.get("local") or {}
            for segment in local.get("segments", []):
                info = segment.get("info", {})
                segments.append({
                    "segment_type": info.get("segment_type"),
                    "num_vectors": info.get("num_vectors", 0),
                    "num_indexed_vectors": info.get("num_indexed_vectors", 0),
                    "is_appendable": info.get("is_appendable"),
                })
    return {
        "public_segment_count": len(segments),
        "nonempty_segment_count": sum(item["num_vectors"] > 0 for item in segments),
        "indexed_nonempty_segment_count": sum(
            item["num_vectors"] > 0 and item["segment_type"] == "indexed" for item in segments
        ),
        "empty_appendable_segment_count": sum(
            item["num_vectors"] == 0 and item["is_appendable"] is True for item in segments
        ),
        "segments": segments,
    }


def qdrant_quantization_config(desc):
    """Collection-level scalar quantization from the recorded description, or None."""
    if not desc:
        return None
    from qdrant_client import models as qm
    return qm.ScalarQuantization(scalar=qm.ScalarQuantizationConfig(
        type=qm.ScalarType.INT8, quantile=desc["quantile"], always_ram=desc["always_ram"]))


def qdrant_search_quantization(desc):
    """Search-time quantization parameters (rescore, oversampling), or None."""
    if not desc:
        return None
    from qdrant_client import models as qm
    return qm.QuantizationSearchParams(rescore=desc["rescore"], oversampling=desc["oversampling"])


class Qdrant(Server):
    name = "qdrant"

    def __init__(self, work, cores, args):
        super().__init__(work, cores, args)
        self.http = int(os.environ.get("QDRANT_HTTP_PORT", "56333"))
        self.grpc = int(os.environ.get("QDRANT_GRPC_PORT", "56334"))
        self.storage = os.path.join(self.work, "storage")
        self.quantization = qdrant_quantization(
            getattr(args, "qdrant_quantization", "none"),
            always_ram=not getattr(args, "qdrant_quant_on_disk", False),
            rescore=not getattr(args, "qdrant_no_rescore", False),
            oversampling=getattr(args, "qdrant_oversampling", None))

    def init(self):
        if os.path.exists(self.work):
            shutil.rmtree(self.work)
        os.makedirs(os.path.join(self.work, "snapshots"))

    def _env(self):
        env = {
            "QDRANT__STORAGE__STORAGE_PATH": self.storage,
            "QDRANT__STORAGE__SNAPSHOTS_PATH": os.path.join(self.work, "snapshots"),
            "QDRANT__SERVICE__HOST": "127.0.0.1",
            "QDRANT__SERVICE__HTTP_PORT": str(self.http),
            "QDRANT__SERVICE__GRPC_PORT": str(self.grpc),
            "QDRANT__TELEMETRY_DISABLED": "true",
            "QDRANT__LOG_LEVEL": "INFO",
        }
        if self.args.qdrant_search_threads:
            env["QDRANT__STORAGE__PERFORMANCE__MAX_SEARCH_THREADS"] = str(
                self.args.qdrant_search_threads
            )
        return env

    def start(self, mem_limit=None):
        waited = wait_for_free_ports([self.http, self.grpc])
        if waited:
            log(f"qdrant: ports {self.http}/{self.grpc} were busy for {waited:.1f}s")
        if MODE == "apptainer":
            envs = []
            for k, v in self._env().items():
                envs += ["--env", f"{k}={v}"]
            # --pwd because the image's entrypoint and config paths are relative to /qdrant,
            # --writable-tmpfs because qdrant drops a marker file into its working directory
            cmd = ["apptainer", "exec", "--cleanenv", "--writable-tmpfs", "--pwd", "/qdrant",
                   "--bind", self.work, *envs, QDRANT_SIF, "/qdrant/qdrant"]
            self._launch(cmd, mem_limit=mem_limit)
        else:
            self._launch([QDRANT_BIN], env={**os.environ, **self._env()}, cwd=self.work,
                         mem_limit=mem_limit)
        self._wait_ready(lambda: urllib.request.urlopen(
            f"http://127.0.0.1:{self.http}/readyz", timeout=2).status == 200)

    def stop(self):
        if not self._kill_group(signal.SIGTERM, 120):
            self._kill_group(signal.SIGKILL, 30)
        log("qdrant: stopped")

    def client(self, proto="grpc"):
        from qdrant_client import QdrantClient
        return QdrantClient(host="127.0.0.1", port=self.http, grpc_port=self.grpc,
                            prefer_grpc=(proto != "rest"), timeout=600, check_compatibility=False)

    def pids(self):
        out = []
        for p in psutil.process_iter(["name", "username", "create_time"]):
            if p.info["name"] == "qdrant" and p.info["username"] == psutil.Process().username() \
                    and p.info["create_time"] >= self.started_at - 2:
                out.append(p.pid)
        return out

    def _get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.http}{path}", timeout=30) as r:
            return json.load(r)

    def collection_state(self, c=None):
        info = (c or self.client("rest")).get_collection(COLL)
        return {"status": str(info.status.value if hasattr(info.status, "value") else info.status),
                "points": info.points_count, "indexed": info.indexed_vectors_count,
                "segments": info.segments_count}

    def build(self, base, m, efc):
        from qdrant_client import models as qm
        a = self.args
        n, dim = base.shape
        c = self.client("grpc")
        if c.collection_exists(COLL):
            c.delete_collection(COLL)
        batch = getattr(a, "qdrant_upload_batch", UPLOAD_BATCH)
        parallel = getattr(a, "qdrant_upload_parallel", 1)
        defer = bool(getattr(a, "qdrant_defer_indexing", False))
        index_threads = getattr(a, "qdrant_max_indexing_threads", 0)
        # The threshold that applies once indexing is allowed. With deferral the collection is
        # created with indexing switched off (threshold 0) and gets this value after the upload.
        final_threshold = (a.qdrant_indexing_threshold_kb if a.qdrant_indexing_threshold_kb is not None
                           else DEFAULT_QDRANT_INDEXING_THRESHOLD_KB)
        optimizer_values = {}
        if defer:
            optimizer_values["indexing_threshold"] = 0
        elif a.qdrant_indexing_threshold_kb is not None:
            optimizer_values["indexing_threshold"] = a.qdrant_indexing_threshold_kb
        if a.qdrant_segments:
            optimizer_values["default_segment_number"] = a.qdrant_segments
        opt = qm.OptimizersConfigDiff(**optimizer_values) if optimizer_values else None
        hnsw_values = {"m": m, "ef_construct": efc, "on_disk": a.qdrant_on_disk}
        if index_threads:
            hnsw_values["max_indexing_threads"] = index_threads
        c.create_collection(
            COLL,
            vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE, on_disk=a.qdrant_on_disk),
            hnsw_config=qm.HnswConfigDiff(**hnsw_values),
            optimizers_config=opt,
            quantization_config=qdrant_quantization_config(self.quantization),
        )
        log(f"qdrant: upload {n} x {dim} over gRPC, batch {batch}, {parallel} stream(s)"
            f"{', indexing deferred' if defer else ''}")
        t0 = time.perf_counter()
        c.upload_collection(COLL, vectors=base, ids=range(n), batch_size=batch,
                            parallel=parallel, wait=True, max_retries=5)
        upload_s = time.perf_counter() - t0
        if defer:
            c.update_collection(COLL, optimizers_config=qm.OptimizersConfigDiff(indexing_threshold=final_threshold))
        log(f"qdrant: upload {upload_s:.1f}s, waiting for optimizer to finish indexing")

        # Upsert returns before the HNSW graph exists. Index build time is the time until the
        # collection is green and stays green; the old harness never waited for this.
        t1 = time.perf_counter()
        greens, trace, last, unresolved_since = 0, [], None, None
        while greens < 3:
            st = self.collection_state(c)
            if st != last:
                trace.append({"t_s": round(time.perf_counter() - t1, 1), **st})
                last = st
            if st["status"] == "grey":
                c.update_collection(COLL, optimizers_config=qm.OptimizersConfigDiff())
            # default_segment_number is an optimizer target, not an exact public
            # segment-count contract. Qdrant may retain an additional appendable segment.
            # We record the actual count/telemetry but gate only on complete indexing.
            controls_met = not (a.qdrant_require_indexed or defer) or st["indexed"] >= st["points"]
            greens = greens + 1 if st["status"] == "green" and controls_met else 0
            if st["status"] == "green" and not controls_met:
                unresolved_since = unresolved_since or time.perf_counter()
                if time.perf_counter() - unresolved_since > a.qdrant_control_grace_s:
                    raise RuntimeError(
                        "qdrant stayed green without satisfying requested controls: "
                        f"segments={st['segments']} indexed={st['indexed']}/{st['points']}"
                    )
            else:
                unresolved_since = None
            if time.perf_counter() - t1 > 6 * 3600:
                raise RuntimeError("qdrant indexing did not finish in 6h")
            time.sleep(0.5)
        index_s = time.perf_counter() - t1 - 1.0  # the two extra confirmation polls
        final = self.collection_state(c)
        log(f"qdrant: indexing wait {index_s:.1f}s, state {final}")
        segment_target_met = not a.qdrant_segments or final["segments"] == a.qdrant_segments
        fully_indexed = final["indexed"] >= final["points"]
        if (a.qdrant_require_indexed or defer) and not fully_indexed:
            raise RuntimeError(
                f"qdrant collection is not fully indexed: {final['indexed']}/{final['points']}"
            )
        return {
            "upload_s": round(upload_s, 2), "index_wait_s": round(max(index_s, 0), 2),
            "total_s": round(upload_s + max(index_s, 0), 2), "final_state": final,
            "fully_indexed": fully_indexed, "state_trace": trace,
            "requested_segments": a.qdrant_segments or "auto",
            "actual_segments": final["segments"],
            "segment_target_met": segment_target_met,
            "requested_search_threads": a.qdrant_search_threads or "auto",
            "storage_bytes": dir_size(self.storage),
            "upload_parallel": parallel, "upload_batch": batch,
            "indexing_deferred": defer, "max_indexing_threads": index_threads or "auto",
            "quantization": self.quantization,
            "method": (f"gRPC upload_collection, batch {batch}, {parallel} stream(s)"
                       f"{', indexing deferred until the upload ends' if defer else ''}, then wait for green"),
        }

    def info(self):
        c = self.client("rest")
        cfg = c.get_collection(COLL).config
        tel = self._get("/telemetry?details_level=1").get("result", {})
        detailed = self._get("/telemetry?details_level=10&per_collection=true").get("result", {})
        collections = detailed.get("collections")
        return {"version": self._get("/").get("version"), "collection_config": cfg.model_dump(),
                "app": tel.get("app"), "image": QDRANT_SIF,
                "collection_segment_telemetry": collections,
                "segment_summary": qdrant_segment_summary(collections),
                "runtime_controls": {
                    "requested_search_threads": self.args.qdrant_search_threads or "auto",
                    "search_threads_environment": self._env().get(
                        "QDRANT__STORAGE__PERFORMANCE__MAX_SEARCH_THREADS", "auto"
                    ),
                    "requested_segments": self.args.qdrant_segments or "auto",
                }}

    def query_spec(self, ef, proto="grpc", k=10):
        return {"engine": "qdrant", "http": self.http, "grpc": self.grpc, "ef": ef, "k": k,
                "proto": proto, "quantization": self.quantization}

    def _query_counters(self, proto):
        side = "rest" if proto == "rest" else "grpc"
        req = self._get("/telemetry?details_level=3")["result"]["requests"][side]["responses"]
        count, total = 0, 0.0
        for endpoint, by_status in req.items():
            if "query" in endpoint.lower() and "points" in endpoint.lower() and "batch" not in endpoint.lower():
                for s in by_status.values():
                    count += s.get("count", 0)
                    total += s.get("total_duration_micros", s.get("avg_duration_micros", 0) * s.get("count", 0))
        return count, total

    def stats_begin(self, proto):
        self._stats0 = self._query_counters(proto)

    def stats_end(self, proto):
        c1, t1 = self._query_counters(proto)
        c0, t0 = self._stats0
        calls = c1 - c0
        return {"server_calls": calls,
                "server_mean_ms": round((t1 - t0) / calls / 1000, 4) if calls else None}


def make_server(engine, work, cores, args):
    return {"pg": Pg, "qdrant": Qdrant}[engine](work, cores, args)


def make_query_fn(spec):
    """Builds a query function in the calling process. Each worker owns one persistent
    connection; nothing about connection setup is ever inside the timed region."""
    k, ef = spec["k"], spec["ef"]
    if spec["engine"] == "pg":
        import psycopg
        from pgvector.psycopg import register_vector
        conn = psycopg.connect(spec["dsn"], autocommit=True)
        register_vector(conn)
        sql = pg_query_sql(spec.get("vector_type", "vector"), spec.get("dim"), k)
        if spec.get("per_query_txn"):
            # Every query carries its own settings (SET LOCAL), which also works through a transaction
            # pooler. The value is checked once, inside a transaction, before anything is timed.
            settings = pg_txn_settings(ef, spec.get("force_index"))
            with conn.transaction():
                for statement in settings:
                    conn.execute(statement)
                seen = conn.execute("SHOW hnsw.ef_search").fetchone()[0]
            if int(seen) != int(ef):
                raise RuntimeError(f"hnsw.ef_search is {seen} inside the transaction, expected {ef}")

            def q_txn(vec):
                return txn_query(conn, settings, sql, vec)
            return q_txn
        set_ef_search(conn, ef)
        if spec.get("force_index"):
            # pgvector's README suggests this when the planner skips the index; see Pg.plan()
            conn.execute("SET enable_seqscan = off")

        def q(vec):
            return [r[0] for r in conn.execute(sql, (vec,), binary=True, prepare=True).fetchall()]
        return q

    from qdrant_client import QdrantClient, models as qm
    c = QdrantClient(host="127.0.0.1", port=spec["http"], grpc_port=spec["grpc"],
                     prefer_grpc=(spec["proto"] != "rest"), timeout=600, check_compatibility=False)

    if spec["proto"] == "grpc_raw":
        # Talks to the generated protobuf stub directly and skips qdrant-client's model
        # conversion layer. This is the lower bound of client overhead, comparable to psycopg.
        from qdrant_client import grpc as qg
        stub = c.grpc_points
        no_payload = qg.WithPayloadSelector(enable=False)
        sq = spec.get("quantization")
        sp = qg.SearchParams(hnsw_ef=int(ef))
        if sq:
            qp = qg.QuantizationSearchParams(rescore=sq["rescore"])
            if sq["oversampling"] is not None:
                qp.oversampling = sq["oversampling"]
            sp = qg.SearchParams(hnsw_ef=int(ef), quantization=qp)

        def q(vec, _client=c):  # holding the client keeps its channel open
            req = qg.QueryPoints(collection_name=COLL, limit=k, params=sp, with_payload=no_payload,
                                 query=qg.Query(nearest=qg.VectorInput(dense=qg.DenseVector(data=vec.tolist()))))
            return [p.id.num for p in stub.Query(req, timeout=600).result]
        return q

    params = qm.SearchParams(hnsw_ef=int(ef), exact=False,
                             quantization=qdrant_search_quantization(spec.get("quantization")))

    def q(vec):
        return [p.id for p in c.query_points(COLL, query=vec, limit=k, search_params=params,
                                             with_payload=False).points]
    return q
