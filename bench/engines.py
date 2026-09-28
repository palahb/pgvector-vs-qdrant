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

from common import dir_size, fmt_cpus, log

MODE = os.environ.get("BENCH_MODE", "apptainer")
PG_SIF = os.environ.get("PG_SIF")
QDRANT_SIF = os.environ.get("QDRANT_SIF")
PG_BIN = os.environ.get("PG_BIN", "/usr/lib/postgresql/16/bin")
QDRANT_BIN = os.environ.get("QDRANT_BIN", "qdrant")
COLL = "items"
UPLOAD_BATCH = 512


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
        self._launch(self._cmd("postgres", "-D", self.data, *flags), mem_limit=mem_limit)
        self._wait_ready(lambda: self.admin().close() is None)

    def stop(self):
        if not self.proc or self.proc.poll() is not None:
            return
        subprocess.run(self._cmd("pg_ctl", "stop", "-D", self.data, "-m", "fast", "-w", "-t", "600"),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not self._kill_group(signal.SIGTERM, 60):
            self._kill_group(signal.SIGKILL, 30)
        log("pg: stopped")

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
            return [pm] + [c.pid for c in p.children(recursive=True)]
        except (OSError, ValueError, psutil.Error):
            return []

    def build(self, base, m, efc):
        dim, n = base.shape[1], len(base)
        notices = []
        with self.admin() as conn:
            conn.add_notice_handler(lambda d: notices.append(d.message_primary))
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
            conn.execute("DROP TABLE IF EXISTS items")
            conn.execute(f"CREATE TABLE items (id bigint PRIMARY KEY, embedding vector({dim}))")
        # fresh connection so register_vector sees the new type
        with self.admin() as conn:
            conn.add_notice_handler(lambda d: notices.append(d.message_primary))
            log(f"pg: COPY {n} x {dim}")
            t0 = time.perf_counter()
            with conn.cursor() as cur:
                with cur.copy("COPY items (id, embedding) FROM STDIN WITH (FORMAT BINARY)") as cp:
                    cp.set_types(["int8", "vector"])
                    for i in range(n):
                        cp.write_row((i, base[i]))
            load_s = time.perf_counter() - t0
            # PostgreSQL sizes parallel index-build workers from the heap, and with TOASTed
            # vectors the heap is tiny (~1.5% of the data), so it would plan few or no workers.
            workers = max(len(self.cores) - 1, 0)
            conn.execute(f"ALTER TABLE items SET (parallel_workers = {workers})")
            log(f"pg: load {load_s:.1f}s, building HNSW m={m} ef_construction={efc} ({workers} workers)")
            t0 = time.perf_counter()
            conn.execute(f"CREATE INDEX items_hnsw ON items USING hnsw (embedding vector_cosine_ops) "
                         f"WITH (m = {m}, ef_construction = {efc})")
            index_s = time.perf_counter() - t0
            log(f"pg: index {index_s:.1f}s")
            t0 = time.perf_counter()
            conn.execute("VACUUM (ANALYZE) items")
            conn.execute("CHECKPOINT")
            vacuum_s = time.perf_counter() - t0
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
            "method": "single-stream binary COPY, then CREATE INDEX (parallel maintenance workers)",
        }

    def info(self):
        with self.admin() as conn:
            ver = conn.execute("SELECT version()").fetchone()[0]
            ext = conn.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()
            rows = conn.execute("SELECT name, setting, unit FROM pg_settings WHERE name = ANY(%s)",
                                (list(self.settings().keys()) + ["huge_pages", "work_mem",
                                                                 "random_page_cost", "wal_level"],)).fetchall()
        return {"version": ver, "pgvector": ext[0] if ext else None,
                "settings": {r[0]: f"{r[1]}{r[2] or ''}" for r in rows}, "image": PG_SIF}

    def query_spec(self, ef, proto="pg", k=10):
        return {"engine": "pg", "dsn": self.dsn, "ef": ef, "k": k, "proto": "pg",
                "force_index": self.args.pg_planner == "force-index"}

    def plan(self, ef, vec, k=10):
        """Plan nodes for the benchmark query at this ef, as a custom and as a generic plan
        (psycopg switches to a server-side prepared statement after 5 executions)."""
        lit = "[" + ",".join(f"{x:.7g}" for x in vec.tolist()) + "]"
        out = {}
        with self.admin() as conn:
            conn.execute(f"SET hnsw.ef_search = {int(ef)}")
            if self.args.pg_planner == "force-index":
                conn.execute("SET enable_seqscan = off")
            conn.execute(f"PREPARE bq(vector) AS SELECT id FROM items ORDER BY embedding <=> $1 LIMIT {int(k)}")
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


class Qdrant(Server):
    name = "qdrant"

    def __init__(self, work, cores, args):
        super().__init__(work, cores, args)
        self.http = int(os.environ.get("QDRANT_HTTP_PORT", "56333"))
        self.grpc = int(os.environ.get("QDRANT_GRPC_PORT", "56334"))
        self.storage = os.path.join(self.work, "storage")

    def init(self):
        if os.path.exists(self.work):
            shutil.rmtree(self.work)
        os.makedirs(os.path.join(self.work, "snapshots"))

    def _env(self):
        return {
            "QDRANT__STORAGE__STORAGE_PATH": self.storage,
            "QDRANT__STORAGE__SNAPSHOTS_PATH": os.path.join(self.work, "snapshots"),
            "QDRANT__SERVICE__HOST": "127.0.0.1",
            "QDRANT__SERVICE__HTTP_PORT": str(self.http),
            "QDRANT__SERVICE__GRPC_PORT": str(self.grpc),
            "QDRANT__TELEMETRY_DISABLED": "true",
            "QDRANT__LOG_LEVEL": "INFO",
        }

    def start(self, mem_limit=None):
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
        opt = None
        if a.qdrant_indexing_threshold_kb is not None:
            opt = qm.OptimizersConfigDiff(indexing_threshold=a.qdrant_indexing_threshold_kb)
        c.create_collection(
            COLL,
            vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE, on_disk=a.qdrant_on_disk),
            hnsw_config=qm.HnswConfigDiff(m=m, ef_construct=efc, on_disk=a.qdrant_on_disk),
            optimizers_config=opt,
        )
        log(f"qdrant: upload {n} x {dim} over gRPC, batch {UPLOAD_BATCH}")
        t0 = time.perf_counter()
        c.upload_collection(COLL, vectors=base, ids=range(n), batch_size=UPLOAD_BATCH,
                            parallel=1, wait=True, max_retries=5)
        upload_s = time.perf_counter() - t0
        log(f"qdrant: upload {upload_s:.1f}s, waiting for optimizer to finish indexing")

        # Upsert returns before the HNSW graph exists. Index build time is the time until the
        # collection is green and stays green; the old harness never waited for this.
        t1 = time.perf_counter()
        greens, trace, last = 0, [], None
        while greens < 3:
            st = self.collection_state(c)
            if st != last:
                trace.append({"t_s": round(time.perf_counter() - t1, 1), **st})
                last = st
            if st["status"] == "grey":
                c.update_collection(COLL, optimizers_config=qm.OptimizersConfigDiff())
            greens = greens + 1 if st["status"] == "green" else 0
            if time.perf_counter() - t1 > 6 * 3600:
                raise RuntimeError("qdrant indexing did not finish in 6h")
            time.sleep(0.5)
        index_s = time.perf_counter() - t1 - 1.0  # the two extra confirmation polls
        final = self.collection_state(c)
        log(f"qdrant: indexing wait {index_s:.1f}s, state {final}")
        return {
            "upload_s": round(upload_s, 2), "index_wait_s": round(max(index_s, 0), 2),
            "total_s": round(upload_s + max(index_s, 0), 2), "final_state": final,
            "fully_indexed": final["indexed"] >= final["points"], "state_trace": trace,
            "storage_bytes": dir_size(self.storage),
            "method": f"single-stream gRPC upload_collection, batch {UPLOAD_BATCH}, then wait for green",
        }

    def info(self):
        c = self.client("rest")
        cfg = c.get_collection(COLL).config
        tel = self._get("/telemetry?details_level=1").get("result", {})
        return {"version": self._get("/").get("version"), "collection_config": cfg.model_dump(),
                "app": tel.get("app"), "image": QDRANT_SIF}

    def query_spec(self, ef, proto="grpc", k=10):
        return {"engine": "qdrant", "http": self.http, "grpc": self.grpc, "ef": ef, "k": k,
                "proto": proto}

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
        conn.execute(f"SET hnsw.ef_search = {int(ef)}")
        if spec.get("force_index"):
            # pgvector's README suggests this when the planner skips the index; see Pg.plan()
            conn.execute("SET enable_seqscan = off")
        sql = f"SELECT id FROM items ORDER BY embedding <=> %s LIMIT {int(k)}"

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
        sp = qg.SearchParams(hnsw_ef=int(ef))

        def q(vec, _client=c):  # holding the client keeps its channel open
            req = qg.QueryPoints(collection_name=COLL, limit=k, params=sp, with_payload=no_payload,
                                 query=qg.Query(nearest=qg.VectorInput(dense=qg.DenseVector(data=vec.tolist()))))
            return [p.id.num for p in stub.Query(req, timeout=600).result]
        return q

    params = qm.SearchParams(hnsw_ef=int(ef), exact=False)

    def q(vec):
        return [p.id for p in c.query_points(COLL, query=vec, limit=k, search_params=params,
                                             with_payload=False).points]
    return q
