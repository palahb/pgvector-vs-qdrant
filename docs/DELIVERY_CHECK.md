# Delivery check

Run at 2026-11-26 22:07 UTC on commit `f81b148`. Produced by `scripts/delivery_check.py`.

| Check | Result | Detail |
|---|---|---|
| unit tests | ok | Ran 299 tests in 4.588s |
| strict audits (zero errors and zero warnings) | ok | 45 audit files; none with errors or warnings (documented exceptions: the E10 all-attempts audit, and the archived baseline E1-E5, whose warnings are only the provenance fields it predates) |
| manifests | ok | 38 manifests; commits, tracked files and table bindings are checked by verify-paper below |
| worktree clean | ok | no tracked changes |
| branch pushed | ok | paper-full-revision at f81b148, origin at f81b148 |
| tag harness-v1 | ok | 6e94ecd local; remote 6e94ecd |
| tag analysis-v1 | ok | 2837c28 local; remote 2837c28 |
| tag analysis-v2 | ok | d39f64f local; remote d39f64f |
| verify-paper (analyses, sections, structure, bindings, claims, tables) | ok | VERIFY_PAPER OK commit=f81b148 tag=None steps=29 failed=[] |

Verdict: **all checks hold**
