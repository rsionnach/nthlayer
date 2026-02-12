# Testing

## Commands

| Command | Purpose |
|---------|---------|
| `make test` | Run test suite |
| `make lint` | Run linter |
| `make lint-fix` | Auto-fix lint issues |
| `make typecheck` | Run type checker |
| `make format` | Format code |
| `make lock` | Lock dependencies |
| `make lock-upgrade` | Lock with upgrades |
| `./scripts/lint/run-all.sh` | Run custom golden-principle linters |

## Test Structure

Tests live in `tests/` (~119 test files). Test files follow the `test_<module>.py` naming convention.

### Patterns

- Use `pytest.mark.asyncio` for async test functions
- Use `AsyncMock` for mocking async provider methods
- Use `MagicMock` for mocking repository/client interfaces
- CLI tests use Click's `CliRunner` for testing command output and exit codes
- Test fixtures live in `tests/fixtures/`
- Integration tests live in `tests/integration/`

### Coverage by Area

Major coverage areas: CLI commands (~33 test files), alerts (5), config (6), PagerDuty (6), dashboards (4), portfolio (3), discovery (3).

Areas with limited or no test coverage: cloudwatch, db, deployments, domain, generators, integrations, logging.

### Running Specific Tests

```bash
pytest tests/test_specific.py          # Single file
pytest tests/test_specific.py -k name  # Specific test
pytest tests/ -x                       # Stop on first failure
```
