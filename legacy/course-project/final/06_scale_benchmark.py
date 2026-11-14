import numpy as np
import json
import time
import sys
import os
import psycopg2
from psycopg2.extras import execute_batch
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct, SearchParams
from tqdm import tqdm

if len(sys.argv) < 2:
    print("Usage: python 06_scale_benchmark.py [100000|500000|1000000]")
    sys.exit(1)

SCALE = int(sys.argv[1])
SCALE_LABEL = f"{SCALE // 1000}K" if SCALE < 1_000_000 else "1M"
CHECKPOINT_FILE = f"checkpoint_{SCALE_LABEL}.json"
RESULTS_FILE = f"results_{SCALE_LABEL}.json"

print(f"=== Running scale experiment at {SCALE_LABEL} ===")

# ── CHECKPOINT MANAGEMENT ────────────────────────────────────
def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {}

def save_checkpoint(cp):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(cp, f, indent=2)

cp = load_checkpoint()
if cp:
    print(f"Found checkpoint with completed phases: {list(cp.keys())}")

# ── LOAD DATA ────────────────────────────────────────────────
print("Loading embeddings...")
if SCALE == 100_000:
    embeddings = np.load("embeddings_100k.npy")
elif SCALE == 500_000:
    embeddings = np.load("embeddings_500k.npy")
elif SCALE == 1_000_000:
    embeddings = np.load("embeddings_1m.npy")
else:
    raise ValueError("SCALE must be 100000, 500000, or 1000000")

DIM = embeddings.shape[1]
N = len(embeddings)
print(f"Dataset: {N} vectors, dimension {DIM}")

# ── PGVECTOR INSERT + INDEX ──────────────────────────────────
if "pgvector_done" not in cp:
    print(f"\n--- pgvector setup ({SCALE_LABEL}) ---")
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

    print("Inserting vectors...")
    insert_start = time.time()
    BATCH = 500
    for i in tqdm(range(0, N, BATCH), desc="pgvector insert"):
        batch = embeddings[i:i+BATCH]
        data = [(e.tolist(),) for e in batch]
        execute_batch(
            cur,
            "INSERT INTO documents (embedding) VALUES (%s::vector)",
            data, page_size=100
        )
        conn.commit()
    pgv_insert_time = time.time() - insert_start

    print("Building HNSW index...")
    idx_start = time.time()
    cur.execute("""
        CREATE INDEX hnsw_idx ON documents
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
    """)
    conn.commit()
    pgv_index_time = time.time() - idx_start
    pgv_total = pgv_insert_time + pgv_index_time

    cur.execute("SELECT MIN(id) FROM documents;")
    id_offset = cur.fetchone()[0]
    cur.close()
    conn.close()

    cp["pgvector_done"] = True
    cp["pgvector_insert_s"] = round(pgv_insert_time, 2)
    cp["pgvector_index_s"] = round(pgv_index_time, 2)
    cp["pgvector_total_s"] = round(pgv_total, 2)
    cp["id_offset"] = id_offset
    save_checkpoint(cp)
    print(f"pgvector done: insert={pgv_insert_time:.1f}s "
          f"index={pgv_index_time:.1f}s total={pgv_total:.1f}s")
else:
    print(f"\n--- pgvector already done (cached) ---")
    print(f"  total: {cp['pgvector_total_s']}s, id_offset: {cp['id_offset']}")

id_offset = cp["id_offset"]

# ── QDRANT INSERT (resumable, hardened) ──────────────────────
QDRANT_BATCH = 100        # smaller batches = fewer timeouts
QDRANT_TIMEOUT = 600      # generous client timeout
MAX_RETRIES = 6           # exponential backoff

client = QdrantClient(host="localhost", port=6333, timeout=QDRANT_TIMEOUT)

if "qdrant_done" not in cp:
    qdrant_resume_from = cp.get("qdrant_inserted_count", 0)

    if qdrant_resume_from == 0:
        print(f"\n--- Qdrant setup ({SCALE_LABEL}) ---")
        try:
            client.delete_collection("documents")
        except Exception:
            pass
        client.create_collection(
            collection_name="documents",
            vectors_config=VectorParams(size=DIM, distance=Distance.COSINE),
        )
        cp["qdrant_start_time"] = time.time()
        cp["qdrant_elapsed_s"] = 0.0
        save_checkpoint(cp)
    else:
        # Verify collection still exists
        try:
            info = client.get_collection("documents")
            actual = info.points_count
            print(f"\n--- Qdrant resuming from index {qdrant_resume_from} "
                  f"(collection has {actual} points) ---")
            # If actual differs, trust the actual count
            qdrant_resume_from = actual
        except Exception:
            print("Qdrant collection lost — restarting from 0")
            client.create_collection(
                collection_name="documents",
                vectors_config=VectorParams(size=DIM, distance=Distance.COSINE),
            )
            qdrant_resume_from = 0
            cp["qdrant_elapsed_s"] = 0.0

    elapsed_before = cp.get("qdrant_elapsed_s", 0.0)
    session_start = time.time()

    with tqdm(total=N, initial=qdrant_resume_from, desc="Qdrant insert") as pbar:
        i = qdrant_resume_from
        while i < N:
            batch = embeddings[i:i+QDRANT_BATCH]
            points = [
                PointStruct(id=i+j, vector=batch[j].tolist())
                for j in range(len(batch))
            ]

            for attempt in range(MAX_RETRIES):
                try:
                    client.upsert(collection_name="documents", points=points)
                    break
                except Exception as e:
                    wait = 5 * (2 ** attempt)
                    if attempt < MAX_RETRIES - 1:
                        print(f"\n  Retry {attempt+1}/{MAX_RETRIES} at i={i}: "
                              f"{type(e).__name__} — waiting {wait}s")
                        time.sleep(wait)
                    else:
                        # Save what we have and re-raise so user can rerun
                        cp["qdrant_inserted_count"] = i
                        cp["qdrant_elapsed_s"] = elapsed_before + (time.time() - session_start)
                        save_checkpoint(cp)
                        print(f"\nGiving up at i={i}. Run script again to resume.")
                        raise

            i += len(batch)
            pbar.update(len(batch))

            # Checkpoint every 5000 vectors
            if i % 5000 == 0 or i >= N:
                cp["qdrant_inserted_count"] = i
                cp["qdrant_elapsed_s"] = elapsed_before + (time.time() - session_start)
                save_checkpoint(cp)

    q_total = elapsed_before + (time.time() - session_start)
    cp["qdrant_done"] = True
    cp["qdrant_total_s"] = round(q_total, 2)
    save_checkpoint(cp)
    print(f"Qdrant done: {q_total:.1f}s total (across all sessions)")
else:
    print(f"\n--- Qdrant already done (cached) ---")
    print(f"  total: {cp['qdrant_total_s']}s")

# ── GROUND TRUTH ─────────────────────────────────────────────
print(f"\nComputing brute-force ground truth (1000 queries)...")
N_QUERIES = 1000
TOPK = 10
query_vectors = embeddings[:N_QUERIES]

ground_truth = []
GT_CHUNK = 50 if SCALE < 500_000 else 20  # smaller chunks at higher scale
for s in tqdm(range(0, N_QUERIES, GT_CHUNK), desc="Ground truth"):
    chunk = query_vectors[s:s+GT_CHUNK]
    sims = chunk @ embeddings.T
    top_ids = np.argsort(sims, axis=1)[:, ::-1][:, :TOPK]
    ground_truth.extend(top_ids.tolist())

def recall_at_k(retrieved, gt, k=10):
    return len(set(retrieved[:k]) & set(gt[:k])) / k

EF_VALUES = [16, 32, 64, 128]

# Load previously completed benchmark results if any
benchmarks_done = cp.get("benchmarks", [])
done_keys = {(r["system"], r["ef"]) for r in benchmarks_done}

# ── PGVECTOR BENCHMARK ──────────────────────────────────────
print("\n--- Benchmarking pgvector ---")
conn = psycopg2.connect(
    host="localhost", port=5432,
    dbname="vectordb", user="postgres", password="password"
)
cur = conn.cursor()
for ef in EF_VALUES:
    if ("pgvector", ef) in done_keys:
        print(f"  ef={ef} already done (cached)")
        continue

    cur.execute(f"SET hnsw.ef_search = {ef};")
    latencies, recalls = [], []
    for i in tqdm(range(N_QUERIES), desc=f"pgv ef={ef}"):
        q = query_vectors[i]
        vec_str = "[" + ",".join(f"{x:.6f}" for x in q.tolist()) + "]"
        t0 = time.perf_counter()
        cur.execute(f"""
            SELECT id FROM documents
            ORDER BY embedding <=> %s::vector LIMIT {TOPK};
        """, (vec_str,))
        rows = cur.fetchall()
        latencies.append((time.perf_counter() - t0) * 1000)
        retrieved = [r[0] - id_offset for r in rows]
        recalls.append(recall_at_k(retrieved, ground_truth[i]))

    r = {
        "system": "pgvector", "ef": ef, "dataset_size": SCALE, "dimensions": DIM,
        "mean_latency_ms": round(float(np.mean(latencies)), 3),
        "p99_latency_ms": round(float(np.percentile(latencies, 99)), 3),
        "recall_at_10": round(float(np.mean(recalls)), 4),
    }
    benchmarks_done.append(r)
    cp["benchmarks"] = benchmarks_done
    save_checkpoint(cp)
    print(f"  ef={ef}: mean={r['mean_latency_ms']}ms "
          f"p99={r['p99_latency_ms']}ms recall={r['recall_at_10']}")

cur.close()
conn.close()

# ── QDRANT BENCHMARK ────────────────────────────────────────
print("\n--- Benchmarking Qdrant ---")
client = QdrantClient(host="localhost", port=6333, timeout=QDRANT_TIMEOUT)
for ef in EF_VALUES:
    if ("qdrant", ef) in done_keys:
        print(f"  ef={ef} already done (cached)")
        continue

    latencies, recalls = [], []
    for i in tqdm(range(N_QUERIES), desc=f"qdrant ef={ef}"):
        q = query_vectors[i]
        t0 = time.perf_counter()
        results = client.query_points(
            collection_name="documents",
            query=q.tolist(),
            limit=TOPK,
            search_params=SearchParams(hnsw_ef=ef)
        )
        latencies.append((time.perf_counter() - t0) * 1000)
        retrieved = [p.id for p in results.points]
        recalls.append(recall_at_k(retrieved, ground_truth[i]))

    r = {
        "system": "qdrant", "ef": ef, "dataset_size": SCALE, "dimensions": DIM,
        "mean_latency_ms": round(float(np.mean(latencies)), 3),
        "p99_latency_ms": round(float(np.percentile(latencies, 99)), 3),
        "recall_at_10": round(float(np.mean(recalls)), 4),
    }
    benchmarks_done.append(r)
    cp["benchmarks"] = benchmarks_done
    save_checkpoint(cp)
    print(f"  ef={ef}: mean={r['mean_latency_ms']}ms "
          f"p99={r['p99_latency_ms']}ms recall={r['recall_at_10']}")

# ── FINAL OUTPUT ─────────────────────────────────────────────
output = {
    "scale": SCALE,
    "build_times": {
        "pgvector_insert_s": cp["pgvector_insert_s"],
        "pgvector_index_s": cp["pgvector_index_s"],
        "pgvector_total_s": cp["pgvector_total_s"],
        "qdrant_total_s": cp["qdrant_total_s"],
    },
    "benchmarks": sorted(benchmarks_done,
                         key=lambda r: (r["system"], r["ef"])),
}

with open(RESULTS_FILE, "w") as f:
    json.dump(output, f, indent=2)

print(f"\n=== Saved to {RESULTS_FILE} ===")
print(f"{'System':10s} {'ef':>4s} {'Mean(ms)':>10s} {'p99(ms)':>10s} {'Recall@10':>10s}")
print("-" * 50)
for r in output["benchmarks"]:
    print(f"{r['system']:10s} {r['ef']:>4d} "
          f"{r['mean_latency_ms']:>10.2f} "
          f"{r['p99_latency_ms']:>10.2f} "
          f"{r['recall_at_10']:>10.4f}")