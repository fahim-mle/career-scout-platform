# Backend

## Setup

Install dependencies in your virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

If your editor still shows unresolved imports, reload the Python language server
after selecting `backend/.venv/bin/python` as the interpreter.

## Testing

Run tests with Make targets:

```bash
make test
make test-cov
make test-fast
make test-verbose
make test-refactor-safety
```

`make test-refactor-safety` runs the scraper refactor safety matrix:

- `tests/scrapers/test_linkedin_scraper.py`
- `tests/scrapers/test_seek_scraper.py`
- `tests/scrapers/test_indeed_scraper.py`
- `tests/tasks/test_scraper_tasks.py`
- `tests/api/test_jobs.py`

`make test-refactor-safety` is intentionally functional-only for fast refactor feedback.

Coverage is enforced at a minimum of 80% by `make test-cov`.

After `make test-cov`, open the HTML coverage report:

```bash
# Linux
xdg-open htmlcov/index.html

# macOS
open htmlcov/index.html

# Windows (cmd)
start htmlcov/index.html

# Windows (PowerShell)
Start-Process htmlcov/index.html
```
