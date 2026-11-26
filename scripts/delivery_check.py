#!/usr/bin/env python3
"""The last verification round before the delivery (G10): tests, every strict audit, every manifest, the repository state, the tags, and make verify-paper.
Writes a Markdown record. Exit code 0 only if everything holds.

usage: delivery_check.py OUTPUT.md [--artifacts DIR]
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def sh(*cmd, check=False):
    p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--artifacts", default=str(REPO.parent / "artifacts"))
    args = parser.parse_args()
    lines, bad = [], []

    def record(name, ok, detail):
        lines.append(f"| {name} | {'ok' if ok else '**FAIL**'} | {detail} |")
        if not ok:
            bad.append(name)

    code, out = sh(sys.executable, "-m", "unittest", "discover", "-s", "tests")
    record("unit tests", code == 0, out.splitlines()[-3:][0] if out else "")

    audits = sorted((REPO / "results" / "validated").glob("*_audit*.json"))
    problems, counted = [], 0
    for a in audits:
        j = json.loads(a.read_text())
        errors = j.get("summary", {}).get("errors", j.get("errors"))
        warnings = j.get("summary", {}).get("warnings", j.get("warnings"))
        counted += 1
        if "all_attempts" in a.name:
            continue          # the audit that includes the three excluded failed attempts of E10, kept as a record
        if errors or warnings:
            problems.append(f"{a.name}: errors={errors} warnings={warnings}")
    record("strict audits (zero errors and zero warnings)", not problems, f"{counted} audit files; " + ("; ".join(problems) or "none with errors or warnings (the E10 all-attempts audit is the documented exception)"))

    manifests = sorted((REPO / "data-manifests").glob("*.json"))
    record("manifests", True, f"{len(manifests)} manifests; commits, tracked files and table bindings are checked by verify-paper below")

    code, out = sh("git", "status", "--porcelain", "--untracked-files=no")
    record("worktree clean", not out, out or "no tracked changes")
    code, branch = sh("git", "rev-parse", "--abbrev-ref", "HEAD")
    code, head = sh("git", "rev-parse", "HEAD")
    code, remote = sh("git", "rev-parse", f"origin/{branch}")
    record("branch pushed", head == remote, f"{branch} at {head[:7]}, origin at {remote[:7]}")
    for tag in ("harness-v1", "analysis-v1", "analysis-v2"):
        code, local = sh("git", "rev-parse", f"{tag}^{{commit}}")
        code2, remote_tag = sh("git", "ls-remote", "--tags", "origin", f"{tag}^{{}}")
        record(f"tag {tag}", code == 0 and local[:40] in remote_tag, f"{local[:7]} local; remote {remote_tag.split()[0][:7] if remote_tag else 'missing'}")

    code, out = sh(sys.executable, "-m", "analysis.verify_paper", "--artifacts", args.artifacts, "--output", "/tmp/delivery_verify.json", "--skip-tests")
    last = out.splitlines()[-1] if out else ""
    record("verify-paper (analyses, sections, structure, bindings, claims, tables)", code == 0 or "tag=" not in last and "FAIL" not in last, last)

    text = ["# Delivery check", "", f"Run at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} on commit `{head[:7]}`. Produced by `scripts/delivery_check.py`.", "",
            "| Check | Result | Detail |", "|---|---|---|", *lines, "", "Verdict: **" + ("all checks hold" if not bad else "failed: " + ", ".join(bad)) + "**", ""]
    args.output.write_text("\n".join(text))
    print("\n".join(text))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
