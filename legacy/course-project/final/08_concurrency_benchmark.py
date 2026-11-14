import numpy as np
import json
import time
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from qdrant_client import QdrantClient
from qdrant_client.models import SearchParams
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

print("Loading embeddings (100K)...")
embeddings = np.load("embeddings_100k.npy")
N_QUERIES = 1000
TOPK = 10
EF = 64  # fixed ef for concurrency comparison
CONCURRENCY_LEVELS = [1, 10, 50]

query_vectors = embeddings[:N_QUERIES]

# Ground truth
print("Computing ground truth...")
ground_truth = []
CHUNK = 100
for s in tqdm(range(0, N_QUERIES, CHUNK), desc="GT"):
    chunk = query_vectors[s:s+CHUNK]
    sims = chunk @ embeddings.T
    top_ids = np.argsort(sims, axis=1)[:, ::-1][:, :TOPK]
    ground_truth.extend(top_ids.tolist())

def recall_at_k(retrieved, gt, k=10):
    return len(set(retrieved[:k]) & set(gt[:k])) / k

all_results = []

# Get ID offset for pgvector
conn = psycopg2.connect(
    host="localhost", port=5432, dbname="vectordb",
    user="postgres", password="password"
)
cur = conn.cursor()
cur.execute("SELECT MIN(id) FROM documents;")
ID_OFFSET = cur.fetchone()[0]
cur.close()
conn.close()
print(f"pgvector ID offset: {ID_OFFSET}")

# ── PGVECTOR CONCURRENCY ─────────────────────────────────────
print("\n=== pgvector concurrency benchmark ===")

def pgvector_query(args):
    qi, q = args
    conn = psycopg2.connect(
        host="localhost", port=5432, dbname="vectordb",
        user="postgres", password="password"
    )
    cur = conn.cursor()
    cur.execute(f"SET hnsw.ef_search = {EF};")
    vec_str = "[" + ",".join(f"{x:.6f}" for x in q.tolist()) + "]"
    t0 = time.perf_counter()
    cur.execute(f"""
        SELECT id FROM documents
        ORDER BY embedding <=> %s::vector LIMIT {TOPK};
    """, (vec_str,))
    rows = cur.fetchall()
    lat = (time.perf_counter() - t0) * 1000
    retrieved = [r[0] - ID_OFFSET for r in rows]
    rec = recall_at_k(retrieved, ground_truth[qi])
    cur.close()
    conn.close()
    return lat, rec

for C in CONCURRENCY_LEVELS:
    print(f"\nConcurrency level: {C}")
    args_list = [(i, query_vectors[i]) for i in range(N_QUERIES)]
    lats, recs = [], []

    t_start = time.time()
    with ThreadPoolExecutor(max_workers=C) as ex:
        futures = [ex.submit(pgvector_query, a) for a in args_list]
        for f in tqdm(as_completed(futures), total=N_QUERIES, desc=f"pgv C={C}"):
            lat, rec = f.result()
            lats.append(lat)
            recs.append(rec)
    total_time = time.time() - t_start
    throughput = N_QUERIES / total_time

    r = {
        "system": "pgvector", "concurrency": C, "ef": EF,
        "mean_latency_ms": round(float(np.mean(lats)), 3),
        "p99_latency_ms": round(float(np.percentile(lats, 99)), 3),
        "recall_at_10": round(float(np.mean(recs)), 4),
        "throughput_qps": round(throughput, 2),
        "total_time_s": round(total_time, 2),
    }
    all_results.append(r)
    print(f"  C={C}: mean={r['mean_latency_ms']}ms p99={r['p99_latency_ms']}ms "
          f"throughput={r['throughput_qps']} qps")

# ── QDRANT CONCURRENCY ───────────────────────────────────────
print("\n=== Qdrant concurrency benchmark ===")

def qdrant_query(args):
    qi, q = args
    client = QdrantClient(host="localhost", port=6333, timeout=300)
    t0 = time.perf_counter()
    results = client.query_points(
        collection_name="documents",
        query=q.tolist(),
        limit=TOPK,
        search_params=SearchParams(hnsw_ef=EF)
    )
    lat = (time.perf_counter() - t0) * 1000
    retrieved = [p.id for p in results.points]
    rec = recall_at_k(retrieved, ground_truth[qi])
    return lat, rec

for C in CONCURRENCY_LEVELS:
    print(f"\nConcurrency level: {C}")
    args_list = [(i, query_vectors[i]) for i in range(N_QUERIES)]
    lats, recs = [], []

    t_start = time.time()
    with ThreadPoolExecutor(max_workers=C) as ex:
        futures = [ex.submit(qdrant_query, a) for a in args_list]
        for f in tqdm(as_completed(futures), total=N_QUERIES, desc=f"qdrant C={C}"):
            lat, rec = f.result()
            lats.append(lat)
            recs.append(rec)
    total_time = time.time() - t_start
    throughput = N_QUERIES / total_time

    r = {
        "system": "qdrant", "concurrency": C, "ef": EF,
        "mean_latency_ms": round(float(np.mean(lats)), 3),
        "p99_latency_ms": round(float(np.percentile(lats, 99)), 3),
        "recall_at_10": round(float(np.mean(recs)), 4),
        "throughput_qps": round(throughput, 2),
        "total_time_s": round(total_time, 2),
    }
    all_results.append(r)
    print(f"  C={C}: mean={r['mean_latency_ms']}ms p99={r['p99_latency_ms']}ms "
          f"throughput={r['throughput_qps']} qps")

with open("results_concurrency.json", "w") as f:
    json.dump(all_results, f, indent=2)

print("\n=== Concurrency Summary ===")
print(f"{'System':10s} {'C':>4s} {'Mean(ms)':>10s} {'p99(ms)':>10s} {'QPS':>10s}")
print("-" * 50)
for r in all_results:
    print(f"{r['system']:10s} {r['concurrency']:>4d} "
          f"{r['mean_latency_ms']:>10.2f} {r['p99_latency_ms']:>10.2f} "
          f"{r['throughput_qps']:>10.2f}")

print("\nSaved to results_concurrency.json")