import numpy as np
import json
from datasets import load_dataset
from tqdm import tqdm

SAMPLE_SIZE = 100_000

print("Streaming MS MARCO passages (first shard download may take 3-5 min)...")

dataset = load_dataset(
    "CohereLabs/msmarco-v2.1-embed-english-v3",
    "passages",
    split="train",
    streaming=True
)

texts = []
embeddings = []

for i, row in enumerate(tqdm(dataset, total=SAMPLE_SIZE, desc="Loading rows")):
    texts.append(row["segment"])
    embeddings.append(row["emb"])
    if i + 1 >= SAMPLE_SIZE:
        break

embeddings = np.array(embeddings, dtype=np.float32)

print(f"\nLoaded {len(texts)} passages")
print(f"Embedding shape: {embeddings.shape}")

# ── STATISTICS ───────────────────────────────────────────────
print("Computing text statistics...")
text_lengths = [len(t.split()) for t in tqdm(texts, desc="Word counts")]

stats = {
    "total_passages": len(texts),
    "embedding_dimension": int(embeddings.shape[1]),
    "embedding_model": "Cohere embed-english-v3.0",
    "source_dataset": "MS MARCO v2.1",
    "avg_words_per_passage": round(float(np.mean(text_lengths)), 2),
    "median_words_per_passage": round(float(np.median(text_lengths)), 2),
    "min_words": int(np.min(text_lengths)),
    "max_words": int(np.max(text_lengths)),
    "std_words": round(float(np.std(text_lengths)), 2),
}

print("\n=== Dataset Statistics ===")
for k, v in stats.items():
    print(f"  {k}: {v}")

# ── SAVE ─────────────────────────────────────────────────────
np.save("embeddings_100k.npy", embeddings)
with open("texts_100k.json", "w") as f:
    json.dump(texts, f)
with open("dataset_stats.json", "w") as f:
    json.dump(stats, f, indent=2)

print("\nSaved: embeddings_100k.npy, texts_100k.json, dataset_stats.json")