"""
Weekly Audit database queries.

This module owns database reads and writes for the weekly audit ETL:
- source data fetches
- weekly_audit upsert
- weekly_audit_item upsert

Do not put audit scoring rules here.
Do not put UI logic here.
Keep write operations idempotent so the ETL can be rerun safely.
"""

import json

from weekly_audit_config import AUDIT_MIN_WEEK_START
from audit_utils import normalize_json_value


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
