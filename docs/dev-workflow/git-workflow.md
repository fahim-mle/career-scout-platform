# Git Workflow for Career Scout

**Strategy:** Trunk-based development with `dev` as the primary integration branch

**Branches:**
- `dev` (default development branch; all day-to-day work lands here)
- `main` (stable release branch; only receives validated merges from `dev`)

**Commit Style:** Conventional Commits

---

## Branch Policy

- All feature, fix, test, and docs work must target `dev`.
- No direct pushes to `main` except approved release merges from `dev`.
- `main` must remain deployable and stable.
- Keep short-lived branches under 48 hours.

---

## Daily Workflow

### For Small Changes (<50 lines, <2 hours)
```bash
# 1) Start from dev
git checkout dev
git pull origin dev

# 2) Make changes
# ... edit files ...

# 3) Stage and commit
git add .
git commit -m "feat: add health check endpoint"

# 4) Push to dev
git push origin dev
```

**When to use:** Single file edits, bug fixes, documentation, config updates

### For Medium Changes (50-200 lines, 2 hours - 2 days)
```bash
# 1) Branch from dev
git checkout dev
git pull origin dev
git checkout -b feat/docker-compose

# 2) Commit incrementally
git add .
git commit -m "feat: add postgres service to docker-compose"

git add .
git commit -m "feat: add redis service to docker-compose"

# 3) Push branch
git push -u origin feat/docker-compose

# 4) Merge back to dev
git checkout dev
git pull origin dev
git merge --ff-only feat/docker-compose
git push origin dev

# 5) Delete branch
git branch -d feat/docker-compose
git push origin --delete feat/docker-compose
```

**When to use:** Complete features, new endpoints, new UI components

### For Large/Risky Changes (>200 lines, >2 days)
```bash
# 1) Work from dev
git checkout dev
git pull origin dev

# 2) Use feature flags for incomplete work
# Example
ENABLE_AI_SCORING = os.getenv("ENABLE_AI_SCORING", "false") == "true"

if settings.ENABLE_AI_SCORING:
    # new logic
    pass
else:
    # current stable logic
    pass

# 3) Commit disabled-by-default changes to dev
git add .
git commit -m "feat: add AI scoring logic (disabled)"
git push origin dev
```

**When to use:** Refactors, multi-day initiatives, high-risk changes

---

## Release Workflow (Dev -> Main)

Only run this when `dev` is validated (tests green, smoke checks pass):

```bash
# 1) Sync local branches
git checkout dev
git pull origin dev
git checkout main
git pull origin main

# 2) Merge validated dev into main
git merge --ff-only dev

# 3) Push release
git push origin main

# 4) Return to dev for ongoing work
git checkout dev
```

---

## Commit Message Format

```text
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Types

| Type | Use | Example |
| --- | --- | --- |
| `feat` | New feature | `feat: add job repository with CRUD` |
| `fix` | Bug fix | `fix: health check returns wrong status code` |
| `refactor` | No behavior change | `refactor: extract logging setup` |
| `test` | Tests | `test: add repository CRUD tests` |
| `docs` | Documentation | `docs: update setup workflow` |
| `chore` | Tooling/config | `chore: add pytest plugin` |
| `style` | Formatting only | `style: fix lint formatting` |
| `perf` | Performance | `perf: add index on jobs.posted_date` |

### Common scopes

- `backend`
- `frontend`
- `infra`
- `db`
- `docs`

---

## Branch Naming

Format: `<type>/<short-description>`

Examples:
- `feat/linkedin-scraper`
- `fix/health-check-500`
- `refactor/repository-base`
- `test/api-integration`
- `docs/setup-guide`

Rules:
- lowercase only
- hyphen-separated words
- max 3 words in description
- delete within 48 hours

---

## Safety Rules

Never commit:
- secrets (`.env`, `secrets/`)
- passwords, tokens, API keys
- virtual envs (`venv/`, `env/`)
- build artifacts (`dist/`, `build/`, `__pycache__/`)
- IDE metadata (`.vscode/`, `.idea/`)
- large binaries (>10MB)
- `node_modules/`
- database files (`*.db`, `*.sqlite`)
- logs (`logs/`, `*.log`)

Always run before commit:
```bash
git status
git diff
```

---

## Pre-Commit Checklist

- [ ] code runs locally
- [ ] relevant tests pass (`pytest`, `npm test`)
- [ ] no secrets in diff
- [ ] no debug leftovers (`console.log`, `print`, `debugger`)
- [ ] conventional commit message used
- [ ] commit is atomic and single-purpose

---

## Agent Instructions (Mandatory)

All agents must follow this section.

### For @orchestrator

Before delegating any code task:
1. `git branch --show-current`
2. ensure `dev` branch is active (`git checkout dev` if needed)
3. `git pull origin dev`
4. require all task outputs to target `dev`

Commit template:
```bash
git add .
git commit -m "<type>: <what changed>

- <detail 1>
- <detail 2>

Refs #<issue-number>"
git push origin dev
```

### For @backend-engineer, @frontend-engineer, @infra-engineer

After completing any task, provide git commands that push to `dev`, not `main`.

```bash
git add <changed-files>
git commit -m "feat(<scope>): <summary>

- <detail 1>
- <detail 2>

Refs #<issue-number>"
git push origin dev
```

### For @qa-engineer

When committing tests:
```bash
git add backend/tests/ frontend/src/**/__tests__/
git commit -m "test(<scope>): <summary>

- <detail 1>
- <detail 2>

Refs #<issue-number>"
git push origin dev
```

### Direct push policy for agents

- Do not push directly to `main`.
- Avoid opening PRs that bypass `dev`.
- Treat `dev` as the default destination branch for all tasks.

---

## Rules Summary

DO:
- commit to `dev` for normal work
- branch from `dev` and merge back to `dev`
- merge `dev` into `main` only after validation
- use conventional commits
- link commits to issues (`Refs #123`, `Closes #123`)

DON'T:
- push directly to `main` (except release merge)
- keep feature branches alive >2 days
- commit secrets or sensitive data
- use `git push --force` on `main` or `dev`

---

## Quick Reference

```bash
# start of day
git checkout dev
git pull origin dev

# normal cycle
git add .
git commit -m "feat: add feature"
git push origin dev

# release cycle
git checkout main
git pull origin main
git merge --ff-only dev
git push origin main
git checkout dev
```

---

**This document is the single source of truth for version control. All agents must follow it.**
