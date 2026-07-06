from constants import M_PER_MI, M_TO_FT


def activity_local_date(activity):
    value = activity.get("start_date_local") or activity.get("start_date")

    if not value:
        return "unknown"

    return value[:10]


def clean_activity_name(name):
    return " ".join(str(name).replace("\n", " ").replace("\r", " ").split())


def classify_activity(activity):
    sport_type = (activity.get("sport_type") or "").strip()
    activity_type = (activity.get("type") or "").strip()
    name = (activity.get("name") or "").strip()

    sport = sport_type.lower().replace(" ", "")
    typ = activity_type.lower().replace(" ", "")
    name_l = name.lower()

    ride_types = {
        "ride",
        "mountainbikeride",
        "emountainbikeride",
        "ebikeride",
        "gravelride",
        "virtualride",
        "handcycle",
    }

    hike_types = {
        "hike",
    }

    walk_types = {
        "walk",
    }

    run_types = {
        "run",
        "trailrun",
        "virtualrun",
    }

    ski_types = {
        "alpineski",
        "backcountryski",
        "nordicski",
        "rollerski",
        "snowboard",
    }

    mobility_types = {
        "yoga",
        "pilates",
    }

    strength_types = {
        "weighttraining",
        "workout",
        "crossfit",
    }

    if sport in ride_types or typ in ride_types or "ride" in sport:
        return "ride"

    if sport in hike_types or typ in hike_types:
        return "hike"

    if sport in walk_types or typ in walk_types:
        return "walk"

    if sport in run_types or typ in run_types:
        return "run"

    if sport in ski_types or typ in ski_types or "ski" in name_l:
        return "ski"

    if sport in mobility_types or typ in mobility_types:
        return "mobility"

    if "mobility" in name_l or "stretch" in name_l:
        return "mobility"

    if sport in strength_types or typ in strength_types:
        return "strength"

    if "strength" in name_l or "gym" in name_l or "lift" in name_l:
        return "strength"

    return "other"


def normalize_activity(activity):
    moving_sec = int(activity.get("moving_time") or 0)
    elapsed_sec = int(activity.get("elapsed_time") or 0)

    if elapsed_sec < moving_sec:
        elapsed_sec = moving_sec

    clean_name = clean_activity_name(activity.get("name") or "")

    row = {
        "id": str(activity.get("id") or ""),
        "date_local": activity_local_date(activity),
        "name": clean_name,
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

    row["activity_category"] = classify_activity(row)

    return row


def is_cycling_activity(row):
    return row.get("activity_category") == "ride"


def is_walk(row):
    return row.get("activity_category") == "walk"


def is_hike(row):
    return row.get("activity_category") == "hike"


def is_ski(row):
    return row.get("activity_category") == "ski"


def is_run(row):
    return row.get("activity_category") == "run"


def is_strength(row):
    return row.get("activity_category") == "strength"


def is_mobility(row):
    return row.get("activity_category") == "mobility"


def sec_to_hms(seconds):
    seconds = int(seconds or 0)
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"