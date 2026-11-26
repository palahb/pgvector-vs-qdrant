#!/usr/bin/env python3
"""Check the numbers in the cells of the result tables of paper/main.tex against the analysis files.

For tables that are typed by hand (not written by a generator), the expected rows are recomputed here from the tracked analysis files, in the paper's
format, and compared cell by cell with the rows of the table. E1-E5 tables are compared with the rows printed by bench/paper_numbers.py from the archived
baseline. A cell that differs is reported with both values.
"""

from __future__ import annotations

import argparse
import json
from decimal import ROUND_HALF_UP, Decimal
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]


def rnd(x: float, digits: int) -> str:
    """Round half up on the decimal value as stored (six decimals), the convention of the paper's typed tables."""
    q = Decimal(1).scaleb(-digits)
    return str(Decimal(repr(round(x, 6))).quantize(q, rounding=ROUND_HALF_UP))


def fmt_pm(mean: float, sd: float, digits: int) -> str:
    return f"{rnd(mean, digits)} $\\pm$ {rnd(sd, digits)}"


def _cells(row: str) -> list[str]:
    row = re.sub(r"\\\\\s*(\[.*?\])?\s*$", "", row.strip())
    return [" ".join(c.replace("\\,", " ").split()) for c in row.split("&")]


def table_rows(tex: str, label: str) -> list[list[str]]:
    i = tex.index("\\label{%s}" % label)
    start = max(tex.rfind("\\begin{table*}", 0, i), tex.rfind("\\begin{table}", 0, i))
    end = min(x for x in (tex.find("\\end{table*}", i), tex.find("\\end{table}", i)) if x >= 0)
    body = tex[start:end]
    body = body[body.index("\\begin{tabular}"):]
    rows, buf = [], ""
    for line in body.splitlines():
        line = re.sub(r"(?<!\\)%.*$", "", line).strip()
        if not line or line.startswith(("\\begin{tabular}", "\\toprule", "\\midrule", "\\bottomrule", "\\end{tabular}", "\\addlinespace")):
            continue
        buf += " " + line
        if line.endswith("\\\\"):
            rows.append(_cells(buf))
            buf = ""
    return rows


def _norm(cell: str) -> str:
    return cell.replace(" ", "")


def compare_rows(expected: list[list[str]], found: list[list[str]], subsequence: bool = False) -> list[str]:
    out = []
    if len(found) < len(expected):
        out.append(f"the table has {len(found)} data rows, {len(expected)} expected")
    for k, exp in enumerate(expected[: len(found)]):
        got = found[k]
        if subsequence:
            it = iter(_norm(c) for c in got)
            if not all(any(_norm(e) == c for c in it) for e in exp):
                out.append(f"row {k}: expected cells {exp} are not a subsequence of {got}")
        elif [_norm(c) for c in exp] != [_norm(c) for c in got]:
            out.append(f"row {k}: expected {exp}, paper has {got}")
    return out


class Data:
    def __init__(self, repo: Path):
        self.repo = repo
        self._c: dict[str, Any] = {}

    def j(self, name: str) -> Any:
        if name not in self._c:
            self._c[name] = json.loads((self.repo / "results" / "derived" / name).read_text())
        return self._c[name]


def expected_hnsw(d: Data) -> list[list[str]]:
    g = {(a["engine"], a["n"], a["m"], a["efc"], a["metric"]): a["stats"] for a in d.j("e8_full_fe88da1_analysis.json")["aggregates"]}
    rows = []
    for m, efc in [(16, 64), (16, 128), (16, 256), (32, 64), (32, 128), (32, 256), (64, 128), (64, 256)]:
        pl, pc = g[("pg", 500000, m, efc, "mean_ms@0.95")], g[("pg", 500000, m, efc, "server_cpu_ms_per_query@0.95")]
        ql, qc = g[("qdrant", 500000, m, efc, "mean_ms@0.95")], g[("qdrant", 500000, m, efc, "server_cpu_ms_per_query@0.95")]
        rows.append([str(m), str(efc), fmt_pm(pl["mean"], pl["sd"], 2), rnd(pc['mean'], 2), fmt_pm(ql["mean"], ql["sd"], 2),
                     rnd(qc['mean'], 2), rnd(pl['mean'] / ql['mean'], 1), rnd(pc['mean'] / qc['mean'], 1)])
    return rows


def expected_ingest(d: Data) -> list[list[str]]:
    g = {(a["n"], a["arm"], a["metric"]): a["stats"] for a in d.j("e9_full_31de7f4_analysis.json")["aggregates"]}
    names = [("pg_logged", "pgvector, logged"), ("pg_unlogged", "pgvector, unlogged"), ("q_base", "Qdrant, baseline"),
             ("q_batch4096", "Qdrant, batch 4096"), ("q_par4", "Qdrant, 4 streams"), ("q_tuned", "Qdrant, tuned")]
    rows = []
    for n, label in ((500000, "500K"), (1000000, "1M")):
        for k, (arm, name) in enumerate(names):
            pg = arm.startswith("pg")
            ing, idx = ("load_s", "index_s") if pg else ("upload_s", "index_wait_s")
            cells = [label if k == 0 else "", name, fmt_pm(g[(n, arm, ing)]["mean"], g[(n, arm, ing)]["sd"], 1),
                     fmt_pm(g[(n, arm, idx)]["mean"], g[(n, arm, idx)]["sd"], 1),
                     fmt_pm(g[(n, arm, "total_s")]["mean"], g[(n, arm, "total_s")]["sd"], 1)]
            if pg:
                wal = g[(n, arm, "wal_mb_copy")]["mean"] + g[(n, arm, "wal_mb_index")]["mean"]
                cells += [rnd(wal, 0), rnd(g[(n, arm, 'io_write_mb')]['mean'], 0)]
            else:
                cells += ["--", "--"]
            rows.append(cells)
    return rows


def expected_perquery(d: Data) -> list[list[str]]:
    g = {(a["engine"], a["dim"], a["metric"]): a["stats"]["mean"] for a in d.j("e18_full_7d1b1c4_analysis.json")["aggregates"]}
    rows = []
    for engine, name in (("pg", "pgvector"), ("qdrant", "Qdrant")):
        for dim in (128, 768, 1024):
            rows.append([name, str(dim), rnd(g[(engine, dim, 'ef_at_target')], 0), rnd(100 * g[(engine, dim, 'share_perfect')], 1),
                         rnd(100 * g[(engine, dim, 'share_below_0_8')], 1), rnd(100 * g[(engine, dim, 'share_at_most_0_5')], 1),
                         rnd(g[(engine, dim, 'p01')], 2)])
    return rows


def _lat(x: float) -> str:
    return rnd(x, 2) if x < 10 else (rnd(x, 1) if x < 100 else rnd(x, 0))


def expected_caps(d: Data) -> list[list[str]]:
    g = {(a["system"], a["limit"], a["phase"], a["metric"]): a["stats"]["mean"] for a in d.j("e10_full_0b0b905_analysis.json")["aggregates"]}
    rows = []
    for limit, label in (("none", "none"), ("16G", "16 GB"), ("8G", "8 GB")):
        cells = [label]
        for system in ("pg_sb1G", "pg_sbq", "qdrant_mmap"):
            cells += [rnd(g[(system, limit, 'cold', 'mean_ms')], 0), _lat(g[(system, limit, "steady_last", "mean_ms")])]
        rows.append(cells)
    return rows


def expected_cpu(d: Data) -> list[list[str]]:
    a = d.j("e6_full_9050d65_analysis.json")["matched_recall_aggregates"]

    def val(n, engine, seg, thr, metric):
        for x in a:
            if (x["n"], x["engine"], str(x["segments"]), str(x["search_threads"]), x["recall_target"]) == (n, engine, seg, thr, 0.95):
                return x["metrics"][metric]["mean"]
        raise KeyError((n, engine, seg, thr, metric))
    rows = []
    cfgs = [("Qdrant, 1 seg., auto", "1", "auto"), ("Qdrant, 4 seg., auto", "4", "auto"), ("Qdrant, 4 seg., 1 thr.", "4", "1"),
            ("Qdrant, 8 seg., auto", "8", "auto")]
    for n, label in ((500000, "500K"), (1000000, "1M")):
        pl, pc = val(n, "pg", "one_graph", "n/a", "mean_ms"), val(n, "pg", "one_graph", "n/a", "server_cpu_ms_per_query")
        rows.append([label, "pgvector", rnd(pl, 2), rnd(pc, 2), "---", "---"])
        for name, seg, thr in cfgs:
            ql, qc = val(n, "qdrant", seg, thr, "mean_ms"), val(n, "qdrant", seg, thr, "server_cpu_ms_per_query")
            rows.append(["", name, rnd(ql, 2), rnd(qc, 2), rnd(pl / ql, 1), rnd(pc / qc, 1)])
    return rows


def expected_quant(d: Data, artifacts: Path) -> list[list[str]]:
    import glob
    a = {(x["engine"], x["arm"], x["metric"]): x["stats"] for x in d.j("e20_full_77f7567_analysis.json")["aggregates"]}
    gib = 2**30

    def storage(engine, arm):
        v = []
        for f in glob.glob(str(artifacts / "truba-experiments/E20/77f7567/full/**/result.json"), recursive=True):
            r = json.load(open(f))
            if r["engine"] == engine and r["args"]["tag"].endswith("_" + arm):
                v.append(r["build"]["storage_bytes"] / gib)
        return v
    rows = []
    for engine, arm, label in (("pg", "vector", "pgvector \\texttt{vector}"), ("pg", "halfvec", "pgvector \\texttt{halfvec}")):
        rows.append([label, rnd(a[(engine, arm, 'index_bytes')]['mean'] / gib, 2), rnd(a[(engine, arm, 'table_total_bytes')]['mean'] / gib, 2),
                     fmt_pm(a[(engine, arm, "build_total_s")]["mean"], a[(engine, arm, "build_total_s")]["sd"], 0),
                     fmt_pm(a[(engine, arm, "mean_ms@0.95")]["mean"], a[(engine, arm, "mean_ms@0.95")]["sd"], 2),
                     rnd(a[(engine, arm, 'server_cpu_ms_per_query@0.95')]['mean'], 2)])
    for arm, label in (("f32", "Qdrant float32"), ("int8", "Qdrant \\texttt{int8}")):
        v = storage("qdrant", arm)
        rows.append([label, f"\\multicolumn{{2}}{{c}}{{{rnd(min(v), 2)}--{rnd(max(v), 2)}}}",
                     fmt_pm(a[("qdrant", arm, "build_total_s")]["mean"], a[("qdrant", arm, "build_total_s")]["sd"], 0),
                     fmt_pm(a[("qdrant", arm, "mean_ms@0.95")]["mean"], a[("qdrant", arm, "mean_ms@0.95")]["sd"], 2),
                     rnd(a[('qdrant', arm, 'server_cpu_ms_per_query@0.95')]['mean'], 2)])
    return rows


def baseline_rows(artifacts: Path) -> dict[str, list[list[str]]]:
    results = artifacts / "remote-archives/2026-11-14_baseline/extracted/results"
    out = subprocess.run([sys.executable, str(REPO / "bench" / "paper_numbers.py"), str(results)], capture_output=True, text=True, cwd=REPO).stdout
    groups: dict[str, list[list[str]]] = {}
    current = None
    for line in out.splitlines():
        if line.startswith("% ---- E1: matched recall"):
            current = "tab:matched"
        elif line.startswith("% ---- E5:"):
            current = "tab:build"
        elif line.startswith("% ---- E4a"):
            current = "tab:sb"
        elif line.startswith("% ----"):
            current = None
        elif current and "\\\\" in line.split("%")[0]:
            groups.setdefault(current, []).append(_cells(line.split("%")[0]))
    return groups


def run_checks(tex: str, repo: Path, artifacts: Path) -> list[dict[str, Any]]:
    d = Data(repo)
    checks = [("tab:hnsw", expected_hnsw(d), False), ("tab:ingest", expected_ingest(d), False), ("tab:perquery", expected_perquery(d), False),
              ("tab:caps", expected_caps(d), False), ("tab:cpu", expected_cpu(d), False), ("tab:quant", expected_quant(d, artifacts), False)]
    for label, rows in baseline_rows(artifacts).items():
        checks.append((label, rows, label != "tab:matched"))
    results = []
    for label, expected, subseq in checks:
        found = table_rows(tex, label)
        # data rows are the last rows of the table; header rows come first
        data = found[-len(expected):] if label != "tab:caps" else [r for r in found if r and r[0] in ("none", "16 GB", "8 GB")]
        diffs = compare_rows(expected, data, subseq)
        results.append({"id": label, "status": "ok" if not diffs else "fail", "rows": len(expected), "differences": diffs[:6]})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, default=REPO.parent / "artifacts")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    results = run_checks((REPO / "paper" / "main.tex").read_text(), REPO, args.artifacts)
    for r in results:
        print(f"  {r['status']:4s} {r['id']:14s} rows={r['rows']} {r['differences'][:2] if r['differences'] else ''}")
    if args.output:
        args.output.write_text(json.dumps(results, indent=1) + "\n")
    failed = [r for r in results if r["status"] != "ok"]
    print(f"TABLES {len(results) - len(failed)}/{len(results)} ok")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
