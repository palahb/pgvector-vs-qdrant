.PHONY: test verify-baseline

PYTHON_BIN ?= python3

test:
	$(PYTHON_BIN) -m unittest discover -s tests -v

verify-baseline:
	PYTHON_BIN="$(PYTHON_BIN)" scripts/verify_baseline.sh

# One command: regenerate every tracked analysis from the raw results with the analysis tools of this checkout, compare, check the
# generated paper sections, the structure of the paper, the table-to-manifest binding and the unit tests. Raw results are read from
# ARTIFACTS (default ../artifacts). Run it on a tag; the report goes to results/derived/verify_paper_<ref>.json.
ARTIFACTS ?= ../artifacts
VERIFY_REF ?= $(shell git describe --tags --exact-match 2>/dev/null || git rev-parse --short HEAD)
.PHONY: verify-paper
verify-paper:
	$(PYTHON_BIN) -m analysis.verify_paper --artifacts "$(ARTIFACTS)" --output results/derived/verify_paper_$(VERIFY_REF).json
