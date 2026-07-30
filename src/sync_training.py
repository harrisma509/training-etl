import sys
from datetime import datetime, timezone

from activity_utils import normalize_activity, sec_to_hms
from daily_builder import build_daily_training
from settings import get_config
from strava_client import fetch_activities, refresh_access_token
from weekly_builder import build_weekly_training
from writers import write_daily_csv, write_json, write_weekly_csv
from db_writer import write_training_to_db
from gear_db import fetch_gear_display_map


def main():
    cfg = get_config()

    print("Training sync starting")
    print(f"Window: last {cfg['DAYS_BACK']} days")
    print(f"Load chronic C used for banding: {cfg['LOAD_CHRONIC_C']}")

    token = refresh_access_token(cfg)
    access_token = token["access_token"]

    activities = fetch_activities(access_token, cfg["DAYS_BACK"])
    rows = [normalize_activity(activity) for activity in activities]

    gear_display_map = fetch_gear_display_map(cfg) if cfg.get("WRITE_DB") else {}
    print(f"Gear records loaded from DB: {len(gear_display_map)}")

    daily, warnings = build_daily_training(
        rows=rows,
        access_token=access_token,
        chronic_c=cfg["LOAD_CHRONIC_C"],
        gear_display_map=gear_display_map,
    )

    weekly = build_weekly_training(daily)

    print(f"Activities pulled: {len(rows)}")
    print(f"Daily rows built: {len(daily)}")

    for row in daily:
        print(
            f"{row['date']} | "
            f"main={row['main_ride_name'] or 'None'} "
            f"bike={row['main_ride_bike_name'] or 'None'} "
            f"main_load={row['main_ride_load']} "
            f"other_load={row['other_load']} "
            f"total_load={row['total_load']} "
            f"z4z5={sec_to_hms(row['z4_z5_sec'])}"
        )

    print(f"Weekly rows built: {len(weekly)}")

    for row in weekly:
        ac_ratio = row["ac_ratio"] if row["ac_ratio"] is not None else "n/a"
        ramp = row["ramp_pct_display"] if row["ramp_pct_display"] else "n/a"

        print(
            f"{row['week_start']} | "
            f"load={row['total_load']} "
            f"ramp={ramp} "
            f"ac={ac_ratio} "
            f"status={row['status_level']}"
        )

    if warnings:
        print(f"Warnings: {len(warnings)}")

        for warning in warnings:
            print(f"WARNING: {warning}")

    run_at_utc = datetime.now(timezone.utc).isoformat()

    daily_output = {
        "run_at_utc": run_at_utc,
        "days_back": cfg["DAYS_BACK"],
        "load_chronic_c": cfg["LOAD_CHRONIC_C"],
        "activity_count": len(rows),
        "daily_training": daily,
        "weekly_training": weekly,
        "activities": rows,
        "warnings": warnings,
    }

    weekly_output = {
        "run_at_utc": run_at_utc,
        "days_back": cfg["DAYS_BACK"],
        "weekly_training": weekly,
        "warnings": warnings,
    }

    write_json(cfg["OUTPUT_JSON"], daily_output)
    write_daily_csv(cfg["OUTPUT_CSV"], daily)

    write_json(cfg["OUTPUT_WEEKLY_JSON"], weekly_output)
    write_weekly_csv(cfg["OUTPUT_WEEKLY_CSV"], weekly)

    print(f"Daily JSON written: {cfg['OUTPUT_JSON']}")
    print(f"Daily CSV written: {cfg['OUTPUT_CSV']}")
    print(f"Weekly JSON written: {cfg['OUTPUT_WEEKLY_JSON']}")
    print(f"Weekly CSV written: {cfg['OUTPUT_WEEKLY_CSV']}")

    write_training_to_db(
        cfg=cfg,
        activities=rows,
        daily_rows=daily,
        weekly_rows=weekly,
        warnings=warnings,
        run_at_utc=run_at_utc,
    )
    if cfg.get("WRITE_DB"):
        print("Postgres write complete")
    
    print("Training sync complete")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)