import logging
import os
import subprocess
import time
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row
from logging_config import configure_logging
from settings import get_config

logger = logging.getLogger(__name__)

"""Long-running sync worker for the ETL container.

This module polls the database for manual sync requests and also
runs automatic sync when enough time has passed since the last
successful run.

The worker executes `/app/sync_training.py` for the main Strava/
training rebuild and then executes `/app/compute_weekly_audit.py`
only after a successful sync.

Because this is a long-lived process inside the sync worker
container, code changes require restarting the container.
Weekly audit recompute failures are warnings only and do not
cause a successful sync request to be marked failed.
"""
# Sync worker timing:
# SYNC_WORKER_POLL_SECONDS controls how often this long-running worker wakes up
# to check for pending manual Sync Now requests and whether an automatic sync is due.
#
# AUTO_SYNC_MINUTES controls how old the latest successful sync_run_log entry can be
# before the worker triggers an automatic sync.
#
# Example:
#   SYNC_WORKER_POLL_SECONDS=60
#   AUTO_SYNC_MINUTES=60
#
# With those settings, the worker checks once per minute, but it only runs an
# automatic sync when the last successful sync is about 60 minutes old or older.
# This means "check every 60 seconds" is not the same as "sync every 60 seconds."
# Manual Sync Now requests are usually picked up within the next polling interval.

CFG = get_config()

POLL_SECONDS = int(CFG.SYNC_WORKER_POLL_SECONDS)
AUTO_SYNC_MINUTES = int(CFG.AUTO_SYNC_MINUTES)
DEFAULT_DAYS_BACK = int(CFG.DAYS_BACK)
LOCK_KEY = 740022


def db_conn():
    return psycopg.connect(
        host=CFG.DB_HOST,
        port=CFG.DB_PORT,
        dbname=CFG.DB_NAME,
        user=CFG.DB_USER,
        password=CFG.DB_PASSWORD,
        row_factory=dict_row,
    )


def get_default_sync_days_back(conn):
    fallback_days_back = DEFAULT_DAYS_BACK

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT default_sync_days_back
                FROM app_settings
                WHERE settings_id = 1
                """
            )
            row = cur.fetchone()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        logger.warning("App setting unavailable; using configured default sync days.")
        return fallback_days_back

    if row is None or row.get("default_sync_days_back") is None:
        logger.warning("App setting unavailable; using configured default sync days.")
        return fallback_days_back

    try:
        value = int(row["default_sync_days_back"])
    except (TypeError, ValueError):
        logger.warning("App setting unavailable; using configured default sync days.")
        return fallback_days_back

    if value < 1 or value > 6000:
        logger.warning("App setting unavailable; using configured default sync days.")
        return fallback_days_back

    return value


def acquire_lock(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s) AS locked", (LOCK_KEY,))
        row = cur.fetchone()
        return bool(row["locked"])


def release_lock(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))


def get_pending_request(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                id,
                days_back
            FROM sync_request
            WHERE status = 'pending'
            ORDER BY requested_at_utc ASC
            LIMIT 1
        """)
        return cur.fetchone()


def mark_request_running(conn, request_id):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE sync_request
            SET
                status = 'running',
                started_at_utc = now(),
                message = 'Started by sync worker'
            WHERE id = %s
        """, (request_id,))
    conn.commit()


def mark_request_completed(conn, request_id):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE sync_request
            SET
                status = 'completed',
                completed_at_utc = now(),
                message = 'Completed by sync worker'
            WHERE id = %s
        """, (request_id,))
    conn.commit()


def mark_request_failed(conn, request_id, message):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE sync_request
            SET
                status = 'failed',
                completed_at_utc = now(),
                message = %s
            WHERE id = %s
        """, (message[:500], request_id))
    conn.commit()


def latest_good_sync_age_minutes(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT run_at_utc
            FROM sync_run_log
            WHERE lower(status) IN ('ok', 'success')
            ORDER BY run_at_utc DESC
            LIMIT 1
        """)
        row = cur.fetchone()

    if not row or not row["run_at_utc"]:
        return None

    last_sync = row["run_at_utc"]

    if last_sync.tzinfo is None:
        last_sync = last_sync.replace(tzinfo=timezone.utc)

    now_utc = datetime.now(timezone.utc)
    return (now_utc - last_sync).total_seconds() / 60


def run_weekly_audit_recompute(env):
    # Post-sync audit recompute is separate from the main sync path.
    # It is allowed to fail without affecting the surrounding sync result.
    logger.info("Running weekly audit recompute...")

    result = subprocess.run(
        ["python", "-u", "/app/compute_weekly_audit.py"],
        env=env,
        text=True,
        capture_output=True,
        timeout=900,
    )

    if result.returncode != 0:
        logger.warning("Weekly audit recompute failed: exit_code=%s", result.returncode)
        if result.stdout:
            logger.debug("Weekly audit recompute stdout summary: %s", result.stdout.strip()[:500])
        if result.stderr:
            logger.debug("Weekly audit recompute stderr summary: %s", result.stderr.strip()[:500])
        return

    logger.info("Weekly audit recompute completed")
    if result.stdout:
        logger.debug("Weekly audit recompute stdout summary: %s", result.stdout.strip()[:500])
    if result.stderr:
        logger.debug("Weekly audit recompute stderr summary: %s", result.stderr.strip()[:500])


def run_sync(days_back):
    # Run the ETL sync that refreshes Strava activities and writes
    # daily_training/weekly_training. Only run audit recompute after
    # a successful sync_training.py execution.
    env = os.environ.copy()
    env["DAYS_BACK"] = str(days_back)

    result = subprocess.run(
        ["python", "-u", "/app/sync_training.py"],
        env=env,
        text=True,
        capture_output=True,
        timeout=900,
    )

    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "sync_training.py failed"
        raise RuntimeError(message)

    run_weekly_audit_recompute(env)
    return result.stdout.strip()


def process_once():
    # One iteration of polling, with advisory lock guarding against
    # concurrent worker execution.
    conn = db_conn()

    try:
        if not acquire_lock(conn):
            logger.info("Another sync is already running; skipping.")
            return

        pending = get_pending_request(conn)

        if pending:
            # Manual Sync Now path: consume the oldest pending request.
            request_id = pending["id"]
            days_back = pending["days_back"] or DEFAULT_DAYS_BACK

            logger.info("Processing sync_request id=%s, days_back=%s", request_id, days_back)
            mark_request_running(conn, request_id)

            try:
                run_sync(days_back)
                mark_request_completed(conn, request_id)
                logger.info("Completed sync_request id=%s", request_id)
            except Exception as exc:
                mark_request_failed(conn, request_id, str(exc))
                logger.error("Failed sync_request id=%s: %s", request_id, exc)
            return

        # Automatic sync path: run if no recent successful sync exists.
        age_minutes = latest_good_sync_age_minutes(conn)

        if age_minutes is None or age_minutes >= AUTO_SYNC_MINUTES:
            automatic_days_back = get_default_sync_days_back(conn)
            logger.info("Running automatic sync, days_back=%s", automatic_days_back)
            run_sync(automatic_days_back)
            logger.info("Automatic sync completed")
        else:
            logger.debug("No sync needed. Last good sync was %.1f minutes ago.", age_minutes)

    finally:
        try:
            release_lock(conn)
        except Exception:
            pass
        conn.close()


def main():
    # Long-running worker entry point. This process remains alive inside
    # the container and periodically polls for manual or automatic sync work.
    logger.info("Sync worker started. Poll=%ss, auto_sync=%sm, days_back=%s", POLL_SECONDS, AUTO_SYNC_MINUTES, DEFAULT_DAYS_BACK)

    while True:
        try:
            process_once()
        except Exception:
            logger.exception("Sync worker error")

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    configure_logging("training-runner")
    main()