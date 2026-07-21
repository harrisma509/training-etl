import csv
import json


DAILY_CSV_FIELDNAMES = [
    "date",
    "activity_count",
    "activity_categories",
    "ride_count",
    "walk_count",
    "hike_count",
    "strength_count",
    "mobility_count",
    "ski_count",
    "run_count",
    "other_count",

    "main_ride_id",
    "main_ride_name",
    "main_ride_sport_type",
    "main_ride_category",
    "main_ride_time",
    "main_ride_elapsed_time",
    "main_ride_miles",
    "main_ride_elevation_ft",
    "main_ride_gear_id",
    "main_ride_bike_name",
    "main_ride_rpe",
    "main_ride_load_source",
    "main_ride_load",
    "main_ride_load_score",
    "main_ride_band",
    "main_ride_load_text",
    "main_ride_hr_zones",

    "z1_sec",
    "z2_sec",
    "z3_sec",
    "z4_sec",
    "z5_sec",
    "z4_z5_sec",
    "stream_moving_sec",

    "other_activity_count",
    "other_activity_names",
    "other_time",
    "other_miles",
    "other_elevation_ft",
    "other_load",
    "other_load_raw",

    "total_load",
]


WEEKLY_CSV_FIELDNAMES = [
    "week_start",
    "week_end",

    "total_load",
    "main_ride_load",
    "other_load",

    "activity_days",
    "ride_count",
    "walk_count",
    "hike_count",
    "strength_count",
    "mobility_count",
    "ski_count",
    "run_count",
    "other_count",

    "very_hard_epic_days",

    "chronic_daily_c",
    "chronic_weekly_cw",
    "ac_ratio",
    "ramp_pct",
    "ramp_pct_display",
    "remaining_to_20pct_ramp",

    "status_level",
    "status_text",
]


def write_json(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def write_daily_csv(path, daily_rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=DAILY_CSV_FIELDNAMES,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(daily_rows)


def write_weekly_csv(path, weekly_rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=WEEKLY_CSV_FIELDNAMES,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(weekly_rows)