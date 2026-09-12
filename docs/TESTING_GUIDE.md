# Testing Guide

## Purpose

Pytest is the standard Python test runner for `training-etl`. Existing `unittest.TestCase` tests remain valid under pytest. New tests may use native pytest style when it improves clarity, but existing tests should not be converted merely for style.

Automated tests complement ETL runtime, database, and operational validation. They do not replace manual checks against approved non-production infrastructure.

## Environment and commands

Run commands from the repository root with the repository-local interpreter. Activation is optional on macOS and Linux:

```bash
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m pip install -r requirements-dev.txt
./.venv/bin/python -m pytest --collect-only -q
./.venv/bin/python -m pytest -q
```

Focused examples:

```bash
./.venv/bin/python -m pytest tests/test_daily_builder.py -q
./.venv/bin/python -m pytest tests/test_daily_builder.py::DailyBuilderOtherActivitiesTests::test_upsert_daily_training_includes_other_activities_in_sql -q
./.venv/bin/python -m pytest -k rebuild -q
./.venv/bin/python -m pytest --lf -q
./.venv/bin/python -m pytest -x -q
```

On Windows, activate the repository virtual environment first and use `python -m pytest`; use `python -m pytest -q` when `python3` is unavailable.

## Local search tooling

- `rg` (ripgrep) is available for fast repository searches on Mike's Mac.
- It is useful for locating tests, references, imports, and affected files.
- It respects `.gitignore` by default.
- It is a convenience tool, not a Python or test dependency, and must not be added to `requirements.txt` or `requirements-dev.txt`.
- If `rg` is unavailable on another development machine or coding-agent environment, use `grep` or `find`; do not block implementation or validation solely because `rg` is missing.

```bash
rg "route_evidence" --glob '*.py'
rg --hidden "TESTING_GUIDE" --glob '*.md'
rg --files tests | rg 'test_.*\.py$'
```

## Manual edit to GHC workflow

GHC is optional for editing ETL code. Mike may make production edits manually and then ask GHC to create and validate the tests. Add one sentence describing the intended behavior change, such as: "The builder must preserve secondary activities in authoritative order and serialize them correctly for jsonb storage."

Reusable prompt:

```text
I am done with my manual edits. Review the current uncommitted diff, identify the intended behavior changes, and infer the contract from my stated intent, current code, existing tests, and documentation. Preserve and distinguish my manual edits. Add or update the smallest focused deterministic tests using exact synthetic activity, day, and week data. Do not merely update expected values or weaken assertions to force green. Ask only if material ambiguity remains. Run the focused tests first, then the complete repository suite, and run py_compile on changed Python files. Report exact commands and outcomes. Do not commit or push.
```

## Test safety invariants

The default suite must never:

- make a real Strava call;
- connect to production PostgreSQL or production training-api;
- use Docker or SSH;
- deploy, restart, rebuild, or recreate services;
- execute backup, restore, alert, health-check, sync-worker, or production resync operations;
- require or print production credentials or tokens.

Use deterministic synthetic activities, days, and weeks; mocks and fakes for Strava and PostgreSQL; and patched network or subprocess boundaries. A dry-run code path must still be tested without assuming that dry-run permits real Strava or production database access.

## What requires tests

Add or update regression tests for new or changed Python behavior and bug fixes, including builders, normalization, date and week boundaries, JSON serialization, selective rebuild behavior, field classification, sanitized API behavior, and load or audit rules when those rules are explicitly changed.

Authoritative ETL calculations should use exact synthetic inputs and expected outputs. Missing data must not be silently treated as zero unless that is the documented contract.

Schema or SQL changes require separate non-production validation and consumer-impact review. They are not validated by the default unit suite alone.

Reasonable exceptions include documentation-only changes, comments, and genuinely nonbehavioral formatting. Manual runtime, provider, database, and operational checks remain separate from pytest.

## Test layers

- **Unit tests:** deterministic builders, helpers, normalization, calculations, and writers with synthetic data.
- **API and consumer contract tests:** bounded response shapes, validation, and sanitized errors without production services.
- **Future controlled integration tests:** non-production database or API infrastructure only; do not introduce it as part of this documentation task.
- **Manual smoke tests:** approved runtime, database, provider, and operational checks kept separate from pytest.

Do not automate backup, restore, alert, health-check, sync-worker, or production resync operations in the default suite.

## Focused-first rule

For every behavior change, run the smallest relevant test file or node first, then run the complete ETL suite. Run `py_compile` on every changed Python file. Report exact commands and outcomes. Never claim validation that did not occur.

## Failure handling

Reproduce the exact failure, then decide whether the code, test, or documented contract is wrong. Do not weaken a test merely to obtain green output. Make the smallest correction and rerun the focused test before rerunning the full suite.

## Completion report checklist

Report:

- files changed;
- tests added or updated and behavior proven;
- focused result;
- full-suite result;
- syntax checks;
- manual validation performed;
- schema or consumer-impact review, when applicable;
- remaining untested behavior;
- isolation confirmation;
- final `git status --short`;
- no commit or push unless explicitly requested.
