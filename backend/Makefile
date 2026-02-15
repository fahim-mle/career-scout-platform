.PHONY: test test-cov test-fast test-verbose clean

PYTEST ?= .venv/bin/pytest

test:
	$(PYTEST)

test-cov:
	$(PYTEST) --cov=src --cov-report=term --cov-report=html --cov-fail-under=80

test-fast:
	$(PYTEST) -m "not slow and not integration"

test-verbose:
	$(PYTEST) -v

clean:
	rm -rf htmlcov .coverage .pytest_cache
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
