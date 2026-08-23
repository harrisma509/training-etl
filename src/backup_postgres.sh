#!/usr/bin/env bash
set -Eeuo pipefail

BACKUP_DIR="${BACKUP_DIR:-/mnt/harrisnas/backups}"
DB_ENV_FILE="${DB_ENV_FILE:-/etc/training/.env}"
ALERT_ENV_FILE="${ALERT_ENV_FILE:-/etc/training/alert.env}"

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
SCRIPT_NAME="$(basename "$0")"
ALERT_SCRIPT="$SCRIPT_DIR/send_alert.py"
LOG_PATH="/opt/training/logs/pg_backup.log"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="$BACKUP_DIR/pg_training_${TIMESTAMP}.sql.gz"

FAILURE_LINE="unknown"
ALERT_SENT=0


capture_failure() {
    local status=$?

    FAILURE_LINE="${BASH_LINENO-unknown}"

    return "$status"
}


send_failure_alert() {
    local exit_code="$1"
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
PostgreSQL backup failed on HarrisServer.

Host: $host_name
Time: $event_time
Script: $SCRIPT_NAME
Exit code: $exit_code
Failure line: $FAILURE_LINE
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
        --subject "HarrisServer PostgreSQL Backup Failed" \
        --body "$body" \
        --env-file "$ALERT_ENV_FILE" \
        >/dev/null 2>&1
    then
        echo "WARNING: Backup failed and the email alert could not be delivered." >&2
    fi
}


cleanup_on_exit() {
    local status=$?

    trap - ERR
    trap - EXIT
    set +e

    unset PGPASSWORD

    if [[ "$status" -ne 0 ]]; then
        send_failure_alert "$status"
    fi

    exit "$status"
}


trap capture_failure ERR
trap cleanup_on_exit EXIT


echo "Starting PostgreSQL backup..."

if ! mountpoint -q "$BACKUP_DIR"; then
    echo "ERROR: HarrisNAS backup share is not mounted at $BACKUP_DIR." >&2
    false
fi

if [[ ! -f "$DB_ENV_FILE" ]]; then
    echo "ERROR: Database environment file not found: $DB_ENV_FILE" >&2
    false
fi

DB_PASSWORD="$(
    grep '^DB_PASSWORD=' "$DB_ENV_FILE" |
    cut -d '=' -f2- |
    tr -d "\"'"
)"

DB_USER="$(
    grep '^DB_USER=' "$DB_ENV_FILE" |
    cut -d '=' -f2- |
    tr -d "\"'"
)"

DB_NAME="$(
    grep '^DB_NAME=' "$DB_ENV_FILE" |
    cut -d '=' -f2- |
    tr -d "\"'"
)"

if [[ -z "$DB_PASSWORD" || -z "$DB_USER" || -z "$DB_NAME" ]]; then
    echo "ERROR: Required database configuration is missing." >&2
    false
fi

export PGPASSWORD="$DB_PASSWORD"
unset DB_PASSWORD

pg_dump \
    --host=127.0.0.1 \
    --username="$DB_USER" \
    --dbname="$DB_NAME" |
gzip > "$BACKUP_FILE"

gzip -t "$BACKUP_FILE"

find "$BACKUP_DIR" -maxdepth 1 -type f -name 'pg_training_*.sql.gz' -mtime +14 -delete

echo "Backup complete: $BACKUP_FILE"