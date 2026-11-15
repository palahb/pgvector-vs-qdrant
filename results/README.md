# Results layout

This directory contains tracked metadata and derived outputs, not the only copy of raw
experimental evidence.

- `raw/`: immutable run outputs staged outside Git; only `.gitkeep` is tracked.
- `validated/`: validation reports and manifests for runs that pass the quality gates.
- `derived/`: reproducible tables and intermediate data generated from validated runs.

The frozen E1-E5 baseline is identified by
`data-manifests/baseline_2026-11-14.json`. Its archive is retained on TRUBA and in the
workspace artifact store. Never edit a raw run in place; produce a new run identifier.
