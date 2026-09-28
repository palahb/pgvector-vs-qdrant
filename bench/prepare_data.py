"""Downloads the first N MS MARCO v2.1 passages (Cohere embed-english-v3, 1024 dims) and the
1,677 TREC-DL 2021-2023 query embeddings. Run on the login node, compute nodes have no internet.

Writes into $BENCH_DATA:
  embeddings_1m.npy   float32 [N, 1024], written incrementally (no 30 GB Python lists this time)
  queries.npy         float32 [1677, 1024]
  queries_meta.json   ids, texts, TREC year
  dataset_stats.json  passage length statistics over all N passages
"""
import argparse
import json
import os
import time

import numpy as np
from datasets import load_dataset

from common import DATA_DIR, log

REPO = "CohereLabs/msmarco-v2.1-embed-english-v3"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1_000_000)
    a = ap.parse_args()
    os.makedirs(DATA_DIR, exist_ok=True)

    log("queries")
    # datasets 4.x returns lazy Column objects for qs["col"], so go through plain lists
    qs = load_dataset(REPO, "queries", split="test").to_dict()
    q = np.asarray(qs["emb"], dtype=np.float32)
    if q.ndim != 2 or q.shape[1] != 1024:
        raise SystemExit(f"unexpected query embedding shape {q.shape}")
    np.save(os.path.join(DATA_DIR, "queries.npy"), q)
    with open(os.path.join(DATA_DIR, "queries_meta.json"), "w") as f:
        json.dump({"id": qs["_id"], "text": qs["text"], "trec_year": qs["trec-year"]}, f)
    log(f"queries: {q.shape}, norms {np.linalg.norm(q, axis=1).min():.4f}..{np.linalg.norm(q, axis=1).max():.4f}")

    path = os.path.join(DATA_DIR, "embeddings_1m.npy")
    part = path + ".partial"
    out = np.lib.format.open_memmap(part, mode="w+", dtype=np.float32, shape=(a.n, 1024))
    words = np.empty(a.n, dtype=np.int32)
    ds = load_dataset(REPO, "passages", split="train", streaming=True)
    t0 = time.time()
    for i, row in enumerate(ds):
        if i >= a.n:
            break
        out[i] = row["emb"]
        words[i] = len(row["segment"].split())
        if (i + 1) % 50_000 == 0:
            rate = (i + 1) / (time.time() - t0)
            log(f"passages {i + 1}/{a.n}  ({rate:.0f}/s, eta {(a.n - i - 1) / rate / 60:.0f} min)")
    else:
        i += 1
    if i < a.n:
        raise SystemExit(f"stream ended early at {i}")
    out.flush()
    del out
    os.replace(part, path)

    norms = np.linalg.norm(np.load(path, mmap_mode="r")[:10_000], axis=1)
    stats = {
        "source_dataset": "MS MARCO v2.1 (segmented passages), first N rows of the HF stream",
        "hf_repo": REPO, "embedding_model": "Cohere embed-english-v3.0", "embedding_dimension": 1024,
        "total_passages": a.n, "queries": int(len(q)), "query_source": "TREC DL 2021-2023",
        "avg_words_per_passage": round(float(words.mean()), 2),
        "median_words_per_passage": float(np.median(words)),
        "min_words": int(words.min()), "max_words": int(words.max()), "std_words": round(float(words.std()), 2),
        "norm_check_first_10k": [round(float(norms.min()), 5), round(float(norms.max()), 5)],
    }
    with open(os.path.join(DATA_DIR, "dataset_stats.json"), "w") as f:
        json.dump(stats, f, indent=2)
    log(f"done: {path}")


if __name__ == "__main__":
    main()
