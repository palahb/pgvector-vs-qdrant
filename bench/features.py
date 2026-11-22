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
    allows nothing else. Stop it with SIGINT."""
    return ["perf", "record", "-e", "cycles:u", "-F", str(int(freq)), "-g", "-p",
            ",".join(str(p) for p in pids), "-o", path]


def poisson_arrivals(rate, duration_s, seed):
    """Planned send times in ns after the start: a Poisson process with `rate` per second."""
    rng = np.random.default_rng(seed)
    n = int(rate * duration_s * 1.5) + 100
    t = np.cumsum(rng.exponential(1.0 / rate, size=n)) * 1e9
    while t[-1] < duration_s * 1e9:  # extremely unlikely: extend
        t = np.concatenate([t, t[-1] + np.cumsum(rng.exponential(1.0 / rate, size=n)) * 1e9])
    return t[t < duration_s * 1e9].astype(np.int64)


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
        f"max_client_conn = {max_client_conn}",
        f"max_prepared_statements = {max_prepared_statements}",
        f"logfile = {log_dir}/pgbouncer.log",
        f"pidfile = {log_dir}/pgbouncer.pid",
        "",
    ])


def pooled_dsn(dsn, pooler_port):
    return " ".join(f"port={pooler_port}" if p.startswith("port=") else p for p in dsn.split())
