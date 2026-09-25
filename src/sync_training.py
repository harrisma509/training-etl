import logging
import sys
from datetime import datetime, timezone

from activity_utils import extract_activity_narrative, normalize_activity, sec_to_hms
from daily_builder import build_daily_training
from db_writer import (
    connect_db,
    fetch_existing_activity_ids,
    fetch_recent_narrative_refresh_ids,
    upsert_activity_narrative,
)
from logging_config import configure_logging
from settings import get_config
from strava_client import fetch_activities, fetch_activity_detail, refresh_access_token
from weekly_builder import build_weekly_training
from gear_db import fetch_gear_display_map
from db_writer import write_training_to_db

logger = logging.getLogger(__name__)


def identify_new_activity_ids(rows, existing_activity_ids):
    new_activity_ids = []
    seen_activity_ids = set()
    existing_activity_ids = {str(activity_id) for activity_id in existing_activity_ids}

    for row in rows:
        activity_id = row.get("id")
        if activity_id is None:
            continue
        activity_id = str(activity_id)
        if activity_id not in existing_activity_ids and activity_id not in seen_activity_ids:
            new_activity_ids.append(activity_id)
            seen_activity_ids.add(activity_id)

    return new_activity_ids


def enrich_new_activity_narratives(cfg, access_token, activity_ids, observed_at=None):
    result = {
        "detail_requests_attempted": 0,
        "narrative_inspections_succeeded": 0,
        "narrative_inspections_failed": 0,
        "narrative_inspections_skipped": 0,
    }

    for activity_id in activity_ids:
        result["detail_requests_attempted"] += 1
        try:
            detail = fetch_activity_detail(access_token, activity_id)
            if not detail:
                raise RuntimeError("empty detail response")
            narrative = extract_activity_narrative(detail)
            if any(
                narrative[field_name]["state"] == "malformed"
                for field_name in ("description", "private_note")
            ):
                raise ValueError("malformed narrative")
            inspection_time = observed_at or datetime.now(timezone.utc)
            with connect_db(cfg) as conn:
                with conn.cursor() as cur:
                    upsert_activity_narrative(
                        cur,
                        activity_id,
                        narrative,
                        observed_at=inspection_time,
                        record_inspection=True,
                    )
                conn.commit()
            result["narrative_inspections_succeeded"] += 1
        except Exception:
            result["narrative_inspections_failed"] += 1
            logger.warning(
                "Narrative enrichment failed for activity_id=%s",
                activity_id,
                exc_info=True,
            )

    return result


def merge_narrative_results(*results):
    merged = {
        "detail_requests_attempted": 0,
        "narrative_inspections_succeeded": 0,
        "narrative_inspections_failed": 0,
        "narrative_inspections_skipped": 0,
    }
    for result in results:
        for key in merged:
            merged[key] += result.get(key, 0)
    return merged


def main():
    cfg = get_config()

    logger.info("Training sync starting")
    logger.info("Window: last %s days", cfg["DAYS_BACK"])
    logger.info("Load chronic C used for banding: %s", cfg["LOAD_CHRONIC_C"])

    token = refresh_access_token(cfg)
    access_token = token["access_token"]

    activities = fetch_activities(access_token, cfg["DAYS_BACK"])
    rows = [normalize_activity(activity) for activity in activities]

    new_activity_ids = []
    if cfg.get("WRITE_DB"):
        existing_activity_ids = fetch_existing_activity_ids(cfg, rows)
        new_activity_ids = identify_new_activity_ids(rows, existing_activity_ids)

    gear_display_map = fetch_gear_display_map(cfg) if not cfg.get("WRITE_DB") else {}
    logger.info("Gear records loaded from DB: %s", len(gear_display_map))

    if cfg.get("WRITE_DB"):
        daily = []
        weekly = []
        warnings = []
    else:
        daily, warnings = build_daily_training(
            rows=rows,
            access_token=access_token,
            chronic_c=cfg["LOAD_CHRONIC_C"],
            gear_display_map=gear_display_map,
        )
        weekly = build_weekly_training(daily)

    run_timestamp = datetime.now(timezone.utc)
    run_at_utc = run_timestamp.isoformat()

    write_result = write_training_to_db(
        cfg=cfg,
        activities=rows,
        daily_rows=daily,
        weekly_rows=weekly,
        warnings=warnings,
        run_at_utc=run_at_utc,
        access_token=access_token,
        chronic_c=cfg["LOAD_CHRONIC_C"],
    )

    if write_result is not None:
        daily = write_result["daily_rows"]
        weekly = write_result["weekly_rows"]
        warnings = write_result["warnings"]

    narrative_result = {
        "detail_requests_attempted": 0,
        "narrative_inspections_succeeded": 0,
        "narrative_inspections_failed": 0,
        "narrative_inspections_skipped": len(rows) - len(new_activity_ids),
    }
    if cfg.get("WRITE_DB"):
        new_narrative_result = enrich_new_activity_narratives(
            cfg,
            access_token,
            new_activity_ids,
            observed_at=run_timestamp,
        )
        recent_ids = fetch_recent_narrative_refresh_ids(
            cfg,
            run_timestamp,
            excluded_ids=new_activity_ids,
        )
        recent_narrative_result = enrich_new_activity_narratives(
            cfg,
            access_token,
            recent_ids,
            observed_at=run_timestamp,
        )
        narrative_result = merge_narrative_results(
            new_narrative_result,
            recent_narrative_result,
        )
        narrative_result["narrative_inspections_skipped"] = len(rows) - len(new_activity_ids)
        logger.info("Recent narrative refresh candidates: %s", len(recent_ids))
        logger.info("Recent narrative refresh attempted: %s", recent_narrative_result["detail_requests_attempted"])
        logger.info("Recent narrative refresh succeeded: %s", recent_narrative_result["narrative_inspections_succeeded"])
        logger.info("Recent narrative refresh failed: %s", recent_narrative_result["narrative_inspections_failed"])

    logger.info("Activities pulled: %s", len(rows))
    logger.info("New activities discovered: %s", len(new_activity_ids))
    logger.info("Detail requests attempted: %s", narrative_result["detail_requests_attempted"])
    logger.info("Narrative inspections succeeded: %s", narrative_result["narrative_inspections_succeeded"])
    logger.info("Narrative inspections failed: %s", narrative_result["narrative_inspections_failed"])
    logger.info("Narrative inspections skipped: %s", narrative_result["narrative_inspections_skipped"])
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