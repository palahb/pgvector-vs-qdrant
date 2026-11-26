#!/usr/bin/env python3
"""Print the LaTeX table of the code commit, Slurm jobs and nodes that produced each experiment of the paper, from the manifests and the
task records of the registry. Nothing is typed by hand.

usage: commits_table.py ARTIFACTS_DIR > table.tex
"""
import glob
import json
import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
artifacts = Path(sys.argv[1])
ROWS = [("E6", "e6_full_9050d65"), ("E8", "e8_full_fe88da1"), ("E9", "e9_full_31de7f4"), ("E10", "e10_full_0b0b905"),
        ("E17", "e17_full_a5bb141"), ("E18", "e18_full_7d1b1c4"), ("E19", "e19_full_518a444"), ("E20", "e20_full_77f7567"),
        ("E21", "e21_full_2516ade"), ("E22", "e22_full_6e94ecd"), ("E23", "e23_full_5276f14")]


def jobs_of(manifest):
    jobs = manifest.get("slurm_jobs", {})
    for key in ("full", "full_array"):
        if key in jobs:
            return str(jobs[key])
    return "/".join(str(v) for v in jobs.values() if v)


def audit_of(manifest):
    audit = manifest.get("result_audit", {})
    audit = audit.get("clean_set", audit)
    return audit.get("result_files"), audit.get("errors"), audit.get("warnings")


lines = []
for name, stem in ROWS:
    m = json.load(open(repo / "data-manifests" / f"{stem}.json"))
    root = (repo / m["workspace_root"]).resolve() if not Path(m["workspace_root"]).is_absolute() else Path(m["workspace_root"])
    exp_dir = artifacts / "truba-experiments" / name / m["code_commit"][:7]
    tasks = [json.load(open(f)) for f in glob.glob(str(exp_dir / "registry-full" / "**" / "task_*.json"), recursive=True)]
    nodes = {t["node"] for t in tasks if t.get("node")}
    files, errors, warnings = audit_of(m)
    lines.append(f"    {name} & \\texttt{{{m['code_commit'][:7]}}} & {jobs_of(m)} & {len(tasks)} & {len(nodes)} & "
                 f"{files} / {errors} / {warnings} \\\\")
print(r"""\begin{table}[t]
  \caption{The code commit, Slurm job (array) and number of tasks and distinct nodes behind each experiment of the main text, and the strict
  audit of its raw results (files / errors / warnings). The records of E1--E5 predate the provenance system and have none of these fields.
  Every manifest is in \texttt{data-manifests/}.}
  \label{tab:commits}
  \small
  \begin{tabular}{@{}llrrrr@{}}
    \toprule
    Exp. & commit & job(s) & tasks & nodes & audit \\
    \midrule""")
print("\n".join(lines))
print(r"""    \bottomrule
  \end{tabular}
\end{table}""")
