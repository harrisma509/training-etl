"""
Weekly Audit ETL entrypoint.

This script orchestrates the weekly audit workflow:
1. Fetch source training and health data.
2. Compute weekly audit items.
3. Build the weekly audit header.
4. Upsert results into weekly_audit and weekly_audit_item.

Business rules, scoring weights, SQL, and utility helpers live in focused
modules so future audit changes can be made safely without editing this
orchestration layer.

This refactor is intended to preserve existing behavior.
"""

import logging
from datetime import datetime, timedelta, timezone

from db_writer import connect_db
from logging_config import configure_logging
from settings import get_db_config

logger = logging.getLogger(__name__)
from weekly_audit_queries import (
    fetch_weekly_training,
    fetch_weekly_zone_summary,
    fetch_daily_training,
    fetch_health_rows,
    upsert_weekly_audit,
    upsert_weekly_audit_item,
)
from weekly_audit_rules import (
    compute_load_item,
    compute_tid_pyramidal_item,
    compute_weight_band_item,
    compute_hard_day_isolation_item,
    compute_recovery_signals_item,
    compute_strength_core_item,
    compute_chain_72_hour_item,
    compute_prehab_knee_item,
)
from weekly_audit_scoring import build_weekly_audit


def main():
    cfg = get_db_config()

    if not cfg.get("WRITE_DB"):
        raise SystemExit("WRITE_DB is not enabled in environment; audit ETL requires database access.")

    with connect_db(cfg) as conn:
        with conn.cursor() as cur:
            weekly_rows = fetch_weekly_training(cur)
            if not weekly_rows:
                logger.info("No weekly_training rows found; nothing to audit.")
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

    logger.info("Weekly audit ETL completed for %s weeks", weeks)


def get_week_dates(week_start):
    return [week_start + timedelta(days=i) for i in range(7)]


if __name__ == "__main__":
    configure_logging("training-runner-audit")
    try:
        main()
    except Exception:
        logger.exception("Weekly audit ETL failed")
        raise
