import json
import logging
from collections.abc import Mapping
from datetime import date, datetime
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from activity_utils import (
    NARRATIVE_FIELDS,
    classify_activity,
    validate_activity_narrative,
)
from daily_builder import build_daily_training
from fitness_fatigue_builder import build_fitness_fatigue, validate_fitness_fatigue_rows
from settings import get_fitness_fatigue_config
from weekly_builder import build_weekly_training

logger = logging.getLogger(__name__)


def connect_db(cfg):
    return psycopg.connect(
        host=cfg["DB_HOST"],
        port=cfg["DB_PORT"],
        dbname=cfg["DB_NAME"],
        user=cfg["DB_USER"],
        password=cfg["DB_PASSWORD"],
        row_factory=dict_row,
    )


def write_training_to_db(
    cfg,
    activities,
    daily_rows,
    weekly_rows,
    warnings,
    run_at_utc,
    access_token=None,
    chronic_c=None,
):
    if not cfg.get("WRITE_DB"):
        return

    with psycopg.connect(
        host=cfg["DB_HOST"],
        port=cfg["DB_PORT"],
        dbname=cfg["DB_NAME"],
        user=cfg["DB_USER"],
        password=cfg["DB_PASSWORD"],
        row_factory=dict_row,
    ) as conn:
        with conn.cursor() as cur:

            logger.info("DB write: activities")
            old_dates = fetch_activity_dates(cur, activities)
            upsert_strava_activities(cur, activities)

            logger.info("DB write: daily")
            affected_dates = affected_activity_dates(old_dates, activities)
            rebuilt_daily, rebuild_warnings, _ = rebuild_daily_for_dates(
                cur=cur,
                dates=affected_dates,
                access_token=access_token,
                chronic_c=chronic_c if chronic_c is not None else cfg["LOAD_CHRONIC_C"],
            )
            warnings = list(warnings or []) + rebuild_warnings
            rebuild_fitness_fatigue(cur)
            logger.info("DB rebuild: weekly from full daily_training")
            all_daily_rows = fetch_all_daily_training_for_weekly(cur)
            weekly_rows = build_weekly_training(all_daily_rows)
            replace_weekly_training(cur, weekly_rows)

            logger.info("DB write: sync log")

            insert_sync_run_log(
                cur=cur,
                run_at_utc=run_at_utc,
                days_back=cfg["DAYS_BACK"],
                activity_count=len(activities),
                daily_rows=len(rebuilt_daily),
                weekly_rows=len(weekly_rows),
                warning_count=len(warnings),
                status="ok" if not warnings else "warnings",
            )

        conn.commit()

    return {
        "daily_rows": rebuilt_daily,
        "weekly_rows": weekly_rows,
        "warnings": warnings,
    }


def date_text(value):
    if value is None:
        return None
    return value.isoformat()[:10] if hasattr(value, "isoformat") else str(value)[:10]


def date_value(value):
    return value if isinstance(value, date) else date.fromisoformat(date_text(value))


def fetch_activity_dates(cur, activities):
    activity_ids = [
        str(activity.get("id"))
        for activity in activities
        if activity.get("id") is not None
    ]
    if not activity_ids:
        return set()

    cur.execute(
        """
        SELECT date_local
        FROM strava_activities
        WHERE activity_id = ANY(%s)
        """,
        (activity_ids,),
    )
    return {date_text(row["date_local"]) for row in cur.fetchall() if row.get("date_local") is not None}


def affected_activity_dates(old_dates, activities):
    new_dates = {
        date_text(activity.get("date_local"))
        for activity in activities
        if date_text(activity.get("date_local"))
    }
    return set(old_dates) | new_dates


def db_activity_to_row(row):
    activity = {
        "id": str(row.get("activity_id") or ""),
        "date_local": date_text(row.get("date_local")),
        "name": row.get("name") or "",
        "sport_type": row.get("sport_type") or "",
        "type": row.get("sport_type") or "",
        "moving_sec": int(row.get("moving_sec") or 0),
        "elapsed_sec": int(row.get("elapsed_sec") or 0),
        "distance_mi": float(row.get("distance_mi") or 0.0),
        "elevation_ft": float(row.get("elevation_ft") or 0.0),
        "has_heartrate": bool(row.get("has_heartrate") or False),
        "gear_id": row.get("gear_id") or "",
        "bike_name": row.get("bike_name") or "",
        "average_hr": row.get("average_hr"),
        "max_hr": row.get("max_hr"),
    }
    activity["activity_category"] = row.get("activity_category") or classify_activity(activity)
    return activity


def fetch_activity_rows_for_dates(cur, dates):
    if not dates:
        return []

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
            bike_name
        FROM strava_activities
        WHERE date_local = ANY(%s)
        ORDER BY date_local, activity_id
        """,
        ([date_value(value) for value in sorted(dates)],),
    )
    return [db_activity_to_row(row) for row in cur.fetchall()]


def rebuild_daily_for_dates(cur, dates, access_token, chronic_c):
    if not dates:
        return [], [], []
    if access_token is None:
        raise ValueError("access_token is required for an authoritative Daily rebuild")

    persisted_rows = fetch_activity_rows_for_dates(cur, dates)
    gear_display_map = {}
    for row in persisted_rows:
        if row.get("gear_id"):
            gear_display_map[row["gear_id"]] = row.get("bike_name") or row["gear_id"]

    daily_rows, warnings = build_daily_training(
        rows=persisted_rows,
        access_token=access_token,
        chronic_c=chronic_c,
        gear_display_map=gear_display_map,
    )
    rebuilt_dates = {date_text(row.get("date")) for row in daily_rows}
    deleted_dates = []
    for date_value in sorted(dates):
        if date_value not in rebuilt_dates:
            cur.execute("DELETE FROM daily_training WHERE date = %s", (date_value,))
            deleted_dates.append(date_value)
    upsert_daily_training(cur, daily_rows)
    return daily_rows, warnings, deleted_dates


def fetch_daily_load_rows(cur, start_date, through_date):
    cur.execute(
        """
        SELECT
            "date",
            total_load
        FROM public.daily_training
        WHERE "date" >= %s
          AND "date" <= %s
        ORDER BY "date"
        """,
        (start_date, through_date),
    )
    columns = [column.name for column in cur.description]
    rows = cur.fetchall()
    return [
        dict(row) if isinstance(row, Mapping) else dict(zip(columns, row))
        for row in rows
    ]


def rebuild_fitness_fatigue(cur):
    logger.info("Fitness/Fatigue/Form rebuild starting")

    try:
        model_rows, model_config, through_date, _ = prepare_fitness_fatigue(cur)
        replace_fitness_fatigue(cur, model_rows)
    except Exception:
        logger.exception("Fitness/Fatigue/Form rebuild failed")
        raise

    logger.info("Fitness/Fatigue/Form rebuild completed: rows=%s", len(model_rows))


def prepare_fitness_fatigue(cur):
    model_config = get_fitness_fatigue_config()
    through_date = datetime.now(ZoneInfo(model_config["app_timezone"])).date()
    logger.info(
        "Fitness/Fatigue/Form config: start=%s through=%s model_version=%s",
        model_config["start_date"],
        through_date,
        model_config["model_version"],
    )

    source_rows = fetch_daily_load_rows(
        cur,
        model_config["start_date"],
        through_date,
    )
    model_rows = build_fitness_fatigue(
        daily_load_rows=source_rows,
        start_date=model_config["start_date"],
        through_date=through_date,
        fitness_days=model_config["fitness_days"],
        fatigue_days=model_config["fatigue_days"],
        model_version=model_config["model_version"],
    )
    validate_fitness_fatigue_rows(
        model_rows,
        model_config["start_date"],
        through_date,
        model_config["model_version"],
    )
    logger.info(
        "Fitness/Fatigue/Form source rows=%s generated rows=%s zero-load days=%s",
        len(source_rows),
        len(model_rows),
        sum(1 for row in model_rows if row["daily_load"] == 0),
    )
    return model_rows, model_config, through_date, source_rows


def replace_fitness_fatigue(cur, model_rows):
    cur.execute("DELETE FROM public.daily_fitness_fatigue")
    for row in model_rows:
        cur.execute(
            """
            INSERT INTO public.daily_fitness_fatigue (
                "date",
                daily_load,
                fitness,
                fatigue,
                form,
                model_version,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, now())
            """,
            (
                row["date"],
                row["daily_load"],
                row["fitness"],
                row["fatigue"],
                row["form"],
                row["model_version"],
            ),
        )
def fetch_all_daily_training_for_weekly(cur):
    cur.execute("""
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
            main_ride_band
        FROM daily_training
        ORDER BY date
    """)

    columns = [column.name for column in cur.description]
    return [dict(row) if isinstance(row, Mapping) else dict(zip(columns, row)) for row in cur.fetchall()]


def replace_weekly_training(cur, weekly_rows):
    cur.execute("DELETE FROM weekly_training")
    upsert_weekly_training(cur, weekly_rows)

def collect_gear_ids(activities):
    gear_ids = set()

    for activity in activities:
        gear_id = activity.get("gear_id")
        if gear_id:
            gear_ids.add(gear_id)

    return sorted(gear_ids)


def infer_gear_type(gear_id):
    if not gear_id:
        return "Unknown"

    if gear_id.startswith("b"):
        return "Bike"

    if gear_id.startswith("g"):
        return "Shoe"

    return "Unknown"


def infer_gear_category(gear_id):
    gear_type = infer_gear_type(gear_id)

    if gear_type == "Bike":
        return "Unknown Bike"

    if gear_type == "Shoe":
        return "Shoe"

    return "Unknown"


def ensure_gear_records(cur, activities):
    gear_ids = collect_gear_ids(activities)

    if not gear_ids:
        return

    sql = """
        INSERT INTO gear (
            gear_id,
            gear_name,
            gear_type,
            category,
            retired
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            FALSE
        )
        ON CONFLICT (gear_id)
        DO NOTHING
    """

    for gear_id in gear_ids:
        gear_type = infer_gear_type(gear_id)
        category = infer_gear_category(gear_id)

        cur.execute(
            sql,
            (
                gear_id,
                f"Unknown Gear {gear_id}",
                gear_type,
                category,
            ),
        )


def fetch_gear_display_names(cur, activities):
    gear_ids = collect_gear_ids(activities)

    if not gear_ids:
        return {}

    cur.execute(
        """
        SELECT
            gear_id,
            brand,
            model_year,
            gear_name
        FROM gear
        WHERE gear_id = ANY(%s)
        """,
        (gear_ids,),
    )

    rows = cur.fetchall()
    display_names = {}

    for row in rows:
        if isinstance(row, Mapping):
            gear_id = row["gear_id"]
            brand = row["brand"]
            model_year = row["model_year"]
            gear_name = row["gear_name"]
        else:
            gear_id, brand, model_year, gear_name = row
        parts = []

        if model_year:
            parts.append(str(model_year))

        if brand:
            parts.append(brand)

        if gear_name:
            parts.append(gear_name)

        display_names[gear_id] = " ".join(parts) if parts else gear_id

    return display_names

def upsert_strava_activities(cur, activities):
    ensure_gear_records(cur, activities)
    gear_display_names = fetch_gear_display_names(cur, activities)
    sql = """
        INSERT INTO strava_activities (
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
            raw_json,
            updated_at
        )
        VALUES (
            %(activity_id)s,
            %(date_local)s,
            %(name)s,
            %(sport_type)s,
            %(activity_category)s,
            %(moving_sec)s,
            %(elapsed_sec)s,
            %(distance_mi)s,
            %(elevation_ft)s,
            %(has_heartrate)s,
            %(average_hr)s,
            %(max_hr)s,
            %(gear_id)s,
            %(bike_name)s,
            %(raw_json)s::jsonb,
            now()
        )
        ON CONFLICT (activity_id)
        DO UPDATE SET
            date_local = EXCLUDED.date_local,
            name = EXCLUDED.name,
            sport_type = EXCLUDED.sport_type,
            activity_category = EXCLUDED.activity_category,
            moving_sec = EXCLUDED.moving_sec,
            elapsed_sec = EXCLUDED.elapsed_sec,
            distance_mi = EXCLUDED.distance_mi,
            elevation_ft = EXCLUDED.elevation_ft,
            has_heartrate = EXCLUDED.has_heartrate,
            average_hr = EXCLUDED.average_hr,
            max_hr = EXCLUDED.max_hr,
            gear_id = EXCLUDED.gear_id,
            bike_name = EXCLUDED.bike_name,
            raw_json = EXCLUDED.raw_json,
            updated_at = now()
    """

    for activity in activities:
        gear_id = activity.get("gear_id") or None

        params = {
            "activity_id": activity.get("id"),
            "date_local": activity.get("date_local"),
            "name": activity.get("name"),
            "sport_type": activity.get("sport_type"),
            "activity_category": activity.get("activity_category"),
            "moving_sec": int_or_none(activity.get("moving_sec")),
            "elapsed_sec": int_or_none(activity.get("elapsed_sec")),
            "distance_mi": activity.get("distance_mi"),
            "elevation_ft": int_or_none(activity.get("elevation_ft")),
            "has_heartrate": bool(activity.get("has_heartrate")),
            "average_hr": activity.get("average_hr"),
            "max_hr": activity.get("max_hr"),
            "gear_id": gear_id,
            "bike_name": gear_display_names.get(gear_id) if gear_id else None,
            "raw_json": json.dumps(activity),
        }
        for key, value in params.items():
            if isinstance(value, dict):
                raise TypeError(
                    f"Dict value found in strava_activities params: key={key}, value={value}"
                )
        cur.execute(sql, params)


class ActivityNarrativeActivityNotFound(Exception):
    pass


def upsert_activity_narrative(cur, activity_id, narrative, observed_at=None):
    validate_activity_narrative(narrative)
    if any(
        narrative[field_name]["state"] == "malformed"
        for field_name in NARRATIVE_FIELDS
    ):
        return False
    updates = {
        "narrative_observed_at": observed_at,
    }
    set_clauses = ["narrative_observed_at = %(narrative_observed_at)s"]

    for field_name in NARRATIVE_FIELDS:
        patch = narrative[field_name]
        if patch["state"] in {"omitted", "malformed"}:
            continue

        updates[field_name] = patch["value"]
        updates[f"{field_name}_observed"] = patch["key_observed"]
        set_clauses.extend(
            [
                f"{field_name} = %({field_name})s",
                f"{field_name}_observed = %({field_name}_observed)s",
            ]
        )

    if len(set_clauses) == 1:
        return False

    updates["activity_id"] = str(activity_id)
    sql = f"""
        UPDATE strava_activities
        SET {', '.join(set_clauses)}
        WHERE activity_id = %(activity_id)s
    """
    cur.execute(sql, updates)
    if getattr(cur, "rowcount", 1) == 0:
        raise ActivityNarrativeActivityNotFound()
    return True


def upsert_daily_training(cur, daily_rows):
    sql = """
        INSERT INTO daily_training (
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
            other_activities,
            other_activity_names,
            other_time,
            other_miles,
            other_elevation_ft,
            other_load,
            other_load_raw,

            total_load,
            updated_at
        )
        VALUES (
            %(date)s,
            %(activity_count)s,
            %(activity_categories)s,
            %(ride_count)s,
            %(walk_count)s,
            %(hike_count)s,
            %(strength_count)s,
            %(mobility_count)s,
            %(ski_count)s,
            %(run_count)s,
            %(other_count)s,

            %(main_ride_id)s,
            %(main_ride_name)s,
            %(main_ride_sport_type)s,
            %(main_ride_category)s,
            %(main_ride_time)s,
            %(main_ride_elapsed_time)s,
            %(main_ride_miles)s,
            %(main_ride_elevation_ft)s,
            %(main_ride_gear_id)s,
            %(main_ride_bike_name)s,
            %(main_ride_rpe)s,
            %(main_ride_load_source)s,
            %(main_ride_load)s,
            %(main_ride_load_score)s,
            %(main_ride_band)s,
            %(main_ride_load_text)s,
            %(main_ride_hr_zones)s,

            %(z1_sec)s,
            %(z2_sec)s,
            %(z3_sec)s,
            %(z4_sec)s,
            %(z5_sec)s,
            %(z4_z5_sec)s,
            %(stream_moving_sec)s,

            %(other_activity_count)s,
            %(other_activities)s::jsonb,
            %(other_activity_names)s,
            %(other_time)s,
            %(other_miles)s,
            %(other_elevation_ft)s,
            %(other_load)s,
            %(other_load_raw)s,

            %(total_load)s,
            now()
        )
        ON CONFLICT (date)
        DO UPDATE SET
            activity_count = EXCLUDED.activity_count,
            activity_categories = EXCLUDED.activity_categories,
            ride_count = EXCLUDED.ride_count,
            walk_count = EXCLUDED.walk_count,
            hike_count = EXCLUDED.hike_count,
            strength_count = EXCLUDED.strength_count,
            mobility_count = EXCLUDED.mobility_count,
            ski_count = EXCLUDED.ski_count,
            run_count = EXCLUDED.run_count,
            other_count = EXCLUDED.other_count,

            main_ride_id = EXCLUDED.main_ride_id,
            main_ride_name = EXCLUDED.main_ride_name,
            main_ride_sport_type = EXCLUDED.main_ride_sport_type,
            main_ride_category = EXCLUDED.main_ride_category,
            main_ride_time = EXCLUDED.main_ride_time,
            main_ride_elapsed_time = EXCLUDED.main_ride_elapsed_time,
            main_ride_miles = EXCLUDED.main_ride_miles,
            main_ride_elevation_ft = EXCLUDED.main_ride_elevation_ft,
            main_ride_gear_id = EXCLUDED.main_ride_gear_id,
            main_ride_bike_name = EXCLUDED.main_ride_bike_name,
            main_ride_rpe = EXCLUDED.main_ride_rpe,
            main_ride_load_source = EXCLUDED.main_ride_load_source,
            main_ride_load = EXCLUDED.main_ride_load,
            main_ride_load_score = EXCLUDED.main_ride_load_score,
            main_ride_band = EXCLUDED.main_ride_band,
            main_ride_load_text = EXCLUDED.main_ride_load_text,
            main_ride_hr_zones = EXCLUDED.main_ride_hr_zones,

            z1_sec = EXCLUDED.z1_sec,
            z2_sec = EXCLUDED.z2_sec,
            z3_sec = EXCLUDED.z3_sec,
            z4_sec = EXCLUDED.z4_sec,
            z5_sec = EXCLUDED.z5_sec,
            z4_z5_sec = EXCLUDED.z4_z5_sec,
            stream_moving_sec = EXCLUDED.stream_moving_sec,

            other_activity_count = EXCLUDED.other_activity_count,
            other_activities = EXCLUDED.other_activities,
            other_activity_names = EXCLUDED.other_activity_names,
            other_time = EXCLUDED.other_time,
            other_miles = EXCLUDED.other_miles,
            other_elevation_ft = EXCLUDED.other_elevation_ft,
            other_load = EXCLUDED.other_load,
            other_load_raw = EXCLUDED.other_load_raw,

            total_load = EXCLUDED.total_load,
            updated_at = now()
    """

    for row in daily_rows:
        params = dict(row)
        params["other_activities"] = json.dumps(params.get("other_activities") or [])
        cur.execute(sql, params)


def upsert_weekly_training(cur, weekly_rows):
    sql = """
        INSERT INTO weekly_training (
            week_start,
            week_end,

            total_load,
            main_ride_load,
            other_load,

            activity_days,
            ride_count,
            walk_count,
            hike_count,
            strength_count,
            mobility_count,
            ski_count,
            run_count,
            other_count,

            very_hard_epic_days,

            chronic_daily_c,
            chronic_weekly_cw,
            ac_ratio,
            ramp_pct,
            ramp_pct_display,
            remaining_to_20pct_ramp,

            status_level,
            status_text,
            updated_at
        )
        VALUES (
            %(week_start)s,
            %(week_end)s,

            %(total_load)s,
            %(main_ride_load)s,
            %(other_load)s,

            %(activity_days)s,
            %(ride_count)s,
            %(walk_count)s,
            %(hike_count)s,
            %(strength_count)s,
            %(mobility_count)s,
            %(ski_count)s,
            %(run_count)s,
            %(other_count)s,

            %(very_hard_epic_days)s,

            %(chronic_daily_c)s,
            %(chronic_weekly_cw)s,
            %(ac_ratio)s,
            %(ramp_pct)s,
            %(ramp_pct_display)s,
            %(remaining_to_20pct_ramp)s,

            %(status_level)s,
            %(status_text)s,
            now()
        )
        ON CONFLICT (week_start)
        DO UPDATE SET
            week_end = EXCLUDED.week_end,

            total_load = EXCLUDED.total_load,
            main_ride_load = EXCLUDED.main_ride_load,
            other_load = EXCLUDED.other_load,

            activity_days = EXCLUDED.activity_days,
            ride_count = EXCLUDED.ride_count,
            walk_count = EXCLUDED.walk_count,
            hike_count = EXCLUDED.hike_count,
            strength_count = EXCLUDED.strength_count,
            mobility_count = EXCLUDED.mobility_count,
            ski_count = EXCLUDED.ski_count,
            run_count = EXCLUDED.run_count,
            other_count = EXCLUDED.other_count,

            very_hard_epic_days = EXCLUDED.very_hard_epic_days,

            chronic_daily_c = EXCLUDED.chronic_daily_c,
            chronic_weekly_cw = EXCLUDED.chronic_weekly_cw,
            ac_ratio = EXCLUDED.ac_ratio,
            ramp_pct = EXCLUDED.ramp_pct,
            ramp_pct_display = EXCLUDED.ramp_pct_display,
            remaining_to_20pct_ramp = EXCLUDED.remaining_to_20pct_ramp,

            status_level = EXCLUDED.status_level,
            status_text = EXCLUDED.status_text,
            updated_at = now()
    """

    for row in weekly_rows:
        cur.execute(sql, row)


def insert_sync_run_log(
    cur,
    run_at_utc,
    days_back,
    activity_count,
    daily_rows,
    weekly_rows,
    warning_count,
    status,
):
    sql = """
        INSERT INTO sync_run_log (
            run_at_utc,
            days_back,
            activity_count,
            daily_rows,
            weekly_rows,
            warning_count,
            status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """

    cur.execute(
        sql,
        (
            run_at_utc,
            days_back,
            activity_count,
            daily_rows,
            weekly_rows,
            warning_count,
            status,
        ),
    )


def int_or_none(value):
    if value in (None, ""):
        return None

    return int(round(float(value)))