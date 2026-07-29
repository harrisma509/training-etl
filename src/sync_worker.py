import os
import time
import subprocess
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row
from settings import get_config

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


def run_sync(days_back):
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

    return result.stdout.strip()


def process_once():
    conn = db_conn()

    try:
        if not acquire_lock(conn):
            print("Another sync is already running; skipping.")
            return

        pending = get_pending_request(conn)

        if pending:
            request_id = pending["id"]
            days_back = pending["days_back"] or DEFAULT_DAYS_BACK

            print(f"Processing sync_request id={request_id}, days_back={days_back}")
            mark_request_running(conn, request_id)

            try:
                run_sync(days_back)
                mark_request_completed(conn, request_id)
                print(f"Completed sync_request id={request_id}")
            except Exception as exc:
                mark_request_failed(conn, request_id, str(exc))
                print(f"Failed sync_request id={request_id}: {exc}")
            return

        age_minutes = latest_good_sync_age_minutes(conn)

        if age_minutes is None or age_minutes >= AUTO_SYNC_MINUTES:
            print(f"Running automatic sync, days_back={DEFAULT_DAYS_BACK}")
            run_sync(DEFAULT_DAYS_BACK)
            print("Automatic sync completed")
        else:
            print(f"No sync needed. Last good sync was {age_minutes:.1f} minutes ago.")

    finally:
        try:
            release_lock(conn)
        except Exception:
            pass
        conn.close()


def main():
    print(
        f"Sync worker started. Poll={POLL_SECONDS}s, "
        f"auto_sync={AUTO_SYNC_MINUTES}m, days_back={DEFAULT_DAYS_BACK}"
    )

    while True:
        try:
            process_once()
        except Exception as exc:
            print(f"Sync worker error: {exc}")

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()