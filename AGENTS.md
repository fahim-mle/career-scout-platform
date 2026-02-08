# Career Scout - Agent Guidelines

This document provides essential instructions for AI agents operating in the `career-scout-platform` repository.

## 1. Project Overview

Career Scout is a personal AI-powered job intelligence platform.
- **Backend:** Python 3.12+, FastAPI, SQLAlchemy (Async), PostgreSQL, Celery, Redis.
- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS, TanStack Query.
- **Infrastructure:** Docker Compose.

## 2. Build, Lint, and Test Commands

### Backend (`/backend`)

- **Install Dependencies:**
  ```bash
  pip install -r requirements.txt
  pip install -r requirements-dev.txt
  ```

- **Run Server (Dev):**
  ```bash
  uvicorn main:app --reload
  ```

- **Linting & Formatting:**
  - We use `ruff` (or `black`/`isort` if configured) and `mypy`.
  ```bash
  ruff check .
  ruff format .
  mypy .
  ```

- **Testing:**
  - Run all tests:
    ```bash
    pytest
    ```
  - Run a single test file:
    ```bash
    pytest tests/api/test_jobs.py
    ```
  - Run a specific test case:
    ```bash
    pytest tests/api/test_jobs.py::test_create_job
    ```
  - Run with coverage:
    ```bash
    pytest --cov=src
    ```

- **Database Migrations:**
  - Create migration: `alembic revision --autogenerate -m "message"`
  - Apply migration: `alembic upgrade head`

### Frontend (`/frontend`)

- **Install Dependencies:**
  ```bash
  npm install
  ```

- **Run Server (Dev):**
  ```bash
  npm run dev
  ```

- **Linting & Formatting:**
  ```bash
  npm run lint
  npm run format  # if script exists, otherwise `prettier --write .`
  ```

- **Testing:**
  - Run all tests:
    ```bash
    npm run test
    ```
  - Run a single test file:
    ```bash
    npm run test -- src/components/jobs/JobCard.test.tsx
    ```

## 3. Code Style Guidelines

### General
- **Language:** English for all code, comments, and documentation.
- **Path:** Use absolute imports where possible (e.g., `from src.core.config import settings`).

### Python (Backend)
- **Type Hints:** MANDATORY for all function arguments and return values.
  ```python
  def get_user(user_id: int) -> Optional[User]: ...
  ```
- **Docstrings:** Google style docstrings for all public modules, classes, and functions.
  ```python
  """
  Fetches a user by ID.

  Args:
      user_id: The unique identifier of the user.

  Returns:
      The User model if found, None otherwise.
  """
  ```
- **Error Handling:**
  - Use custom exceptions in the Service layer (`BusinessLogicError`, `NotFoundError`).
  - Catch specific exceptions (never `except Exception:` unless logging/re-raising).
  - Log errors with context using `loguru`.
- **Architecture:** Strict 3-Layer (Repository -> Service -> API).
  - **API:** Validation, HTTP status codes, dependency injection. NO business logic.
  - **Service:** Business logic, transactions. NO direct DB access.
  - **Repository:** DB queries only. NO business logic.

### TypeScript (Frontend)
- **Types:** Strict typing. Avoid `any`. Use interfaces for props and state.
  ```typescript
  interface JobCardProps {
    job: Job;
    onApply: (id: number) => void;
  }
  ```
- **Components:** Functional components with hooks.
- **State Management:**
  - Server state: `TanStack Query` (useQuery, useMutation).
  - Client state: `Zustand` (for global UI state) or `useState` (local).
- **Styling:** Tailwind CSS utility classes. Avoid inline styles.
- **Naming:**
  - Components: PascalCase (`JobCard.tsx`)
  - Hooks: camelCase (`useJobs.ts`)
  - Utils: camelCase (`dateFormatter.ts`)

## 4. Git Workflow

- **Branching:** Work on `dev` or feature branches (`feat/`, `fix/`). NEVER push directly to `main`.
- **Commits:** Conventional Commits format.
  - `feat: add job scraping service`
  - `fix: resolve database connection timeout`
  - `docs: update API documentation`
  - `refactor: simplify job matching logic`

## 5. Agent Behavior

- **Planning:** Before writing code, analyze the request and plan the changes.
- **Incremental Changes:** Make small, verifiable changes.
- **Verification:** Always verify changes by running relevant tests or linting commands.
- **Context:** Respect the existing project structure. Do not create new top-level directories unless explicitly instructed.
- **Communication:** If a task is ambiguous, ask clarifying questions.

## 6. Specific Rules

- **Async:** Use `async/await` for all I/O operations (DB, API calls).
- **Configuration:** Use `pydantic-settings` for environment variables.
- **Logging:** Use `loguru` instead of standard `logging`.
