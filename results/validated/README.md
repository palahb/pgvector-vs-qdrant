# Validated result manifests

Validation reports are written here after schema, completeness, provenance and anomaly
checks pass. A file in this directory should refer to immutable raw evidence by checksum.

## Frozen baseline

`baseline_2026-11-14_audit.json` covers all 77 `result.json` files in the transferred
baseline, including four supplemental pilot/probe results. It found zero integrity or
schema errors. Its verdict is `usable_with_provenance_gaps` because all historical files
lack explicit result-schema version, Git commit, stable config ID and seed fields. These
gaps are preserved as findings; the raw files are not rewritten.
