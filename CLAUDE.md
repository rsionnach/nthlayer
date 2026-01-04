# CLAUDE.md
This repo’s agent instructions live in AGENTS.md.

## Mission
NthLayer: Reliability at build time, not incident time. Validate production readiness in CI/CD (Generate → Validate → Gate).

## How to work in this repo
- Keep changes small and testable (PR-sized chunks).
- Prefer refactors that reduce touch points for adding templates/backends.
- Keep CLI thin; move business logic into modules/classes.
- Always update/extend tests when changing behavior.
- Never commit secrets (use env vars).

## Commands
- Tests: `make test`
- Lint: `make lint` / `make lint-fix`
- Typecheck: `make typecheck`
- Format: `make format`
- Lock deps: `make lock` / `make lock-upgrade`

## Releases
- PyPI uses trusted publisher (no token needed)
- Create a GitHub release → triggers `.github/workflows/release.yml` → auto-publishes to PyPI
- Version must be updated in both `pyproject.toml` and `src/nthlayer/demo.py`
