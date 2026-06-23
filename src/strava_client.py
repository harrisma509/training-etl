import json
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from constants import STRAVA_API_BASE, STRAVA_TOKEN_URL


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


def sec_to_hms(seconds):
    seconds = int(seconds or 0)
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"