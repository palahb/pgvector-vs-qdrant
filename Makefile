.PHONY: test verify-baseline

PYTHON_BIN ?= python3

test:
	$(PYTHON_BIN) -m unittest discover -s tests -v

verify-baseline:
	PYTHON_BIN="$(PYTHON_BIN)" scripts/verify_baseline.sh
