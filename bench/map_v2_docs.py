"""Reads one shard of the MS MARCO v2 document collection straight from the public tar and writes
(docid, url) for every document, so v2 document ids (used by the TREC DL document qrels) can be matched to
the v2.1 segments in the benchmark corpus by URL. The ids of the two versions are not the same numbers.

Only the member for the requested shard is fetched (HTTP range request), decompressed on the fly.
usage: map_v2_docs.py SHARD OUTPUT.tsv
"""
import json
import re
import sys
import urllib.request
import zlib

URL = "https://msmarco.z22.web.core.windows.net/msmarcoranking/msmarco_v2_doc.tar"


def request(start, end):
    return urllib.request.urlopen(urllib.request.Request(URL, headers={"Range": f"bytes={start}-{end}"}), timeout=120)


def member(shard):
    offset = 0
    while True:
        header = request(offset, offset + 511).read()
        name = header[:100].rstrip(b"\0").decode()
        size = int(header[124:135].decode().strip("\0 ") or "0", 8)
        if name.endswith(f"msmarco_doc_{shard:02d}.gz"):
            return offset + 512, size
        offset += 512 + ((size + 511) // 512) * 512


def main():
    shard, out = int(sys.argv[1]), sys.argv[2]
    start, size = member(shard)
    print(f"shard {shard}: {size} bytes at {start}", flush=True)
    resp = request(start, start + size - 1)
    inflate = zlib.decompressobj(31)
    buf, pos, n = b"", 0, 0
    with open(out, "w") as f:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            buf += inflate.decompress(chunk)
            *lines, buf = buf.split(b"\n")
            for line in lines:
                doc = json.loads(line)
                f.write(f"{doc['docid']}\t{doc['url']}\t{pos}\n")
                pos += len(line) + 1
                n += 1
        if buf:
            doc = json.loads(buf)
            f.write(f"{doc['docid']}\t{doc['url']}\t{pos}\n")
            n += 1
    print(f"docs {n}", flush=True)


if __name__ == "__main__":
    main()
