"""
Weekly Audit item scoring rules.

This module owns the individual audit item logic that produces:
- item_key
- item_label
- status
- summary
- sort_order
- evidence_json

Each function should score one audit item using already-fetched weekly or
daily data. The functions should not perform database reads or writes.

The current rules are V1 training-coach rules. Keep changes targeted:
if fixing one metric, edit only that metric's function.
"""

from datetime import timedelta

from audit_utils import safe_int
from weekly_audit_config import (
    AUDIT_ITEMS,
    KNEE_SURGERY_DATE,
    PREHAB_START_DATE,
    REHAB_END_DATE,
    SURGERY_GRACE_DAYS,
    STATUS_GREEN,
    STATUS_YELLOW,
    STATUS_RED,
)


def compute_load_item(weekly_data):
    ac_ratio = weekly_data.get("ac_ratio")
    ramp_pct = weekly_data.get("ramp_pct")
    total_load = weekly_data.get("total_load")

    evidence = {
        "ac_ratio": ac_ratio,
        "ramp_pct": ramp_pct,
        "total_load": total_load,
    }

    if ac_ratio is None or ramp_pct is None:
        return make_item("load", STATUS_YELLOW, "Load data incomplete", evidence)

    if ramp_pct is not None and ramp_pct > 0.20:
        return make_item("load", STATUS_RED, "Ramp above 20% hard cap", evidence)

    if ac_ratio is not None and ac_ratio > 1.4:
        return make_item("load", STATUS_RED, "A/C above 1.4", evidence)

    if ramp_pct is not None and ramp_pct < -0.40:
        return make_item("load", STATUS_YELLOW, "Sharp load drop", evidence)

    if 0.8 <= ac_ratio <= 1.3 and 0 <= ramp_pct <= 0.15:
        return make_item("load", STATUS_GREEN, "A/C stable, ramp controlled", evidence)

    if 0.7 <= ac_ratio < 0.8:
        return make_item("load", STATUS_YELLOW, "A/C slightly below range", evidence)

    if 1.3 < ac_ratio <= 1.4:
        return make_item("load", STATUS_YELLOW, "A/C slightly above range", evidence)

    if 0.15 < ramp_pct <= 0.20:
        return make_item("load", STATUS_YELLOW, "Ramp elevated above 15%", evidence)

    if ramp_pct is not None and ramp_pct < 0:
        return make_item("load", STATUS_YELLOW, "Load dropping", evidence)

    return make_item("load", STATUS_YELLOW, "Load data incomplete", evidence)


def compute_tid_pyramidal_item(zone_data):
    if not zone_data:
        return make_item("tid_pyramidal", STATUS_YELLOW, "Zone data missing", {})

    z1_z2 = zone_data.get("z1_z2_pct")
    z3 = zone_data.get("z3_pct")
    z4_z5 = zone_data.get("z4_z5_pct")
    evidence = {"z1_z2_pct": z1_z2, "z3_pct": z3, "z4_z5_pct": z4_z5}

    if z1_z2 is None or z3 is None or z4_z5 is None:
        return make_item("tid_pyramidal", STATUS_YELLOW, "Zone data missing", evidence)

    if z1_z2 < 60:
        return make_item("tid_pyramidal", STATUS_RED, "Z1-Z2 below 60%", evidence)

    if z3 > 30:
        return make_item("tid_pyramidal", STATUS_RED, "Z3 above 30%", evidence)

    if z4_z5 > 12:
        return make_item("tid_pyramidal", STATUS_RED, "Z4-Z5 elevated", evidence)

    if 65 <= z1_z2 <= 85 and z3 <= 25 and z4_z5 <= 8:
        return make_item("tid_pyramidal", STATUS_GREEN, "Clean pyramidal distribution", evidence)

    if z1_z2 > 85:
        return make_item("tid_pyramidal", STATUS_YELLOW, "Easy-heavy distribution", evidence)

    if 25 <= z3 <= 30:
        return make_item("tid_pyramidal", STATUS_YELLOW, "Z3 creeping high", evidence)

    if 8 <= z4_z5 <= 12:
        return make_item("tid_pyramidal", STATUS_YELLOW, "Z4-Z5 elevated", evidence)

    return make_item("tid_pyramidal", STATUS_YELLOW, "Pyramidal distribution uneven", evidence)


def compute_weight_band_item(week_dates, weight_by_date):
    week_weights = [weight_by_date.get(day) for day in week_dates if day in weight_by_date]
    evidence = {"weights": week_weights}

    if not week_weights:
        return make_item("weight_band", STATUS_YELLOW, "Weight data missing", evidence)

    average_weight = sum(week_weights) / len(week_weights)
    latest_weight = week_weights[-1]
    evidence.update({"average_weight": average_weight, "latest_weight": latest_weight})

    if 177 <= average_weight <= 182 or 177 <= latest_weight <= 182:
        return make_item("weight_band", STATUS_GREEN, "Weight inside target band", evidence)

    if average_weight > 205 or latest_weight > 205:
        return make_item("weight_band", STATUS_RED, "Weight unusually high", evidence)

    if average_weight < 177 or latest_weight < 177:
        return make_item("weight_band", STATUS_YELLOW, "Weight below target band", evidence)

    return make_item("weight_band", STATUS_YELLOW, "Weight outside target band", evidence)


def compute_hard_day_isolation_item(weekly_daily):
    hard_days = []
    borderline_hard_days = []

    for row in weekly_daily:
        if not row:
            continue
        if is_hard_day(row):
            hard_days.append(row)
        elif is_borderline_hard_day(row):
            borderline_hard_days.append(row)

    evidence = {
        "hard_day_count": len(hard_days),
        "borderline_hard_day_count": len(borderline_hard_days),
        "hard_day_dates": [str(row["date"]) for row in hard_days],
        "borderline_dates": [str(row["date"]) for row in borderline_hard_days],
    }

    if len(hard_days) == 1 and len(borderline_hard_days) == 0:
        return make_item("hard_day_isolation", STATUS_GREEN, "One hard day isolated", evidence)
    if len(hard_days) == 0:
        return make_item("hard_day_isolation", STATUS_YELLOW, "No hard stimulus logged", evidence)
    if len(hard_days) == 1 and len(borderline_hard_days) == 1:
        return make_item("hard_day_isolation", STATUS_YELLOW, "One hard day, one borderline", evidence)

    return make_item("hard_day_isolation", STATUS_RED, "Multiple hard days detected", evidence)


def is_hard_day(row):
    total_load = safe_int(row.get("total_load"))
    main_ride_load = safe_int(row.get("main_ride_load"))
    band = (row.get("main_ride_band") or "").lower()
    return (
        total_load >= 400
        or main_ride_load >= 400
        or "very hard" in band
        or "epic" in band
    )


def is_borderline_hard_day(row):
    total_load = safe_int(row.get("total_load"))
    main_ride_load = safe_int(row.get("main_ride_load"))
    band = (row.get("main_ride_band") or "").strip().lower()
    return (
        band == "hard"
        or (300 <= total_load < 400)
        or (300 <= main_ride_load < 400)
    )


def compute_recovery_signals_item(week_start, week_dates, sleep_by_date, hrv_by_date, rhr_by_date):
    sleep_scores = [sleep_by_date.get(day) for day in week_dates if day in sleep_by_date]
    hrv_values = [hrv_by_date.get(day) for day in week_dates if day in hrv_by_date]
    rhr_values = [rhr_by_date.get(day) for day in week_dates if day in rhr_by_date]

    poor_sleep_days = sum(1 for score in sleep_scores if score is not None and score < 80)
    hrv_baseline, rhr_baseline = build_recovery_baseline(week_start, hrv_by_date, rhr_by_date)

    hrv_warnings = 0
    if hrv_baseline is not None:
        hrv_baseline = float(hrv_baseline)
        hrv_warnings = sum(
            1
            for value in hrv_values
            if value is not None and float(value) < hrv_baseline * 0.9
        )

    rhr_warnings = 0
    if rhr_baseline is not None:
        rhr_baseline = float(rhr_baseline)
        rhr_warnings = sum(
            1
            for value in rhr_values
            if value is not None and float(value) > rhr_baseline * 1.05
        )

    warning_points = poor_sleep_days + (1 if hrv_warnings else 0) + (1 if rhr_warnings else 0)
    evidence = {
        "poor_sleep_days": poor_sleep_days,
        "hrv_baseline": hrv_baseline,
        "hrv_warnings": hrv_warnings,
        "rhr_baseline": rhr_baseline,
        "rhr_warnings": rhr_warnings,
        "warning_points": warning_points,
    }

    if not sleep_scores and not hrv_values and not rhr_values:
        return make_item("recovery_signals", STATUS_YELLOW, "Recovery data missing", evidence)

    if warning_points <= 1:
        return make_item("recovery_signals", STATUS_GREEN, "Sleep and recovery stable", evidence)
    if warning_points <= 3:
        return make_item("recovery_signals", STATUS_YELLOW, "Recovery signals slightly off", evidence)
    return make_item("recovery_signals", STATUS_RED, "Multiple recovery signals off", evidence)


def build_recovery_baseline(week_start, hrv_by_date, rhr_by_date):
    lookback_start = week_start - timedelta(days=28)
    lookback_end = week_start - timedelta(days=1)
    hrv_values = [value for date, value in hrv_by_date.items() if lookback_start <= date <= lookback_end]
    rhr_values = [value for date, value in rhr_by_date.items() if lookback_start <= date <= lookback_end]

    hrv_baseline = float(sum(hrv_values) / len(hrv_values)) if len(hrv_values) >= 3 else None
    rhr_baseline = float(sum(rhr_values) / len(rhr_values)) if len(rhr_values) >= 3 else None
    return hrv_baseline, rhr_baseline


def compute_strength_core_item(weekly_daily):
    session_days = 0
    details = []

    for row in weekly_daily:
        if not row:
            continue
        categories = (row.get("activity_categories") or "").lower()
        other_names = (row.get("other_activity_names") or "").lower()
        if "strength" in categories or "strength" in other_names or "core" in categories or "core" in other_names:
            session_days += 1
            details.append(str(row.get("date")))

    evidence = {"strength_core_days": session_days, "dates": details}

    if session_days >= 2:
        return make_item("strength_core", STATUS_GREEN, "Two strength days completed", evidence)
    if session_days == 1:
        return make_item("strength_core", STATUS_YELLOW, "One strength day completed", evidence)
    return make_item("strength_core", STATUS_RED, "No strength days logged", evidence)


def compute_chain_72_hour_item(week_dates, weekly_daily):
    daily_by_date = {row["date"]: row for row in weekly_daily if row}
    hard_days = [row for row in weekly_daily if row and is_hard_day(row)]
    evidence = {"hard_day_count": len(hard_days)}

    if not hard_days:
        return make_item("chain_72_hour", STATUS_GREEN, "No hard day to protect", evidence)

    protected = 0
    partial = 0
    incomplete = False

    for row in hard_days:
        day = row["date"]
        before = daily_by_date.get(day - timedelta(days=1))
        after = daily_by_date.get(day + timedelta(days=1))

        before_easy = before is not None and not is_hard_day(before) and safe_int(before.get("total_load")) < 150
        after_easy = after is not None and not is_hard_day(after) and safe_int(after.get("total_load")) < 150

        if before is None or after is None:
            incomplete = True

        if before_easy and after_easy:
            protected += 1
        elif before_easy or after_easy:
            partial += 1

    evidence.update({"protected_hard_days": protected, "partial_buffer_hard_days": partial, "incomplete": incomplete})

    if protected >= 1 and not incomplete:
        return make_item("chain_72_hour", STATUS_GREEN, "Hard day protected by easy days", evidence)
    if partial >= 1 or incomplete:
        return make_item("chain_72_hour", STATUS_YELLOW, "Partial recovery buffer around hard day", evidence)
    return make_item("chain_72_hour", STATUS_RED, "Hard days stacked", evidence)


def compute_prehab_knee_item(week_start, weekly_daily):
    if week_start < PREHAB_START_DATE:
        return make_item("prehab_knee", STATUS_YELLOW, "Prehab tracking not active", {}, item_label="PreHab knee")

    if week_start < KNEE_SURGERY_DATE:
        prehab_days = []

        for row in weekly_daily:
            if not row:
                continue
            text = " ".join(
                [str(row.get("activity_categories") or ""), str(row.get("other_activity_names") or ""), str(row.get("main_ride_name") or "")]
            ).lower()
            if "prehab" in text:
                prehab_days.append(str(row.get("date")))

        evidence = {"prehab_days": len(prehab_days), "dates": prehab_days}

        if len(prehab_days) >= 2:
            return make_item("prehab_knee", STATUS_GREEN, "Two prehab sessions completed", evidence, item_label="PreHab knee")
        if len(prehab_days) == 1:
            return make_item("prehab_knee", STATUS_YELLOW, "One prehab session completed", evidence, item_label="PreHab knee")
        return make_item("prehab_knee", STATUS_RED, "No prehab sessions logged", evidence, item_label="PreHab knee")

    surgery_end = KNEE_SURGERY_DATE + timedelta(days=SURGERY_GRACE_DAYS)
    if week_start < surgery_end:
        return make_item("prehab_knee", STATUS_YELLOW, "Surgery recovery grace period", {}, item_label="Knee surgery recovery")

    if week_start <= REHAB_END_DATE:
        rehab_days = []

        for row in weekly_daily:
            if not row:
                continue
            text = " ".join(
                [
                    str(row.get("activity_categories") or ""),
                    str(row.get("other_activity_names") or ""),
                    str(row.get("main_ride_name") or ""),
                ]
            ).lower()
            if any(term in text for term in ["rehab", "pt", "physical therapy", "knee"]):
                rehab_days.append(str(row.get("date")))

        evidence = {"rehab_days": len(rehab_days), "dates": rehab_days}

        if len(rehab_days) >= 2:
            return make_item("prehab_knee", STATUS_GREEN, "Two rehab sessions completed", evidence, item_label="Rehab knee")
        if len(rehab_days) == 1:
            return make_item("prehab_knee", STATUS_YELLOW, "One rehab session completed", evidence, item_label="Rehab knee")
        return make_item("prehab_knee", STATUS_RED, "No rehab sessions logged", evidence, item_label="Rehab knee")

    knee_care_days = []

    for row in weekly_daily:
        if not row:
            continue
        text = " ".join(
            [
                str(row.get("activity_categories") or ""),
                str(row.get("other_activity_names") or ""),
                str(row.get("main_ride_name") or ""),
            ]
        ).lower()
        if any(term in text for term in ["strength", "core", "mobility", "balance", "knee", "prehab", "rehab", "pt"]):
            knee_care_days.append(str(row.get("date")))

    evidence = {"knee_care_days": len(knee_care_days), "dates": knee_care_days}

    if len(knee_care_days) >= 2:
        return make_item("prehab_knee", STATUS_GREEN, "Two knee-care sessions completed", evidence, item_label="Knee maintenance")
    if len(knee_care_days) == 1:
        return make_item("prehab_knee", STATUS_YELLOW, "One knee-care session completed", evidence, item_label="Knee maintenance")
    return make_item("prehab_knee", STATUS_RED, "No knee-care sessions logged", evidence, item_label="Knee maintenance")


def make_item(item_key, status, summary, evidence, item_label=None):
    return {
        "item_key": item_key,
        "item_label": item_label if item_label is not None else dict(AUDIT_ITEMS)[item_key],
        "status": status,
        "summary": summary,
        "sort_order": next(idx for idx, item in enumerate(AUDIT_ITEMS, start=1) if item[0] == item_key),
        "source": "computed",
        "evidence_json": evidence,
    }
