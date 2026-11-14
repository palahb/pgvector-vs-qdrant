import numpy as np
import json
from datasets import load_dataset
from tqdm import tqdm

SAMPLE_SIZE = 1_000_000

print("Streaming 1M MS MARCO passages with Cohere embeddings...")
print("This will take 30-60 minutes on first run...")

dataset = load_dataset(
    "CohereLabs/msmarco-v2.1-embed-english-v3",
    "passages",
    split="train",
    streaming=True
)

texts = []
embeddings = []

for i, row in enumerate(tqdm(dataset, total=SAMPLE_SIZE, desc="Loading")):
    texts.append(row["segment"].replace('\x00', ''))
    embeddings.append(row["emb"])
    if i + 1 >= SAMPLE_SIZE:
        break

embeddings = np.array(embeddings, dtype=np.float32)
print(f"\nLoaded {len(texts)} passages, shape {embeddings.shape}")

# Save in three slices to support all experiments
np.save("embeddings_1m.npy", embeddings)
with open("texts_1m.json", "w") as f:
    json.dump(texts, f)

# Also save 500K slice
np.save("embeddings_500k.npy", embeddings[:500_000])

print("Saved: embeddings_1m.npy, embeddings_500k.npy, texts_1m.json")
print("(embeddings_100k.npy from milestone is still valid)")