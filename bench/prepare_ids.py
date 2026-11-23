"""Writes the segment id of the first N MS MARCO v2.1 passages, in the stream order that
prepare_data.py used for embeddings_1m.npy. Run on the login node (compute nodes have no internet).

Output in $BENCH_DATA:
  passage_ids_1m.txt   one id per line, line i is row i of embeddings_1m.npy
  passage_ids_check.json   the check of the first rows against the saved embeddings

prepare_data.py did not keep the ids, so they are read again here. To make sure the order is the same,
the first CHECK rows are streamed with their embeddings and compared with the saved array.
"""
import argparse
import hashlib
import json
import os
import time

import numpy as np
from datasets import load_dataset

from common import DATA_DIR, log

REPO = "CohereLabs/msmarco-v2.1-embed-english-v3"
CHECK = 2000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1_000_000)
    a = ap.parse_args()
    emb = np.load(os.path.join(DATA_DIR, "embeddings_1m.npy"), mmap_mode="r")
    if a.n > len(emb):
        raise SystemExit(f"embeddings_1m.npy has only {len(emb)} rows")

    log(f"checking the first {CHECK} rows against embeddings_1m.npy")
    stream = load_dataset(REPO, "passages", split="train", streaming=True)
    worst = 0.0
    first_ids = []
    for i, row in enumerate(stream):
        if i >= CHECK:
            break
        worst = max(worst, float(np.abs(np.asarray(row["emb"], dtype=np.float32) - emb[i]).max()))
        first_ids.append(row["docid"])
    if worst > 1e-6:
        raise SystemExit(f"stream order differs from embeddings_1m.npy (max abs difference {worst})")

    log(f"reading {a.n} ids")
    ids = load_dataset(REPO, "passages", split="train", streaming=True).select_columns(["docid"])
    path = os.path.join(DATA_DIR, "passage_ids_1m.txt")
    t0 = time.time()
    count = 0
    last = None
    with open(path + ".partial", "w") as f:
        for row in ids:
            if count >= a.n:
                break
            f.write(row["docid"] + "\n")
            last = row["docid"]
            count += 1
            if count % 100_000 == 0:
                log(f"ids {count}/{a.n} ({count / (time.time() - t0):.0f}/s)")
    if count < a.n:
        raise SystemExit(f"stream ended early at {count}")
    with open(path + ".partial") as f:
        head = [next(f).strip() for _ in range(CHECK)]
    if head != first_ids:
        raise SystemExit("ids of the two passes differ in the first rows")
    os.replace(path + ".partial", path)
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    with open(os.path.join(DATA_DIR, "passage_ids_check.json"), "w") as f:
        json.dump({"rows": a.n, "checked_rows_with_embeddings": CHECK, "max_abs_difference": worst,
                   "sha256": digest, "first_id": head[0], "last_id": last}, f, indent=2)
    log(f"done: {path} sha256 {digest[:12]}")


if __name__ == "__main__":
    main()
