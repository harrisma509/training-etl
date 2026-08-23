#!/usr/bin/env bash
set -Eeuo pipefail

BACKUP_DIR="/mnt/harrisnas/backups"
TEST_DB="training_restore_test"
LOCK_FILE="/tmp/training_restore_test.lock"

cleanup() {
  echo "Cleaning up test database..."
  sudo -u postgres dropdb --if-exists --force "$TEST_DB"
}

trap cleanup EXIT

if [ "$TEST_DB" = "training" ] || [ "$TEST_DB" = "postgres" ]; then
  echo "ERROR: Refusing to operate on a protected database."
  exit 1
fi

if ! mountpoint -q /mnt/harrisnas; then
  echo "ERROR: HarrisNAS is not mounted at /mnt/harrisnas."
  exit 1
fi

LATEST_BACKUP="$(
  find "$BACKUP_DIR" \
    -maxdepth 1 \
    -type f \
    -name 'pg_training_*.sql.gz' \
    -printf '%T@ %p\n' |
  sort -nr |
  head -n 1 |
  cut -d' ' -f2-
)"

if [ -z "$LATEST_BACKUP" ]; then
  echo "ERROR: No PostgreSQL backups found in $BACKUP_DIR."
  exit 1
fi

exec 9>"$LOCK_FILE"

if ! flock -n 9; then
  echo "ERROR: Another restore test is already running."
  exit 1
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
    >/tmp/training_restore_output.log

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