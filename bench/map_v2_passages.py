"""Reads one shard of the MS MARCO v2 passage collection from the public tar and writes the passage id and the
id of the document it comes from, for passages of documents of one document shard. The TREC DL 2023
judgments name v2 passages; this links them to documents and so to v2.1 segments (by url, see e23_gate.py).

usage: map_v2_passages.py PASSAGE_SHARD DOC_SHARD OUTPUT.tsv
Prints how many passages of the passage shard belong to documents of DOC_SHARD, and the first and last document id seen.
"""
import json
import sys
import urllib.request
import zlib

URL = "https://msmarco.z22.web.core.windows.net/msmarcoranking/msmarco_v2_passage.tar"


def request(start, end):
    return urllib.request.urlopen(urllib.request.Request(URL, headers={"Range": f"bytes={start}-{end}"}), timeout=120)


def member(shard):
    offset = 0
    while True:
        header = request(offset, offset + 511).read()
        name = header[:100].rstrip(b"\0").decode()
        size = int(header[124:135].decode().strip("\0 ") or "0", 8)
        if name.endswith(f"msmarco_passage_{shard:02d}.gz"):
            return offset + 512, size
        offset += 512 + ((size + 511) // 512) * 512


def main():
    pshard, dshard, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    start, size = member(pshard)
    print(f"passage shard {pshard}: {size} bytes at {start}", flush=True)
    prefix = f"msmarco_doc_{dshard:02d}_"
    resp = request(start, start + size - 1)
    inflate = zlib.decompressobj(31)
    buf, total, kept, first, last = b"", 0, 0, None, None
    with open(out, "w") as f:
        def handle(line):
            nonlocal total, kept, first, last
            total += 1
            doc = json.loads(line)
            if first is None:
                first = doc["docid"]
            last = doc["docid"]
            if doc["docid"].startswith(prefix):
                f.write(f"{doc['pid']}\t{doc['docid']}\n")
                kept += 1
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            buf += inflate.decompress(chunk)
            *lines, buf = buf.split(b"\n")
            for line in lines:
                handle(line)
        if buf:
            handle(buf)
    print(f"passages {total}, of documents {prefix}*: {kept}, first doc {first}, last doc {last}", flush=True)


if __name__ == "__main__":
    main()
