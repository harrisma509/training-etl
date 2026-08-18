from activity_utils import is_cycling_activity, sec_to_hms
from load_rules import (
    intensity_band,
    intensity_score_from_zones,
    round_half_up,
    session_rpe_load,
    supplemental_load_for_other,
)
from strava_client import fetch_activity_detail, fetch_activity_stream_zones, fetch_hr_zones


def build_daily_training(rows, access_token, chronic_c, gear_display_map=None):
    warnings = []
    gear_display_map = gear_display_map or {}
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
        category_counts = count_activity_categories(activities)

        rides = [activity for activity in activities if is_cycling_activity(activity)]

        main_ride = None

        if rides:
            main_ride = max(rides, key=lambda activity: activity["moving_sec"])

        other_activities = []

        for activity in activities:
            if main_ride and activity["id"] == main_ride["id"]:
                continue

            other_activities.append(activity)

        other_moving_sec = sum(activity["moving_sec"] for activity in other_activities)
        other_distance_mi = round(sum(activity["distance_mi"] for activity in other_activities), 2)
        other_elevation_ft = round(sum(activity["elevation_ft"] for activity in other_activities))

        other_activities_payload = [
            {
                "activity_id": str(activity.get("id")) if activity.get("id") is not None else "",
                "name": activity.get("name") if activity.get("name") is not None else "",
                "activity_category": activity.get("activity_category") or "other",
            }
            for activity in other_activities
        ]

        other_names = [
            f"{activity['name']} ({activity.get('activity_category', 'other')})"
            for activity in other_activities
        ]

        other_load_raw = 0.0

        for other in other_activities:
            rpe = -1

            if other.get("activity_category") == "ride" and not other.get("has_heartrate"):
                rpe = get_activity_rpe(other, access_token, rpe_cache, warnings)

            other_load_raw += supplemental_load_for_other(other, rpe)

        other_load = round_half_up(other_load_raw) if other_load_raw > 0 else 0

        zone = empty_zone_result()

        main_load = 0
        main_load_score = 0.0
        main_band = ""
        main_load_text = ""
        main_rpe = -1
        main_load_source = ""

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

                if main_load > 0:
                    main_band = intensity_band(main_load_score, chronic_c)
                    main_load_text = f"{main_load} ({main_band})"
                    main_load_source = "hr_zones"

            except Exception as exc:
                warnings.append(
                    f"Could not fetch HR streams for {main_ride['id']} {main_ride['name']}: {exc}"
                )

        if main_ride and main_load == 0:
            main_rpe = get_activity_rpe(main_ride, access_token, rpe_cache, warnings)

            if main_rpe is not None and main_rpe >= 0:
                minutes = main_ride["moving_sec"] / 60.0
                main_load_score = session_rpe_load(minutes, main_rpe)
                main_load = round_half_up(main_load_score)
                main_band = intensity_band(main_load_score, chronic_c)
                main_load_text = f"{main_load} ({main_band}, RPE)"
                main_load_source = "rpe"

        total_load = main_load + other_load

        daily.append({
            "date": date_key,
            "activity_count": len(activities),

            "activity_categories": format_category_counts(category_counts),
            "ride_count": category_counts.get("ride", 0),
            "walk_count": category_counts.get("walk", 0),
            "hike_count": category_counts.get("hike", 0),
            "strength_count": category_counts.get("strength", 0),
            "mobility_count": category_counts.get("mobility", 0),
            "ski_count": category_counts.get("ski", 0),
            "run_count": category_counts.get("run", 0),
            "other_count": category_counts.get("other", 0),
            "main_ride_id": main_ride["id"] if main_ride else "",
            "main_ride_name": main_ride["name"] if main_ride else "",
            "main_ride_sport_type": main_ride["sport_type"] if main_ride else "",
            "main_ride_category": main_ride.get("activity_category", "") if main_ride else "",
            "main_ride_moving_sec": main_ride["moving_sec"] if main_ride else 0,
            "main_ride_elapsed_sec": main_ride["elapsed_sec"] if main_ride else 0,
            "main_ride_time": sec_to_hms(main_ride["moving_sec"]) if main_ride else "",
            "main_ride_elapsed_time": sec_to_hms(main_ride["elapsed_sec"]) if main_ride else "",
            "main_ride_miles": main_ride["distance_mi"] if main_ride else 0,
            "main_ride_elevation_ft": main_ride["elevation_ft"] if main_ride else 0,
            "main_ride_gear_id": main_ride["gear_id"] if main_ride else "",
            "main_ride_bike_name": (
                gear_display_map.get(main_ride.get("gear_id"))
                if main_ride and main_ride.get("gear_id")
                else ""
            ),
            "main_ride_rpe": main_rpe,
            "main_ride_load_source": main_load_source,
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
            "other_activities": other_activities_payload,
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


def count_activity_categories(activities):
    category_counts = {}

    for activity in activities:
        category = activity.get("activity_category") or "other"
        category_counts[category] = category_counts.get(category, 0) + 1

    return category_counts


def format_category_counts(category_counts):
    if not category_counts:
        return ""

    return ", ".join(
        f"{category}:{count}"
        for category, count in sorted(category_counts.items())
    )


def empty_zone_result():
    return {
        "z1_sec": 0,
        "z2_sec": 0,
        "z3_sec": 0,
        "z4_sec": 0,
        "z5_sec": 0,
        "stream_moving_sec": 0,
        "zone_text": "",
        "warning": "",
    }


def get_activity_rpe(row, access_token, rpe_cache, warnings):
    activity_id = row.get("id")

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