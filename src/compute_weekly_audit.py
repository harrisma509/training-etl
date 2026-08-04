import decimal
import json
from datetime import date, datetime, timedelta, timezone

from db_writer import connect_db
from settings import get_db_config

# Weekly Audit intentionally runs for the current year only.
#
# Reasoning:
# - The audit is a forward-looking coaching tool, not a full historical backfill.
# - Pre-2026 / older training data has inconsistent coverage for zones, weight,
#   sleep, HRV, RHR, strength naming, and prehab tagging, which creates noisy
#   or misleading audit grades.
# - Limiting to the current year keeps ETL runtime fast and makes reruns cheap
#   while rules are still being tuned.
# - Current-year scoring gives cleaner feedback because the source data model,
#   activity naming conventions, and training priorities are more consistent.
# - If the audit rules prove useful, older years can be backfilled later with
#   year-specific rule versions or relaxed historical-data handling.
# - The daily lookback can still include late prior-year data when needed for
#   baselines, but persisted audit rows should stay focused on the current year.
AUDIT_MIN_WEEK_START = date(date.today().year, 1, 1)
KNEE_SURGERY_DATE = date(2026, 11, 19)
PREHAB_START_DATE = date(date.today().year, 8, 1)
SURGERY_GRACE_DAYS = 14
REHAB_END_DATE = date(2027, 5, 19)

STATUS_GREEN = "🟩 Green"
STATUS_YELLOW = "🟨 Yellow"
STATUS_RED = "🟥 Red"

GRADE_WEIGHTS = {
    "load": 25,
    "tid_pyramidal": 20,
    "hard_day_isolation": 15,
    "recovery_signals": 15,
    "strength_core": 12,
    "chain_72_hour": 8,
    "weight_band": 5,
}

GATE_ITEM_KEYS = {"prehab_knee"}
CRITICAL_ITEM_KEYS = {"load", "tid_pyramidal", "hard_day_isolation", "recovery_signals"}
STATUS_MULTIPLIERS = {
    STATUS_GREEN: 1.0,
    STATUS_YELLOW: 0.65,
    STATUS_RED: 0.0,
}

AUDIT_ITEMS = [
    ("load", "Load"),
    ("tid_pyramidal", "TID / Pyramidal"),
    ("weight_band", "Weight band"),
    ("hard_day_isolation", "Hard day isolation"),
    ("recovery_signals", "Recovery signals"),
    ("strength_core", "Strength & core"),
    ("chain_72_hour", "72-hour chain rule"),
    ("prehab_knee", "PreHab knee"),
]


def main():
    cfg = get_db_config()

    if not cfg.get("WRITE_DB"):
        raise SystemExit("WRITE_DB is not enabled in environment; audit ETL requires database access.")

    with connect_db(cfg) as conn:
        with conn.cursor() as cur:
            weekly_rows = fetch_weekly_training(cur)
            if not weekly_rows:
                print("No weekly_training rows found; nothing to audit.")
                return

            zone_rows = fetch_weekly_zone_summary(cur)
            daily_rows = fetch_daily_training(cur)
            weight_rows = fetch_health_rows(cur, "health_weight", ["date", "weight_lb"])
            sleep_rows = fetch_health_rows(cur, "health_sleep", ["date", "sleep_score"])
            hrv_rows = fetch_health_rows(cur, "health_hrv", ["date", "hrv_sdnn_ms"])
            rhr_rows = fetch_health_rows(cur, "health_rhr", ["date", "rhr_bpm"])

            zone_by_week = {row["week_start"]: row for row in zone_rows}
            daily_by_date = {row["date"]: row for row in daily_rows}
            weight_by_date = {row["date"]: row["weight_lb"] for row in weight_rows if row.get("weight_lb") is not None}
            sleep_by_date = {row["date"]: row["sleep_score"] for row in sleep_rows if row.get("sleep_score") is not None}
            hrv_by_date = {row["date"]: row["hrv_sdnn_ms"] for row in hrv_rows if row.get("hrv_sdnn_ms") is not None}
            rhr_by_date = {row["date"]: row["rhr_bpm"] for row in rhr_rows if row.get("rhr_bpm") is not None}

            computed_at = datetime.now(timezone.utc)
            weeks = 0

            for week_start, weekly_data in weekly_rows.items():
                week_dates = get_week_dates(week_start)
                weekly_daily = [daily_by_date.get(day) for day in week_dates]
                zone_data = zone_by_week.get(week_start)

                items = [
                    compute_load_item(weekly_data),
                    compute_tid_pyramidal_item(zone_data),
                    compute_weight_band_item(week_dates, weight_by_date),
                    compute_hard_day_isolation_item(weekly_daily),
                    compute_recovery_signals_item(week_start, week_dates, sleep_by_date, hrv_by_date, rhr_by_date),
                    compute_strength_core_item(weekly_daily),
                    compute_chain_72_hour_item(week_dates, weekly_daily),
                    compute_prehab_knee_item(week_start, weekly_daily),
                ]

                audit = build_weekly_audit(week_start, items, computed_at)
                upsert_weekly_audit(cur, audit)
                for item in items:
                    upsert_weekly_audit_item(cur, week_start, item)

                weeks += 1

            conn.commit()

    print(f"Weekly audit ETL completed for {weeks} weeks")


def get_audit_min_date():
    if AUDIT_MIN_WEEK_START is None:
        return None
    return AUDIT_MIN_WEEK_START - timedelta(days=28)


def fetch_weekly_training(cur):
    sql = """
        SELECT
            week_start,
            total_load,
            ac_ratio,
            ramp_pct,
            ramp_pct_display
        FROM weekly_training
    """

    params = {}

    if AUDIT_MIN_WEEK_START is not None:
        sql += "\n        WHERE week_start >= %(min_week_start)s"
        params["min_week_start"] = AUDIT_MIN_WEEK_START

    sql += "\n        ORDER BY week_start"

    cur.execute(sql, params)
    return {row["week_start"]: dict(row) for row in cur.fetchall()}


def fetch_weekly_zone_summary(cur):
    sql = """
        SELECT
            week_start,
            z1_z2_pct,
            z3_pct,
            z4_z5_pct
        FROM weekly_zone_summary
    """

    params = {}

    if AUDIT_MIN_WEEK_START is not None:
        sql += "\n        WHERE week_start >= %(min_week_start)s"
        params["min_week_start"] = AUDIT_MIN_WEEK_START

    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def fetch_daily_training(cur):
    cur.execute(
        """
        SELECT
            date,
            total_load,
            main_ride_load,
            main_ride_band,
            activity_categories,
            other_activity_names,
            main_ride_name,
            strength_count,
            mobility_count
        FROM daily_training
        ORDER BY date
        """
    )
    return [dict(row) for row in cur.fetchall()]


def fetch_health_rows(cur, table_name, fields):
    fields_sql = ", ".join(fields)
    cur.execute(f"SELECT {fields_sql} FROM {table_name} ORDER BY date")
    return [dict(row) for row in cur.fetchall()]


def get_week_dates(week_start):
    return [week_start + timedelta(days=i) for i in range(7)]


def build_weekly_audit(week_start, items, computed_at):
    green_count = sum(1 for item in items if item["status"] == STATUS_GREEN)
    yellow_count = sum(1 for item in items if item["status"] == STATUS_YELLOW)
    red_count = sum(1 for item in items if item["status"] == STATUS_RED)

    weighted_score, critical_red_count, gate_flags = calculate_weighted_score(items)
    overall_grade = calculate_overall_grade(weighted_score, critical_red_count)
    audit_summary = build_audit_summary(items)
    next_week_action = build_next_week_action(overall_grade)

    return {
        "week_start": week_start,
        "audit_version": "v1",
        "overall_grade": overall_grade,
        "green_count": green_count,
        "yellow_count": yellow_count,
        "red_count": red_count,
        "audit_summary": audit_summary,
        "next_week_action": next_week_action,
        "source": "computed",
        "computed_at": computed_at,
    }


def calculate_weighted_score(items):
    weighted_score = 0.0
    critical_red_count = 0
    gate_flags = []

    for item in items:
        item_key = item["item_key"]
        status = item["status"]

        if item_key in GATE_ITEM_KEYS:
            if status == STATUS_RED:
                gate_flags.append(item_key)
            continue

        weight = GRADE_WEIGHTS.get(item_key)
        if weight is None:
            continue

        multiplier = STATUS_MULTIPLIERS.get(status, 0.0)
        weighted_score += weight * multiplier

        if item_key in CRITICAL_ITEM_KEYS and status == STATUS_RED:
            critical_red_count += 1

    return round(weighted_score, 1), critical_red_count, gate_flags


def calculate_overall_grade(weighted_score, critical_red_count):
    if critical_red_count >= 2:
        return "R"
    if weighted_score >= 80:
        return "G"
    if weighted_score >= 65:
        return "Y"
    return "R"


def build_audit_summary(items):
    problems = [item["summary"] for item in items if item["status"] != STATUS_GREEN]
    if not problems:
        return "All eight audit items look balanced"

    summary = ", ".join(problems[:3])
    if len(summary.split()) > 12:
        summary = "; ".join(problems[:2])
    return summary[:180]


def build_next_week_action(overall_grade):
    if overall_grade == "G":
        return "Build normally and maintain recovery balance"
    if overall_grade == "Y":
        return "Watch warning areas before adding intensity"
    return "Reduce load and prioritize recovery"


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


def safe_int(value):
    if value is None:
        return 0
    try:
        return int(round(float(value)))
    except Exception:
        return 0


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


def normalize_json_value(value):
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: normalize_json_value(subval) for key, subval in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_json_value(item) for item in value]
    return value


def upsert_weekly_audit(cur, audit):
    cur.execute(
        """
        INSERT INTO weekly_audit (
            week_start,
            audit_version,
            overall_grade,
            green_count,
            yellow_count,
            red_count,
            audit_summary,
            next_week_action,
            source,
            computed_at,
            updated_at
        ) VALUES (
            %(week_start)s,
            %(audit_version)s,
            %(overall_grade)s,
            %(green_count)s,
            %(yellow_count)s,
            %(red_count)s,
            %(audit_summary)s,
            %(next_week_action)s,
            %(source)s,
            %(computed_at)s,
            now()
        )
        ON CONFLICT (week_start) DO UPDATE SET
            audit_version = EXCLUDED.audit_version,
            overall_grade = EXCLUDED.overall_grade,
            green_count = EXCLUDED.green_count,
            yellow_count = EXCLUDED.yellow_count,
            red_count = EXCLUDED.red_count,
            audit_summary = EXCLUDED.audit_summary,
            next_week_action = EXCLUDED.next_week_action,
            source = EXCLUDED.source,
            computed_at = EXCLUDED.computed_at,
            updated_at = now()
        """,
        audit,
    )


def upsert_weekly_audit_item(cur, week_start, item):
    parameters = item.copy()
    parameters["week_start"] = week_start
    parameters["evidence_json"] = json.dumps(
        normalize_json_value(parameters.get("evidence_json")),
    )

    cur.execute(
        """
        INSERT INTO weekly_audit_item (
            week_start,
            item_key,
            item_label,
            status,
            summary,
            sort_order,
            source,
            evidence_json
        ) VALUES (
            %(week_start)s,
            %(item_key)s,
            %(item_label)s,
            %(status)s,
            %(summary)s,
            %(sort_order)s,
            %(source)s,
            %(evidence_json)s
        )
        ON CONFLICT (week_start, item_key) DO UPDATE SET
            item_label = EXCLUDED.item_label,
            status = EXCLUDED.status,
            summary = EXCLUDED.summary,
            sort_order = EXCLUDED.sort_order,
            source = EXCLUDED.source,
            evidence_json = EXCLUDED.evidence_json,
            updated_at = now()
        """,
        parameters,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}")
        raise
