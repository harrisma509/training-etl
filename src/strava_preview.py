import csv
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"

M_PER_MI = 1609.344
M_TO_FT = 3.28084

SKI_LOAD_MIN = 100
SKI_LOAD_BASE = 300
SKI_LOAD_MAX = 500
SKI_RPE_STEP = 50

SUPP_MIN_MULT = 2.0
SUPP_MIN_WALK = 1.0
SUPP_MIN_MOBI = 0.75

DEFAULT_CHRONIC_C = 217.0
EASY_MULT = 0.55
ENDUR_MULT = 1.0
HARD_MULT = 1.5
VERYHARD_MULT = 2.3


def read_env_file(path):
    values = {}
    if not path or not os.path.exists(path):
        return values

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")

    return values


def get_config():
    env_file = os.environ.get("ENV_FILE", "/config/strava.env")
    file_values = read_env_file(env_file)

    keys = [
        "STRAVA_CLIENT_ID",
        "STRAVA_CLIENT_SECRET",
        "STRAVA_REFRESH_TOKEN",
        "DAYS_BACK",
        "OUTPUT_JSON",
        "OUTPUT_CSV",
        "LOAD_CHRONIC_C",
        "GEAR_MAP_CSV",
    ]

    cfg = {}
    for key in keys:
        cfg[key] = os.environ.get(key) or file_values.get(key)

    missing = [
        key
        for key in ["STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET", "STRAVA_REFRESH_TOKEN"]
        if not cfg.get(key)
    ]

    if missing:
        raise SystemExit(f"Missing required config values: {', '.join(missing)}")

    cfg["DAYS_BACK"] = int(cfg.get("DAYS_BACK") or 7)
    cfg["OUTPUT_JSON"] = cfg.get("OUTPUT_JSON") or "/tmp/daily_training_preview.json"
    cfg["OUTPUT_CSV"] = cfg.get("OUTPUT_CSV") or "/tmp/daily_training_preview.csv"
    cfg["LOAD_CHRONIC_C"] = float(cfg.get("LOAD_CHRONIC_C") or DEFAULT_CHRONIC_C)

    return cfg


def http_json(method, url, headers=None, data=None):
    body = None
    final_headers = headers or {}

    if data is not None:
        body = json.dumps(data).encode("utf-8")
        final_headers = {
            **final_headers,
            "Content-Type": "application/json",
        }

    req = Request(url, data=body, headers=final_headers, method=method)

    try:
        with urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} calling {url}: {detail}") from e
    except URLError as e:
        raise RuntimeError(f"Network error calling {url}: {e}") from e


def refresh_access_token(cfg):
    payload = {
        "client_id": cfg["STRAVA_CLIENT_ID"],
        "client_secret": cfg["STRAVA_CLIENT_SECRET"],
        "grant_type": "refresh_token",
        "refresh_token": cfg["STRAVA_REFRESH_TOKEN"],
    }

    token = http_json("POST", STRAVA_TOKEN_URL, data=payload)

    if not token or "access_token" not in token:
        raise RuntimeError("Token refresh failed: no access_token returned")

    return token


def auth_header(access_token):
    return {"Authorization": f"Bearer {access_token}"}


def fetch_activities(access_token, days_back):
    now = datetime.now(timezone.utc)
    after = int((now - timedelta(days=days_back)).timestamp())
    before = int((now + timedelta(days=1)).timestamp())

    all_activities = []
    page = 1

    while True:
        query = urlencode({
            "after": after,
            "before": before,
            "page": page,
            "per_page": 200,
        })

        url = f"{STRAVA_API_BASE}/athlete/activities?{query}"
        batch = http_json("GET", url, headers=auth_header(access_token))

        if not batch:
            break

        all_activities.extend(batch)

        if len(batch) < 200:
            break

        page += 1
        time.sleep(0.25)

    return all_activities


def fetch_activity_detail(access_token, activity_id):
    url = f"{STRAVA_API_BASE}/activities/{activity_id}?include_all_efforts=false"
    return http_json("GET", url, headers=auth_header(access_token))


def fetch_hr_zones(access_token):
    url = f"{STRAVA_API_BASE}/athlete/zones"
    data = http_json("GET", url, headers=auth_header(access_token))

    zones = data.get("heart_rate", {}).get("zones", [])
    if len(zones) < 5:
        raise RuntimeError("Strava HR zones response did not include 5 zones")

    z_min = []
    z_max = []

    for i, zone in enumerate(zones):
        z_min.append(float(zone.get("min", -1_000_000)))
        z_max.append(float(zone.get("max", 1_000_000)) if i < 4 else 1_000_000)

    return z_min, z_max


def fetch_activity_stream_zones(access_token, activity_id, z_min, z_max):
    url = (
        f"{STRAVA_API_BASE}/activities/{activity_id}/streams?"
        "keys=heartrate,time,moving&key_by_type=true"
    )

    data = http_json("GET", url, headers=auth_header(access_token))

    if not data or "heartrate" not in data or "time" not in data:
        return {
            "z1_sec": 0,
            "z2_sec": 0,
            "z3_sec": 0,
            "z4_sec": 0,
            "z5_sec": 0,
            "stream_moving_sec": 0,
            "zone_text": "",
            "warning": "No heartrate/time stream returned",
        }

    hrs = data["heartrate"].get("data", [])
    times = data["time"].get("data", [])
    moving = data.get("moving", {}).get("data")

    n = min(len(hrs), len(times), len(moving) if moving is not None else len(times))

    if n < 2:
        return {
            "z1_sec": 0,
            "z2_sec": 0,
            "z3_sec": 0,
            "z4_sec": 0,
            "z5_sec": 0,
            "stream_moving_sec": 0,
            "zone_text": "",
            "warning": "Stream too short",
        }

    z = [0, 0, 0, 0, 0]
    total_moving = 0
    last_moving_index = None

    for i in range(1, n):
        dt = int(times[i]) - int(times[i - 1])
        if dt <= 0:
            continue

        is_moving = True
        if moving is not None:
            is_moving = bool(moving[i])

        if not is_moving:
            continue

        total_moving += dt
        last_moving_index = i
        hr_prev = float(hrs[i - 1])

        zone_index = zone_index_for_hr(hr_prev, z_min, z_max)
        if zone_index is not None:
            z[zone_index] += dt

    delta = total_moving - sum(z)

    if delta != 0 and last_moving_index is not None and last_moving_index >= 1:
        hr_prev = float(hrs[last_moving_index - 1])
        zone_index = zone_index_for_hr(hr_prev, z_min, z_max)
        if zone_index is not None:
            z[zone_index] += delta

    zone_text = (
        f"Z1 {sec_to_hms(z[0])}, "
        f"Z2 {sec_to_hms(z[1])}, "
        f"Z3 {sec_to_hms(z[2])}, "
        f"Z4 {sec_to_hms(z[3])}, "
        f"Z5 {sec_to_hms(z[4])}"
    )

    return {
        "z1_sec": z[0],
        "z2_sec": z[1],
        "z3_sec": z[2],
        "z4_sec": z[3],
        "z5_sec": z[4],
        "stream_moving_sec": total_moving,
        "zone_text": zone_text,
        "warning": "",
    }


def zone_index_for_hr(hr, z_min, z_max):
    if hr <= z_max[0]:
        return 0
    if z_min[1] <= hr <= z_max[1]:
        return 1
    if z_min[2] <= hr <= z_max[2]:
        return 2
    if z_min[3] <= hr <= z_max[3]:
        return 3
    if hr >= z_min[4]:
        return 4
    return None


def activity_local_date(activity):
    value = activity.get("start_date_local") or activity.get("start_date")
    if not value:
        return "unknown"
    return value[:10]


def normalize_activity(activity):
    moving_sec = int(activity.get("moving_time") or 0)
    elapsed_sec = int(activity.get("elapsed_time") or 0)

    if elapsed_sec < moving_sec:
        elapsed_sec = moving_sec

    return {
        "id": str(activity.get("id") or ""),
        "date_local": activity_local_date(activity),
        "name": clean_activity_name(activity.get("name") or ""),
        "sport_type": activity.get("sport_type") or "",
        "type": activity.get("type") or "",
        "moving_sec": moving_sec,
        "elapsed_sec": elapsed_sec,
        "distance_m": float(activity.get("distance") or 0),
        "distance_mi": round(float(activity.get("distance") or 0) / M_PER_MI, 2),
        "elevation_m": float(activity.get("total_elevation_gain") or 0),
        "elevation_ft": round(float(activity.get("total_elevation_gain") or 0) * M_TO_FT),
        "has_heartrate": bool(activity.get("has_heartrate") or False),
        "gear_id": activity.get("gear_id") or "",
        "average_hr": activity.get("average_heartrate"),
        "max_hr": activity.get("max_heartrate"),
    }


def clean_activity_name(name):
    return " ".join(str(name).replace("\n", " ").replace("\r", " ").split())


def is_cycling_activity(row):
    sport = (row.get("sport_type") or "").lower()
    typ = (row.get("type") or "").lower()
    return "ride" in sport or "ride" in typ


def is_walk(row):
    sport = (row.get("sport_type") or "").lower().replace(" ", "")
    typ = (row.get("type") or "").lower().replace(" ", "")
    return sport == "walk" or typ == "walk"


def is_ski(row):
    sport = (row.get("sport_type") or "").lower().replace(" ", "")
    typ = (row.get("type") or "").lower().replace(" ", "")
    name = (row.get("name") or "").lower()

    ski_types = {"alpineski", "nordicski", "backcountryski"}

    return sport in ski_types or typ in ski_types or "ski" in name


def supplemental_load_for_other(row, access_token, rpe_cache, warnings):
    minutes = row["moving_sec"] / 60.0
    sport = (row.get("sport_type") or "").lower().replace(" ", "")
    name = (row.get("name") or "").lower()

    if is_ski(row):
        rpe = get_activity_rpe(row["id"], access_token, rpe_cache, warnings)
        return ski_load_from_rpe(rpe)

    if sport == "walk":
        return SUPP_MIN_WALK * minutes

    if sport == "yoga":
        return SUPP_MIN_MOBI * minutes

    if "mobility" in name or "stretch" in name:
        return SUPP_MIN_MOBI * minutes

    return SUPP_MIN_MULT * minutes


def get_activity_rpe(activity_id, access_token, rpe_cache, warnings):
    if not activity_id:
        return -1

    if activity_id in rpe_cache:
        return rpe_cache[activity_id]

    try:
        detail = fetch_activity_detail(access_token, activity_id)
        rpe = detail.get("perceived_exertion")
        rpe = int(rpe) if rpe is not None else -1
    except Exception as exc:
        warnings.append(f"Could not fetch RPE for activity {activity_id}: {exc}")
        rpe = -1

    rpe_cache[activity_id] = rpe
    return rpe


def ski_load_from_rpe(rpe):
    if rpe < 0:
        load = SKI_LOAD_BASE
    else:
        load = SKI_LOAD_BASE + SKI_RPE_STEP * (rpe - 5)

    return max(SKI_LOAD_MIN, min(SKI_LOAD_MAX, load))


def intensity_score_from_zones(z1, z2, z3, z4, z5):
    return (
        (z1 / 60.0) * 1.0
        + (z2 / 60.0) * 2.0
        + (z3 / 60.0) * 4.0
        + (z4 / 60.0) * 7.0
        + (z5 / 60.0) * 10.0
    )


def intensity_band(score, chronic_c):
    easy_max = round(EASY_MULT * chronic_c)
    endur_max = round(ENDUR_MULT * chronic_c)
    hard_max = round(HARD_MULT * chronic_c)
    very_hard_max = round(VERYHARD_MULT * chronic_c)

    if score <= easy_max:
        return "Easy"
    if score <= endur_max:
        return "Endurance"
    if score <= hard_max:
        return "Hard"
    if score <= very_hard_max:
        return "Very Hard"
    return "Epic Hard"


def round_half_up(value):
    return int(value + 0.5)


def sec_to_hms(seconds):
    seconds = int(seconds or 0)
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def build_daily_training(rows, access_token, chronic_c, gear_map):
    warnings = []
    rpe_cache = {}

    try:
        z_min, z_max = fetch_hr_zones(access_token)
    except Exception as exc:
        z_min, z_max = None, None
        warnings.append(f"Could not fetch athlete HR zones: {exc}")

    by_day = {}

    for row in rows:
        by_day.setdefault(row["date_local"], []).append(row)

    daily = []

    for date_key in sorted(by_day.keys()):
        activities = by_day[date_key]
        rides = [a for a in activities if is_cycling_activity(a)]

        main_ride = None
        if rides:
            main_ride = max(rides, key=lambda x: x["moving_sec"])

        other_activities = []
        for activity in activities:
            if main_ride and activity["id"] == main_ride["id"]:
                continue
            other_activities.append(activity)

        other_moving_sec = sum(a["moving_sec"] for a in other_activities)
        other_distance_mi = round(sum(a["distance_mi"] for a in other_activities), 2)
        other_elevation_ft = round(sum(a["elevation_ft"] for a in other_activities))
        other_names = [a["name"] for a in other_activities]

        other_load_raw = 0.0
        for other in other_activities:
            other_load_raw += supplemental_load_for_other(other, access_token, rpe_cache, warnings)

        other_load = round_half_up(other_load_raw) if other_load_raw > 0 else 0

        zone = {
            "z1_sec": 0,
            "z2_sec": 0,
            "z3_sec": 0,
            "z4_sec": 0,
            "z5_sec": 0,
            "stream_moving_sec": 0,
            "zone_text": "",
            "warning": "",
        }

        main_load = 0
        main_load_score = 0.0
        main_band = ""
        main_load_text = ""

        if main_ride and main_ride["has_heartrate"] and z_min and z_max:
            try:
                zone = fetch_activity_stream_zones(access_token, main_ride["id"], z_min, z_max)
                if zone.get("warning"):
                    warnings.append(f"{date_key} {main_ride['name']}: {zone['warning']}")

                main_load_score = intensity_score_from_zones(
                    zone["z1_sec"],
                    zone["z2_sec"],
                    zone["z3_sec"],
                    zone["z4_sec"],
                    zone["z5_sec"],
                )

                main_load = round_half_up(main_load_score)
                main_band = intensity_band(main_load_score, chronic_c)
                main_load_text = f"{main_load} ({main_band})"
            except Exception as exc:
                warnings.append(f"Could not fetch HR streams for {main_ride['id']} {main_ride['name']}: {exc}")

        total_load = main_load + other_load

        daily.append({
            "date": date_key,
            "activity_count": len(activities),

            "main_ride_id": main_ride["id"] if main_ride else "",
            "main_ride_name": main_ride["name"] if main_ride else "",
            "main_ride_sport_type": main_ride["sport_type"] if main_ride else "",
            "main_ride_moving_sec": main_ride["moving_sec"] if main_ride else 0,
            "main_ride_elapsed_sec": main_ride["elapsed_sec"] if main_ride else 0,
            "main_ride_time": sec_to_hms(main_ride["moving_sec"]) if main_ride else "",
            "main_ride_elapsed_time": sec_to_hms(main_ride["elapsed_sec"]) if main_ride else "",
            "main_ride_miles": main_ride["distance_mi"] if main_ride else 0,
            "main_ride_elevation_ft": main_ride["elevation_ft"] if main_ride else 0,
            "main_ride_gear_id": main_ride["gear_id"] if main_ride else "",
            "main_ride_bike_name": lookup_gear_name(gear_map, main_ride["gear_id"]) if main_ride else "",
            "main_ride_load": main_load,
            "main_ride_load_score": round(main_load_score, 2),
            "main_ride_band": main_band,
            "main_ride_load_text": main_load_text,
            "main_ride_hr_zones": zone["zone_text"],

            "z1_sec": zone["z1_sec"],
            "z2_sec": zone["z2_sec"],
            "z3_sec": zone["z3_sec"],
            "z4_sec": zone["z4_sec"],
            "z5_sec": zone["z5_sec"],
            "z4_z5_sec": zone["z4_sec"] + zone["z5_sec"],
            "stream_moving_sec": zone["stream_moving_sec"],

            "other_activity_count": len(other_activities),
            "other_activity_names": "\n".join(other_names),
            "other_moving_sec": other_moving_sec,
            "other_time": sec_to_hms(other_moving_sec) if other_moving_sec else "",
            "other_miles": other_distance_mi,
            "other_elevation_ft": other_elevation_ft,
            "other_load": other_load,
            "other_load_raw": round(other_load_raw, 2),

            "total_load": total_load,
        })

    return daily, warnings


def write_json(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def write_daily_csv(path, daily_rows):
    fieldnames = [
        "date",
        "activity_count",
        "main_ride_id",
        "main_ride_name",
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
        "other_activity_names",
        "other_time",
        "other_miles",
        "other_elevation_ft",
        "other_load",
        "total_load",
    ]

    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(daily_rows)
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

def main():
    cfg = get_config()

    print("Daily training preview starting")
    print(f"Window: last {cfg['DAYS_BACK']} days")
    print(f"Load chronic C used for banding: {cfg['LOAD_CHRONIC_C']}")
    gear_map = read_gear_map(cfg["GEAR_MAP_CSV"])
    print(f"Gear map entries loaded: {len(gear_map)}")

    token = refresh_access_token(cfg)
    access_token = token["access_token"]

    activities = fetch_activities(access_token, cfg["DAYS_BACK"])
    rows = [normalize_activity(a) for a in activities]

    daily, warnings = build_daily_training(rows, access_token, cfg["LOAD_CHRONIC_C"], gear_map)

    print(f"Activities pulled: {len(rows)}")
    print(f"Daily rows built: {len(daily)}")

    for row in daily:
        print(
            f"{row['date']} | "
            f"main={row['main_ride_name'] or 'None'} "
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

    print(f"Preview JSON written: {cfg['OUTPUT_JSON']}")
    print(f"Preview CSV written: {cfg['OUTPUT_CSV']}")
    print("Daily training preview complete")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
