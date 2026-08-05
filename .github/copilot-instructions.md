# GitHub Copilot Instructions for training-etl

## Project Overview

This repo contains the ETL, data builders, database writers, schema SQL, Strava sync logic, weekly audit computation, and future service-log import work for the Training Dashboard.

The separate `training-web` repo owns the FastAPI web app, dashboard routes, browser UI, static frontend files, and NAS web deployment.

## Repo Boundary

This repo owns:

- Strava ingestion
- Training data builders
- Daily and weekly summary generation
- Database writes
- Gear database helpers
- Weekly audit computation
- Schema/reference SQL
- Future Service_Log import
- Future service status builders

The separate `training-web` repo owns:

- FastAPI routes
- Browser dashboard UI
- Static JavaScript and CSS
- Web Docker runtime
- NAS web app deployment

Do not modify `training-web` files from this repo unless explicitly requested.

## Runtime

- ETL runs separately from the web app.
- Database-backed data is consumed by the `training-web` dashboard.
- Schema or ETL changes can break web routes, so validate affected web endpoints after database changes.
- Local `.venv` may differ from NAS/container runtime.
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
python -m py_compile src/changed_file.py