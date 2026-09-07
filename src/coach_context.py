"""Assemble bounded, authoritative facts for the internal Coach context API.

This module selects persisted ETL outputs only. It owns no training
calculations, scoring rules, readiness interpretation, or provider-specific
behavior.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from db_writer import connect_db


APP_TIMEZONE = ZoneInfo("America/Denver")
DAILY_DAYS = 14
WEEKLY_ROWS = 12
MODELLED_DAYS = 90
RECOVERY_DAYS = 28
NARRATIVE_LIMIT = 2_000
OTHER_ACTIVITY_LIMIT = 20


def _week_start(value: date) -> date:
    return value - timedelta(days=value.weekday())


def _clip_text(value: Any) -> Any:
    if isinstance(value, str):
        return value[:NARRATIVE_LIMIT]
    return value


def _bounded_json(value: Any, depth: int = 0) -> Any:
    if depth >= 4:
        return "[truncated]"
    if isinstance(value, dict):
        return {str(key): _bounded_json(item, depth + 1) for key, item in list(value.items())[:50]}
    if isinstance(value, list):
        return [_bounded_json(item, depth + 1) for item in value[:50]]
    if isinstance(value, str):
        return value[:NARRATIVE_LIMIT]
    if isinstance(value, (date, datetime, Decimal)):
        return str(value)
    return value


def _rows(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchall()


def _row(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def _source_freshness(cur, table, date_column="date", updated_column="updated_at"):
    return _row(
        cur,
        f"""
        SELECT max({date_column}) AS latest_date,
               max({updated_column}) AS latest_updated_at
        FROM {table}
        """,
    )


def _audit(cur, current_week):
    header = _row(cur, """
        SELECT week_start, audit_version, overall_grade, green_count, yellow_count,
               red_count, audit_summary, next_week_action, source, computed_at,
               reviewed_at, updated_at
        FROM weekly_audit
        WHERE week_start = %s
        """, (current_week,))
    if not header:
        return None
    items = _rows(cur, """
        SELECT item_key, item_label, status, summary, sort_order, source,
               evidence_json, updated_at
        FROM weekly_audit_item
        WHERE week_start = %s
        ORDER BY sort_order, item_key
        """, (current_week,))
    header["items"] = [
        {**item, "evidence_json": _bounded_json(item.get("evidence_json"))}
        for item in items
    ]
    return header


def _latest_completed_audit(cur, current_week):
    header = _row(cur, """
        SELECT week_start, audit_version, overall_grade, green_count, yellow_count,
               red_count, audit_summary, next_week_action, source, computed_at,
               reviewed_at, updated_at
        FROM weekly_audit
        WHERE week_start < %s
        ORDER BY week_start DESC
        LIMIT 1
        """, (current_week,))
    if not header:
        return None
    items = _rows(cur, """
        SELECT item_key, item_label, status, summary, sort_order, source,
               evidence_json, updated_at
        FROM weekly_audit_item
        WHERE week_start = %s
        ORDER BY sort_order, item_key
        """, (header["week_start"],))
    header["items"] = [
        {**item, "evidence_json": _bounded_json(item.get("evidence_json"))}
        for item in items
    ]
    header["evaluation_state"] = "complete_week"
    header["is_provisional"] = False
    return header


def _audit_history(cur, current_week):
    rows = _rows(cur, """
        SELECT week_start, overall_grade, green_count, yellow_count, red_count,
               audit_summary, next_week_action, computed_at
        FROM weekly_audit
        WHERE week_start <= %s
        ORDER BY week_start DESC
        LIMIT %s
        """, (current_week, WEEKLY_ROWS))
    if not rows:
        return []

    week_starts = [row["week_start"] for row in rows]
    items = _rows(cur, """
        SELECT week_start, item_key, status, summary, sort_order
        FROM weekly_audit_item
        WHERE week_start = ANY(%s)
        ORDER BY week_start DESC, sort_order, item_key
        """, (week_starts,))
    items_by_week = {week_start: [] for week_start in week_starts}
    for item in items:
        items_by_week[item["week_start"]].append({
            "item_key": item["item_key"],
            "status": item["status"],
            "summary": item["summary"],
            "sort_order": item["sort_order"],
        })
    for row in rows:
        row["items"] = items_by_week[row["week_start"]]
    return rows


def _daily(cur, current_date):
    rows = _rows(cur, """
        SELECT date, activity_count, activity_categories, ride_count, walk_count,
               hike_count, strength_count, mobility_count, ski_count, run_count,
               other_count, total_load, main_ride_id, main_ride_name,
               main_ride_sport_type, main_ride_category, main_ride_time,
               main_ride_elapsed_time, main_ride_miles, main_ride_elevation_ft,
               main_ride_bike_name, main_ride_rpe, main_ride_load_source,
               main_ride_load, main_ride_load_score, main_ride_band,
               main_ride_load_text, z1_sec, z2_sec, z3_sec, z4_sec, z5_sec,
               z4_z5_sec, stream_moving_sec, other_activity_count,
               other_activity_names, other_time, other_miles, other_elevation_ft,
               other_load, other_activities, updated_at
        FROM daily_training
        WHERE date BETWEEN %s AND %s
        ORDER BY date DESC
        """, (current_date - timedelta(days=DAILY_DAYS - 1), current_date))
    for row in rows:
        activities = row.get("other_activities")
        row["other_activities"] = _bounded_json(activities[:OTHER_ACTIVITY_LIMIT] if isinstance(activities, list) else activities)
        if row.get("main_ride_rpe") == -1:
            row["main_ride_rpe"] = None
    return rows


def _fitness_fatigue_form(cur, current_date):
    history = _rows(cur, """
        SELECT date, daily_load, fitness, fatigue, form, model_version, updated_at
        FROM daily_fitness_fatigue
        WHERE date BETWEEN %s AND %s
        ORDER BY date
        """, (current_date - timedelta(days=MODELLED_DAYS - 1), current_date))
    current = _row(cur, """
        SELECT date, daily_load, fitness, fatigue, form, model_version, updated_at
        FROM daily_fitness_fatigue
        WHERE date <= %s
        ORDER BY date DESC
        LIMIT 1
        """, (current_date,))
    changes = {}
    current_date_value = current["date"] if current else None
    reference_rows = {}
    if current_date_value:
        reference_dates = [current_date_value - timedelta(days=days) for days in (7, 28, 90)]
        placeholders = ", ".join("%s" for _ in reference_dates)
        reference_rows = {
            row["date"]: row
            for row in _rows(cur, f"""
                SELECT date, fitness, fatigue, form
                FROM daily_fitness_fatigue
                WHERE date IN ({placeholders})
                """, reference_dates)
        }
    for days in (7, 28, 90):
        reference_date = current_date_value - timedelta(days=days) if current_date_value else None
        reference = reference_rows.get(reference_date) if reference_date else None
        changes[str(days)] = {
            "reference_date": reference_date,
            "fitness_change": current["fitness"] - reference["fitness"] if current and reference else None,
            "fatigue_change": current["fatigue"] - reference["fatigue"] if current and reference else None,
            "form_change": current["form"] - reference["form"] if current and reference else None,
        }
    return {"current": current, "history": history, "changes": changes,
            "note": "Form is a modeled training-load value, not a complete readiness score."}


def _recovery(cur, current_date):
    start = current_date - timedelta(days=RECOVERY_DAYS - 1)
    sources = {
        "sleep": ("health_sleep", "sleep_score, total_sleep_hr, source, updated_at", "sleep_score", "updated_at"),
        "hrv": ("health_hrv", "hrv_sdnn_ms, measured_at, source, updated_at", "hrv_sdnn_ms", "updated_at"),
        "rhr": ("health_rhr", "rhr_bpm, measured_at, source, updated_at", "rhr_bpm", "updated_at"),
        "steps": ("health_steps", "steps, measured_at, source, updated_at", "steps", "updated_at"),
        "weight": ("health_weight", "weight_lb, measured_at, source, updated_at", "weight_lb", "updated_at"),
        "falls": ("health_falls", "falls, measured_at, source, updated_at", "falls", "updated_at"),
    }
    result = {}
    for key, (table, columns, value_column, update_column) in sources.items():
        rows = _rows(cur, f"""
            SELECT date, {columns}
            FROM {table}
            WHERE date BETWEEN %s AND %s
            ORDER BY date ASC
            """, (start, current_date))
        for row in rows:
            target = result.setdefault(row["date"], {"date": row["date"]})
            target[value_column] = row.get(value_column)
            if key == "sleep":
                target["total_sleep_hr"] = row.get("total_sleep_hr")
            target[f"{key}_measured_at"] = row.get("measured_at")
            target[f"{key}_source"] = row.get("source")
            target[f"{key}_updated_at"] = row.get(update_column)
    return [result[key] for key in sorted(result)]


def _commentary(cur, current_week):
    rows = _rows(cur, """
        SELECT week_start, week_type, event, planned_focus, actual_focus,
               weekly_comment, risk_note, coach_note, task_note, lesson_learned,
               status_override, is_travel_week, is_sick_week, is_injury_week,
               is_bike_park_week, is_recovery_week, is_goal_week,
               display_priority, created_at, updated_at
        FROM weekly_commentary
        WHERE week_start <= %s AND week_start > %s AND hide_from_dashboard = false
        ORDER BY week_start DESC
        LIMIT %s
        """, (current_week, current_week - timedelta(days=7 * WEEKLY_ROWS), WEEKLY_ROWS))
    text_fields = ("event", "planned_focus", "actual_focus", "weekly_comment", "risk_note",
                   "coach_note", "task_note", "lesson_learned", "status_override")
    for row in rows:
        for field in text_fields:
            row[field] = _clip_text(row.get(field)) if row.get(field) else None
    return rows


def _next_commentary(cur, next_week):
    rows = _rows(cur, """
        SELECT week_start, week_type, event, planned_focus, actual_focus,
               weekly_comment, risk_note, coach_note, task_note, lesson_learned,
               status_override, is_travel_week, is_sick_week, is_injury_week,
               is_bike_park_week, is_recovery_week, is_goal_week,
               display_priority, created_at, updated_at
        FROM weekly_commentary
        WHERE week_start = %s AND hide_from_dashboard = false
        """, (next_week,))
    if not rows:
        return None
    text_fields = ("event", "planned_focus", "actual_focus", "weekly_comment", "risk_note",
                   "coach_note", "task_note", "lesson_learned", "status_override")
    for row in rows:
        for field in text_fields:
            row[field] = _clip_text(row.get(field)) if row.get(field) else None
    return rows[0]


def _year_summary(cur, current_date):
    row = _row(cur, """
        SELECT calendar_year, training_hours, strava_activity_hours,
               total_elevation_ft, ride_count, ride_days, strength_sessions,
               mobility_sessions, ski_days, through_date, coverage_status, updated_at
        FROM training_year
        WHERE calendar_year = %s
        """, (current_date.year,))
    if row:
        commentary = _row(cur, """
            SELECT good_summary, bad_summary, annual_summary
            FROM training_year_commentary
            WHERE calendar_year = %s
            """, (current_date.year,))
        if commentary:
            row.update({key: _clip_text(value) for key, value in commentary.items()})
    return row


def build_coach_context(cfg):
    """Return the fixed-range coaching snapshot using SELECT-only queries."""
    now = datetime.now(APP_TIMEZONE)
    current_date = now.date()
    current_week = _week_start(current_date)
    current_week_end = current_week + timedelta(days=6)

    with connect_db(cfg) as conn:
        with conn.cursor() as cur:
            daily = _daily(cur, current_date)
            weekly = _rows(cur, """
                SELECT week_start, week_end, total_load, main_ride_load, other_load,
                       activity_days, ride_count, walk_count, hike_count, strength_count,
                       mobility_count, ski_count, run_count, other_count,
                       very_hard_epic_days, chronic_daily_c, chronic_weekly_cw, ac_ratio,
                       ramp_pct, ramp_pct_display, remaining_to_20pct_ramp, status_level,
                       status_text, updated_at
                FROM weekly_training
                WHERE week_start <= %s
                ORDER BY week_start DESC
                LIMIT %s
                """, (current_week, WEEKLY_ROWS))
            zones = _rows(cur, """
                SELECT week_start, week_end, ride_count, ride_time_sec, z1_sec, z2_sec,
                       z3_sec, z4_sec, z5_sec, z1_z2_sec, z4_z5_sec, z1_z2_pct,
                       z3_pct, z4_z5_pct, zone_coverage_pct, zone_flag
                FROM weekly_zone_summary
                WHERE week_start <= %s
                ORDER BY week_start DESC
                LIMIT %s
                """, (current_week, WEEKLY_ROWS))
            current_audit = _audit(cur, current_week)
            latest_completed_audit = _latest_completed_audit(cur, current_week)
            audit_history = _audit_history(cur, current_week)
            fff = _fitness_fatigue_form(cur, current_date)
            recovery = _recovery(cur, current_date)
            commentary = _commentary(cur, current_week)
            next_commentary = _next_commentary(cur, current_week + timedelta(days=7))
            year_summary = _year_summary(cur, current_date)
            latest_activity = _row(cur, "SELECT max(date_local) AS latest_date FROM strava_activities")
            freshness = {
                "daily_training": _source_freshness(cur, "daily_training"),
                "weekly_training": _source_freshness(cur, "weekly_training", "week_start"),
                "weekly_audit": _source_freshness(cur, "weekly_audit", "week_start", "computed_at"),
                "weekly_zone_summary": {"latest_date": zones[0]["week_start"] if zones else None, "latest_updated_at": None},
                "daily_fitness_fatigue": _source_freshness(cur, "daily_fitness_fatigue"),
                "recovery": {"latest_date": recovery[-1]["date"] if recovery else None,
                             "latest_updated_at": max((value for row in recovery for key, value in row.items() if key.endswith("_updated_at") and value), default=None)},
                "weekly_commentary": _source_freshness(cur, "weekly_commentary", "week_start"),
                "training_year": _source_freshness(cur, "training_year", "calendar_year"),
            }

    data_through = daily[0]["date"] if daily else None
    days_elapsed = (current_date - current_week).days + 1
    # Sunday remains an active, incomplete coaching week until it has ended.
    is_complete = current_date > current_week_end
    current_zone = next((row for row in zones if row["week_start"] == current_week), None)
    if current_audit:
        current_audit.update({
            "evaluation_state": "complete_week" if is_complete else "partial_week",
            "is_provisional": not is_complete,
            "days_elapsed": days_elapsed,
            "days_remaining": max(0, 7 - days_elapsed),
            "data_through_date": data_through,
        })
    current_commentary = next((row for row in commentary if row["week_start"] == current_week), None)
    current_flags = (
        {key: current_commentary.get(key) for key in ("is_travel_week", "is_sick_week", "is_injury_week", "is_bike_park_week", "is_recovery_week", "is_goal_week")}
        if current_commentary else {}
    )
    has_upcoming_text = any(
        current_commentary and (current_commentary.get(field) or "").strip()
        for field in ("event", "planned_focus", "risk_note")
    )
    has_upcoming_flag = any(current_flags.values())
    upcoming_context_available = bool(has_upcoming_text or has_upcoming_flag or next_commentary)
    return {
        "as_of": {"timezone": "America/Denver", "current_date": current_date,
                  "current_week_start": current_week, "current_week_end": current_week_end,
                  "latest_activity_date": latest_activity["latest_date"] if latest_activity else None,
                  "latest_daily_update": freshness["daily_training"]["latest_updated_at"],
                  "latest_weekly_update": freshness["weekly_training"]["latest_updated_at"],
                  "latest_audit_computed_at": freshness["weekly_audit"]["latest_updated_at"],
                  "latest_fitness_fatigue_form_update": freshness["daily_fitness_fatigue"]["latest_updated_at"],
                  "response_generated_at": now},
        "week_progress": {"week_start": current_week, "week_end": current_week_end,
                          "is_current_week": True, "is_complete_week": is_complete,
                          "days_elapsed": days_elapsed, "days_remaining": max(0, 7 - days_elapsed),
                          "data_through_date": data_through},
        "freshness": freshness,
        "coverage": {"detailed_daily_days_returned": len(daily), "weekly_rows_returned": len(weekly),
                     "fitness_fatigue_form_days_returned": len(fff["history"]), "recovery_days_requested": RECOVERY_DAYS,
                     "sleep_days_measured": sum(1 for row in recovery if row.get("sleep_score") is not None),
                     "sleep_duration_days_measured": sum(1 for row in recovery if row.get("total_sleep_hr") is not None),
                     "hrv_days_measured": sum(1 for row in recovery if row.get("hrv_sdnn_ms") is not None),
                     "rhr_days_measured": sum(1 for row in recovery if row.get("rhr_bpm") is not None),
                     "weight_days_measured": sum(1 for row in recovery if row.get("weight_lb") is not None),
                     "steps_days_measured": sum(1 for row in recovery if row.get("steps") is not None),
                     "falls_days_measured": sum(1 for row in recovery if row.get("falls") is not None),
                     "commentary_weeks_available": len(commentary), "current_audit_available": current_audit is not None,
                     "latest_completed_audit_available": latest_completed_audit is not None,
                     "current_zone_coverage_pct": current_zone["zone_coverage_pct"] if current_zone else None,
                     "missing_sources": [name for name, value in freshness.items() if not value.get("latest_date") and not value.get("latest_updated_at")] + (["current_weekly_audit"] if current_audit is None else [])},
        "current_weekly_audit": current_audit,
        "latest_completed_weekly_audit": latest_completed_audit,
        "audit_history": audit_history,
        "weekly_load_history": weekly,
        "weekly_tid_history": zones,
        "recent_days": daily,
        "fitness_fatigue_form": fff,
        "recovery_history": recovery,
        "athlete_narrative": {"current_week": current_commentary, "recent_weeks": commentary},
        "upcoming_context": {"current_week_event": current_commentary.get("event") if current_commentary else None,
                             "current_week_planned_focus": current_commentary.get("planned_focus") if current_commentary else None,
                             "current_week_risk_note": current_commentary.get("risk_note") if current_commentary else None,
                     "current_week_flags": current_flags,
                     "next_week_commentary": next_commentary, "upcoming_context_available": upcoming_context_available},
        "year_summary": year_summary,
        "missing_subjective_context": ["current knee pain", "current leg freshness", "current soreness", "current illness symptoms", "recent unrecorded physical labor", "current handling or coordination quality", "today's schedule constraints", "upcoming hard commitments not recorded in commentary"],
    }