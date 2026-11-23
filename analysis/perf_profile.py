#!/usr/bin/env python3
"""Turn `perf record` profiles of the server processes into shares of CPU time per category.

perf cannot read the binaries inside an Apptainer image, so function names come out as hex
addresses. The images are unpacked once (`apptainer build --sandbox`) and given to
`perf report --symfs`. pgvector's `vector.so` has a symbol table and `postgres` exports its
dynamic symbols, so most names resolve; static functions of the stripped `postgres` binary stay
hex and are counted as "unresolved". Qdrant is a stripped Rust binary with its symbol table kept.

The categories are a classification of function names. Inlining moves work between
categories, so a share is the share of samples whose top frame is in that category, not an
exact cost of the operation.

usage (on the cluster login node, where perf is installed):
  perf_profile.py ROOT --symfs-pg SANDBOX_PG --symfs-qdrant SANDBOX_QDRANT --output ROOT/perf_profiles.json
"""

from __future__ import annotations

import argparse
import bisect
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CATEGORIES = ("distance", "graph_and_element_access", "queues_and_visited", "buffer_manager",
              "request_path", "other", "unresolved")

ROW = re.compile(r"^\s*(?P<pct>\d+\.\d+)%\s+(?P<dso>\S+)\s+\[[.k]\]\s+(?P<sym>\S+)")
SAMPLES = re.compile(r"^# Samples:\s+(?P<n>[\d.]+)(?P<unit>[KMG]?)\s+of event '(?P<event>[^']+)'")
UNITS = {"": 1, "K": 1000, "M": 1_000_000, "G": 1_000_000_000}


def parse_report(text: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows, meta = [], {}
    for line in text.splitlines():
        header = SAMPLES.match(line)
        if header:
            meta["samples"] = int(round(float(header["n"]) * UNITS[header["unit"]]))
            meta["event"] = header["event"]
            continue
        match = ROW.match(line)
        if match:
            rows.append({"percent": float(match["pct"]), "dso": match["dso"], "symbol": match["sym"]})
    return rows, meta


PG_DISTANCE = re.compile(r"(InnerProduct|inner_product|Cosine|cosine|L2|l2_|Distance|distance|Similarity|F16c|Avx|Fma)")
PG_BUFFER = re.compile(r"^(LWLock|hash_search|hash_bytes|ReadBuffer|StartReadBuffer|ReleaseBuffer|BufferAlloc|"
                       r"PinBuffer|UnpinBuffer|LockBuffer|Buf|GetPrivateRefCount|ResourceOwner|pgstat_count_io_op|"
                       r"WaitReadBuffers|IncrBuffer|UnlockReleaseBuffer|ConditionalLockBuffer|PrefetchBuffer)")
PG_QUEUE = re.compile(r"^(pairingheap|tidhash|ItemPointerEquals)")
PG_REQUEST = re.compile(r"^(pq_|Exec|Postgres|Process|PortalRun|Bind|Parse|Pg|printtup|SocketBackend|secure_|"
                        r"CheckDeadLock|ReadyForQuery|exec_|MemoryContext|palloc|pfree|AllocSet|GetPortal|"
                        r"index_|ExecIndex|ExecProcNode|standard_Execute|PortalStart)")
QD_DISTANCE = re.compile(r"(dot_similarity|simple_avx|simple_sse|simple_neon|cosine|euclid|manhattan|"
                         r"spaces)")
QD_ACCESS = re.compile(r"(vector_storage|chunked_vectors|raw_scorer|mmap|memmap|score_internal|"
                       r"vector_scorer|quantized)")
QD_QUEUE = re.compile(r"(top_k|TopK|priority_queue|visited|binary_heap|FixedLength|nearest_heap|"
                      r"search_on_level|ScoredPointOffset)")
QD_REQUEST = re.compile(r"(tonic|hyper|h2|tokio|prost|tower|http|collection|segments_searcher|"
                        r"replica_set|parking_lot|crossbeam|futures|rayon|std\d*thread|Condvar|search_in|"
                        r"read_view|query_points|shard|api)")
HEX = re.compile(r"^0x[0-9a-fA-F]+$")


def categorize(engine: str, dso: str, symbol: str) -> str:
    if HEX.match(symbol):
        return "unresolved"
    if engine == "pg":
        if dso.startswith("vector"):
            if PG_QUEUE.match(symbol):
                return "queues_and_visited"
            if PG_DISTANCE.search(symbol) and not symbol.startswith("HnswLoad"):
                return "distance"
            return "graph_and_element_access"
        if dso == "postgres":
            if PG_QUEUE.match(symbol):
                return "queues_and_visited"
            if PG_BUFFER.match(symbol):
                return "buffer_manager"
            if PG_REQUEST.match(symbol):
                return "request_path"
        return "other"
    if dso == "qdrant":
        if QD_DISTANCE.search(symbol) and "raw_scorer" not in symbol:
            return "distance"
        if QD_QUEUE.search(symbol) and "raw_scorer" not in symbol:
            return "queues_and_visited"
        if QD_ACCESS.search(symbol):
            return "graph_and_element_access"
        if "hnsw_index" in symbol or "point_scorer" in symbol or "vector_index" in symbol:
            return "graph_and_element_access"
        if QD_REQUEST.search(symbol):
            return "request_path"
    return "other"


def hex_address(symbol: str) -> int:
    return int(symbol, 16)


def parse_nm(text: str) -> list[tuple[int, str]]:
    """Exported (dynamic) symbols of a binary from `nm -D --defined-only`, sorted by address."""
    out = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 3 and re.fullmatch(r"[0-9a-fA-F]+", parts[0]):
            out.append((int(parts[0], 16), parts[2]))
    return sorted(out)


def nearest_symbol(symbols: list[tuple[int, str]], address: int) -> tuple[str, int] | None:
    """The exported symbol at or before an address and the distance to it. A hint about the
    neighborhood of a static function in the same object file, not an attribution."""
    index = bisect.bisect_right([a for a, _ in symbols], address) - 1
    if index < 0:
        return None
    return symbols[index][1], address - symbols[index][0]


def summarize_profile(engine: str, rows: list[dict[str, Any]], meta: dict[str, Any],
                      hints: list[tuple[int, str]] | None = None) -> dict[str, Any]:
    totals = {name: 0.0 for name in CATEGORIES}
    top: dict[str, list[tuple[float, str]]] = {name: [] for name in CATEGORIES}
    for row in rows:
        name = categorize(engine, row["dso"], row["symbol"])
        totals[name] += row["percent"]
        top[name].append((row["percent"], f"{row['dso']}:{row['symbol'][:90]}"))
    listed = sum(totals.values())
    return {
        "engine": engine, "samples": meta.get("samples"), "event": meta.get("event"),
        "listed_percent": round(listed, 6),
        "shares": {name: (totals[name] / listed if listed else 0.0) for name in CATEGORIES},
        "top_symbols": {name: [_top_entry(p, sym, name, hints) for p, sym in sorted(items, reverse=True)[:5]]
                        for name, items in top.items()},
    }


def _top_entry(percent: float, symbol: str, category: str, hints: list[tuple[int, str]] | None) -> dict[str, Any]:
    entry: dict[str, Any] = {"percent": percent, "symbol": symbol}
    if category == "unresolved" and hints:
        address = symbol.rsplit(":", 1)[-1]
        if HEX.match(address):
            near = nearest_symbol(hints, hex_address(address))
            if near:
                entry["hint"] = {"nearest_exported_symbol": near[0], "offset": near[1]}
    return entry


def run_report(data: Path, symfs: Path | None) -> str:
    cmd = ["perf", "report", "-i", str(data), "--stdio", "--sort", "dso,symbol", "-g", "none",
           "--no-children", "--percent-limit", "0"]
    if symfs:
        cmd += ["--symfs", str(symfs)]
    return subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout


def load_hints(symfs: Path | None, relative: str) -> list[tuple[int, str]] | None:
    if not symfs:
        return None
    try:
        out = subprocess.run(["nm", "-D", "--defined-only", str(symfs / relative)], check=True, text=True,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return parse_nm(out)


def profile_tree(root: Path, symfs: dict[str, Path | None]) -> dict[str, Any]:
    pg_hints = load_hints(symfs.get("pg"), "usr/lib/postgresql/17/bin/postgres")
    profiles = []
    for data in sorted(root.glob("**/perfrec_*.data")):
        result_json = data.parent / "result.json"
        engine = json.loads(result_json.read_text())["engine"] if result_json.exists() else (
            "pg" if "pg" in data.parent.name else "qdrant")
        rows, meta = parse_report(run_report(data, symfs.get(engine)))
        profile = summarize_profile(engine, rows, meta, pg_hints if engine == "pg" else None)
        profile["file"] = str(data.relative_to(root))
        profiles.append(profile)
    return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "root": str(root),
            "symfs": {key: str(value) if value else None for key, value in symfs.items()}, "profiles": profiles}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--symfs-pg", type=Path)
    parser.add_argument("--symfs-qdrant", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = profile_tree(args.root, {"pg": args.symfs_pg, "qdrant": args.symfs_qdrant})
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"profiles={len(report['profiles'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
