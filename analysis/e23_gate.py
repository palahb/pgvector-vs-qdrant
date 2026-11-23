#!/usr/bin/env python3
"""E23 gate: how many TREC DL relevance judgments fall inside the 1M-passage benchmark corpus?

The rule is in docs/E23_GATE.md and was fixed before any of this was measured. Judgments are
read at document level (relevance grade 2 or 3 counts as relevant). A v2.1 segment id
"msmarco_v2.1_doc_XX_N#S_Z" belongs to the v2 document "msmarco_doc_XX_N", which is the id used by
the TREC document qrels.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RELEVANT_GRADE = 2
MIN_COVERAGE = 0.50
MIN_QUERIES = 50
SEGMENT = re.compile(r"^msmarco_v2\.1_doc_(?P<doc>\d+_\d+)#")


def doc_of_segment(identifier: str) -> str:
    match = SEGMENT.match(identifier)
    return f"msmarco_doc_{match['doc']}" if match else identifier


def segment_v2_docs(segment_lines: list[str], v2_lines: list[str]) -> list[str | None]:
    """The v2 document id of every stream segment, matched by URL. The numbers inside the v2 and v2.1
    ids are byte offsets in different files, so the ids themselves cannot be compared. A url carried by two v2
    documents is ambiguous and maps to None."""
    by_url: dict[str, list[str]] = defaultdict(list)
    for line in v2_lines:
        doc, url = line.split("\t")[:2]
        by_url[url].append(doc)
    out: list[str | None] = []
    for line in segment_lines:
        url = line.rstrip("\n").split("\t", 1)[1]
        docs = by_url.get(url, [])
        out.append(docs[0] if len(docs) == 1 else None)
    return out


def passages_to_documents(qrels: dict[str, dict[str, int]], passage_doc: dict[str, str]) -> dict[str, dict[str, int]]:
    """Passage-level judgments as document-level ones (best grade per document). A passage whose document is
    unknown stays a document of its own: it still counts as a relevant item of the query, and it cannot lie in the
    prefix because the documents of the prefix are all known."""
    out: dict[str, dict[str, int]] = {}
    for query, passages in qrels.items():
        docs: dict[str, int] = {}
        for passage, grade in passages.items():
            doc = passage_doc.get(passage, passage)
            docs[doc] = max(docs.get(doc, 0), grade)
        out[query] = docs
    return out


def prefix_judgments(qrels: dict[str, dict[str, int]], segment_docs: list[str | None],
                     query_index: dict[str, int]) -> dict[str, Any]:
    """For the queries that have a relevant (grade 2 or 3) document in the prefix: the grade of every prefix
    segment of every judged document, by row number of the embeddings file. This is all that nDCG needs."""
    rows_of: dict[str, list[int]] = defaultdict(list)
    for row, doc in enumerate(segment_docs):
        if doc:
            rows_of[doc].append(row)
    out: dict[str, Any] = {}
    for query, docs in qrels.items():
        if query not in query_index:
            continue
        inside = {d: g for d, g in docs.items() if d in rows_of and g >= 1}
        if not any(g >= RELEVANT_GRADE for g in inside.values()):
            continue
        out[query] = {"query_index": query_index[query],
                      "relevant_docs_in_prefix": {d: g for d, g in inside.items() if g >= RELEVANT_GRADE},
                      "segments": {str(r): g for d, g in inside.items() for r in rows_of[d]}}
    return out


def load_qrels(path: Path) -> dict[str, dict[str, int]]:
    """Query id -> document id -> highest grade given."""
    out: dict[str, dict[str, int]] = defaultdict(dict)
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        query, _, doc, grade = parts
        out[query][doc] = max(out[query].get(doc, 0), int(grade))
    return dict(out)


def coverage(qrels: dict[str, dict[str, int]], prefix_docs: set[str], query_ids: set[str]) -> dict[str, Any]:
    q_judged = r_total = r_in = q_cov = 0
    for query, docs in qrels.items():
        if query not in query_ids:
            continue
        relevant = {d for d, g in docs.items() if g >= RELEVANT_GRADE}
        if not relevant:
            continue
        inside = relevant & prefix_docs
        q_judged += 1
        r_total += len(relevant)
        r_in += len(inside)
        q_cov += bool(inside)
    return {"q_judged": q_judged, "r_total": r_total, "r_in": r_in,
            "coverage": r_in / r_total if r_total else 0.0, "q_cov": q_cov}


def decide(c: dict[str, Any]) -> dict[str, Any]:
    if c["q_cov"] >= MIN_QUERIES and c["coverage"] >= MIN_COVERAGE:
        mode = "absolute"
    elif c["q_cov"] >= MIN_QUERIES:
        mode = "sensitivity"
    else:
        mode = "not_measured"
    return {"mode": mode, "min_coverage": MIN_COVERAGE, "min_queries": MIN_QUERIES}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segment-urls", type=Path, required=True,
                        help="stream segment id and url per line, in corpus order (prepare_urls.py)")
    parser.add_argument("--v2-urls", type=Path, action="append", required=True,
                        help="docid, url, offset per line of a v2 document shard (map_v2_docs.py)")
    parser.add_argument("--segment-docs-output", type=Path,
                        help="write the v2 document id of every segment, one per line ('-' when unmapped)")
    parser.add_argument("--queries-meta", type=Path, required=True)
    parser.add_argument("--qrels", action="append", required=True, metavar="YEAR=PATH",
                        help="document-level TREC qrels")
    parser.add_argument("--passage-qrels", action="append", default=[], metavar="YEAR=PATH",
                        help="passage-level TREC qrels, linked to documents with --passage-docs")
    parser.add_argument("--passage-docs", type=Path, action="append", default=[],
                        help="pid and document id per line (map_v2_passages.py)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--judgments-output", type=Path,
                        help="write the grade of every prefix segment of the judged documents (input of analyze_e23)")
    args = parser.parse_args()
    segment_lines = args.segment_urls.read_text().splitlines()
    v2_lines = [line for path in args.v2_urls for line in path.read_text().splitlines()]
    segment_docs = segment_v2_docs(segment_lines, v2_lines)
    prefix_docs = {d for d in segment_docs if d}
    if args.segment_docs_output:
        args.segment_docs_output.write_text("\n".join(d or "-" for d in segment_docs) + "\n")
    meta = json.loads(args.queries_meta.read_text())
    by_year: dict[str, set[str]] = defaultdict(set)
    for query, year in zip(meta["id"], meta["trec_year"]):
        by_year[str(year)].add(str(query))
    report: dict[str, Any] = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
                              "prefix_segments": len(segment_lines), "prefix_documents": len(prefix_docs),
                              "unmapped_segments": sum(d is None for d in segment_docs),
                              "years": {}}
    merged: dict[str, dict[str, int]] = {}
    for spec in args.qrels:
        year, path = spec.split("=", 1)
        qrels = load_qrels(Path(path))
        report["years"][year] = {"qrels_file": Path(path).name, "queries_with_qrels": len(qrels),
                                 **coverage(qrels, prefix_docs, by_year[year])}
        merged.update(qrels)
    if args.passage_qrels:
        passage_doc = dict(line.split("\t") for path in args.passage_docs for line in path.read_text().splitlines())
        for spec in args.passage_qrels:
            year, path = spec.split("=", 1)
            qrels = passages_to_documents(load_qrels(Path(path)), passage_doc)
            report["years"][year] = {"qrels_file": Path(path).name, "level": "passage, linked to documents",
                                     "queries_with_qrels": len(qrels), **coverage(qrels, prefix_docs, by_year[year])}
            merged.update(qrels)
    if args.judgments_output:
        index = {str(q): i for i, q in enumerate(meta["id"])}
        judgments = prefix_judgments(merged, segment_docs, index)
        year_of = {str(q): str(y) for q, y in zip(meta["id"], meta["trec_year"])}
        for query, value in judgments.items():
            value["year"] = year_of[query]
        args.judgments_output.write_text(json.dumps({"schema_version": 1, "queries": judgments}, indent=1) + "\n")
    all_ids = set().union(*by_year.values())
    report["total"] = coverage(merged, prefix_docs, all_ids)
    report["decision"] = decide(report["total"])
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"total": report["total"], "decision": report["decision"]["mode"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
