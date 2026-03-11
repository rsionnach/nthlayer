# C→B Package Promotion DAG

**Date:** 2026-03-06
**Status:** Active
**Scope:** Promote domain/, core/, db/, identity/ to B-grade (or A for domain/)

## Context

After eliminating all F-grade packages, 4 packages need promotion:
- **domain/** — misgraded C, actually ~100% tested, needs docstrings only → A
- **core/** — misgraded C, actually 0% dedicated tests → D→B
- **db/** — C-grade, ~40% tested → B
- **identity/** — C-grade, ~65% tested → B

## DAG

```
Layer 0: domain/ (C→A) + core/ (D→B)    [no deps]
Layer 1: db/ (C→B)                        [depends on core/ for error types]
Layer 2: identity/ (C→B)                  [depends on domain/ models]
Layer 3: Grade refresh in quality.md      [depends on all above]
```

## Layer 0: domain/ + core/

### domain/ (C→A)
- Add module-level docstrings to `models.py`
- Already has 21 tests in `test_domain_models.py` with full coverage

### core/ (D→B)
Two files, ~45 new tests total:

**errors.py (173 lines):**
- ExitCode enum values and integer mapping
- NthLayerError base + 6 subclasses: construction, message, exit_code attribute
- `main_with_error_handling` decorator: catches each error type → correct exit code
- `format_error_message` output formatting
- `exit_with_error` behavior
- ~25 tests

**tiers.py (181 lines):**
- Tier StrEnum values
- TierConfig frozen dataclass construction
- TIER_CONFIGS dict completeness
- `normalize_tier`: case-insensitive, alias resolution, invalid input
- `get_tier_config`: valid and invalid tiers
- `is_valid_tier`: boundary cases
- `get_tier_thresholds` and `get_slo_targets`: return correct values per tier
- ~20 tests

## Layer 1: db/ (C→B)

**session.py (50 lines) — new test file:**
- Async engine creation
- Session lifecycle (create, close)
- URL construction from environment variables
- ~10 tests

**Expand test_db_models.py:**
- Relationship traversal tests
- Nullable field verification
- ~5 new tests

**Expand test_db_repositories.py:**
- list_runs query
- update_status on nonexistent run
- ~5 new tests

## Layer 2: identity/ (C→B)

**Expand existing test files (~15 new tests):**
- Edge cases: empty strings, unicode service names, very long names
- Fallback resolution path coverage
- Missing branch coverage in identity resolution

## Layer 3: Grade Refresh

Update `docs/quality.md`:
- domain/ C → A
- core/ C → B
- db/ C → B
- identity/ C → B

## Test Summary

| Package | Current | New | Total | Grade |
|---------|---------|-----|-------|-------|
| domain/ | 21 | 0 | 21 | A |
| core/ | 0 | ~45 | ~45 | B |
| db/ | 24 | ~20 | ~44 | B |
| identity/ | 78 | ~15 | ~93 | B |

## Verification

```bash
pytest tests/test_core_errors.py tests/test_core_tiers.py -v
pytest tests/test_db_models.py tests/test_db_repositories.py tests/test_db_session.py -v
pytest tests/test_identity*.py -v
make test && make lint && make typecheck
grep "| F \||  D |" docs/quality.md  # should be empty
```
