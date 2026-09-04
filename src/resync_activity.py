import argparse
import json
import sys
import time
from datetime import datetime, timedelta

import psycopg
from psycopg.rows import dict_row

from activity_utils import classify_activity, normalize_activity
from daily_builder import build_daily_training
from db_writer import (
    rebuild_fitness_fatigue,
    replace_weekly_training,
    upsert_daily_training,
    upsert_strava_activities,
)
from gear_db import fetch_gear_display_map
from settings import get_config
from strava_client import fetch_activity_detail, refresh_access_token
from weekly_builder import build_weekly_training


def validate_activity_id(value):
    if value is None or not str(value).strip() or not str(value).isdigit():
        raise ValueError("activity_id must be a positive integer")
    return int(value)


def safe_iso(value):
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def week_start_for_date(date_text):
    value = datetime.strptime(str(date_text)[:10], "%Y-%m-%d").date()
    return (value - timedelta(days=value.weekday())).isoformat()


def compute_rebuild_plan(old_date, new_date):
    date_values = []
    seen = set()

    for candidate in (str(old_date)[:10], str(new_date)[:10]):
        if candidate and candidate not in seen:
            date_values.append(candidate)
            seen.add(candidate)

    week_starts = []
    seen_weeks = set()

    for candidate in date_values:
        week_start = week_start_for_date(candidate)
        if week_start not in seen_weeks:
            week_starts.append(week_start)
            seen_weeks.add(week_start)

    return {"dates": date_values, "week_starts": week_starts}


def _db_activity_to_row(row):
    activity = {
        "id": str(row.get("activity_id") or ""),
        "date_local": safe_iso(row.get("date_local")),
        "name": row.get("name") or "",
        "sport_type": row.get("sport_type") or "",
        "type": row.get("sport_type") or "",
        "moving_sec": int(row.get("moving_sec") or 0),
        "elapsed_sec": int(row.get("elapsed_sec") or 0),
        "distance_mi": float(row.get("distance_mi") or 0.0),
        "elevation_ft": float(row.get("elevation_ft") or 0.0),
        "has_heartrate": bool(row.get("has_heartrate") or False),
        "gear_id": row.get("gear_id") or "",
        "average_hr": row.get("average_hr"),
        "max_hr": row.get("max_hr"),
    }

    activity["activity_category"] = classify_activity(activity)

    if row.get("raw_json") is not None:
        raw_json = row.get("raw_json") or {}
        for key, default_value in {
            "name": activity.get("name"),
            "sport_type": activity.get("sport_type"),
            "type": activity.get("type"),
            "moving_sec": activity.get("moving_sec"),
            "elapsed_sec": activity.get("elapsed_sec"),
            "distance_mi": activity.get("distance_mi"),
            "elevation_ft": activity.get("elevation_ft"),
            "has_heartrate": activity.get("has_heartrate"),
            "gear_id": activity.get("gear_id"),
            "average_hr": activity.get("average_hr"),
            "max_hr": activity.get("max_hr"),
        }.items():
            if key in raw_json and default_value in (None, "", 0, 0.0, False):
                activity[key] = raw_json.get(key)

    activity["date_local"] = safe_iso(activity.get("date_local"))
    return activity


def fetch_activity_detail_row(access_token, activity_id):
    detail = fetch_activity_detail(access_token, activity_id)
    if not detail:
        raise RuntimeError(f"Strava activity {activity_id} not found")
    return normalize_activity(detail)


def fetch_existing_activity(cfg, activity_id):
    with psycopg.connect(
        host=cfg["DB_HOST"],
        port=cfg["DB_PORT"],
        dbname=cfg["DB_NAME"],
        user=cfg["DB_USER"],
        password=cfg["DB_PASSWORD"],
        row_factory=dict_row,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    activity_id,
                    date_local,
                    name,
                    sport_type,
                    activity_category,
                    moving_sec,
                    elapsed_sec,
                    distance_mi,
                    elevation_ft,
                    has_heartrate,
                    average_hr,
                    max_hr,
                    gear_id,
                    bike_name,
                    raw_json
                FROM strava_activities
                WHERE activity_id = %s
                """,
                (str(activity_id),),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return {
                "activity_id": str(row["activity_id"]),
                "date_local": safe_iso(row["date_local"]),
                "name": row["name"],
                "sport_type": row["sport_type"],
                "activity_category": row["activity_category"],
                "moving_sec": row["moving_sec"],
                "elapsed_sec": row["elapsed_sec"],
                "distance_mi": row["distance_mi"],
                "elevation_ft": row["elevation_ft"],
                "has_heartrate": row["has_heartrate"],
                "average_hr": row["average_hr"],
                "max_hr": row["max_hr"],
                "gear_id": row["gear_id"],
                "bike_name": row["bike_name"],
            }


def fetch_date_rows(cfg, date_text):
    with psycopg.connect(
        host=cfg["DB_HOST"],
        port=cfg["DB_PORT"],
        dbname=cfg["DB_NAME"],
        user=cfg["DB_USER"],
        password=cfg["DB_PASSWORD"],
        row_factory=dict_row,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM strava_activities
                WHERE date_local = %s
                ORDER BY activity_id
                """,
                (date_text,),
            )
            return [_db_activity_to_row(row) for row in cur.fetchall()]


def compare_activity_change(old_row, new_row, gear_display_map):
    old_gear = old_row.get("gear_id") if old_row else None
    new_gear = new_row.get("gear_id") if new_row else None

    old_bike = gear_display_map.get(old_gear) if old_gear else None
    new_bike = gear_display_map.get(new_gear) if new_gear else None

    return {
        "date_local": {"old": old_row.get("date_local") if old_row else None, "new": new_row.get("date_local") if new_row else None},
        "name": {"old": old_row.get("name") if old_row else None, "new": new_row.get("name") if new_row else None},
        "sport_type": {"old": old_row.get("sport_type") if old_row else None, "new": new_row.get("sport_type") if new_row else None},
        "activity_category": {"old": old_row.get("activity_category") if old_row else None, "new": new_row.get("activity_category") if new_row else None},
        "moving_sec": {"old": old_row.get("moving_sec") if old_row else None, "new": new_row.get("moving_sec") if new_row else None},
        "elapsed_sec": {"old": old_row.get("elapsed_sec") if old_row else None, "new": new_row.get("elapsed_sec") if new_row else None},
        "distance_mi": {"old": old_row.get("distance_mi") if old_row else None, "new": new_row.get("distance_mi") if new_row else None},
        "elevation_ft": {"old": old_row.get("elevation_ft") if old_row else None, "new": new_row.get("elevation_ft") if new_row else None},
        "has_heartrate": {"old": old_row.get("has_heartrate") if old_row else None, "new": new_row.get("has_heartrate") if new_row else None},
        "hr_summary": {"old": {"average_hr": old_row.get("average_hr") if old_row else None, "max_hr": old_row.get("max_hr") if old_row else None}, "new": {"average_hr": new_row.get("average_hr") if new_row else None, "max_hr": new_row.get("max_hr") if new_row else None}},
        "gear_id": {"old": old_gear, "new": new_gear},
        "bike_name": {"old": old_bike, "new": new_bike},
    }


def normalize_compare_value(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return value.strip()
    if hasattr(value, "as_tuple"):
        try:
            return float(value)
        except (TypeError, ValueError):
            return str(value).strip()
    if hasattr(value, "__float__"):
        try:
            return float(value)
        except (TypeError, ValueError):
            return str(value).strip()
    return str(value).strip()


def compare_numeric_field(old_value, new_value, tolerance=1e-6):
    if old_value is None and new_value is None:
        return False
    if old_value is None or new_value is None:
        return True
    try:
        old_float = float(old_value)
        new_float = float(new_value)
    except (TypeError, ValueError):
        return old_value != new_value
    return abs(old_float - new_float) > tolerance


def build_missing_load_warning(activity_id, daily_row):
    if not daily_row:
        return None
    selected_activity_id = str(daily_row.get("main_ride_id") or "")
    if selected_activity_id != str(activity_id):
        return None
    if int(daily_row.get("main_ride_load") or 0) != 0:
        return None
    source = str(daily_row.get("main_ride_load_source") or "").strip()
    if source:
        return None
    return f"Activity {activity_id} has no supported HR or RPE load source; calculated load remains 0."


def classify_changed_fields(old_row, new_row):
    daily_fields = [
        "date_local",
        "name",
        "sport_type",
        "activity_category",
        "moving_sec",
        "elapsed_sec",
        "distance_mi",
        "elevation_ft",
        "has_heartrate",
        "average_hr",
        "max_hr",
        "gear_id",
    ]
    changed = []

    for field in daily_fields:
        old_value = old_row.get(field)
        new_value = new_row.get(field)

        if field in {"moving_sec", "elapsed_sec"}:
            if int(old_value or 0) != int(new_value or 0):
                changed.append(field)
            continue

        if field in {"distance_mi", "elevation_ft", "average_hr", "max_hr"}:
            if compare_numeric_field(old_value, new_value):
                changed.append(field)
            continue

        if field == "has_heartrate":
            if bool(old_value) != bool(new_value):
                changed.append(field)
            continue

        if field in {"date_local", "name", "sport_type", "activity_category", "gear_id"}:
            if normalize_compare_value(old_value) != normalize_compare_value(new_value):
                changed.append(field)

    return changed


def classify_weekly_rebuild(changed_fields):
    weekly_fields = [
        "date_local",
        "activity_category",
        "moving_sec",
        "elapsed_sec",
        "distance_mi",
        "elevation_ft",
        "has_heartrate",
        "average_hr",
        "max_hr",
    ]
    if not changed_fields:
        return False, "no training-impacting change"
    if any(field in weekly_fields for field in changed_fields):
        return True, "training-impacting fields changed"
    return False, "gear-only or metadata-only change"


def fetch_existing_activity_tx(cur, activity_id):
    cur.execute(
        """
        SELECT
            activity_id,
            date_local,
            name,
            sport_type,
            activity_category,
            moving_sec,
            elapsed_sec,
            distance_mi,
            elevation_ft,
            has_heartrate,
            average_hr,
            max_hr,
            gear_id,
            bike_name,
            raw_json
        FROM strava_activities
        WHERE activity_id = %s
        """,
        (str(activity_id),),
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"No existing row found for activity_id={activity_id}")
    return {
        "activity_id": str(row["activity_id"]),
        "date_local": safe_iso(row["date_local"]),
        "name": row["name"],
        "sport_type": row["sport_type"],
        "activity_category": row["activity_category"],
        "moving_sec": int(row["moving_sec"] or 0),
        "elapsed_sec": int(row["elapsed_sec"] or 0),
        "distance_mi": float(row["distance_mi"] or 0.0),
        "elevation_ft": float(row["elevation_ft"] or 0.0),
        "has_heartrate": bool(row["has_heartrate"] or False),
        "average_hr": row["average_hr"],
        "max_hr": row["max_hr"],
        "gear_id": row["gear_id"],
        "bike_name": row["bike_name"],
    }


def fetch_date_activity_rows(cur, date_text):
    cur.execute(
        """
        SELECT *
        FROM strava_activities
        WHERE date_local = %s
        ORDER BY activity_id
        """,
        (date_text,),
    )
    return [_db_activity_to_row(row) for row in cur.fetchall()]


def fetch_all_daily_rows(cur):
    cur.execute(
        """
        SELECT
            date,
            activity_count,
            activity_categories,
            ride_count,
            walk_count,
            hike_count,
            strength_count,
            mobility_count,
            ski_count,
            run_count,
            other_count,
            main_ride_id,
            main_ride_name,
            main_ride_sport_type,
            main_ride_category,
            main_ride_time,
            main_ride_elapsed_time,
            main_ride_miles,
            main_ride_elevation_ft,
            main_ride_gear_id,
            main_ride_bike_name,
            main_ride_rpe,
            main_ride_load_source,
            main_ride_load,
            main_ride_load_score,
            main_ride_band,
            main_ride_load_text,
            main_ride_hr_zones,
            z1_sec,
            z2_sec,
            z3_sec,
            z4_sec,
            z5_sec,
            z4_z5_sec,
            stream_moving_sec,
            other_activity_count,
            other_activity_names,
            other_time,
            other_miles,
            other_elevation_ft,
            other_load,
            other_load_raw,
            total_load,
            updated_at
        FROM daily_training
        ORDER BY date
        """
    )
    return cur.fetchall()


def delete_daily_training_row(cur, date_text):
    cur.execute("DELETE FROM daily_training WHERE date = %s", (date_text,))


def resync_activity(cfg, activity_id):
    activity_id = validate_activity_id(activity_id)
    started_at = time.monotonic()

    token = refresh_access_token(cfg)
    access_token = token["access_token"]
    refreshed = fetch_activity_detail_row(access_token, activity_id)

    with psycopg.connect(
        host=cfg["DB_HOST"],
        port=cfg["DB_PORT"],
        dbname=cfg["DB_NAME"],
        user=cfg["DB_USER"],
        password=cfg["DB_PASSWORD"],
        row_factory=dict_row,
    ) as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(%s)", (activity_id,))
                existing = fetch_existing_activity_tx(cur, activity_id)
                old_date = existing.get("date_local")
                old_gear_id = existing.get("gear_id")
                new_date = refreshed.get("date_local")
                new_gear_id = refreshed.get("gear_id")

                changed_fields = classify_changed_fields(existing, refreshed)
                daily_rebuilt = bool(changed_fields)
                weekly_rebuilt, weekly_skip_reason = classify_weekly_rebuild(changed_fields)
                rebuilt_dates = []
                deleted_daily_dates = []
                warnings = []

                upsert_strava_activities(cur, [refreshed])

                gear_display_map = fetch_gear_display_map(cfg)

                if daily_rebuilt:
                    for date_text in sorted({old_date, new_date} - {None}):
                        rows = fetch_date_activity_rows(cur, date_text)
                        if date_text == old_date:
                            rows = [row for row in rows if str(row.get("id")) != str(activity_id)]
                        if date_text == new_date:
                            rows = [row for row in rows if str(row.get("id")) != str(activity_id)]
                            rows.append(refreshed)

                        rebuilt_daily, rebuild_warnings = build_daily_training(
                            rows=rows,
                            access_token=access_token,
                            chronic_c=cfg["LOAD_CHRONIC_C"],
                            gear_display_map=gear_display_map,
                        )
                        warnings.extend(rebuild_warnings)

                        if rebuilt_daily:
                            rebuilt_dates.append(date_text)
                            upsert_daily_training(cur, rebuilt_daily)
                        elif date_text == old_date and date_text != new_date:
                            delete_daily_training_row(cur, date_text)
                            deleted_daily_dates.append(date_text)

                    if old_date and old_date != new_date and old_date not in rebuilt_dates and old_date not in deleted_daily_dates:
                        existing_old_date_rows = fetch_date_activity_rows(cur, old_date)
                        if not existing_old_date_rows:
                            delete_daily_training_row(cur, old_date)
                            deleted_daily_dates.append(old_date)

                    if new_date and new_date not in rebuilt_dates and old_date != new_date:
                        new_rows = fetch_date_activity_rows(cur, new_date)
                        if new_rows:
                            rebuilt_new_daily, _ = build_daily_training(
                                rows=new_rows,
                                access_token=access_token,
                                chronic_c=cfg["LOAD_CHRONIC_C"],
                                gear_display_map=gear_display_map,
                            )
                            if rebuilt_new_daily:
                                upsert_daily_training(cur, rebuilt_new_daily)
                                if new_date not in rebuilt_dates:
                                    rebuilt_dates.append(new_date)

                if daily_rebuilt:
                    for date_text in rebuilt_dates:
                        built_rows = fetch_date_activity_rows(cur, date_text)
                        if built_rows:
                            daily_rows = build_daily_training(
                                rows=built_rows,
                                access_token=access_token,
                                chronic_c=cfg["LOAD_CHRONIC_C"],
                                gear_display_map=gear_display_map,
                            )[0]
                            warning = build_missing_load_warning(activity_id, daily_rows[0] if daily_rows else None)
                            if warning:
                                warnings.append(warning)

                fitness_fatigue_rebuilt = bool(changed_fields) and any(
                    field not in {"name", "gear_id"}
                    for field in changed_fields
                )
                if fitness_fatigue_rebuilt:
                    rebuild_fitness_fatigue(cur)

                if weekly_rebuilt:
                    all_daily_rows = fetch_all_daily_rows(cur)
                    weekly_rows = build_weekly_training(all_daily_rows)
                    replace_weekly_training(cur, weekly_rows)
                else:
                    weekly_rows = []

                conn.commit()
        except Exception:
            conn.rollback()
            raise

    return {
        "status": "success",
        "activity_id": activity_id,
        "activity_name": refreshed.get("name"),
        "changed_fields": changed_fields,
        "old_date": old_date,
        "new_date": new_date,
        "rebuilt_dates": rebuilt_dates,
        "deleted_daily_dates": deleted_daily_dates,
        "daily_rebuilt": daily_rebuilt,
        "weekly_rebuilt": weekly_rebuilt,
        "weekly_rows_rebuilt": len(weekly_rows),
        "fitness_fatigue_rebuilt": fitness_fatigue_rebuilt,
        "weekly_skip_reason": weekly_skip_reason if not weekly_rebuilt else None,
        "old_gear_id": old_gear_id,
        "new_gear_id": new_gear_id,
        "old_bike_name": fetch_gear_display_map(cfg).get(old_gear_id) if old_gear_id else None,
        "new_bike_name": fetch_gear_display_map(cfg).get(new_gear_id) if new_gear_id else None,
        "warnings": warnings,
        "elapsed_seconds": round(time.monotonic() - started_at, 3),
    }


def preview_resync(cfg, activity_id):
    activity_id = validate_activity_id(activity_id)

    existing = fetch_existing_activity(cfg, activity_id)
    if existing is None:
        raise RuntimeError(f"No existing row found for activity_id={activity_id}")

    token = refresh_access_token(cfg)
    access_token = token["access_token"]
    refreshed = fetch_activity_detail_row(access_token, activity_id)

    gear_display_map = fetch_gear_display_map(cfg)
    old_row = {**existing}
    new_row = {**refreshed}
    changes = compare_activity_change(old_row, new_row, gear_display_map)
    plan = compute_rebuild_plan(existing.get("date_local"), refreshed.get("date_local"))

    base_date_rows = {}
    for date_text in plan["dates"]:
        base_date_rows[date_text] = fetch_date_rows(cfg, date_text)

    preview_date_rows = {}
    for date_text in plan["dates"]:
        rows = list(base_date_rows.get(date_text, []))
        if date_text == existing.get("date_local"):
            rows = [row for row in rows if str(row.get("id")) != str(activity_id)]
        if date_text == refreshed.get("date_local"):
            rows.append(refreshed)
        preview_date_rows[date_text] = rows

    for date_text, rows in preview_date_rows.items():
        for row in rows:
            if row.get("date_local") is None or not isinstance(row.get("date_local"), str) or len(row.get("date_local")) != 10:
                raise ValueError(f"Preview activity has invalid date_local for {row.get('id')}: {row.get('date_local')!r}")
            if row.get("date_local") == "unknown":
                raise ValueError(f"Preview activity has date_local='unknown' for {row.get('id')}")

    daily_plan = {}
    warnings = []
    for date_text in plan["dates"]:
        rebuilt_daily, rebuild_warnings = build_daily_training(
            rows=preview_date_rows.get(date_text, []),
            access_token=access_token,
            chronic_c=cfg["LOAD_CHRONIC_C"],
            gear_display_map=gear_display_map,
        )
        daily_plan[date_text] = rebuilt_daily
        warnings.extend(rebuild_warnings)

    for date_text, rows in daily_plan.items():
        if rows:
            if len(rows) != 1:
                raise ValueError(f"Affected date {date_text} did not produce exactly one Daily aggregate row: {len(rows)}")
            if rows[0].get("date") == "unknown":
                raise ValueError(f"Preview Daily row for {date_text} has date='unknown'")
            if rows[0].get("date") != date_text:
                raise ValueError(f"Preview Daily row for {date_text} returned unexpected date: {rows[0].get('date')!r}")

    preview_rows = []
    for rows in preview_date_rows.values():
        preview_rows.extend(rows)

    selected_preview_ids = [str(row.get("id")) for row in preview_rows if row.get("id") is not None]
    if str(activity_id) not in selected_preview_ids:
        raise ValueError(f"Preview activity {activity_id} is missing from the affected preview sets")
    if selected_preview_ids.count(str(activity_id)) != 1:
        raise ValueError(f"Preview activity {activity_id} appears {selected_preview_ids.count(str(activity_id))} times in the affected preview sets")

    all_daily_rows = []
    with psycopg.connect(
        host=cfg["DB_HOST"],
        port=cfg["DB_PORT"],
        dbname=cfg["DB_NAME"],
        user=cfg["DB_USER"],
        password=cfg["DB_PASSWORD"],
        row_factory=dict_row,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    date,
                    total_load,
                    main_ride_load,
                    other_load,
                    ride_count,
                    walk_count,
                    hike_count,
                    strength_count,
                    mobility_count,
                    ski_count,
                    run_count,
                    other_count,
                    main_ride_band,
                    updated_at
                FROM daily_training
                ORDER BY date
                """
            )
            all_daily_rows = cur.fetchall()

    preview_daily_by_date = {row["date"].isoformat(): row for row in all_daily_rows if row.get("date") is not None}
    for date_text, rows in daily_plan.items():
        if rows:
            preview_daily_by_date[date_text] = rows[0]

    affected_week_starts = []
    seen_weeks = set()
    for date_text in plan["dates"]:
        week_start = week_start_for_date(date_text)
        if week_start not in seen_weeks:
            affected_week_starts.append(week_start)
            seen_weeks.add(week_start)

    preview_daily_history = list(preview_daily_by_date.values())
    weekly_rows = build_weekly_training(preview_daily_history)
    affected_week_rows = [
        row for row in weekly_rows if row.get("week_start") in affected_week_starts
    ]

    if not affected_week_rows:
        raise ValueError("Preview weekly rebuild produced no affected weekly rows")

    changed_fields = classify_changed_fields(existing, refreshed)
    daily_rebuilt = bool(changed_fields)
    weekly_rebuilt, weekly_skip_reason = classify_weekly_rebuild(changed_fields)

    for date_text, rows in daily_plan.items():
        if not rows and date_text in plan["dates"]:
            if date_text == existing.get("date_local") and date_text != refreshed.get("date_local"):
                continue

    payload = {
        "status": "success",
        "dry_run": True,
        "activity_id": activity_id,
        "changed_fields": changed_fields,
        "affected_dates": plan["dates"],
        "daily_rebuilt": daily_rebuilt,
        "weekly_rebuilt": weekly_rebuilt,
        "weekly_skip_reason": weekly_skip_reason if not weekly_rebuilt else None,
        "weekly_validation_only": not weekly_rebuilt,
        "planned_daily_rows": daily_plan,
        "planned_weekly_rows": affected_week_rows,
        "planned_deleted_daily_dates": [],
        "writes_prevented": True,
        "warnings": warnings,
    }

    if daily_rebuilt and existing.get("date_local") and refreshed.get("date_local") and existing.get("date_local") != refreshed.get("date_local"):
        old_date_rows = preview_date_rows.get(existing.get("date_local"), [])
        if not old_date_rows:
            payload["planned_deleted_daily_dates"] = [existing.get("date_local")]

    for daily_row in daily_plan.get(refreshed.get("date_local") or "", []):
        warning = build_missing_load_warning(activity_id, daily_row)
        if warning and warning not in payload["warnings"]:
            payload["warnings"].append(warning)

    return json.loads(json.dumps(payload, sort_keys=True, default=str))


def main():
    parser = argparse.ArgumentParser(description="Resync a single Strava activity in one transaction.")
    parser.add_argument("activity_id", help="Strava activity id to resync")
    parser.add_argument("--dry-run", action="store_true", help="preview the resync without writing any database rows")
    args = parser.parse_args()

    cfg = get_config()

    try:
        if args.dry_run:
            payload = preview_resync(cfg, args.activity_id)
            sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str))
            sys.stdout.write("\n")
            return 0

        payload = resync_activity(cfg, args.activity_id)
        sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str))
        sys.stdout.write("\n")
        return 0
    except Exception:
        try:
            activity_id = validate_activity_id(args.activity_id)
        except Exception:
            activity_id = None

        error_payload = {
            "status": "error",
            "activity_id": activity_id,
            "error": "resync failed",
        }
        sys.stdout.write(json.dumps(error_payload, sort_keys=True, separators=(",", ":"), default=str))
        sys.stdout.write("\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
