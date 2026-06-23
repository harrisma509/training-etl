from constants import M_PER_MI, M_TO_FT


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


def sec_to_hms(seconds):
    seconds = int(seconds or 0)
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"