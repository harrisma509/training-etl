import logging
import sys
from datetime import datetime, timezone

from activity_utils import normalize_activity, sec_to_hms
from daily_builder import build_daily_training
from logging_config import configure_logging
from settings import get_config
from strava_client import fetch_activities, refresh_access_token
from weekly_builder import build_weekly_training
from db_writer import write_training_to_db
from gear_db import fetch_gear_display_map

logger = logging.getLogger(__name__)


def main():
    cfg = get_config()

    logger.info("Training sync starting")
    logger.info("Window: last %s days", cfg["DAYS_BACK"])
    logger.info("Load chronic C used for banding: %s", cfg["LOAD_CHRONIC_C"])

    token = refresh_access_token(cfg)
    access_token = token["access_token"]

    activities = fetch_activities(access_token, cfg["DAYS_BACK"])
    rows = [normalize_activity(activity) for activity in activities]

    gear_display_map = fetch_gear_display_map(cfg) if cfg.get("WRITE_DB") else {}
    logger.info("Gear records loaded from DB: %s", len(gear_display_map))

    daily, warnings = build_daily_training(
        rows=rows,
        access_token=access_token,
        chronic_c=cfg["LOAD_CHRONIC_C"],
        gear_display_map=gear_display_map,
    )

    weekly = build_weekly_training(daily)

    logger.info("Activities pulled: %s", len(rows))
    logger.info("Daily rows built: %s", len(daily))

    for row in daily:
        logger.info(
            "%s | main=%s bike=%s main_load=%s other_load=%s total_load=%s z4z5=%s",
            row["date"],
            row["main_ride_name"] or "None",
            row["main_ride_bike_name"] or "None",
            row["main_ride_load"],
            row["other_load"],
            row["total_load"],
            sec_to_hms(row["z4_z5_sec"]),
        )

    logger.info("Weekly rows built: %s", len(weekly))

    for row in weekly:
        ac_ratio = row["ac_ratio"] if row["ac_ratio"] is not None else "n/a"
        ramp = row["ramp_pct_display"] if row["ramp_pct_display"] else "n/a"

        logger.info(
            "%s | load=%s ramp=%s ac=%s status=%s",
            row["week_start"],
            row["total_load"],
            ramp,
            ac_ratio,
            row["status_level"],
        )

    if warnings:
        logger.warning("Warnings: %s", len(warnings))

        for warning in warnings:
            logger.warning("%s", warning)

    run_at_utc = datetime.now(timezone.utc).isoformat()

    write_training_to_db(
        cfg=cfg,
        activities=rows,
        daily_rows=daily,
        weekly_rows=weekly,
        warnings=warnings,
        run_at_utc=run_at_utc,
    )
    if cfg.get("WRITE_DB"):
        logger.info("Postgres write complete")

    logger.info("Training sync complete")


if __name__ == "__main__":
    configure_logging("training-runner-sync")
    try:
        main()
    except Exception:
        logger.exception("Training sync failed")
        sys.exit(1)