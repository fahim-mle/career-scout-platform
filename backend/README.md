# Backend

## Setup

Install dependencies in your virtual environment:

```bash
pip install -r requirements-dev.txt
```

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
xdg-open htmlcov/index.html
```
