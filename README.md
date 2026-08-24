# Training ETL

Python ETL project for the Training Dashboard.

## Current scope

- Pull recent Strava activities
- Build daily and weekly training summary data
- Write dashboard source data to Postgres
- Support weekly audit computation
- Maintain gear-related database helpers
- Store schema/reference SQL for the training database
- Avoid desktop Excel dependency for app runtime

## Repo boundary

This repo owns:

- Strava ingestion
- ETL builders
- database writes
- schema SQL
- weekly audit computation
- future service log import and service status builders

The separate `training-web` repo owns:

- FastAPI web app
- browser dashboard UI
- API routes
- NAS web deployment
- static frontend files

Schema changes in this repo must be validated against the web app before deploy.

## HarrisServer operations, logging, and alerting

The production ETL platform runs on `harrisserver` with native PostgreSQL and Dockerized application services. Operational monitoring is intentionally independent of PostgreSQL where possible so the system can report a database outage rather than depending on the failed database to store alert state.

### Production runtime

- Host: `harrisserver`
HP EliteDesk 800 G5 Desktop Mini
Intel Core i5-9500T
6 physical cores
2.20 GHz base clock
16 GiB DDR4-2667
One dual-rank DIMM
One open memory slot
SK hynix PC601 NVMe SSD
Intel I219-LM Ethernet
Intel Wi-Fi 6 AX200
BIOS dated May 5, 2026
- Operating system: Ubuntu Server 26.04 LTS
- Database: native PostgreSQL 18.6
- Docker services:
  - `training-runner`
  - `training-web` in the separate `training-web` project
  - `training-api` is defined for future or controlled deployment
- Shared Docker network: `training_net`
- PostgreSQL is available to containers through `host.docker.internal`
- HarrisNAS backup storage is mounted through NFS at `/mnt/harrisnas/backups`

### Operational files

Deployed ETL and monitoring code:

```text
/opt/training/etl/
├── backup_postgres.sh
├── backup_test_latest_postgres.sh
├── send_alert.py
├── alert_manager.py
├── check_system_health.py
└── weekly_health_report.py
```

Protected configuration:

```text
/etc/training/
├── .env
├── strava.env
└── alert.env
```

Persistent state and logs:

```text
/opt/training/state/
└── alert_state.json

/opt/training/logs/
├── pg_backup.log
├── pg_restore_test.log
├── training_restore_output.log
├── health_check.log
└── weekly_health.log
```

Runtime lock:

```text
/run/lock/training_restore_test.lock
```

Secrets must remain outside Git and outside `/opt/training`. Current secret files are owned by `root`, grouped to `mike`, and use mode `640`.

### Logging model

Python monitoring components use the standard-library `logging` framework with timestamp, severity, logger name, and message. The application containers continue writing logs to stdout and stderr so Docker and Portainer can collect them.

The two PostgreSQL maintenance jobs are Bash scripts and use Bash-native error handling rather than Python logging:

- `set -Eeuo pipefail`
- nonzero process exit codes
- `ERR` and `EXIT` traps
- stdout and stderr redirected by cron
- failure-only email through `send_alert.py`

A failed email attempt must never hide or replace the original backup or restore failure. Successful backup and restore jobs do not send routine email.

### Gmail alert transport

`send_alert.py` is the single email transport used by the monitoring framework. It:

- reads `/etc/training/alert.env`
- connects to Gmail SMTP using STARTTLS
- authenticates with a Gmail App Password
- sends alerts to the configured recipient
- returns exit code `0` after Gmail accepts the message
- returns nonzero after a configuration, authentication, network, or SMTP failure
- never prints or logs the App Password

The sender display name is formatted as `Harris Server` while the authenticated sender remains the configured Gmail address.

Expected variables in `/etc/training/alert.env`:

```text
SMTP_HOST
SMTP_PORT
SMTP_USER
SMTP_APP_PASSWORD
ALERT_FROM
ALERT_FROM_NAME
ALERT_TO
```

Do not commit real values or paste them into logs, issues, documentation, or chat transcripts.

### Incident state and deduplication

`alert_manager.py` stores incident state at:

```text
/opt/training/state/alert_state.json
```

State is stored locally rather than in PostgreSQL so PostgreSQL outages can still be reported. The manager provides:

- one email when a new incident opens
- duplicate suppression for six hours
- a reminder after the cooldown if the incident remains active
- one recovery email for critical incidents
- silent recovery for lower-severity incidents
- atomic JSON file replacement
- file locking to prevent concurrent state corruption
- sanitized summaries with no credentials or connection strings

Typical command examples:

```bash
sudo /opt/training/etl/alert_manager.py list

sudo /opt/training/etl/alert_manager.py fail \
  --key test_incident \
  --severity warning \
  --summary "Controlled alert-manager test"

sudo /opt/training/etl/alert_manager.py recover \
  --key test_incident \
  --summary "Controlled test completed"
```

### Nightly PostgreSQL backup

`backup_postgres.sh`:

- verifies that `/mnt/harrisnas/backups` is mounted
- reads database credentials from `/etc/training/.env`
- creates a compressed SQL backup named `pg_training_YYYYMMDD_HHMMSS.sql.gz`
- validates gzip integrity
- retains backups for 14 days
- unsets `PGPASSWORD` during cleanup
- sends one failure email and no success email

The production backup has been tested successfully and its failure alert was validated using an intentionally invalid mount path without modifying production data.

### Monthly restore validation

`backup_test_latest_postgres.sh`:

- selects the newest PostgreSQL backup
- validates gzip integrity
- creates the disposable database `training_restore_test`
- restores the complete SQL backup with `ON_ERROR_STOP=1`
- validates required tables
- validates that core tables are nonempty
- prints key row counts and restored database size
- drops the disposable database on success or failure
- sends one failure email and no success email

The restore test must run as root because the script switches to the `postgres` operating-system user for database creation, restore, validation, and cleanup. The production `training` database is never a permitted restore-test target.

The backup and restore process has been proven end to end with a restored database size of approximately 14 MB and validated activity, Daily, Weekly, Steps, and sync-request rows.

### Hourly system health check

`check_system_health.py` runs as root and remains silent by email when healthy. It currently checks:

- PostgreSQL accepts connections on `127.0.0.1:5432`
- `training-web` is running
- `training-runner` is running
- HarrisNAS backup storage is mounted through NFS
- the newest backup is nonempty and less than 26 hours old
- root filesystem usage is below 85 percent
- `nut-monitor.service` is active
- the latest successful automatic sync in `sync_run_log` is less than three hours old
- no `sync_request` row has remained `pending` or `running` for more than 30 minutes

The health checker uses `alert_manager.py` to open, suppress, remind, and recover incidents. It does not restart services or modify application data.

Manual check:

```bash
sudo /opt/training/etl/check_system_health.py
```

A healthy result exits with status `0`. One or more failed checks exit with status `1`. Framework-level execution failure exits with status `2`.

### Weekly health summary

`weekly_health_report.py` sends one Sunday operational summary and supports a no-email preview:

```bash
sudo /opt/training/etl/weekly_health_report.py --dry-run
sudo /opt/training/etl/weekly_health_report.py
```

The report includes:

- overall `HEALTHY` or `ATTENTION NEEDED` status
- `✅ PASS` and `❌ FAIL` platform-health lines
- PostgreSQL version and database size
- Activities, Daily, and Weekly row counts
- successful and non-OK sync runs during the last seven days
- latest successful sync and warning count
- stuck sync-request count
- freshness of Steps, Weight, Sleep, HRV, resting heart rate, and VO2 max
- newest backup name, age, size, and retained backup count
- latest recorded restore-validation result
- active incidents from `alert_state.json`

The weekly report observes current health but does not open or recover incidents. The hourly health checker owns incident lifecycle.

### Production schedules

Mike's user crontab runs the nightly backup:

```cron
0 2 * * * /opt/training/etl/backup_postgres.sh >> /opt/training/logs/pg_backup.log 2>&1
```

Root's crontab runs privileged monitoring and restore validation:

```cron
5 * * * * /opt/training/etl/check_system_health.py >> /opt/training/logs/health_check.log 2>&1
0 3 1-7 * 0 /opt/training/etl/backup_test_latest_postgres.sh >> /opt/training/logs/pg_restore_test.log 2>&1
0 8 * * 0 /opt/training/etl/weekly_health_report.py >> /opt/training/logs/weekly_health.log 2>&1
```

Schedule meaning:

- every day at 2:00 AM: create the PostgreSQL backup
- five minutes after every hour: run silent health checks
- first Sunday of each month at 3:00 AM: restore and validate the newest backup
- every Sunday at 8:00 AM: send the weekly health summary

### Alert policy

Immediate email is reserved for actionable failures, including:

- PostgreSQL unavailable
- application container stopped
- HarrisNAS backup mount missing
- backup stale or empty
- root disk above threshold
- NUT monitor inactive
- automatic sync stale
- sync request stuck
- backup job failed
- restore validation failed

Routine healthy checks do not send email. Most healthy weeks should produce exactly one email: the Sunday summary.

### Current validation record

The operations framework has been manually proven with:

- successful Gmail SMTP delivery
- sender display name `Harris Server`
- successful PostgreSQL backup with no success email
- controlled backup failure with one email alert
- successful full restore validation with no success email
- controlled restore-test failure with one email alert
- alert open, duplicate suppression, and recovery tests
- hourly health-check detection of a stopped runner
- automatic recovery of corrected false incidents
- weekly-report dry run showing healthy and failed states
- all nine current health checks passing after schema corrections

### Remaining observability work

Future work should stay narrow and staged:

- add log rotation for persistent operational logs
- standardize Python `logging` inside `training-runner`, `training-web`, and health-ingest routes
- add contextual application alerts only after normal retries are exhausted
- distinguish persistent Strava authentication failures from transient network errors
- preserve the current policy of no daily healthy emails

Do not add Sentry, Prometheus, Grafana, or another monitoring platform unless a measured need justifies the added operational complexity.

## Internal ETL API

### Purpose

The training-api service provides a narrow synchronous HTTP boundary around existing ETL operations. It exists so callers do not need to mount ETL source into training-web, install ETL dependencies in training-web, expose Strava credentials to training-web, or use SSH, Docker socket access, docker exec, or subprocess execution from the web app.

Current flow:

training-web or trusted administrative client
→ training-api
→ existing ETL function
→ Strava and PostgreSQL
→ sanitized JSON result

This API is intentionally small and reuses the authoritative ETL logic instead of duplicating it.

### Service ownership

training-runner:
- scheduled synchronization
- existing Sync Now processing
- background worker behavior

training-api:
- synchronous ETL HTTP operations
- token-protected internal endpoints
- direct reuse of existing ETL functions
- sanitized JSON responses

training-web:
- browser-facing UI and routes
- future server-side proxy to training-api
- no direct Strava or ETL write logic

### Non-negotiable implementation rule

API handlers must call an existing authoritative ETL function.

API handlers must not reproduce, copy, fork, or independently implement:

- Strava fetching
- activity normalization
- activity comparison
- database writes
- Daily rebuilding
- Weekly rebuilding
- load calculation
- gear calculations
- service-event behavior

If an ETL operation does not already exist as a callable function, the function must be implemented and validated first. Only then is it exposed through the API.

### Authentication

The current internal API uses the required header:

X-Internal-Token

The expected value comes from `TRAINING_API_TOKEN` and is loaded through the existing `ENV_FILE` configuration path. Comparison uses `hmac.compare_digest`.

Important rules:
- the token must be a long random value
- the token must not be committed to Git
- the token must not appear in URLs
- the token must not be sent to browser JavaScript
- the token must not be logged
- missing or invalid authentication returns HTTP 401
- the API refuses to start if `TRAINING_API_TOKEN` is missing or blank

Do not include a real token in documentation.

### Health endpoint

GET /health

Authentication:
- none

Purpose:
- confirm Uvicorn and the FastAPI application can answer requests
- support container health monitoring

Current response:

```json
{
  "status": "ok",
  "service": "training-api"
}
```

The health endpoint does not:

- call Strava
- query PostgreSQL
- validate credentials
- expose configuration
- prove that an activity resync will succeed

### Activity-resync endpoint

POST /internal/activities/{activity_id}/resync

Authentication:
- `X-Internal-Token: <configured token>`

Input rules:
- `activity_id` is supplied in the URL path
- positive decimal integer only
- no request body is required
- no arbitrary command name is accepted
- no caller-provided script, URL, SQL, filesystem path, or CLI argument is accepted

Execution:
- call `resync_activity(CFG, activity_id)`
- wait synchronously for completion
- return its sanitized result

Side effects may include:
- refreshing one Strava activity
- updating `strava_activities`
- rebuilding complete affected Daily dates
- deleting an emptied old Daily date
- rebuilding Weekly only for training-impacting changes

The endpoint does not invent training load or rewrite service events.

### Success response

The current success response is the existing sanitized dictionary returned by the ETL function. Current fields include:

- status
- activity_id
- activity_name
- changed_fields
- old_date
- new_date
- rebuilt_dates
- deleted_daily_dates
- daily_rebuilt
- weekly_rebuilt
- weekly_rows_rebuilt
- weekly_skip_reason
- old_gear_id
- new_gear_id
- old_bike_name
- new_bike_name
- warnings
- elapsed_seconds

Notes:
- additional safe fields may be added later
- callers should not depend on JSON property order
- `changed_fields` is the authoritative change classification
- `daily_rebuilt` reports whether Daily was written
- `weekly_rebuilt` reports whether Weekly was written
- `rebuilt_dates` identifies Daily dates rebuilt
- `deleted_daily_dates` identifies stale old Daily dates removed
- `warnings` reports nonfatal conditions

Example sanitized response:

```json
{
  "status": "success",
  "activity_id": 19767854251,
  "activity_name": "Deer Creeks",
  "changed_fields": ["name"],
  "old_date": "2026-08-16",
  "new_date": "2026-08-16",
  "rebuilt_dates": ["2026-08-16"],
  "deleted_daily_dates": [],
  "daily_rebuilt": true,
  "weekly_rebuilt": false,
  "weekly_rows_rebuilt": 0,
  "weekly_skip_reason": "gear-only or metadata-only change",
  "old_gear_id": "abc123",
  "new_gear_id": "abc123",
  "old_bike_name": "Road Bike",
  "new_bike_name": "Road Bike",
  "warnings": [],
  "elapsed_seconds": 2.123
}
```

### No-change response

An already-current activity normally returns a success payload with no real change, for example:

```json
{
  "status": "success",
  "activity_id": 18512036019,
  "changed_fields": [],
  "rebuilt_dates": [],
  "daily_rebuilt": false,
  "weekly_rebuilt": false,
  "weekly_rows_rebuilt": 0,
  "weekly_skip_reason": "no training-impacting change"
}
```

This is expected idempotent behavior: the ETL checks the live Strava record, sees no training-impacting difference, and returns a no-op result.

### Error contract

Current HTTP behavior:

HTTP 400:
- invalid activity ID

HTTP 401:
- missing or invalid `X-Internal-Token`

HTTP 500:
- `resync_activity()` raised an exception
- response remains generic and sanitized

Representative response shapes:

```json
{
  "status": "error",
  "error": "Invalid activity id"
}
```

```json
{
  "status": "error",
  "error": "Unauthorized"
}
```

```json
{
  "status": "error",
  "activity_id": 19767854251,
  "error": "Resync failed"
}
```

The API does not expose exception text, stack traces, credentials, tokens, PostgreSQL connection details, raw Strava payloads, or internal filesystem paths.

Future Improvements:
- 404 for unknown local activity IDs
- 409 for duplicate in-flight requests if a guard is added later
- 503 or 504 for external dependency or timeout issues, if the API later adds explicit timeout handling

### Timeouts

The direct training-api endpoint does not currently impose an application-level timeout in the code path inspected here. Current operational guidance is to use a bounded client timeout at the caller boundary, for example `curl --max-time 35` during manual validation.

Important notes:
- a future training-web proxy should use a bounded timeout
- timeout policy belongs at the calling boundary unless a future API-specific mechanism is added
- callers must not assume a guaranteed two-second response time
- proven calls have varied from approximately two to six seconds

### Concurrency

Current behavior is intentionally simple:

- `resync_activity()` keeps its PostgreSQL transaction and advisory-lock safety
- the API does not currently provide a queue
- the API does not currently use `sync_request`
- the API does not currently poll
- the API waits synchronously
- browser or proxy duplicate-click handling is future work unless a guard is added later

The API is a direct synchronous boundary around the ETL function, not a background-processing framework.

### Curl examples

Health check:

```bash
curl -sS http://<training-api-host>:8090/health | python3 -m json.tool
```

Unauthorized resync request:

```bash
curl -sS -D - \
  -X POST \
  http://<training-api-host>:8090/internal/activities/19767854251/resync
```

Authorized resync request using a shell environment variable:

```bash
read -s TRAINING_API_TOKEN
export TRAINING_API_TOKEN

curl --max-time 35 -sS \
  -X POST \
  -H "X-Internal-Token: $TRAINING_API_TOKEN" \
  http://<training-api-host>:8090/internal/activities/<activity_id>/resync \
  | python3 -m json.tool
```

Clear the token after testing:

```bash
unset TRAINING_API_TOKEN
```

When entering the token, paste only the token value. Do not paste the surrounding quotes used in `strava.env`.

### Container and deployment notes

The current runtime is split between two containers in the same Compose project:

- `training-runner`: runs the scheduled ETL worker and normal sync automation
- `training-api`: runs FastAPI/Uvicorn for the internal synchronous API

Both services use the same ETL image, source, dependencies, configuration, and private Docker network.

Relevant Compose behavior currently in place:

- `training-runner` executes `python -u /app/sync_worker.py`
- `training-api` executes `python -m uvicorn internal_api:app --host 0.0.0.0 --port 8090`
- the ETL source is mounted read-only at `/app`
- protected configuration is mounted read-only at `/config`
- settings are loaded from `/config/strava.env` via `ENV_FILE`

Operational distinctions:
- Python source change → deploy source and restart the affected container
- `strava.env` change → restart the affected container
- Dockerfile or requirements change → rebuild image and recreate affected services
- Compose command, port, volume, or health-check change → recreate service or project
- simple stop/start does not apply changed Compose configuration

Manual project-level stop affects both `training-runner` and `training-api`.

### Health-check behavior

The current health-check contract is:

- GET /health
- periodic Docker check
- container can transition from unhealthy back to healthy after later successful checks
- an unhealthy status does not necessarily mean the Uvicorn process exited
- restart policy responds to process exit, not merely to failing health checks

Current confirmed health-check values from the Compose file:

- interval = 5 minutes
- timeout = 10 seconds
- retries = 3
- start_period = 90 seconds

### Future training-web integration

The intended boundary is:

trusted LAN browser
→ training-web POST route
→ server-side internal API token
→ training-api
→ resync_activity()

Rules for that future integration:
- browser JavaScript must never receive `TRAINING_API_TOKEN`
- training-web should provide a thin server-side proxy
- proxy must validate the activity ID
- proxy must impose a bounded timeout
- proxy should prevent duplicate in-flight calls
- proxy must return sanitized responses
- proxy must not duplicate ETL logic
- user authentication and CSRF protection are required before exposing the web application publicly

training-web is currently LAN-only and the proxy is not yet implemented.

### Validation record

The service has been proven with:

- successful health check
- failed authentication returning HTTP 401
- authenticated no-change activity resync
- authenticated name-only activity change
- Daily selective rebuild
- Weekly selective skip
- second-call idempotency

### Future API design rules

Future handlers should adhere to these rules:

- expose narrow operations, not generic command execution
- prefer path and typed parameters over arbitrary command payloads
- validate input at the HTTP boundary
- call an existing ETL function
- keep data-write transactions inside ETL functions
- return sanitized structured JSON
- never return credentials, raw environment values, stack traces, SQL, or raw source payloads
- add authentication to every mutating endpoint
- add an endpoint only when the operation has a clear owner and testable contract
- do not turn training-api into a generic administration shell

## Security rules

- Do not commit real Strava tokens
- Do not commit database passwords
- Do not commit `.env` files
- Do not mount NAS family/cloud/photo/finance folders
- NAS runtime folders are limited to `/docker/training`
- Do not expose raw Strava JSON or secrets in logs or dashboard APIs

## Validation

For ETL changes:

1. Run syntax checks on touched Python files.
2. Run the relevant ETL script locally or in the intended runtime.
3. Confirm database writes land in the expected tables.
4. Confirm the web dashboard still loads affected tabs.
5. Confirm no token, credential, or raw secret-like value is logged.
sync_worker.py is a long-running container process. Deploying updated files is not enough; restart the sync runner container for code changes to take effect.

## Current log-management layers
/opt/training/logs/*.log
→ Linux logrotate
→ weekly, 8 copies, gzip, 10 MB maximum

Docker container stdout/stderr
→ Docker json-file rotation
→ 10 MB per file, 5 files per container

# HarrisServer Logging and Alerting

## Overview

HarrisServer uses separate but complementary layers for application logging, operational logging, health monitoring, and email alerting.

The design goals are:

- Keep healthy operation quiet
- Preserve useful diagnostic details
- Send email only for actionable failures
- Prevent duplicate alert emails
- Keep monitoring functional when PostgreSQL is unavailable
- Prevent log files from growing indefinitely
- Avoid logging credentials, tokens, health payloads, or other secrets

## Architecture

```text
training-web and training-runner
        |
        | Python standard logging
        v
Docker stdout and stderr
        |
        | Docker json-file rotation
        v
Portainer and docker logs


Cron and maintenance jobs
        |
        | stdout and stderr
        v
/opt/training/logs
        |
        | Linux logrotate
        v
Compressed historical logs


Health checks and operational failures
        |
        v
alert_manager.py
        |
        | Local incident state
        v
/opt/training/state/alert_state.json
        |
        v
send_alert.py
        |
        | Gmail SMTP with App Password
        v
Operations email recipient