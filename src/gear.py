import csv
import os


def read_gear_map(path):
    gear = {}

    if not path or not os.path.exists(path):
        return gear

    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            gear_id = (row.get("gear_id") or "").strip()

            if not gear_id:
                continue

            gear[gear_id] = {
                "gear_id": gear_id,
                "bike_name": (row.get("bike_name") or "").strip(),
                "type": (row.get("type") or "").strip(),
                "retired": parse_bool(row.get("retired")),
            }

    return gear


def parse_bool(value):
    s = str(value or "").strip().lower()
    return s in {"true", "yes", "y", "1"}


def lookup_gear_name(gear_map, gear_id):
    if not gear_id:
        return ""

    item = gear_map.get(gear_id)

    if not item:
        return ""

    return item.get("bike_name") or ""