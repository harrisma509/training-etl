#!/usr/bin/env bash
set -Eeuo pipefail

BACKUP_DIR="${BACKUP_DIR:-/mnt/harrisnas/backups}"
ALERT_ENV_FILE="${ALERT_ENV_FILE:-/etc/training/alert.env}"

TEST_DB="training_restore_test"
LOCK_FILE="/run/lock/training_restore_test.lock"
RESTORE_OUTPUT="/opt/training/logs/training_restore_output.log"
LOG_PATH="/opt/training/logs/pg_restore_test.log"

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SCRIPT_NAME="$(basename "$0")"
ALERT_SCRIPT="$SCRIPT_DIR/send_alert.py"

FAILURE_LINE="unknown"
FAILURE_COMMAND="unknown"
ALERT_SENT=0


capture_failure() {
    local status=$?

   FAILURE_LINE="${BASH_LINENO[0]:-unknown}"
    FAILURE_COMMAND="${BASH_COMMAND:-unknown}"

    return "$status"
}


send_failure_alert() {
    local exit_code="$1"
    local failure_detail="$2"
    local host_name
    local event_time
    local body

    if [[ "$ALERT_SENT" -eq 1 ]]; then
        return 0
    fi

    ALERT_SENT=1

    host_name="$(hostname 2>/dev/null || printf '%s' 'unknown-host')"
    event_time="$(date '+%Y-%m-%d %H:%M:%S %Z')"

    body="$(cat <<EOF
PostgreSQL backup restore validation failed on HarrisServer.

Host: $host_name
Time: $event_time
Script: $SCRIPT_NAME
Exit code: $exit_code
Failure line: $FAILURE_LINE
Failure: $failure_detail
Log: $LOG_PATH

Operator review is required.
EOF
)"

    if [[ ! -f "$ALERT_SCRIPT" ]]; then
        echo "WARNING: Alert sender not found: $ALERT_SCRIPT" >&2
        return 0
    fi

    if [[ ! -f "$ALERT_ENV_FILE" ]]; then
        echo "WARNING: Alert configuration not found: $ALERT_ENV_FILE" >&2
        return 0
    fi

    if ! python3 "$ALERT_SCRIPT" \
        --subject "HarrisServer PostgreSQL Restore Test Failed" \
        --body "$body" \
        --env-file "$ALERT_ENV_FILE" \
        >/dev/null 2>&1
    then
        echo "WARNING: Restore test failed and the email alert could not be delivered." >&2
    fi
}


cleanup_on_exit() {
    local status=$?
    local cleanup_status=0
    local failure_detail

    trap - ERR
    trap - EXIT
    set +e

    echo "Cleaning up test database..."

    sudo -u postgres dropdb \
        --if-exists \
        --force \
        "$TEST_DB" \
        >/dev/null 2>&1

    cleanup_status=$?

    if [[ "$status" -eq 0 && "$cleanup_status" -ne 0 ]]; then
        status="$cleanup_status"
        FAILURE_COMMAND="dropdb cleanup"
        failure_detail="Restore validation completed, but test database cleanup failed"
    else
        failure_detail="Command failed: $FAILURE_COMMAND"
    fi

    if [[ "$status" -ne 0 ]]; then
        send_failure_alert "$status" "$failure_detail"
    fi

    exit "$status"
}


trap capture_failure ERR
trap cleanup_on_exit EXIT


if [[ "$TEST_DB" == "training" || "$TEST_DB" == "postgres" ]]; then
    echo "ERROR: Refusing to operate on protected database: $TEST_DB" >&2
    false
fi

if ! mountpoint -q "$BACKUP_DIR"; then
    echo "ERROR: HarrisNAS backup share is not mounted at $BACKUP_DIR." >&2
    false
fi

LATEST_BACKUP="$(
    find "$BACKUP_DIR" \
        -maxdepth 1 \
        -type f \
        -name 'pg_training_*.sql.gz' \
        -printf '%T@ %p\n' |
    sort -nr |
    sed -n '1p' |
    cut -d ' ' -f2-
)"

if [[ -z "$LATEST_BACKUP" ]]; then
    echo "ERROR: No PostgreSQL backups found in $BACKUP_DIR." >&2
    false
fi

exec 9>"$LOCK_FILE"

if ! flock -n 9; then
    echo "ERROR: Another restore test is already running." >&2
    false
fi

echo "Testing latest backup:"
echo "$LATEST_BACKUP"
echo

echo "Checking compressed-file integrity..."
gzip -t "$LATEST_BACKUP"

echo "Creating empty test database..."
sudo -u postgres dropdb --if-exists --force "$TEST_DB"
sudo -u postgres createdb "$TEST_DB"

echo "Restoring backup..."

gunzip -c "$LATEST_BACKUP" |
    sudo -u postgres psql \
        -v ON_ERROR_STOP=1 \
        --dbname="$TEST_DB" \
        >"$RESTORE_OUTPUT"

echo "Running validation queries..."

sudo -u postgres psql \
    -v ON_ERROR_STOP=1 \
    --dbname="$TEST_DB" <<'SQL'
DO $$
DECLARE
    required_table text;
BEGIN
    FOREACH required_table IN ARRAY ARRAY[
        'app_settings',
        'strava_activities',
        'daily_training',
        'weekly_training',
        'sync_request',
        'health_steps',
        'health_weight',
        'health_sleep',
        'health_hrv',
        'health_rhr',
        'health_vo2_max'
    ]
    LOOP
        IF to_regclass('public.' || required_table) IS NULL THEN
            RAISE EXCEPTION 'Required table is missing: %', required_table;
        END IF;
    END LOOP;
END
$$;

SELECT
    current_database() AS database,
    pg_size_pretty(pg_database_size(current_database())) AS size;

SELECT
    (SELECT COUNT(*) FROM strava_activities) AS activities,
    (SELECT COUNT(*) FROM daily_training) AS daily_rows,
    (SELECT COUNT(*) FROM weekly_training) AS weekly_rows,
    (SELECT COUNT(*) FROM health_steps) AS steps_rows,
    (SELECT COUNT(*) FROM sync_request) AS sync_requests;

DO $$
BEGIN
    IF (SELECT COUNT(*) FROM strava_activities) = 0 THEN
        RAISE EXCEPTION 'strava_activities is empty';
    END IF;

    IF (SELECT COUNT(*) FROM daily_training) = 0 THEN
        RAISE EXCEPTION 'daily_training is empty';
    END IF;

    IF (SELECT COUNT(*) FROM weekly_training) = 0 THEN
        RAISE EXCEPTION 'weekly_training is empty';
    END IF;
END
$$;
SQL

echo
echo "SUCCESS: Backup restored and validated."
echo "Backup: $LATEST_BACKUP"
echo "The test database will now be removed."