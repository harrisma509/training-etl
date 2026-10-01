"""Historical SummaryActivity backfill for the Structured Activity Data Contract."""

import argparse
import json
import time
from datetime import date, datetime, time as datetime_time, timezone

from activity_utils import normalize_activity
from db_writer import connect_db, update_structured_activity_data
from settings import get_config, get_db_config
from strava_client import (
    StravaNetworkError,
    StravaRequestError,
    fetch_activity_page_with_metadata,
    refresh_access_token,
)


DEFAULT_START_DATE = date(2012, 1, 1)
DEFAULT_PAGE_SIZE = 200
BACKFILL_LOCK_KEY = 817431903


class BackfillLockUnavailable(Exception):
    pass


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE.isoformat())
    parser.add_argument("--end-date", default=date.today().isoformat())
    parser.add_argument("--max-pages", type=int)
    return parser


def validate_args(args):
    try:
        args.start_date = date.fromisoformat(args.start_date)
        args.end_date = date.fromisoformat(args.end_date)
    except ValueError as exc:
        raise ValueError("dates must use YYYY-MM-DD") from exc
    if args.start_date > args.end_date:
        raise ValueError("start date must not be after end date")
    if args.max_pages is not None and args.max_pages < 1:
        raise ValueError("max pages must be positive")
    return args


def epoch_at_start(value):
    return int(datetime.combine(value, datetime_time.min, tzinfo=timezone.utc).timestamp())


def scope_summary(rows, args):
    observed = sum(row.get("summary_observed_at") is not None for row in rows)
    dates = [str(row["date_local"])[:10] for row in rows if row.get("date_local") is not None]
    return {
        "local_rows_in_scope": len(rows),
        "local_rows_observed_before": observed,
        "local_rows_unobserved_before": len(rows) - observed,
        "local_date_min": min(dates, default=None),
        "local_date_max": max(dates, default=None),
        "page_size": DEFAULT_PAGE_SIZE,
        "estimated_provider_pages": (len(rows) + DEFAULT_PAGE_SIZE - 1) // DEFAULT_PAGE_SIZE,
        "start_date": args.start_date.isoformat(),
        "end_date": args.end_date.isoformat(),
    }


def fetch_scope_rows(conn, args):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT activity_id, date_local, summary_observed_at
            FROM public.strava_activities
            WHERE date_local >= %s AND date_local <= %s
            ORDER BY date_local, activity_id
            """,
            (args.start_date, args.end_date),
        )
        return list(cur.fetchall())


def acquire_backfill_lock(cfg):
    conn = connect_db(cfg)
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s) AS locked", (BACKFILL_LOCK_KEY,))
        locked = cur.fetchone()["locked"]
    if not locked:
        conn.close()
        raise BackfillLockUnavailable()
    return conn


def release_backfill_lock(conn):
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(%s)", (BACKFILL_LOCK_KEY,))
        conn.commit()
    finally:
        conn.close()


def classify_failure(error):
    if isinstance(error, StravaRequestError):
        return "rate_limited" if error.status_code == 429 else f"provider_http_{error.status_code}"
    if isinstance(error, StravaNetworkError):
        return "provider_network"
    if isinstance(error, ValueError):
        return "normalization"
    if isinstance(error, (OSError, RuntimeError)):
        return "persistence"
    return "failed"


def rate_state(rate_limits):
    return rate_limits.get("read") or rate_limits.get("overall")


def page_result(page, provider_rows, rate_limits):
    return {
        "page": page,
        "request_outcome": "ok",
        "provider_row_count": len(provider_rows),
        "matched_local_count": 0,
        "provider_only_count": 0,
        "normalized_count": 0,
        "persisted_count": 0,
        "skipped_count": 0,
        "normalization_failure_count": 0,
        "persistence_failure_count": 0,
        "rate_limits": rate_state(rate_limits),
    }


def persist_page(cfg, normalized_rows):
    with connect_db(cfg) as conn:
        with conn.cursor() as cur:
            persisted = update_structured_activity_data(cur, normalized_rows)
        conn.commit()
    return persisted


def apply_backfill(args, cfg, db_cfg, now_fn=lambda: datetime.now(timezone.utc), page_fetcher=None):
    lock_conn = acquire_backfill_lock(db_cfg)
    try:
        run_before = min(
            int(now_fn().timestamp()),
            epoch_at_start(args.end_date) + 86400,
        )
        after = epoch_at_start(args.start_date)
        token = refresh_access_token(cfg)["access_token"]
        with connect_db(db_cfg) as conn:
            scope_rows = fetch_scope_rows(conn, args)
        local_ids = {str(row["activity_id"]) for row in scope_rows}
        results = []
        provider_ids = set()
        page = 1
        stopped_reason = "completed"
        fetcher = page_fetcher or fetch_activity_page_with_metadata

        while args.max_pages is None or page <= args.max_pages:
            started = time.monotonic()
            try:
                provider_rows, rate_limits = fetcher(
                    token,
                    before=run_before,
                    after=after,
                    page=page,
                    per_page=DEFAULT_PAGE_SIZE,
                )
            except StravaRequestError as error:
                result = {
                    "page": page,
                    "request_outcome": "failed",
                    "provider_row_count": 0,
                    "failure_class": classify_failure(error),
                    "rate_limits": rate_state(error.rate_limits),
                }
                results.append(result)
                stopped_reason = "rate_limited" if error.status_code == 429 else "provider_failed"
                break
            except (StravaNetworkError, OSError) as error:
                results.append({
                    "page": page,
                    "request_outcome": "failed",
                    "provider_row_count": 0,
                    "failure_class": classify_failure(error),
                })
                stopped_reason = "provider_failed"
                break

            provider_rows = provider_rows or []
            provider_ids.update(str(row.get("id")) for row in provider_rows if row.get("id") is not None)
            result = page_result(page, provider_rows, rate_limits)
            matched = [row for row in provider_rows if str(row.get("id")) in local_ids]
            result["matched_local_count"] = len(matched)
            result["provider_only_count"] = len(provider_rows) - len(matched)
            normalized = []
            for provider_row in matched:
                try:
                    normalized.append(normalize_activity(provider_row, summary_observed=True))
                except (TypeError, ValueError):
                    result["normalization_failure_count"] += 1
            result["normalized_count"] = len(normalized)
            try:
                result["persisted_count"] = persist_page(db_cfg, normalized)
            except Exception:
                result["persistence_failure_count"] = len(normalized)
                result["request_outcome"] = "failed"
                result["failure_class"] = "persistence"
                results.append(result)
                stopped_reason = "persistence_failed"
                break
            result["skipped_count"] = result["provider_only_count"] + result["normalization_failure_count"]
            result["elapsed_ms"] = round((time.monotonic() - started) * 1000, 2)
            results.append(result)
            if not provider_rows:
                stopped_reason = "empty_page"
                break
            if len(provider_rows) < DEFAULT_PAGE_SIZE:
                stopped_reason = "short_page"
                break
            page += 1

        with connect_db(db_cfg) as conn:
            after_rows = fetch_scope_rows(conn, args)
        observed_after = sum(row.get("summary_observed_at") is not None for row in after_rows)
        matched_ids = provider_ids & local_ids
        provider_only_ids = provider_ids - local_ids
        local_only_ids = local_ids - provider_ids
        return {
            "fixed_before_epoch": run_before,
            "lower_boundary_epoch": after,
            "page_size": DEFAULT_PAGE_SIZE,
            "pages_requested": len(results),
            "pages_completed": sum(result["request_outcome"] == "ok" for result in results),
            "provider_rows_received": sum(result.get("provider_row_count", 0) for result in results),
            "unique_provider_activity_ids": len(provider_ids),
            "matched_local_rows": len(matched_ids),
            "provider_only_rows": len(provider_only_ids),
            "local_only_rows": len(local_only_ids),
            "local_rows_in_scope": len(scope_rows),
            "local_rows_observed_before": sum(row.get("summary_observed_at") is not None for row in scope_rows),
            "local_rows_observed_after": observed_after,
            "rows_still_unobserved": len(after_rows) - observed_after,
            "normalization_failures": sum(result.get("normalization_failure_count", 0) for result in results),
            "persistence_failures": sum(result.get("persistence_failure_count", 0) for result in results),
            "stopped_reason": stopped_reason,
            "rate_limits": next((result.get("rate_limits") for result in reversed(results) if result.get("rate_limits")), None),
        }, results
    finally:
        release_backfill_lock(lock_conn)


def main(argv=None):
    args = validate_args(build_parser().parse_args(argv))
    db_cfg = get_db_config()
    with connect_db(db_cfg) as conn:
        rows = fetch_scope_rows(conn, args)
    if args.preview:
        print(json.dumps({"run_mode": "preview", **scope_summary(rows, args)}, sort_keys=True, default=str))
        return 0
    summary, pages = apply_backfill(args, get_config(), db_cfg)
    for page in pages:
        print(json.dumps(page, sort_keys=True, default=str))
    print(json.dumps({"run_mode": "apply", **summary}, sort_keys=True, default=str))
    return 0 if summary["stopped_reason"] in {"completed", "empty_page", "short_page"} else 1


if __name__ == "__main__":
    raise SystemExit(main())