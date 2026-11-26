# Tags, and what the paper is regenerated from (26 November 2026)

The results of the paper were produced by **different commits of the harness**, one per experiment (table `tab:commits` in the paper, the
`code_commit` of every manifest). Re-running everything with a single commit would take days of queue time and would not change a number, so the paper makes a
different promise, in two parts:

1. **Every raw result keeps the commit that produced it.** The commit is in the result file (`code_commit`, `code_dirty = false`) and in the manifest
   of the experiment. The harness at that commit is the harness that measured.
2. **Every table and figure is regenerated from the raw results by one set of analysis tools**, the one at the tag `analysis-v1`. The command
   `make verify-paper` does it and compares with the tracked files (`results/derived/`), so a reader needs only the raw results and this repository.

## Tags

| Tag | Commit | Meaning |
|---|---|---|
| `harness-v1` | `6e94ecd` | The last commit that changed what the harness does (`bench/`): the one that produced E22. Later commits under `bench/` only add the read-only `storage_check.sbatch`. The harness commits of E6-E21 and E23 are ancestors of it. |
| `analysis-v1` | `2837c28` | The commit at which `make verify-paper` first passed (28 steps): analysis tools, generators of paper sections, registry (`docs/PAPER_VERIFY.json`) and tracked analysis files agree with the raw results. Superseded by `analysis-v2`; kept. |
| `analysis-v2` | `d39f64f` | `analysis-v1` plus the checks of the headline numbers (`docs/PAPER_CLAIMS.json`) and of the table cells (`analysis/check_tables.py`); passes 30 steps. The one the paper cites. |

If an analysis tool, a generator or a tracked analysis file changes after `analysis-v2`, the tag is not moved: a new tag `analysis-v3` is made and the change is
recorded here. The paper text may change after the tag (G9 rewrites it), because `verify-paper` checks the generated sections and the structure of whatever text is in
`paper/main.tex`, not the prose.

## What `make verify-paper` checks, and what it does not

Checks: (from `analysis-v2`) the 27 headline numbers of the abstract, discussion and conclusion are recomputed from the analysis files (`docs/PAPER_CLAIMS.json`) and the cells of the nine hand-typed result tables (`analysis/check_tables.py`: E1, E5, E4, E6, E8, E9, E10, E18, E20) equal the values recomputed from the analysis files (E1, E4 and E5 from the archived baseline through `bench/paper_numbers.py`); the 18 tracked analysis files are regenerated from the raw results and equal the tracked ones (floats to a relative 1e-9, ignoring timestamp and root path); the
six sections and tables written by generators (`scripts/*_section.py`, `scripts/commits_table.py`) are in `paper/main.tex` verbatim; environments, labels and references of the
paper are consistent and there is no open `\todo`; every table and figure of the paper is bound to an experiment, a manifest and an analysis file that exist
(`docs/PAPER_VERIFY.json`), and each manifest's commit is an ancestor of the checkout; the unit tests pass.

Not checked: the numbers typed into the prose of the sections that have no generator and are not among the headline claims (the discussion of E6, E8-E10, E17, E18, E20 and the earlier sections), and the cells of `tab:laptop`, of the 4 GB row of `tab:caps` and the descriptive tables. They were copied from the analysis
summaries by hand, and the analysis files they come from are checked, not the copying. The first run of the table check found three values that had been copied from a rounded display instead of the stored number (2.01 for 2.00, 571 for 570, 3.94 for 3.93) and a ratio computed from rounded cells (2.4 for 2.3); they were corrected, which is what this check is for. E1-E5 (archived before the provenance system) are bound through
`data-manifests/baseline_2026-11-14.json`, `results/derived/paper_source_index.json` and the figure reproduction, which check files and figures, not provenance of seeds and commits.
The E22 run-1 analysis is regenerated with the analysis tools of commit `936736e`, the ones that produced it, because the later tool implements the second protocol.

## Use

```
make verify-paper            # raw results in ../artifacts, report in results/derived/verify_paper_<tag or commit>.json
make verify-paper ARTIFACTS=/path/to/artifacts
```
The raw results are not in git (about 3 GB); the manifests give their checksums (`artifact_tree`). The command needs a clean worktree for an `ok` verdict.
