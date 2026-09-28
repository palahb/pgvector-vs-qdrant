import numpy as np
import json
import time
import psycopg2
from qdrant_client import QdrantClient
from qdrant_client.models import SearchParams
from tqdm import tqdm

print("Loading embeddings...")
embeddings = np.load("embeddings_100k.npy")

N_QUERIES = 1000
query_vectors = embeddings[:N_QUERIES]
corpus_vectors = embeddings
TOPK = 10

# ── BRUTE FORCE GROUND TRUTH ─────────────────────────────────
print("Computing brute-force ground truth...")
ground_truth = []
CHUNK = 100

for start in tqdm(range(0, N_QUERIES, CHUNK), desc="Ground truth"):
    chunk = query_vectors[start:start+CHUNK]
    sims = chunk @ corpus_vectors.T
    top_ids = np.argsort(sims, axis=1)[:, ::-1][:, :TOPK]
    ground_truth.extend(top_ids.tolist())

print(f"Ground truth ready for {len(ground_truth)} queries")

def recall_at_k(retrieved, gt, k=10):
    return len(set(retrieved[:k]) & set(gt[:k])) / k

EF_VALUES = [16, 32, 64, 128]
all_results = []

# ── PGVECTOR ─────────────────────────────────────────────────
print("\n=== Benchmarking pgvector ===")
conn = psycopg2.connect(
    host="localhost", port=5432,
    dbname="vectordb", user="postgres", password="password"
)
cur = conn.cursor()

# Get the ID offset dynamically
cur.execute("SELECT MIN(id) FROM documents;")
id_offset = cur.fetchone()[0]  # e.g. 29001
print(f"pgvector ID offset: {id_offset}")

for ef in EF_VALUES:
    cur.execute(f"SET hnsw.ef_search = {ef};")
    latencies = []
    recalls = []

    for i in tqdm(range(N_QUERIES), desc=f"pgvector ef={ef}"):
        q = query_vectors[i]
        vec_str = "[" + ",".join(f"{x:.6f}" for x in q.tolist()) + "]"

        start = time.perf_counter()
        cur.execute(f"""
            SELECT id
            FROM documents
            ORDER BY embedding <=> %s::vector
            LIMIT {TOPK};
        """, (vec_str,))
        rows = cur.fetchall()
        latency_ms = (time.perf_counter() - start) * 1000

        # pgvector id is 1-based SERIAL, ground truth is 0-based index
        # convert: pgvector id 1 -> index 0
        retrieved_ids = [r[0] - id_offset for r in rows]
        recall = recall_at_k(retrieved_ids, ground_truth[i])
        latencies.append(latency_ms)
        recalls.append(recall)

    result = {
        "system": "pgvector",
        "ef": ef,
        "dataset_size": len(embeddings),
        "n_queries": N_QUERIES,
        "mean_latency_ms": round(float(np.mean(latencies)), 3),
        "p50_latency_ms": round(float(np.percentile(latencies, 50)), 3),
        "p99_latency_ms": round(float(np.percentile(latencies, 99)), 3),
        "recall_at_10": round(float(np.mean(recalls)), 4),
    }
    all_results.append(result)
    print(f"  ef={ef:3d} | mean={result['mean_latency_ms']:7.2f}ms "
          f"| p99={result['p99_latency_ms']:7.2f}ms "
          f"| recall={result['recall_at_10']:.4f}")

cur.close()
conn.close()

# ── QDRANT ───────────────────────────────────────────────────
print("\n=== Benchmarking Qdrant ===")
client = QdrantClient(host="localhost", port=6333)

for ef in EF_VALUES:
    latencies = []
    recalls = []

    for i in tqdm(range(N_QUERIES), desc=f"Qdrant ef={ef}"):
        q = query_vectors[i]

        start = time.perf_counter()
        # newer qdrant-client API
        results = client.query_points(
            collection_name="documents",
            query=q.tolist(),
            limit=TOPK,
            search_params=SearchParams(hnsw_ef=ef)
        )
        latency_ms = (time.perf_counter() - start) * 1000

        retrieved_ids = [p.id for p in results.points]
        recall = recall_at_k(retrieved_ids, ground_truth[i])
        latencies.append(latency_ms)
        recalls.append(recall)

    result = {
        "system": "qdrant",
        "ef": ef,
        "dataset_size": len(embeddings),
        "n_queries": N_QUERIES,
        "mean_latency_ms": round(float(np.mean(latencies)), 3),
        "p50_latency_ms": round(float(np.percentile(latencies, 50)), 3),
        "p99_latency_ms": round(float(np.percentile(latencies, 99)), 3),
        "recall_at_10": round(float(np.mean(recalls)), 4),
    }
    all_results.append(result)
    print(f"  ef={ef:3d} | mean={result['mean_latency_ms']:7.2f}ms "
          f"| p99={result['p99_latency_ms']:7.2f}ms "
          f"| recall={result['recall_at_10']:.4f}")

# ── SAVE ─────────────────────────────────────────────────────
with open("benchmark_results.json", "w") as f:
    json.dump(all_results, f, indent=2)

print("\n=== Final Summary ===")
print(f"{'System':<10} {'ef':>4} {'Mean(ms)':>10} "
      f"{'p99(ms)':>10} {'Recall@10':>10}")
print("-" * 50)
for r in all_results:
    print(f"{r['system']:<10} {r['ef']:>4} "
          f"{r['mean_latency_ms']:>10.2f} "
          f"{r['p99_latency_ms']:>10.2f} "
          f"{r['recall_at_10']:>10.4f}")

print("\nSaved to benchmark_results.json")