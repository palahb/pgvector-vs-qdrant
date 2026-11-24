"""Pure helpers for the optional harness features (returned IDs, perf record, halfvec, int8
quantization, open-loop arrivals, PgBouncer). Nothing here touches a server, so every default
that matches the old behavior can be tested offline."""
import numpy as np

from common import summarize


def pad_ids(ids, k):
    """Returned row numbers as a fixed-width int64 row; missing neighbors are -1."""
    out = np.full(k, -1, dtype=np.int64)
    ids = list(ids)[:k]
    out[:len(ids)] = ids
    return out


PG_VECTOR_TYPES = {"vector": "vector", "halfvec": "halfvec"}


def pg_vector_type(kind, dim):
    if kind not in PG_VECTOR_TYPES:
        raise ValueError(f"unknown pgvector column type {kind!r}")
    return {"column": f"{kind}({dim})", "opclass": f"{kind}_cosine_ops", "copy_type": kind,
            "param_cast": "" if kind == "vector" else f"::{kind}({dim})"}


def pg_copy_value(kind, vec):
    """Value for binary COPY: numpy arrays dump as vector, halfvec needs its own wrapper."""
    if kind == "halfvec":
        from pgvector import HalfVector
        return HalfVector(vec)
    return vec


def pg_create_table_sql(kind, dim, unlogged):
    return (f"CREATE {'UNLOGGED ' if unlogged else ''}TABLE items "
            f"(id bigint PRIMARY KEY, embedding {pg_vector_type(kind, dim)['column']})")


def pg_create_index_sql(kind, m, efc):
    return (f"CREATE INDEX items_hnsw ON items USING hnsw (embedding {kind}_cosine_ops) "
            f"WITH (m = {m}, ef_construction = {efc})")


def pg_plan_prepare_sql(kind, dim, k):
    cast = pg_vector_type(kind, dim)["param_cast"]
    return f"PREPARE bq(vector) AS SELECT id FROM items ORDER BY embedding <=> $1{cast} LIMIT {int(k)}"


def pg_query_sql(kind, dim, k):
    cast = pg_vector_type(kind, dim)["param_cast"]
    return f"SELECT id FROM items ORDER BY embedding <=> %s{cast} LIMIT {int(k)}"


def qdrant_quantization(kind, always_ram=True, rescore=True, oversampling=None, quantile=None):
    """Recorded description of the scalar quantization arm, or None for full precision."""
    if kind == "none":
        return None
    if kind != "int8":
        raise ValueError(f"unknown quantization {kind!r}")
    return {"type": "int8", "quantile": quantile, "always_ram": bool(always_ram),
            "rescore": bool(rescore), "oversampling": oversampling}


def perf_record_cmd(pids, path, freq=499):
    """User-space cycle sampling of the server processes. perf_event_paranoid=2 on the cluster
    allows nothing else. No call graphs: the analysis uses self time, and neither server is
    built with frame pointers. Stop it with SIGINT."""
    return ["perf", "record", "-e", "cycles:u", "-F", str(int(freq)), "-p",
            ",".join(str(p) for p in pids), "-o", path]


def poisson_arrivals(rate, duration_s, seed):
    """Planned send times in ns after the start: a Poisson process with `rate` per second."""
    rng = np.random.default_rng(seed)
    n = int(rate * duration_s * 1.5) + 100
    t = np.cumsum(rng.exponential(1.0 / rate, size=n)) * 1e9
    while t[-1] < duration_s * 1e9:  # extremely unlikely: extend
        t = np.concatenate([t, t[-1] + np.cumsum(rng.exponential(1.0 / rate, size=n)) * 1e9])
    return t[t < duration_s * 1e9].astype(np.int64)


def parse_fractions(text):
    """Load levels as fractions of the measured capacity, e.g. "0.5,0.8,0.95,1.1"."""
    try:
        values = [float(x) for x in text.split(",") if x]
    except ValueError as exc:
        raise ValueError(f"load fractions must be numbers: {text!r}") from exc
    if any(v <= 0 for v in values):
        raise ValueError(f"load fractions must be positive: {text!r}")
    return values


def open_loop_rates(capacity, fractions):
    """Offered rates (queries per second) as fractions of the capacity of a build, whole numbers, at least 1."""
    if capacity is None or capacity <= 0:
        raise ValueError("the capacity of the build was not measured; no open-loop rate can be derived")
    return [max(1, int(round(capacity * f))) for f in fractions]


def capacity_qps(rows, proto, ef, clients):
    """Closed-loop throughput of the window with `clients` clients at `ef`, or None."""
    for r in rows:
        if r.get("proto") == proto and r.get("ef") == ef and r.get("clients") == clients:
            return r.get("throughput_qps")
    return None


def open_loop_summary(planned, started, finished, hits, k, offered_rate, window_s):
    """Latency is taken from the planned send time, so a sender that falls behind (a saturated
    server) shows up as queueing delay instead of being hidden by the closed loop."""
    planned, started, finished = (np.asarray(x, dtype=np.int64) for x in (planned, started, finished))
    lag = (started - planned) / 1e6
    out = {"offered_qps": offered_rate, "completed": int(len(planned)),
           "achieved_qps": round(len(planned) / window_s, 6),
           "recall_at_k": round(float(np.sum(hits)) / (k * max(len(planned), 1)), 5),
           "mean_send_lag_ms": round(float(lag.mean()), 4) if len(lag) else None,
           "max_send_lag_ms": round(float(lag.max()), 4) if len(lag) else None}
    out.update(summarize(finished - planned))
    service = summarize(finished - started)
    out.update({f"service_{key}": value for key, value in service.items() if key != "count"})
    return out


PG_EF_SEARCH_MAX = 1000
CONN_MODES = ("direct", "direct_txn", "pooled")


def pg_txn_settings(ef, force_index):
    """Settings that a pooled query carries inside its own transaction. A session-level SET does not
    survive a transaction pooler: the next statement may reach another server connection."""
    if not 1 <= int(ef) <= PG_EF_SEARCH_MAX:
        raise ValueError(f"hnsw.ef_search {ef} is outside 1..{PG_EF_SEARCH_MAX}; pgvector would ignore it")
    out = [f"SET LOCAL hnsw.ef_search = {int(ef)}"]
    if force_index:
        out.append("SET LOCAL enable_seqscan = off")
    return out


def parse_conn_modes(text):
    modes = [m for m in text.split(",") if m]
    if not modes or len(set(modes)) != len(modes) or any(m not in CONN_MODES for m in modes):
        raise ValueError(f"connection modes must be distinct values of {CONN_MODES}, got {text!r}")
    return modes


def conn_mode_flags(mode):
    return {"use_pooler": mode == "pooled", "per_query_txn": mode in ("direct_txn", "pooled")}


POOLER_BINARY_IN_IMAGE = "/opt/pgbouncer/pgbouncer"


def pooler_cmd(sif, binary, ini, work):
    """The pgbouncer command: from the digest-pinned image (the binary is not on its PATH) or a native one."""
    if sif:
        return ["apptainer", "exec", "--cleanenv", "--bind", work, sif, POOLER_BINARY_IN_IMAGE, ini]
    return [binary or "pgbouncer", ini]


def pooler_usage(cpu0, cpu1, wall_s, completed):
    return {"pooler_cores_busy": round((cpu1 - cpu0) / wall_s, 4) if wall_s else None,
            "pooler_cpu_ms_per_query": round((cpu1 - cpu0) * 1000 / completed, 6) if completed else None}


def txn_query(conn, settings, sql, vec):
    """One pooled query: BEGIN, the SET LOCAL statements, the SELECT, COMMIT."""
    with conn.transaction():
        for statement in settings:
            conn.execute(statement)
        return [r[0] for r in conn.execute(sql, (vec,), binary=True, prepare=True).fetchall()]


def pgbouncer_ini(listen_port, pg_port, pool_size, max_client_conn, auth_file, log_dir,
                  max_prepared_statements=200):
    """Transaction pooling, with protocol-level prepared statements tracked by the pooler
    (PgBouncer 1.21+), because the benchmark client prepares its query."""
    return "\n".join([
        "[databases]",
        f"postgres = host=127.0.0.1 port={pg_port} dbname=postgres",
        "",
        "[pgbouncer]",
        "listen_addr = 127.0.0.1",
        f"listen_port = {listen_port}",
        "auth_type = trust",
        f"auth_file = {auth_file}",
        "pool_mode = transaction",
        f"default_pool_size = {pool_size}",
        f"min_pool_size = {pool_size}",
        "ignore_startup_parameters = extra_float_digits",
        "unix_socket_dir =",
        f"max_client_conn = {max_client_conn}",
        f"max_prepared_statements = {max_prepared_statements}",
        f"logfile = {log_dir}/pgbouncer.log",
        f"pidfile = {log_dir}/pgbouncer.pid",
        "",
    ])


def pooled_dsn(dsn, pooler_port):
    return " ".join(f"port={pooler_port}" if p.startswith("port=") else p for p in dsn.split())
