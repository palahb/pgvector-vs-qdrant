#!/usr/bin/env python3
"""One command that checks the paper against the raw results (`make verify-paper`).

For a given checkout (normally a tag) it:
  1. regenerates every tracked analysis file from the raw results with the analysis tools of this checkout and compares it with the tracked
     file (ignoring the timestamp and the root path; floats with a relative tolerance);
  2. regenerates every section that is written from analysis files (scripts/*_section.py) and checks that the text is in paper/main.tex verbatim;
  3. checks the structure of paper/main.tex (balanced environments, no undefined reference, no unused label, no open todo);
  4. checks that every table and figure of the paper is bound to a source (docs/PAPER_VERIFY.json: experiment, manifest, analysis file), that the
     files exist, and that the commit that produced each manifest is an ancestor of the checkout;
  5. runs the unit tests (unless --skip-tests).

The registry is docs/PAPER_VERIFY.json. The report is written to --output and the exit code is 0 only if every step passes.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

IGNORED_KEYS = {"generated_at", "root"}
REL_TOL = 1e-9
REPO = Path(__file__).resolve().parents[1]


def compare_json(a: Any, b: Any, path: str = "", ignore: set[str] = IGNORED_KEYS, rel: float = REL_TOL) -> list[str]:
    """Differences between two JSON documents as human-readable lines; empty if they agree."""
    out: list[str] = []
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            if key in ignore:
                continue
            here = f"{path}.{key}" if path else key
            if key not in a:
                out.append(f"{here}: missing in first")
            elif key not in b:
                out.append(f"{here}: missing in second")
            else:
                out += compare_json(a[key], b[key], here, ignore, rel)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} != {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            out += compare_json(x, y, f"{path}[{i}]", ignore, rel)
    elif isinstance(a, bool) or isinstance(b, bool):
        if a is not b:
            out.append(f"{path}: {a!r} != {b!r}")
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if not math.isclose(a, b, rel_tol=rel, abs_tol=1e-12):
            out.append(f"{path}: {a!r} != {b!r}")
    elif a != b:
        out.append(f"{path}: {a!r} != {b!r}")
    return out


def strip_comments(tex: str) -> str:
    return re.sub(r"(?m)(?<!\\)%.*$", "", tex)


def paper_structure(tex: str) -> dict[str, Any]:
    body = strip_comments(tex)
    begins = Counter(re.findall(r"\\begin\{(\w+\*?)\}", body))
    ends = Counter(re.findall(r"\\end\{(\w+\*?)\}", body))
    labels = set(re.findall(r"\\label\{([^}]+)\}", body))
    refs = set(re.findall(r"\\ref\{([^}]+)\}", body))
    return {"env_mismatch": {k: [begins[k], ends[k]] for k in set(begins) | set(ends) if begins[k] != ends[k]},
            "undefined_refs": sorted(refs - labels), "unused_labels": sorted(labels - refs),
            "todo_calls": len(re.findall(r"\\todo\{", body))}


def label_coverage(tex: str, table_sources: dict[str, Any], exempt: set[str]) -> dict[str, Any]:
    labels = {m for m in re.findall(r"\\label\{([^}]+)\}", strip_comments(tex)) if m.startswith(("tab:", "fig:"))}
    return {"uncovered": sorted(labels - set(table_sources) - exempt),
            "stale_entries": sorted(set(table_sources) - labels)}


def expand(value: str, artifacts: Path) -> str:
    """Paths are given relative to the repository, as the tracked files were produced (they record the root they were given)."""
    rel = os.path.relpath(artifacts, REPO) if artifacts.is_absolute() else str(artifacts)
    return value.replace("{repo}", ".").replace("{artifacts}", rel)


def mirror(sources: list[Path], target: Path) -> None:
    """One root made of several: the directories are copied as directories and the files are linked, because the analysis tools
    search with `glob("**/...")`, which does not enter linked directories."""
    for src in sources:
        for current, dirs, files in os.walk(src):
            rel = Path(current).relative_to(src.parent)
            (target / rel).mkdir(parents=True, exist_ok=True)
            for name in files:
                (target / rel / name).symlink_to((Path(current) / name).resolve())


def run(cmd: list[str], env: dict[str, str] | None = None, cwd: Path = REPO) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, env={**os.environ, **(env or {})}, capture_output=True, text=True)


def step_analysis(entry: dict[str, Any], artifacts: Path, repo_head: Path) -> dict[str, Any]:
    tracked = REPO / entry["derived"]
    result: dict[str, Any] = {"id": entry["id"], "kind": "analysis", "derived": entry["derived"]}
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        roots = [Path(expand(r, artifacts)) for r in entry["roots"]]
        missing = [str(r) for r in roots if not r.exists()]
        if missing:
            return {**result, "status": "fail", "problem": "raw results not found", "missing": missing}
        if len(roots) > 1:
            combined = tmp_path / "root"
            combined.mkdir()
            mirror(roots, combined)
            root_arg = [str(combined)]
        else:
            root_arg = [str(roots[0])] if roots else []
        code_root = repo_head
        if entry.get("tool_commit"):
            code_root = tmp_path / "tools"
            code_root.mkdir()
            archive = subprocess.run(["git", "archive", entry["tool_commit"], "analysis"], cwd=REPO, capture_output=True)
            if archive.returncode:
                return {**result, "status": "fail", "problem": f"cannot extract analysis/ at {entry['tool_commit']}"}
            subprocess.run(["tar", "-x", "-C", str(code_root)], input=archive.stdout, check=True)
            result["tool_commit"] = entry["tool_commit"]
        out_json = tmp_path / "out.json"
        cmd = [sys.executable, "-P", "-m", entry["module"], *root_arg, *[expand(a, artifacts) for a in entry.get("args", [])],
               "--output", str(out_json)]
        proc = run(cmd, env={"PYTHONPATH": str(code_root)})
        if not out_json.exists():
            return {**result, "status": "fail", "problem": "tool wrote no output", "stderr": proc.stderr[-600:]}
        diffs = compare_json(json.loads(tracked.read_text()), json.loads(out_json.read_text()),
                             ignore=IGNORED_KEYS | set(entry.get("ignore_keys", [])))
    return {**result, "status": "ok" if not diffs else "fail", "tool_exit": proc.returncode,
            "differences": diffs[:8], "difference_count": len(diffs)}


def step_section(entry: dict[str, Any], tex: str) -> dict[str, Any]:
    proc = run([sys.executable, str(REPO / entry["script"]), *[str(REPO / a) for a in entry["args"]]])
    result = {"id": entry["id"], "kind": "generated section", "script": entry["script"]}
    if proc.returncode:
        return {**result, "status": "fail", "problem": "generator failed", "stderr": proc.stderr[-400:]}
    text = proc.stdout.strip()
    return {**result, "status": "ok" if text and text in tex else "fail",
            "problem": None if text and text in tex else "the generated text is not in paper/main.tex verbatim",
            "characters": len(text)}


def step_manifests(head: str) -> dict[str, Any]:
    problems, checked = [], 0
    for path in sorted((REPO / "data-manifests").glob("*.json")):
        manifest = json.loads(path.read_text())
        commit = manifest.get("code_commit")
        if commit and len(commit) == 40:
            checked += 1
            if run(["git", "cat-file", "-e", f"{commit}^{{commit}}"]).returncode:
                problems.append(f"{path.name}: commit {commit[:7]} not in this repository")
            elif run(["git", "merge-base", "--is-ancestor", commit, head]).returncode:
                problems.append(f"{path.name}: commit {commit[:7]} is not an ancestor of {head[:7]}")
        for key in ("tracked_report", "tracked_json", "tracked_summary"):
            for holder in (manifest.get("result_audit", {}), manifest.get("analysis", {})):
                rel = holder.get(key) if isinstance(holder, dict) else None
                if rel and not (REPO / rel).exists():
                    problems.append(f"{path.name}: {key} {rel} does not exist")
    return {"id": "manifests", "kind": "manifests", "status": "ok" if not problems else "fail", "checked": checked,
            "problems": problems}


def step_table_sources(tex: str, registry: dict[str, Any]) -> dict[str, Any]:
    sources = registry["table_sources"]
    exempt = set(registry.get("exempt_labels", []))
    coverage = label_coverage(tex, sources, exempt)
    problems = []
    for label, entry in sorted(sources.items()):
        for rel in entry.get("manifests", []) + entry.get("analysis", []):
            if not (REPO / rel).exists():
                problems.append(f"{label}: {rel} does not exist")
        if not entry.get("experiment"):
            problems.append(f"{label}: no experiment named")
    ok = not coverage["uncovered"] and not coverage["stale_entries"] and not problems
    return {"id": "table_sources", "kind": "table sources", "status": "ok" if ok else "fail", **coverage,
            "problems": problems, "bound": len(sources), "exempt": sorted(exempt)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=REPO / "docs" / "PAPER_VERIFY.json")
    parser.add_argument("--artifacts", type=Path, default=REPO.parent / "artifacts")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--only", help="run only the analysis entry with this id")
    args = parser.parse_args()
    registry = json.loads(args.registry.read_text())
    tex = (REPO / "paper" / "main.tex").read_text()
    head = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    tag = run(["git", "describe", "--tags", "--exact-match", "HEAD"]).stdout.strip() or None
    dirty = bool(run(["git", "status", "--porcelain", "--untracked-files=no"]).stdout.strip())
    steps: list[dict[str, Any]] = []
    for entry in registry["analyses"]:
        if args.only and entry["id"] != args.only:
            continue
        steps.append(step_analysis(entry, args.artifacts, REPO))
        print(f"  {steps[-1]['status']:4s} analysis {entry['id']}", flush=True)
    if not args.only:
        for entry in registry["sections"]:
            steps.append(step_section(entry, tex))
            print(f"  {steps[-1]['status']:4s} section  {entry['id']}", flush=True)
        structure = paper_structure(tex)
        bad = structure["env_mismatch"] or structure["undefined_refs"] or structure["unused_labels"] or structure["todo_calls"]
        steps.append({"id": "paper_structure", "kind": "structure", "status": "fail" if bad else "ok", **structure})
        steps.append(step_manifests(head))
        steps.append(step_table_sources(tex, registry))
        for s in steps[-3:]:
            print(f"  {s['status']:4s} {s['id']}", flush=True)
        if not args.skip_tests:
            proc = run([sys.executable, "-m", "unittest", "discover", "-s", "tests"])
            tail = proc.stderr.strip().splitlines()[-3:]
            steps.append({"id": "unit_tests", "kind": "tests", "status": "ok" if proc.returncode == 0 else "fail",
                          "summary": tail})
            print(f"  {steps[-1]['status']:4s} unit tests", flush=True)
    failed = [s["id"] for s in steps if s["status"] != "ok"]
    report = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "commit": head, "tag": tag,
              "worktree_dirty": dirty, "verdict": "ok" if not failed and not dirty else "fail", "failed": failed,
              "steps": steps}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"VERIFY_PAPER {report['verdict'].upper()} commit={head[:7]} tag={tag} steps={len(steps)} failed={failed}")
    return 0 if report["verdict"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
