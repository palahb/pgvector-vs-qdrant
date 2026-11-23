"""Writes docid and url of the first N MS MARCO v2.1 passages (login node only). With the v2 document
urls from map_v2_docs.py this matches v2 document ids to v2.1 segments.
Output: $BENCH_DATA/passage_urls_1m.tsv with a line per row of embeddings_1m.npy: segment id, url."""
import argparse
import os

from datasets import load_dataset

from common import DATA_DIR, log

REPO = "CohereLabs/msmarco-v2.1-embed-english-v3"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1_000_000)
    a = ap.parse_args()
    ids = [line.strip() for line in open(os.path.join(DATA_DIR, "passage_ids_1m.txt"))]
    stream = load_dataset(REPO, "passages", split="train", streaming=True).select_columns(["docid", "url"])
    path = os.path.join(DATA_DIR, "passage_urls_1m.tsv")
    count = 0
    with open(path + ".partial", "w") as f:
        for row in stream:
            if count >= a.n:
                break
            if row["docid"] != ids[count]:
                raise SystemExit(f"row {count}: {row['docid']} differs from the saved id {ids[count]}")
            f.write(f"{row['docid']}\t{row['url']}\n")
            count += 1
            if count % 200_000 == 0:
                log(f"urls {count}/{a.n}")
    if count < a.n:
        raise SystemExit(f"stream ended early at {count}")
    os.replace(path + ".partial", path)
    log(f"done: {path}")


if __name__ == "__main__":
    main()
