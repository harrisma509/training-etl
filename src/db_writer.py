import json
from weekly_builder import build_weekly_training



def write_training_to_db(cfg, activities, daily_rows, weekly_rows, warnings, run_at_utc):
    if not cfg.get("WRITE_DB"):
        return

    import psycopg

    with psycopg.connect(
        host=cfg["DB_HOST"],
        port=cfg["DB_PORT"],
        dbname=cfg["DB_NAME"],
        user=cfg["DB_USER"],
        password=cfg["DB_PASSWORD"],
    ) as conn:
        with conn.cursor() as cur:

            print("DB write: activities")
            upsert_strava_activities(cur, activities)

            print("DB write: daily")
            upsert_daily_training(cur, daily_rows)
            print("DB rebuild: weekly from full daily_training")
            all_daily_rows = fetch_all_daily_training_for_weekly(cur)
            weekly_rows = build_weekly_training(all_daily_rows)
            replace_weekly_training(cur, weekly_rows)


            print("DB write: sync log")

            insert_sync_run_log(
                cur=cur,
                run_at_utc=run_at_utc,
                days_back=cfg["DAYS_BACK"],
                activity_count=len(activities),
                daily_rows=len(daily_rows),
                weekly_rows=len(weekly_rows),
                warning_count=len(warnings),
                status="ok" if not warnings else "warnings",
            )

        conn.commit()
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
    return [dict(zip(columns, row)) for row in cur.fetchall()]


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

    for gear_id, brand, model_year, gear_name in rows:
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
        cur.execute(sql, row)


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