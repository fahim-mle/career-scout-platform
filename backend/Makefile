.PHONY: test test-cov test-fast test-verbose test-refactor-safety clean

PYTEST ?= .venv/bin/pytest

test:
	$(PYTEST)

test-cov:
	$(PYTEST) --cov=src --cov-report=term --cov-report=html --cov-fail-under=80

test-fast:
	$(PYTEST) -m "not slow and not integration"

test-verbose:
	$(PYTEST) -v

test-refactor-safety:
	$(PYTEST) -v tests/scrapers/test_linkedin_scraper.py tests/scrapers/test_seek_scraper.py tests/scrapers/test_indeed_scraper.py tests/tasks/test_scraper_tasks.py tests/api/test_jobs.py

clean:
	rm -rf htmlcov .coverage .pytest_cache
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
