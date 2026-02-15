.PHONY: test test-cov test-fast test-verbose

PYTEST ?= .venv/bin/pytest

test:
	$(PYTEST)

test-cov:
	$(PYTEST) --cov=src --cov-report=term --cov-report=html --cov-fail-under=80

test-fast:
	$(PYTEST) -m "not slow and not integration"

test-verbose:
	$(PYTEST) -v
