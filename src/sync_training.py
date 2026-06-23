import sys
from datetime import datetime, timezone

from activity_utils import normalize_activity, sec_to_hms
from daily_builder import build_daily_training
from gear import read_gear_map
from settings import get_config
from strava_client import fetch_activities, refresh_access_token
from writers import write_daily_csv, write_json


def main():
    cfg = get_config()

    print("Training sync starting")
    print(f"Window: last {cfg['DAYS_BACK']} days")
    print(f"Load chronic C used for banding: {cfg['LOAD_CHRONIC_C']}")

    gear_map = read_gear_map(cfg["GEAR_MAP_CSV"])
    print(f"Gear map entries loaded: {len(gear_map)}")

    token = refresh_access_token(cfg)
    access_token = token["access_token"]

    activities = fetch_activities(access_token, cfg["DAYS_BACK"])
    rows = [normalize_activity(a) for a in activities]

    daily, warnings = build_daily_training(
        rows=rows,
        access_token=access_token,
        chronic_c=cfg["LOAD_CHRONIC_C"],
        gear_map=gear_map,
    )

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

    if warnings:
        print(f"Warnings: {len(warnings)}")

        for warning in warnings:
            print(f"WARNING: {warning}")

    output = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "days_back": cfg["DAYS_BACK"],
        "load_chronic_c": cfg["LOAD_CHRONIC_C"],
        "activity_count": len(rows),
        "daily_training": daily,
        "activities": rows,
        "warnings": warnings,
    }

    write_json(cfg["OUTPUT_JSON"], output)
    write_daily_csv(cfg["OUTPUT_CSV"], daily)

    print(f"JSON written: {cfg['OUTPUT_JSON']}")
    print(f"CSV written: {cfg['OUTPUT_CSV']}")
    print("Training sync complete")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)