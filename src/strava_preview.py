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

    cfg = {}
    for key in [
        "STRAVA_CLIENT_ID",
        "STRAVA_CLIENT_SECRET",
        "STRAVA_REFRESH_TOKEN",
        "DAYS_BACK",
        "OUTPUT_JSON",
    ]:
        cfg[key] = os.environ.get(key) or file_values.get(key)

    missing = [
        key for key in ["STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET", "STRAVA_REFRESH_TOKEN"]
        if not cfg.get(key)
    ]

    if missing:
        raise SystemExit(f"Missing required config values: {', '.join(missing)}")

    cfg["DAYS_BACK"] = int(cfg.get("DAYS_BACK") or 7)
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
        with urlopen(req, timeout=30) as resp:
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
        batch = http_json(
            "GET",
            url,
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if not batch:
            break

        all_activities.extend(batch)

        if len(batch) < 200:
            break

        page += 1
        time.sleep(0.25)

    return all_activities


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
        "name": activity.get("name") or "",
        "sport_type": activity.get("sport_type") or activity.get("type") or "",
        "moving_sec": moving_sec,
        "elapsed_sec": elapsed_sec,
        "distance_mi": round(float(activity.get("distance") or 0) / 1609.344, 2),
        "elevation_ft": round(float(activity.get("total_elevation_gain") or 0) * 3.28084),
        "has_heartrate": bool(activity.get("has_heartrate") or False),
        "gear_id": activity.get("gear_id") or "",
        "average_hr": activity.get("average_heartrate"),
        "max_hr": activity.get("max_heartrate"),
    }


def summarize_by_day(rows):
    days = {}

    for row in rows:
        d = row["date_local"]

        if d not in days:
            days[d] = {
                "date": d,
                "activities": 0,
                "moving_sec": 0,
                "distance_mi": 0.0,
                "elevation_ft": 0,
                "rides": 0,
                "walks": 0,
                "other": 0,
                "activity_names": [],
            }

        days[d]["activities"] += 1
        days[d]["moving_sec"] += row["moving_sec"]
        days[d]["distance_mi"] += row["distance_mi"]
        days[d]["elevation_ft"] += row["elevation_ft"]
        days[d]["activity_names"].append(row["name"])

        st = row["sport_type"].lower()

        if "ride" in st or "cycling" in st:
            days[d]["rides"] += 1
        elif "walk" in st:
            days[d]["walks"] += 1
        else:
            days[d]["other"] += 1

    return [days[k] for k in sorted(days.keys())]


def hms(seconds):
    seconds = int(seconds or 0)
    return f"{seconds // 3600}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def main():
    cfg = get_config()

    print("Strava preview starting")
    print(f"Window: last {cfg['DAYS_BACK']} days")

    token = refresh_access_token(cfg)
    access_token = token["access_token"]

    activities = fetch_activities(access_token, cfg["DAYS_BACK"])
    rows = [normalize_activity(a) for a in activities]
    daily = summarize_by_day(rows)

    print(f"Activities pulled: {len(rows)}")
    print(f"Days found: {len(daily)}")

    for day in daily:
        print(
            f"{day['date']} | "
            f"activities={day['activities']} "
            f"rides={day['rides']} "
            f"walks={day['walks']} "
            f"other={day['other']} "
            f"time={hms(day['moving_sec'])} "
            f"miles={day['distance_mi']:.2f} "
            f"elev_ft={day['elevation_ft']}"
        )

    output = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "days_back": cfg["DAYS_BACK"],
        "activity_count": len(rows),
        "daily": daily,
        "activities": rows,
    }

    output_path = cfg.get("OUTPUT_JSON")

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
        print(f"Preview written: {output_path}")

    print("Strava preview complete")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)