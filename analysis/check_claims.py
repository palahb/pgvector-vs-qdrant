#!/usr/bin/env python3
"""Recompute the headline numbers of the paper from the tracked analysis files.

docs/PAPER_CLAIMS.json lists claims: a fragment of text that must be in paper/main.tex, and an expression over the analysis files that must be true.
The expressions use the helpers of `Lookup`; a missing value raises, so a claim cannot pass on a default. The abstract, the highlights, the discussion and the
conclusion are covered this way; the numbers of the other sections are checked by the generators (verbatim) and by audit_numbers.py (a screening).
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]


class Lookup:
    def __init__(self, repo: Path, artifacts: Path):
        self.repo, self.artifacts = repo, artifacts
        self._cache: dict[str, Any] = {}

    def j(self, name: str) -> Any:
        if name not in self._cache:
            self._cache[name] = json.loads((self.repo / "results" / "derived" / name).read_text())
        return self._cache[name]

    # E6: matched-recall latency and CPU
    def e6(self, n, engine, seg, thr, target, metric):
        for a in self.j("e6_full_9050d65_analysis.json")["matched_recall_aggregates"]:
            if (a["engine"], a["n"], str(a["segments"]), str(a["search_threads"]), a["recall_target"]) == (engine, n, seg, thr, target):
                return a["metrics"][metric]["mean"]
        raise KeyError(("e6", n, engine, seg, thr, target, metric))

    def e6ratio(self, n, seg, thr, target, metric):
        return self.e6(n, "pg", "one_graph", "n/a", target, metric) / self.e6(n, "qdrant", seg, thr, target, metric)

    # E19: causal decomposition
    def e19(self, engine, arm, metric):
        for a in self.j("e19_full_518a444_analysis.json")["aggregates"]:
            if (a["engine"], a["arm"], a["metric"]) == (engine, arm, metric):
                return a["stats"]["mean"]
        raise KeyError(("e19", engine, arm, metric))

    def e19cmp(self, arm, metric):
        for c in self.j("e19_full_518a444_analysis.json")["comparisons"]:
            if (c["arm"], c["metric"]) == (arm, metric):
                return c["ratio_of_means"]
        raise KeyError(("e19cmp", arm, metric))

    # E20: quantization (paired comparisons with the float arm)
    def e20c(self, engine, arm, metric, field="mean"):
        for c in self.j("e20_full_77f7567_analysis.json")["comparisons"]:
            if (c["engine"], c["arm"], c["metric"]) == (engine, arm, metric):
                return c["stats"][{"mean": "mean", "lo": "ci95_low", "hi": "ci95_high"}[field]]
        raise KeyError(("e20c", engine, arm, metric))

    def e20a(self, engine, arm, metric):
        for a in self.j("e20_full_77f7567_analysis.json")["aggregates"]:
            if (a["engine"], a["arm"], a["metric"]) == (engine, arm, metric):
                return a["stats"]["mean"]
        raise KeyError(("e20a", engine, arm, metric))

    def e20builds(self, engine, arm, key):
        """Per-build values of a build field (bytes) from the raw results, in GiB."""
        out = []
        for f in glob.glob(str(self.artifacts / "truba-experiments/E20/77f7567/full/**/result.json"), recursive=True):
            r = json.load(open(f))
            if r["engine"] == engine and r["args"]["tag"].endswith("_" + arm):
                out.append(r["build"][key] / 2**30)
        if not out:
            raise KeyError(("e20builds", engine, arm, key))
        return out

    # E21: pooler
    def e21(self, base, mode, role, clients, metric, field="mean"):
        for c in self.j("e21_full_2516ade_analysis.json")["comparisons"]:
            if (c["baseline"], c["mode"], c["ef_role"], c["clients"], c["metric"]) == (base, mode, role, clients, metric):
                return c["stats"][{"mean": "mean", "lo": "ci95_low", "hi": "ci95_high"}[field]]
        raise KeyError(("e21", base, mode, role, clients, metric))

    # E22: open loop
    def e22(self, engine, fraction, metric):
        for a in self.j("e22_full_6e94ecd_analysis.json")["aggregates"]:
            if (a["engine"], a["load_fraction"], a["metric"]) == (engine, fraction, metric):
                return a["stats"]["mean"]
        raise KeyError(("e22", engine, fraction, metric))

    # E23: ranking quality at the matched point
    def e23(self, engine, key):
        return self.j("e23_full_5276f14_analysis.json")["matched"][engine][key]

    # E9: build times
    def e9(self, n, arm, metric):
        for a in self.j("e9_full_31de7f4_analysis.json")["aggregates"]:
            if (a["n"], a["arm"], a["metric"]) == (n, arm, metric):
                return a["stats"]["mean"]
        raise KeyError(("e9", n, arm, metric))

    # M7
    def m7(self, engine, arm, clients, metric):
        for a in self.j("m7_e20_77f7567_analysis.json")["aggregates"]:
            if (a["engine"], a["arm"], a["clients"], a["metric"]) == (engine, arm, clients, metric):
                return a["stats"]["mean"]
        raise KeyError(("m7", engine, arm, clients, metric))

    # E23 gate
    def gate(self, key):
        return self.j("e23_gate.json")["total"][key]


def run_claims(claims: list[dict[str, Any]], tex: str, lookup: Lookup) -> list[dict[str, Any]]:
    names = {n: getattr(lookup, n) for n in dir(lookup) if not n.startswith("_") and callable(getattr(lookup, n))}
    out = []
    flat = " ".join(tex.split())
    for claim in claims:
        row = {"id": claim["id"], "where": claim["where"]}
        if " ".join(claim["tex"].split()) not in flat:
            out.append({**row, "status": "fail", "problem": "text not in paper"})
            continue
        try:
            ok = bool(eval(claim["check"], {"__builtins__": {"round": round, "abs": abs, "min": min, "max": max, "all": all, "any": any, "sum": sum, "len": len}}, names))
        except Exception as exc:  # a missing value or a bad expression must fail, not pass
            out.append({**row, "status": "fail", "problem": f"{type(exc).__name__}: {exc}"})
            continue
        out.append({**row, "status": "ok" if ok else "fail", "problem": None if ok else "the data do not support the claim"})
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims", type=Path, default=REPO / "docs" / "PAPER_CLAIMS.json")
    parser.add_argument("--artifacts", type=Path, default=REPO.parent / "artifacts")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    claims = json.loads(args.claims.read_text())["claims"]
    results = run_claims(claims, (REPO / "paper" / "main.tex").read_text(), Lookup(REPO, args.artifacts))
    failed = [r for r in results if r["status"] != "ok"]
    for r in results:
        print(f"  {r['status']:4s} {r['id']:28s} {r['where']:12s} {r.get('problem') or ''}")
    if args.output:
        args.output.write_text(json.dumps({"claims": len(results), "failed": len(failed), "results": results}, indent=1) + "\n")
    print(f"CLAIMS {len(results) - len(failed)}/{len(results)} ok")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
