"""Restartable, rate-aware historical Strava narrative backfill."""

import argparse
import copy
import json
import random
import time
from datetime import date, datetime, timezone

from activity_utils import NARRATIVE_FIELDS, extract_activity_narrative
from db_writer import connect_db, upsert_activity_narrative
from settings import get_config, get_db_config
from strava_client import (
    StravaRequestError,
    StravaNetworkError,
    fetch_activity_detail_with_metadata,
    refresh_access_token,
)
from strava_narrative_pilot import classify_failure, state_summary


DEFAULT_START_DATE = date(2012, 1, 1)
DEFAULT_BATCH_SIZE = 100
MAX_BATCH_SIZE = 150
DEFAULT_DAILY_HEADROOM = 400
MIN_DAILY_HEADROOM = 200
BACKFILL_LOCK_KEY = 817431902
DEFAULT_RETRY_BASE_SECONDS = 2.0
MAX_BACKOFF_SECONDS = 30.0


class QuotaStop(Exception):
    def __init__(self, reason, rate_limits=None):
        super().__init__(reason)
        self.reason = reason
        self.rate_limits = rate_limits or {}


class BackfillLockUnavailable(Exception):
    pass


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE.isoformat())
    parser.add_argument("--end-date", default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--daily-headroom", type=int, default=DEFAULT_DAILY_HEADROOM)
    parser.add_argument("--max-requests", type=int)
    parser.add_argument("--activity-id", action="append")
    parser.add_argument("--refresh-observed", action="store_true")
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--retry-base-seconds", type=float, default=DEFAULT_RETRY_BASE_SECONDS)
    return parser


def validate_args(args):
    try:
        args.start_date = date.fromisoformat(args.start_date)
        args.end_date = date.fromisoformat(args.end_date)
    except ValueError as exc:
        raise ValueError("dates must use YYYY-MM-DD") from exc
    if args.start_date > args.end_date:
        raise ValueError("start date must not be after end date")
    if not 1 <= args.batch_size <= MAX_BATCH_SIZE:
        raise ValueError(f"batch size must be between 1 and {MAX_BATCH_SIZE}")
    if args.daily_headroom < MIN_DAILY_HEADROOM:
        raise ValueError(f"daily headroom must be at least {MIN_DAILY_HEADROOM}")
    if args.max_requests is not None and args.max_requests < 1:
        raise ValueError("max requests must be positive")
    if args.max_retries < 0:
        raise ValueError("max retries must not be negative")
    if args.retry_base_seconds < 0:
        raise ValueError("retry base seconds must not be negative")
    args.activity_id = validate_activity_ids(args.activity_id or [])
    return args


def validate_activity_ids(values):
    normalized = []
    seen = set()
    for value in values:
        text = str(value).strip()
        if not text.isdigit() or int(text) <= 0:
            raise ValueError("activity IDs must be positive integers")
        if text not in seen:
            normalized.append(text)
            seen.add(text)
    return normalized


def _where_clause(args):
    clauses = ["date_local >= %s", "date_local <= %s"]
    params = [args.start_date, args.end_date]
    if args.activity_id:
        clauses.append("activity_id = ANY(%s)")
        params.append(args.activity_id)
    if not args.refresh_observed:
        clauses.append("narrative_observed_at IS NULL")
    return " AND ".join(clauses), params


def fetch_population_rows(conn, args, limit=None):
    where, params = _where_clause(args)
    limit_sql = " LIMIT %s" if limit is not None else ""
    if limit is not None:
        params.append(limit)
    with conn.cursor() as cur:
        cur.execute(
            f"""
                 SELECT activity_id, date_local, description_observed,
                     private_note_observed, narrative_observed_at
            FROM public.strava_activities
            WHERE {where}
            ORDER BY date_local DESC, activity_id DESC
            {limit_sql}
            """,
            tuple(params),
        )
        return list(cur.fetchall())


def population_summary(rows, args):
    completed = sum(row.get("narrative_observed_at") is not None for row in rows)
    eligible = len(rows) - completed
    return {
        "total_local_in_scope": len(rows),
        "eligible_count": eligible,
        "completed_count": completed,
        "fully_observed_count": completed,
        "description_unobserved_count": sum(not row["description_observed"] for row in rows),
        "private_note_unobserved_count": sum(not row["private_note_observed"] for row in rows),
        "date_min": min((str(row["date_local"])[:10] for row in rows), default=None),
        "date_max": max((str(row["date_local"])[:10] for row in rows), default=None),
        "ordering": "date_local_desc_activity_id_desc",
        "batch_size": args.batch_size,
        "daily_headroom": args.daily_headroom,
        "estimated_maximum_calls": min(
            sum(
                row.get("narrative_observed_at") is None for row in rows
            ),
            args.batch_size,
        ),
    }


class RateBudget:
    def __init__(self, headroom, max_requests=None, sleep_fn=time.sleep):
        self.headroom = headroom
        self.max_requests = max_requests
        self.sleep_fn = sleep_fn
        self.requests = 0
        self.latest = {}
        self.headers_available = False

    def update(self, rate_limits):
        if rate_limits:
            self.latest = rate_limits
            self.headers_available = True

    def safe_read(self):
        return self.latest.get("read") or self.latest.get("overall")

    def check(self):
        if self.max_requests is not None and self.requests >= self.max_requests:
            raise QuotaStop("max_requests_reached", self.latest)
        read = self.safe_read()
        if read:
            limits = read.get("limit", [])
            usage = read.get("usage", [])
            if len(limits) >= 2 and len(usage) >= 2:
                if usage[1] >= limits[1] - self.headroom:
                    raise QuotaStop("daily_headroom_reached", self.latest)
            if limits and usage and usage[0] >= limits[0] - 5:
                raise QuotaStop("short_window_headroom_reached", self.latest)

    def before_request(self):
        self.check()
        if not self.headers_available:
            self.sleep_fn(0.25)
        self.requests += 1


def _retryable(error):
    return isinstance(error, StravaRequestError) and error.status_code >= 500 or (
        isinstance(error, StravaNetworkError)
    )


def fetch_with_retries(activity_id, token_state, budget, args, refresh_used):
    retries = 0
    while True:
        budget.before_request()
        try:
            detail, rate_limits = fetch_activity_detail_with_metadata(
                token_state["token"], activity_id
            )
            budget.update(rate_limits)
            return detail, retries, refresh_used, rate_limits
        except StravaRequestError as error:
            budget.update(error.rate_limits)
            if error.status_code == 429:
                raise QuotaStop("rate_limited", error.rate_limits) from error
            if error.status_code == 401 and not refresh_used:
                token_state["token"] = refresh_access_token(token_state["cfg"])["access_token"]
                refresh_used = True
                retries += 1
                continue
            if error.status_code not in {500, 502, 503, 504}:
                raise
            latest_error = error
        except StravaNetworkError as error:
            latest_error = error

        if retries >= args.max_retries:
            raise latest_error
        delay = min(MAX_BACKOFF_SECONDS, args.retry_base_seconds * (2 ** retries))
        time.sleep(delay + random.random() * min(0.25, delay / 4))
        retries += 1


def result_template(activity_id, batch_number):
    return {
        "activity_id": str(activity_id),
        "batch_number": batch_number,
        "request_outcome": "not_requested",
        "persistence_outcome": "not_attempted",
        "failure_class": None,
        "retry_count": 0,
        "description_state": "omitted",
        "description_key_observed": False,
        "private_note_state": "omitted",
        "private_note_key_observed": False,
        "observed_at": None,
    }


def acquire_backfill_lock(cfg):
    conn = connect_db(cfg)
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s) AS locked", (BACKFILL_LOCK_KEY,))
        row = cur.fetchone()
    if not row["locked"]:
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


def apply_backfill(args, cfg=None):
    cfg = cfg or get_config()
    lock_conn = acquire_backfill_lock(cfg)
    results = []
    quota_stop = None
    stopped = False
    token_state = {"cfg": cfg, "token": refresh_access_token(cfg)["access_token"]}
    budget = RateBudget(args.daily_headroom, args.max_requests)
    try:
        with connect_db(cfg) as conn:
            selected = fetch_population_rows(conn, args, args.batch_size)
        for row in selected:
            activity_id = str(row["activity_id"])
            result = result_template(activity_id, 1)
            try:
                detail, retries, _, rate_limits = fetch_with_retries(
                    activity_id, token_state, budget, args, False
                )
                narrative = extract_activity_narrative(detail)
                result.update(state_summary(narrative))
                result["request_outcome"] = "ok"
                result["retry_count"] = retries
                result["rate_limits"] = rate_limits
                if any(narrative[field]["state"] == "malformed" for field in NARRATIVE_FIELDS):
                    result["failure_class"] = "malformed_narrative"
                else:
                    observed_at = datetime.now(timezone.utc)
                    with connect_db(cfg) as conn:
                        with conn.cursor() as cur:
                            changed = upsert_activity_narrative(
                                cur,
                                activity_id,
                                narrative,
                                observed_at,
                                record_inspection=True,
                            )
                        conn.commit()
                    has_field_update = any(
                        narrative[field]["state"] not in {"omitted", "malformed"}
                        for field in NARRATIVE_FIELDS
                    )
                    result["persistence_outcome"] = (
                        "updated" if has_field_update and changed else
                        "checkpointed" if changed else
                        "no_observed_fields"
                    )
                    result["observed_at"] = observed_at.isoformat()
            except QuotaStop as error:
                quota_stop = error.reason
                result["failure_class"] = "rate_limited" if error.reason == "rate_limited" else None
                result["request_outcome"] = "stopped"
                result["rate_limits"] = error.rate_limits
                results.append(result)
                stopped = True
                break
            except Exception as error:
                result["request_outcome"] = "failed"
                result["failure_class"] = classify_failure(error)
                results.append(result)
                if result["failure_class"] == "database_failed":
                    stopped = True
                    break
            results.append(result) if result not in results else None
    finally:
        release_backfill_lock(lock_conn)
    return results, quota_stop, stopped, budget, len(selected)


def summarize(
    results,
    population,
    args,
    budget,
    quota_stop=None,
    preview=False,
    remaining_eligible_count=None,
    selected_count=None,
):
    successful = sum(
        result["request_outcome"] == "ok"
        and result["failure_class"] is None
        and result["persistence_outcome"] in {
            "updated", "checkpointed", "no_observed_fields"
        }
        for result in results
    )
    stopped = sum(result["request_outcome"] == "stopped" for result in results)
    attempted = sum(
        result["request_outcome"] in {"ok", "failed"}
        or (
            result["request_outcome"] == "stopped"
            and result["failure_class"] == "rate_limited"
        )
        for result in results
    )
    failures = sum(
        bool(result["failure_class"])
        and result["request_outcome"] != "stopped"
        for result in results
    )
    return {
        "run_mode": "preview" if preview else "apply",
        "total_eligible_at_start": population["eligible_count"],
        "skipped_already_observed_count": population["fully_observed_count"],
        "selected_count": 0 if preview else (
            len(results) if selected_count is None else selected_count
        ),
        "attempted_count": 0 if preview else attempted,
        "successful_count": 0 if preview else successful,
        "failed_count": failures,
        "updated_count": sum(result["persistence_outcome"] == "updated" for result in results),
        "no_observed_fields_count": sum(
            result["persistence_outcome"] == "no_observed_fields" for result in results
        ),
        "checkpointed_count": sum(
            result["persistence_outcome"] == "checkpointed" for result in results
        ),
        "quota_stopped_count": stopped,
        "unprocessed_count": max(
            0,
            (0 if preview else (selected_count or len(results)))
            - attempted - successful - failures - stopped,
        ),
        "retried_count": sum(result.get("retry_count", 0) > 0 for result in results),
        "quota_stop_reason": quota_stop,
        "remaining_eligible_count": remaining_eligible_count,
        "current_safe_read_limits": budget.safe_read(),
        "header_rate_state": "available" if budget.headers_available else "unavailable",
        "date_start": args.start_date.isoformat(),
        "date_end": args.end_date.isoformat(),
        "overall_status": (
            "preview" if preview else
            "quota_stopped" if quota_stop else
            "failed" if failures else "ok"
        ),
    }


def main(argv=None):
    args = validate_args(build_parser().parse_args(argv))
    db_cfg = get_db_config()
    scope_args = copy.copy(args)
    scope_args.refresh_observed = True
    with connect_db(db_cfg) as conn:
        all_rows = fetch_population_rows(conn, scope_args)
    population = population_summary(all_rows, args)
    if args.preview:
        results = []
        summary = {**population, **summarize(results, population, args, RateBudget(args.daily_headroom), preview=True, remaining_eligible_count=population["eligible_count"])}
        print(json.dumps(summary, sort_keys=True, default=str))
        return 0

    try:
        cfg = get_config()
        results, quota_stop, stopped, budget, selected_count = apply_backfill(args, cfg)
    except BackfillLockUnavailable:
        print(json.dumps({"overall_status": "locked", "failure_class": "backfill_already_running"}, sort_keys=True))
        return 1
    except Exception as error:
        print(json.dumps({"overall_status": "failed", "failure_class": classify_failure(error)}, sort_keys=True))
        return 1

    for result in results:
        print(json.dumps(result, sort_keys=True, default=str))
    with connect_db(db_cfg) as conn:
        remaining_eligible_count = len(fetch_population_rows(conn, args))
    summary = summarize(
        results,
        population,
        args,
        budget,
        quota_stop,
        remaining_eligible_count=remaining_eligible_count,
        selected_count=selected_count,
    )
    print(json.dumps(summary, sort_keys=True, default=str))
    return 2 if quota_stop else (1 if summary["failed_count"] or stopped else 0)


if __name__ == "__main__":
    raise SystemExit(main())