"""Explicit-ID Strava narrative pilot.

The command performs no work without --preview or --apply. Apply fetches at
most three detailed activities and writes only narrative columns.
"""

import argparse
import json
from datetime import datetime, timezone

from activity_utils import NARRATIVE_FIELDS, extract_activity_narrative
from settings import get_config
from strava_client import (
    StravaNetworkError,
    StravaRequestError,
    fetch_activity_detail,
    refresh_access_token,
)


MAX_ACTIVITY_IDS = 3
FAILURE_CLASSES = frozenset({
    "auth_failed",
    "fetch_failed",
    "activity_not_found",
    "schema_not_ready",
    "database_failed",
    "malformed_narrative",
    "unexpected_failure",
})


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--activity-id", action="append", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview", action="store_true")
    mode.add_argument("--apply", action="store_true")
    return parser


def validate_activity_ids(values):
    if not values or len(values) > MAX_ACTIVITY_IDS:
        raise ValueError("provide one to three --activity-id values")

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


def state_summary(narrative):
    return {
        key: value
        for field_name in NARRATIVE_FIELDS
        for key, value in (
            (f"{field_name}_state", narrative[field_name]["state"]),
            (f"{field_name}_key_observed", narrative[field_name]["key_observed"]),
        )
    }


def result_template(activity_id):
    return {
        "activity_id": activity_id,
        "request_outcome": "not_requested",
        "persistence_outcome": "not_attempted",
        "failure_class": None,
        "description_state": "omitted",
        "description_key_observed": False,
        "private_note_state": "omitted",
        "private_note_key_observed": False,
        "observed_at": None,
    }


def preview(activity_ids):
    return [result_template(activity_id) for activity_id in activity_ids]


def classify_failure(error):
    if isinstance(error, StravaRequestError):
        if error.status_code == 401:
            return "auth_failed"
        if error.status_code == 404:
            return "activity_not_found"
        return "fetch_failed"
    if isinstance(error, StravaNetworkError):
        return "fetch_failed"
    if error.__class__.__name__ == "ActivityNarrativeActivityNotFound":
        return "activity_not_found"
    if error.__class__.__name__ in {"UndefinedColumn", "UndefinedTable"}:
        return "schema_not_ready"
    if error.__class__.__module__.startswith("psycopg"):
        return "database_failed"
    return "unexpected_failure"


def summarize(results, preview_mode=False):
    failures = sum(result["failure_class"] is not None for result in results)
    updated = sum(result["persistence_outcome"] == "updated" for result in results)
    no_observed = sum(
        result["persistence_outcome"] == "no_observed_fields" for result in results
    )
    return {
        "requested_count": len(results),
        "attempted_count": 0 if preview_mode else len(results) - failures,
        "successful_count": len(results) - failures,
        "failed_count": failures,
        "updated_count": updated,
        "no_observed_fields_count": no_observed,
        "overall_status": "preview" if preview_mode else ("failed" if failures else "ok"),
    }


def apply_pilot(activity_ids, cfg=None, token=None):
    from db_writer import connect_db, upsert_activity_narrative

    cfg = cfg or get_config()
    token = token or refresh_access_token(cfg)["access_token"]
    results = []

    for activity_id in activity_ids:
        result = result_template(activity_id)
        try:
            detail = fetch_activity_detail(token, activity_id)
            narrative = extract_activity_narrative(detail)
            result.update(state_summary(narrative))
            if any(
                narrative[field_name]["state"] == "malformed"
                for field_name in NARRATIVE_FIELDS
            ):
                result["request_outcome"] = "ok"
                result["failure_class"] = "malformed_narrative"
                results.append(result)
                continue

            observed_at = datetime.now(timezone.utc)
            with connect_db(cfg) as conn:
                with conn.cursor() as cur:
                    updated = upsert_activity_narrative(
                        cur, activity_id, narrative, observed_at
                    )
                conn.commit()
            result["request_outcome"] = "ok"
            result["persistence_outcome"] = (
                "updated" if updated else "no_observed_fields"
            )
            result["observed_at"] = observed_at.isoformat()
        except Exception as error:
            result["request_outcome"] = "failed"
            result["failure_class"] = classify_failure(error)
        results.append(result)

    return results


def main(argv=None):
    args = build_parser().parse_args(argv)
    activity_ids = validate_activity_ids(args.activity_id)
    if args.preview:
        results = preview(activity_ids)
        summary = summarize(results, preview_mode=True)
    else:
        try:
            results = apply_pilot(activity_ids)
        except Exception:
            results = []
            for activity_id in activity_ids:
                result = result_template(activity_id)
                result["request_outcome"] = "not_attempted"
                result["failure_class"] = "auth_failed"
                results.append(result)
        summary = summarize(results)

    for result in results:
        print(json.dumps(result, sort_keys=True))
    print(json.dumps(summary, sort_keys=True))
    return 1 if summary["failed_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())