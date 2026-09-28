import numpy as np
import json
import time
import psycopg2
from psycopg2.extras import execute_batch
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct, SearchParams
from tqdm import tqdm

# Load 100K vectors at full 1024 dim
print("Loading embeddings...")
full = np.load("embeddings_100k.npy")
N = len(full)
N_QUERIES = 1000
TOPK = 10
EF = 64  # fixed ef for this experiment

# Three dimensionality levels via Matryoshka truncation
# Cohere v3 supports this — leading dimensions are semantically richer
DIMS_TO_TEST = [384, 512, 1024]
all_results = []

for DIM in DIMS_TO_TEST:
    print(f"\n=== Testing dimension {DIM} ===")
    # Normalize after truncation (important — partial vectors are not unit norm)
    truncated = full[:, :DIM].astype(np.float32)
    norms = np.linalg.norm(truncated, axis=1, keepdims=True)
    norms[norms == 0] = 1
    embeddings = truncated / norms

    query_vectors = embeddings[:N_QUERIES]

    # Ground truth at this dimension
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

    # ── PGVECTOR ─────────────────────────────────────────────
    print(f"--- pgvector at {DIM} dim ---")
    conn = psycopg2.connect(
        host="localhost", port=5432,
        dbname="vectordb", user="postgres", password="password"
    )
    cur = conn.cursor()
    cur.execute("DROP INDEX IF EXISTS hnsw_idx;")
    cur.execute("DROP TABLE IF EXISTS documents;")
    cur.execute(f"""
        CREATE TABLE documents (
            id SERIAL PRIMARY KEY,
            embedding vector({DIM})
        );
    """)
    conn.commit()

    pgv_start = time.time()
    BATCH = 500
    for i in tqdm(range(0, N, BATCH), desc=f"pgv insert {DIM}d"):
        batch = embeddings[i:i+BATCH]
        data = [(e.tolist(),) for e in batch]
        execute_batch(cur,
            "INSERT INTO documents (embedding) VALUES (%s::vector)",
            data, page_size=100)
        conn.commit()
    cur.execute("""
        CREATE INDEX hnsw_idx ON documents
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
    """)
    conn.commit()
    pgv_build = time.time() - pgv_start

    cur.execute("SELECT MIN(id) FROM documents;")
    offset = cur.fetchone()[0]

    cur.execute(f"SET hnsw.ef_search = {EF};")
    lats, recs = [], []
    for i in tqdm(range(N_QUERIES), desc=f"pgv query {DIM}d"):
        q = query_vectors[i]
        vec_str = "[" + ",".join(f"{x:.6f}" for x in q.tolist()) + "]"
        t0 = time.perf_counter()
        cur.execute(f"""
            SELECT id FROM documents
            ORDER BY embedding <=> %s::vector LIMIT {TOPK};
        """, (vec_str,))
        rows = cur.fetchall()
        lats.append((time.perf_counter() - t0) * 1000)
        retrieved = [r[0] - offset for r in rows]
        recs.append(recall_at_k(retrieved, ground_truth[i]))

    all_results.append({
        "system": "pgvector", "dimensions": DIM, "ef": EF,
        "build_time_s": round(pgv_build, 2),
        "mean_latency_ms": round(float(np.mean(lats)), 3),
        "p99_latency_ms": round(float(np.percentile(lats, 99)), 3),
        "recall_at_10": round(float(np.mean(recs)), 4),
    })
    print(f"  pgvector: build={pgv_build:.1f}s mean={np.mean(lats):.2f}ms recall={np.mean(recs):.4f}")

    cur.close()
    conn.close()

    # ── QDRANT ───────────────────────────────────────────────
    print(f"--- Qdrant at {DIM} dim ---")
    client = QdrantClient(host="localhost", port=6333, timeout=300)
    try:
        client.delete_collection(collection_name="documents")
    except:
        pass
    client.create_collection(
        collection_name="documents",
        vectors_config=VectorParams(size=DIM, distance=Distance.COSINE),
    )

    q_start = time.time()
    for i in tqdm(range(0, N, BATCH), desc=f"qdrant insert {DIM}d"):
        batch = embeddings[i:i+BATCH]
        points = [
            PointStruct(id=i+j, vector=batch[j].tolist())
            for j in range(len(batch))
        ]
        client.upsert(collection_name="documents", points=points)
    q_build = time.time() - q_start

    lats, recs = [], []
    for i in tqdm(range(N_QUERIES), desc=f"qdrant query {DIM}d"):
        q = query_vectors[i]
        t0 = time.perf_counter()
        results = client.query_points(
            collection_name="documents",
            query=q.tolist(),
            limit=TOPK,
            search_params=SearchParams(hnsw_ef=EF)
        )
        lats.append((time.perf_counter() - t0) * 1000)
        retrieved = [p.id for p in results.points]
        recs.append(recall_at_k(retrieved, ground_truth[i]))

    all_results.append({
        "system": "qdrant", "dimensions": DIM, "ef": EF,
        "build_time_s": round(q_build, 2),
        "mean_latency_ms": round(float(np.mean(lats)), 3),
        "p99_latency_ms": round(float(np.percentile(lats, 99)), 3),
        "recall_at_10": round(float(np.mean(recs)), 4),
    })
    print(f"  qdrant: build={q_build:.1f}s mean={np.mean(lats):.2f}ms recall={np.mean(recs):.4f}")

with open("results_dimensionality.json", "w") as f:
    json.dump(all_results, f, indent=2)

print("\n=== Saved to results_dimensionality.json ===")
for r in all_results:
    print(f"  {r['system']:9s} d={r['dimensions']:4d} "
          f"mean={r['mean_latency_ms']:6.2f}ms "
          f"recall={r['recall_at_10']:.4f} "
          f"build={r['build_time_s']:.1f}s")