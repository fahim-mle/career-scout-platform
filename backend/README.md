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
```

Coverage is enforced at a minimum of 80%.

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
