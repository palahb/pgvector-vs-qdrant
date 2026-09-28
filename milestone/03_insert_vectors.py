import numpy as np
import json
import time
import psycopg2
from psycopg2.extras import execute_batch
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from tqdm import tqdm

print("Loading data...")
embeddings = np.load("embeddings_100k.npy")
with open("texts_100k.json") as f:
    texts = json.load(f)

DIM = embeddings.shape[1]
N = len(embeddings)
print(f"Loaded {N} vectors of dimension {DIM}")

# ── PGVECTOR ─────────────────────────────────────────────────
print("\n=== Inserting into pgvector ===")
conn = psycopg2.connect(
    host="localhost", port=5432,
    dbname="vectordb", user="postgres", password="password"
)
cur = conn.cursor()
cur.execute("TRUNCATE documents;")
conn.commit()

insert_start = time.time()
BATCH = 200
for i in tqdm(range(0, N, BATCH), desc="pgvector insert"):
    batch_texts = texts[i:i+BATCH]
    batch_embs = embeddings[i:i+BATCH]
    data = [(t.replace('\x00', ''), e.tolist()) for t, e in zip(batch_texts, batch_embs)]
    execute_batch(
        cur,
        "INSERT INTO documents (text, embedding) VALUES (%s, %s::vector)",
        data,
        page_size=50
    )
    conn.commit()

pgvector_insert_time = time.time() - insert_start
print(f"Insert time: {pgvector_insert_time:.2f}s")

print("Building HNSW index on pgvector...")
index_start = time.time()
cur.execute("""
    CREATE INDEX hnsw_idx
    ON documents
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
""")
conn.commit()
pgvector_index_time = time.time() - index_start
pgvector_total = pgvector_insert_time + pgvector_index_time
print(f"Index build time: {pgvector_index_time:.2f}s")
print(f"pgvector total: {pgvector_total:.2f}s")

cur.close()
conn.close()

# ── QDRANT ───────────────────────────────────────────────────
print("\n=== Inserting into Qdrant ===")
client = QdrantClient(host="localhost", port=6333)

client.recreate_collection(
    collection_name="documents",
    vectors_config=VectorParams(size=DIM, distance=Distance.COSINE),
)

qdrant_start = time.time()
BATCH = 200
for i in tqdm(range(0, N, BATCH), desc="Qdrant insert"):
    batch_embs = embeddings[i:i+BATCH]
    batch_texts = texts[i:i+BATCH]
    points = [
        PointStruct(
            id=i+j,
            vector=batch_embs[j].tolist(),
            payload={"text": batch_texts[j]}
        )
        for j in range(len(batch_embs))
    ]
    client.upsert(collection_name="documents", points=points)

qdrant_total = time.time() - qdrant_start
print(f"Qdrant total: {qdrant_total:.2f}s")

# ── SAVE ─────────────────────────────────────────────────────
build_times = {
    "dataset_size": N,
    "dimensions": DIM,
    "pgvector_insert_time_s": round(pgvector_insert_time, 2),
    "pgvector_index_time_s": round(pgvector_index_time, 2),
    "pgvector_total_build_time_s": round(pgvector_total, 2),
    "qdrant_total_build_time_s": round(qdrant_total, 2),
}

with open("build_times.json", "w") as f:
    json.dump(build_times, f, indent=2)

print("\n=== Build Time Summary ===")
print(f"  pgvector: {pgvector_total:.2f}s")
print(f"  Qdrant:   {qdrant_total:.2f}s")
print("Saved to build_times.json")