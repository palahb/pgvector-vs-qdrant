import psycopg2
import json

with open("dataset_stats.json") as f:
    stats = json.load(f)

DIM = stats["embedding_dimension"]
print(f"Setting up pgvector with dimension {DIM}...")

conn = psycopg2.connect(
    host="localhost", port=5432,
    dbname="vectordb", user="postgres", password="password"
)
cur = conn.cursor()

cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
cur.execute("DROP TABLE IF EXISTS documents;")
cur.execute(f"""
    CREATE TABLE documents (
        id SERIAL PRIMARY KEY,
        text TEXT,
        embedding vector({DIM})
    );
""")

conn.commit()
cur.close()
conn.close()
print("pgvector schema ready.")