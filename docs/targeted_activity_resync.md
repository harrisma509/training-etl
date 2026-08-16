# Targeted Strava Activity Resync

This document covers the single-activity resync workflow implemented in [src/resync_activity.py](../src/resync_activity.py). It is intended to be a practical reference for ETL operators and developers who need to refresh one Strava activity without running a broad sync.

## Purpose

The command refreshes one Strava activity from the live Strava API, compares it against the stored row in `strava_activities`, and rebuilds the affected daily and weekly training aggregates in the database.

This is a focused repair workflow for cases such as:

- a Strava activity was edited after ingestion
- the activity date changed
- gear changed on an activity
- the load or duration fields were corrected upstream
- a maintenance fix requires validating a single impacted day without rerunning the full ETL

It is not a general-purpose ingestion path and should not be treated as a replacement for the normal sync worker.

## Location and ownership

- Entry point: [src/resync_activity.py](../src/resync_activity.py)
- Canonical normalization: [src/activity_utils.py](../src/activity_utils.py)
- Daily rebuild logic: [src/daily_builder.py](../src/daily_builder.py)
- Weekly rebuild logic: [src/weekly_builder.py](../src/weekly_builder.py)
- Database writes: [src/db_writer.py](../src/db_writer.py)
- Config loader: [src/settings.py](../src/settings.py)

The ETL remains the owner of this workflow; the separate `training-web` repository does not participate in the actual resync logic.

## CLI contract

Run the CLI from the repo root:

```bash
python src/resync_activity.py <activity_id>
python src/resync_activity.py 1234567890 --dry-run
```

### Required inputs

- `activity_id`: positive integer string or integer value
- `--dry-run`: preview the intended changes without writing to the database

### Output

The command emits compact JSON to stdout. The payload is designed for shell piping or automation and includes the activity id, changed fields, affected dates, rebuild status, and warnings.

## Configuration and environment

The script loads configuration from the standard ETL env setup flow via `get_config()` in [src/settings.py](../src/settings.py).

A normal runtime expects these values to be available from the environment or from the configured env file:

- `STRAVA_CLIENT_ID`
- `STRAVA_CLIENT_SECRET`
- `STRAVA_REFRESH_TOKEN`
- `DB_HOST`
- `DB_PORT`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `LOAD_CHRONIC_C`

The default env file location is `/config/strava.env`, but the code also honors `ENV_FILE` when set.

## Operational flow

The script follows this sequence:

1. Validate the activity id as a positive integer.
2. Refresh the Strava access token.
3. Fetch the current Strava activity detail from the API.
4. Connect to Postgres and acquire a transaction-level advisory lock for the activity id.
5. Fetch the existing stored row from `strava_activities`.
6. Compare the stored row with the fresh Strava payload.
7. Upsert the latest activity row.
8. Rebuild the affected `daily_training` rows for the old date, new date, or both.
9. Delete stale daily rows when a date disappears.
10. Rebuild `weekly_training` only when the activity change is training-impacting.
11. Commit the transaction or roll back on failure.

## Comparison policy

The comparison logic is intentionally field-aware and avoids treating metadata-only or gear-only changes as if they were a training load change.

The fields considered for a daily rebuild are:

- `date_local`
- `name`
- `sport_type`
- `activity_category`
- `moving_sec`
- `elapsed_sec`
- `distance_mi`
- `elevation_ft`
- `has_heartrate`
- `average_hr`
- `max_hr`
- `gear_id`

The weekly rebuild classifier uses a smaller training-impacting set:

- `date_local`
- `activity_category`
- `moving_sec`
- `elapsed_sec`
- `distance_mi`
- `elevation_ft`
- `has_heartrate`
- `average_hr`
- `max_hr`

If the changed fields are outside that set, the script marks the change as a gear-only or metadata-only change and does not rebuild weekly data.

This is intentional and matches the current production policy: an activity can change gear without constituting a new training stress signature.

## Date and weekly rebuild logic

The script computes the affected dates using `compute_rebuild_plan()` in [src/resync_activity.py](../src/resync_activity.py).

That helper:

- gathers old and new date values
- deduplicates the list
- maps each affected date to its ISO week start
- returns both `dates` and `week_starts`

The affected date rebuild path is the operational heart of the resync:

- remove the activity from the prior date set
- add the freshly normalized activity to the new date set
- call `build_daily_training()` on the rebuilt rows
- upsert the resulting aggregate row into `daily_training`
- if the old date disappears, delete the `daily_training` row for it

Weekly rebuilds are done by reading all `daily_training` rows and calling `build_weekly_training()` from [src/weekly_builder.py](../src/weekly_builder.py). The logic refreshes the full weekly table rather than patching a single week row.

## Dry-run behavior

`--dry-run` does not write any database rows. It calls `preview_resync()` instead of `resync_activity()`.

The dry-run flow:

- fetches the stored activity row
- refreshes the current Strava payload
- builds a comparison report
- simulates the affected date rows and aggregated daily results
- builds the relevant weekly rows for validation only
- returns the same core payload shape but with `dry_run: true` and `writes_prevented: true`

Important operational note:

- `dry_run` is validation-only and should be used before any live edit
- even in dry-run mode, the code still shows the exact affected dates and intended weekly rebuild set
- the `weekly_validation_only` field indicates when weekly rebuilds are being evaluated but intentionally not written

## Data handling rules

This script relies on the canonical normalizer in [src/activity_utils.py](../src/activity_utils.py). The implementation deliberately avoids passing a stored DB row back through `normalize_activity()` again.

Instead, it:

- takes the live Strava payload from the API
- normalizes it once with `normalize_activity()`
- compares it to the stored row using explicit field logic
- rebuilds derived tables using the normalized payload and `build_daily_training()` / `build_weekly_training()`

This avoids reintroducing stale JSON state or double-normalizing data that was already canonicalized once when written to `strava_activities`.

## Affected tables

The resync flow is expected to operate on the following tables:

- `strava_activities`: canonical per-activity source row
- `daily_training`: one-row-per-day derived aggregate
- `weekly_training`: weekly summary aggregate derived from daily rows
- `gear`: used for display-name lookup; no direct write occurs in this resync path beyond the normal `strava_activities` gear relationship

The script does not alter schema. It does not create new service tables or change the weekly audit rules.

## JSON result shape

Successful live execution returns a payload shaped roughly like this:

```json
{
  "status": "success",
  "activity_id": 1234567890,
  "activity_name": "Morning Ride",
  "changed_fields": ["distance_mi", "gear_id"],
  "old_date": "2024-04-03",
  "new_date": "2024-04-03",
  "rebuilt_dates": ["2024-04-03"],
  "deleted_daily_dates": [],
  "daily_rebuilt": true,
  "weekly_rebuilt": false,
  "weekly_skip_reason": "gear-only or metadata-only change",
  "old_gear_id": "b123",
  "new_gear_id": "b456",
  "warnings": [],
  "elapsed_seconds": 0.812
}
```

Dry-run output adds preview-only metadata such as:

```json
{
  "status": "success",
  "dry_run": true,
  "writes_prevented": true,
  "weekly_validation_only": true,
  "planned_daily_rows": {"2024-04-03": [...]},
  "planned_weekly_rows": [...],
  "warnings": []
}
```

## Failure handling

The script catches errors and emits a JSON error payload instead of a stack trace on stdout:

```json
{
  "status": "error",
  "activity_id": 1234567890,
  "error": "resync failed"
}
```

Operationally, that means callers should treat the CLI as a machine-readable interface and not assume the command will print Python exceptions in normal usage.

## Safety notes

The implementation includes the following safeguards:

- activity id validation before any DB or API operation
- refresh-token-based auth before requesting Strava detail
- transaction-scoped Postgres advisory lock to prevent overlapping edits on the same activity
- atomic commit or rollback around the update sequence
- dry-run preview path that prevents writes
- field-aware rebuild policy so gear-only changes do not incorrectly rewrite weekly aggregates

## Recommended runbook

1. Confirm the activity id is the one that needs repair.
2. Run the CLI in dry-run mode:

```bash
python src/resync_activity.py 1234567890 --dry-run
```

3. Review the returned `changed_fields`, `affected_dates`, and `weekly_skip_reason`.
4. If the output matches expectations, run the live command only in the intended runtime environment:

```bash
python src/resync_activity.py 1234567890
```

5. Verify the resulting `daily_training` and `weekly_training` rows in Postgres.
6. Treat the script as a narrow corrective operation, not as a data migration or bulk re-import.

## Limits

This workflow is intentionally scoped:

- it handles one activity at a time
- it rebuilds affected dates and weekly aggregates after the fact
- it does not rehydrate or reprocess the full historical dataset
- it does not modify the schema
- it does not alter the audit or load rules themselves

For broader data repair, use the normal ETL sync or a more explicit batch workflow rather than this targeted command.
