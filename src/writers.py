import csv
import json


DAILY_CSV_FIELDNAMES = [
    "date",
    "activity_count",
    "main_ride_id",
    "main_ride_name",
    "main_ride_sport_type",
    "main_ride_time",
    "main_ride_elapsed_time",
    "main_ride_miles",
    "main_ride_elevation_ft",
    "main_ride_gear_id",
    "main_ride_bike_name",
    "main_ride_load",
    "main_ride_band",
    "main_ride_load_text",
    "main_ride_hr_zones",
    "z1_sec",
    "z2_sec",
    "z3_sec",
    "z4_sec",
    "z5_sec",
    "z4_z5_sec",
    "other_activity_count",
    "activity_categories",
    "ride_count",
    "walk_count",
    "hike_count",
    "strength_count",
    "mobility_count",
    "ski_count",
    "run_count",
    "other_count",
    "other_activity_names",
    "other_time",
    "other_miles",
    "other_elevation_ft",
    "other_load",
    "total_load",
]


def write_json(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def write_daily_csv(path, daily_rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=DAILY_CSV_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(daily_rows)