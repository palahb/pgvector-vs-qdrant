# Validated result manifests

Validation reports are written here after schema, completeness, provenance and anomaly
checks pass. A file in this directory should refer to immutable raw evidence by checksum.

## Frozen baseline

`baseline_2026-11-14_audit.json` covers all 77 `result.json` files in the transferred
baseline, including four supplemental pilot/probe results. It found zero integrity or
schema errors. Its verdict is `usable_with_provenance_gaps` because all historical files
lack explicit result-schema version, Git commit, stable config ID and seed fields. These
gaps are preserved as findings; the raw files are not rewritten.

`smoke_6983850_audit.json` is the first schema-v2 result audit. It covers a real
two-engine ARF/Apptainer smoke job at commit `91bb290`, and passes strict validation
with zero errors and zero warnings.

`smoke_6983902_audit.json` validates the completed Phase-3 pipeline at commit
`906d7eb`: both native schema-v2 results contain unique experiment/config IDs, the full
clean commit, explicit seeds and container digests, again with zero errors or warnings.
