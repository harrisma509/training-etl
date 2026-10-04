## Required Engineering Grounding

Before planning, investigating, or changing code, read:

1. `docs/ENGINEERING_CONSTITUTION.md`
2. The relevant architecture or feature document
3. `docs/TESTING_GUIDE.md`

The Engineering Constitution defines cross-repository principles.
This file defines repository-specific mandatory instructions.
Feature documents define detailed contracts and current behavior.

# GitHub Copilot Instructions for training-etl

## Project Overview

This repo contains the ETL, data builders, database writers, schema SQL, Strava sync logic, weekly audit computation, and future service-log import work for the Training Dashboard.

Before any Strava-related work, read `docs/STRAVA_ARCHITECTURE.md` and verify the latest official Strava developer documentation and API reference. Record relevant contract findings before changing Strava code, schema, OAuth, endpoints, fields, webhooks, rate handling, retention, or integrations.

The separate `training-web` repo owns the FastAPI web app, dashboard routes, browser UI, static frontend files, and HarrisServer web deployment.

## Repo Boundary

This repo owns:
- External-source ingestion, including Strava
- OAuth and provider credentials for ETL-owned sources
- Normalization and authoritative field semantics
- ETL-managed writes
- Schema SQL, migrations, and schema evolution
- Daily, Weekly, Load, TID, Fitness, Fatigue, Form, Weekly Audit, and other authoritative calculations
- Historical imports, backfills, rebuilds, reconciliation, and repair logic
- Queue processing and operational ETL scripts
- Implementation and deployment artifacts for `training-runner` and `training-api`

The separate `training-web` repo owns:
- The browser-facing FastAPI application and browser-facing routes
- Dashboard, Search, reporting, narrative, export, and presentation workflows
- Bounded server-side read-only PostgreSQL queries over processed data
- Web-owned application records
- Coach persistence, orchestration, settings, memories, receipts, and AI-provider integration

Do not modify `training-web` files from this repo unless explicitly requested.

The accepted cross-repository and runtime boundary is documented in `docs/ARD/TRAINING_SYSTEM_SERVICE_BOUNDARIES.md`. Read it for work involving database access, internal APIs, Search/reporting, service placement, or cross-service orchestration.

`training-runner` is the asynchronous and scheduled ETL service. It executes scheduled sync, queue-driven work, background ETL, and explicitly invoked backfills or rebuilds. `training-api` is the narrow authenticated synchronous facade over approved ETL functions and coordinated ETL-owned contracts; it is not a universal query layer or the mandatory path for ordinary `training-web` reads.
## Runtime

- ETL runs separately from the web app.
- Database-backed data is consumed by the `training-web` dashboard.
- Schema or ETL changes can break web routes, so validate affected web endpoints after database changes.
- Local `.venv` may differ from the HarrisServer/container runtime.
- Local syntax checks are useful but are not sufficient by themselves.

## Safety Rules

- Keep changes scoped and commit-friendly.
- Do not refactor unrelated ETL modules.
- Do not change database schema unless explicitly requested.
- Do not change weekly audit scoring unless explicitly requested.
- Do not change load/ramp rules unless explicitly requested.
- Do not expose or log tokens, secrets, `.env` values, refresh tokens, access tokens, database passwords, or raw credential-like values.
- Do not commit `.env`, `.venv`, `__pycache__`, `.DS_Store`, generated secrets, or local runtime artifacts.
- Prefer deterministic ETL logic over runtime AI.
- Prefer read-only/planning work before write/import functionality.

## Existing Design Principles

- `gear` is the canonical gear registry.
- `strava_activities` is the source for activity-level gear usage.
- `gear_id` is the stable join key.
- `gear_name` is display text.
- Service components such as Chain, Tires, Brake Pads, Rotors, Fork, Shock, Cassette, and Battery are not gear rows.
- Future service tracking should use dedicated service tables or clean derived views, not overload the `gear` table.
- Service status should be derived from service events plus activity usage.

## Database and Schema Rules

- Treat schema changes as high-risk.
- If schema changes are requested, provide:
  - exact SQL changes
  - affected tables
  - affected ETL modules
  - affected web routes
  - validation queries
  - rollback notes if practical
- Do not silently rename columns or change table semantics.
- Do not make web-facing breaking changes without identifying the matching `training-web` route/UI impact.
- Prefer additive schema changes over destructive changes.

## Weekly Audit Rules

- Weekly Audit V1 exists and writes to `weekly_audit` and `weekly_audit_item`.
- Do not change audit scoring, thresholds, weights, gate-item behavior, or item semantics unless explicitly requested.
- If touching weekly audit code, validate:
  - `compute_weekly_audit.py`
  - `weekly_audit_config.py`
  - `weekly_audit_rules.py`
  - `weekly_audit_scoring.py`
  - `weekly_audit_queries.py`
  - `audit_utils.py`

## Service / Gear Future Work Rules

For future Service_Log work:

- Inspect current workbook mapping before implementation.
- Do not import workbook Service_Dashboard as source of truth.
- Treat Service_Log as maintenance event history.
- Normalize bike/component/action names during import.
- Map bike names to `gear.gear_id` during controlled import.
- Preserve notes and costs.
- Preserve carry-over miles, hours, rides, and elevation where needed.
- Keep service status derived from service events plus `strava_activities`.

Suggested future model:

- `gear` = gear registry
- `service_component` = trackable component per gear item
- `service_event` = maintenance event history
- service status = computed or view-derived result

Do not create service tables unless explicitly requested.

## Validation Required

For Python changes:

1. Run syntax checks on touched Python files.

```bash
./.venv/bin/python -m py_compile src/changed_file.py
```

On Windows, use `.\.venv\Scripts\python.exe -m py_compile src\changed_file.py`.

## Deployment tooling

Use `.\deploy_training_etl.ps1` on Windows or
`./deploy_to_server_from_mac.sh` on macOS/Linux. Both require a clean worktree
whose `HEAD` equals its configured upstream revision and package the same four
members: `src`, `Dockerfile`, `requirements.txt`, and
`docker-compose.server.yml`. Use `-DryRun` or `--dry-run` to inspect the local
archive without upload.

The scripts only stage files and do not rebuild or restart containers. After a
source change, restart the affected ETL service. A Dockerfile or requirements
change requires an image rebuild and recreation; a Compose command, port,
volume, or health-check change requires service/project recreation. Routine
source deployment does not use `--force-recreate`.

## Permanent architecture and execution budget

For frontend ownership and cross-repository boundaries, use
`training-web/docs/FRONTEND_ARCHITECTURE.md` together with this repository's
constitution and the accepted service-boundary ARD. Permanent instructions
and architecture documents are authoritative, followed by executable
contracts, current source, runbooks, and Git history. Temporary prompts and
chat transcripts are not sources of truth.

Apply single-pass rigor: discover once, patch narrowly, validate in order, and
stop when evidence is green.

- One ownership inventory per slice and one focused follow-up search for an
  unclear boundary.
- At most two narrow patch attempts per boundary.
- Restore formatter or line-ending churn immediately; do not rebuild whole
  source files through broad replacement.
- Stop and report when a bounded change requires a broad rewrite.
- Validate in order: focused contract, changed-file syntax, adjacent contracts,
  complete relevant suite, `git diff --check`, and scope review.
- Trust an unchanged green baseline and do not rerun complete suites after they
  are green unless source or test code changes again.
- After commit, push normally and report the final clean status; do not amend,
  force-push, or perform speculative cleanup.

## Automated Testing

- Read [docs/TESTING_GUIDE.md](../docs/TESTING_GUIDE.md) before changing Python behavior.
- Every new or changed Python behavior and every bug fix should add or update focused deterministic tests unless the completion report documents a concrete exception.
- When Mike says he is done with manual edits and asks GHC to update tests, inspect and preserve his uncommitted diff, add the smallest tests that prove the intended behavior, and do not merely update expectations to force green.
- Run focused tests first, then the full suite using the platform-native repository-local interpreter documented in `docs/TESTING_GUIDE.md`.
- Default tests must not access paid providers, external services, production data, Docker, SSH, or deployment.
- `rg` is available on Mike's Mac for focused repository searches. Use it when helpful, but fall back to `grep` or `find` rather than treating it as a required dependency.
- Report exact commands and results.