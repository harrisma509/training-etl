#!/usr/bin/env python3
"""Send one concise weekly HarrisServer health summary.

Run as root from cron. This script gathers current health without opening or
closing incidents. It sends one weekly email through the existing Gmail sender.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alert_manager import AlertManager
from check_system_health import collect_checks
from send_alert import send_alert


DEFAULT_ALERT_ENV_FILE = "/etc/training/alert.env"
DEFAULT_STATE_FILE = "/opt/training/state/alert_state.json"
DEFAULT_BACKUP_DIR = "/mnt/harrisnas/backups"
DEFAULT_RESTORE_LOG = "/opt/training/logs/pg_restore_test.log"
DEFAULT_BACKUP_LOG = "/opt/training/logs/pg_backup.log"
DEFAULT_SYNC_MAX_AGE_HOURS = 3.0
DEFAULT_BACKUP_MAX_AGE_HOURS = 26.0
DEFAULT_DISK_WARNING_PERCENT = 85.0
DEFAULT_DISK_CRITICAL_PERCENT = 95.0

logger = logging.getLogger("harrisserver.weekly")


@dataclass
class SummarySection:
    title: str
    lines: list[str]


@dataclass
class HealthArguments:
    backup_dir: str
    state_file: str
    env_file: str
    backup_max_age_hours: float
    sync_max_age_hours: float
    disk_warning_percent: float
    disk_critical_percent: float


def run_command(command: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def require_command(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"Required command unavailable: {name}")
    return path


def psql_scalar(sql: str) -> str:
    psql = require_command("psql")

    if os.geteuid() == 0:
        runuser = require_command("runuser")
        command = [
            runuser,
            "-u",
            "postgres",
            "--",
            psql,
            "-Atq",
            "-d",
            "training",
            "-c",
            sql,
        ]
    else:
        command = [psql, "-Atq", "-d", "training", "-c", sql]

    result = run_command(command, timeout=20)
    if result.returncode != 0:
        raise RuntimeError("PostgreSQL summary query failed")
    return result.stdout.strip()


def format_local_timestamp(value: str | None) -> str:
    if not value:
        return "No data"
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone().strftime("%b %d, %Y %I:%M %p %Z")


def newest_backup(backup_dir: Path) -> Path | None:
    candidates = [
        path
        for path in backup_dir.glob("pg_training_*.sql.gz")
        if path.is_file()
    ]
    return max(candidates, key=lambda path: path.stat().st_mtime, default=None)


def tail_contains(path: Path, text: str, max_bytes: int = 100_000) -> bool:
    if not path.is_file():
        return False
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(max(0, size - max_bytes))
        content = handle.read().decode("utf-8", errors="replace")
    return text in content


def collect_postgresql_section() -> SummarySection:
    try:
        value = psql_scalar(
            """
            SELECT current_setting('server_version') || '|' ||
                   pg_size_pretty(pg_database_size(current_database())) || '|' ||
                   (SELECT COUNT(*) FROM strava_activities) || '|' ||
                   (SELECT COUNT(*) FROM daily_training) || '|' ||
                   (SELECT COUNT(*) FROM weekly_training) || '|' ||
                   (SELECT COUNT(*) FROM sync_run_log WHERE status = 'ok' AND run_at_utc >= CURRENT_TIMESTAMP - INTERVAL '7 days') || '|' ||
                   (SELECT COUNT(*) FROM sync_run_log WHERE status IS DISTINCT FROM 'ok' AND run_at_utc >= CURRENT_TIMESTAMP - INTERVAL '7 days');
            """
        )
        version, size, activities, daily, weekly, successful_syncs, failed_syncs = value.split("|")
        return SummarySection(
            "PostgreSQL and training data",
            [
                f"Status: online, PostgreSQL {version}",
                f"Database size: {size}",
                f"Activities: {activities}",
                f"Daily rows: {daily}",
                f"Weekly rows: {weekly}",
                f"Successful sync runs, last 7 days: {successful_syncs}",
                f"Non-OK sync runs, last 7 days: {failed_syncs}",
            ],
        )
    except Exception as error:
        return SummarySection(
            "PostgreSQL and training data",
            [f"Unable to collect database summary: {type(error).__name__}"],
        )


def collect_sync_section() -> SummarySection:
    try:
        value = psql_scalar(
            """
            SELECT COALESCE(MAX(run_at_utc)::text, '') || '|' ||
                   COALESCE(MAX(warning_count) FILTER (WHERE run_at_utc = (SELECT MAX(run_at_utc) FROM sync_run_log)), 0)::text || '|' ||
                   (SELECT COUNT(*) FROM sync_request WHERE status IN ('pending', 'running') AND requested_at_utc < CURRENT_TIMESTAMP - INTERVAL '30 minutes')::text
            FROM sync_run_log
            WHERE status = 'ok';
            """
        )
        latest, warning_count, stuck_count = value.split("|")
        return SummarySection(
            "Synchronization",
            [
                f"Last successful sync: {format_local_timestamp(latest)}",
                f"Warnings on latest successful sync: {warning_count}",
                f"Sync requests stuck over 30 minutes: {stuck_count}",
            ],
        )
    except Exception as error:
        return SummarySection(
            "Synchronization",
            [f"Unable to collect synchronization summary: {type(error).__name__}"],
        )


def collect_health_freshness_section() -> SummarySection:
    queries = {
        "Steps": "SELECT MAX(measured_at)::text FROM health_steps;",
        "Weight": "SELECT MAX(measured_at)::text FROM health_weight;",
        "Sleep": "SELECT MAX(date)::text FROM health_sleep;",
        "HRV": "SELECT MAX(measured_at)::text FROM health_hrv;",
        "Resting heart rate": "SELECT MAX(measured_at)::text FROM health_rhr;",
        "VO2 max": "SELECT MAX(measured_at)::text FROM health_vo2_max;",
    }
    lines: list[str] = []

    for label, query in queries.items():
        try:
            lines.append(f"{label} latest: {format_local_timestamp(psql_scalar(query))}")
        except Exception as error:
            lines.append(f"{label} latest: unavailable ({type(error).__name__})")

    return SummarySection("Health-data freshness", lines)


def collect_backup_section(backup_dir: Path, restore_log: Path) -> SummarySection:
    lines: list[str] = []
    try:
        backup = newest_backup(backup_dir)
        retained = len(list(backup_dir.glob("pg_training_*.sql.gz")))
        if backup is None:
            lines.append("Latest backup: none found")
        else:
            modified = datetime.fromtimestamp(backup.stat().st_mtime, tz=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - modified).total_seconds() / 3600.0
            lines.extend(
                [
                    f"Latest backup: {backup.name}",
                    f"Backup age: {age_hours:.1f} hours",
                    f"Backup size: {backup.stat().st_size / 1024:.0f} KB",
                ]
            )
        lines.append(f"Backups retained: {retained}")
        restore_passed = tail_contains(restore_log, "SUCCESS: Backup restored and validated.")
        lines.append(
            "Latest recorded restore validation: PASSED"
            if restore_passed
            else "Latest recorded restore validation: no passing result found in persistent log"
        )
    except Exception as error:
        lines.append(f"Unable to collect backup summary: {type(error).__name__}")

    return SummarySection("Backups and recovery", lines)


def collect_platform_section(health_results: list[Any]) -> SummarySection:
    return SummarySection(
        "Platform health",
        [
            f"{'✅ PASS' if result.healthy else '❌ FAIL'}: {result.summary}"
            for result in health_results
        ],
    )


def collect_incident_section(manager: AlertManager) -> SummarySection:
    try:
        active = manager.list_active()
        if not active:
            return SummarySection("Active incidents", ["None"])
        lines = [
            f"{key}: {value.get('severity', 'unknown')} - {value.get('summary', '')}"
            for key, value in sorted(active.items())
        ]
        return SummarySection("Active incidents", lines)
    except Exception as error:
        return SummarySection(
            "Active incidents",
            [f"Unable to read incident state: {type(error).__name__}"],
        )


def render_report(hostname: str, overall: str, sections: list[SummarySection]) -> str:
    now = datetime.now().astimezone()
    lines = [
        "HarrisServer Weekly Health",
        "",
        f"Host: {hostname}",
        f"Generated: {now.strftime('%b %d, %Y %I:%M %p %Z')}",
        f"Overall: {overall}",
    ]

    for section in sections:
        lines.extend(["", section.title])
        lines.extend(f"- {line}" for line in section.lines)

    lines.extend(["", "This is the scheduled weekly operational summary."])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send HarrisServer weekly health summary")
    parser.add_argument("--env-file", default=DEFAULT_ALERT_ENV_FILE)
    parser.add_argument("--state-file", default=DEFAULT_STATE_FILE)
    parser.add_argument("--backup-dir", default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--restore-log", default=DEFAULT_RESTORE_LOG)
    parser.add_argument("--backup-log", default=DEFAULT_BACKUP_LOG)
    parser.add_argument("--backup-max-age-hours", type=float, default=DEFAULT_BACKUP_MAX_AGE_HOURS)
    parser.add_argument("--sync-max-age-hours", type=float, default=DEFAULT_SYNC_MAX_AGE_HOURS)
    parser.add_argument("--disk-warning-percent", type=float, default=DEFAULT_DISK_WARNING_PERCENT)
    parser.add_argument("--disk-critical-percent", type=float, default=DEFAULT_DISK_CRITICAL_PERCENT)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the report without sending email",
    )
    return parser


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    arguments = build_parser().parse_args()

    if os.geteuid() != 0:
        logger.error("Run weekly_health_report.py as root")
        return 2

    manager = AlertManager(
        state_file=arguments.state_file,
        alert_env_file=arguments.env_file,
    )
    health_arguments = HealthArguments(
        backup_dir=arguments.backup_dir,
        state_file=arguments.state_file,
        env_file=arguments.env_file,
        backup_max_age_hours=arguments.backup_max_age_hours,
        sync_max_age_hours=arguments.sync_max_age_hours,
        disk_warning_percent=arguments.disk_warning_percent,
        disk_critical_percent=arguments.disk_critical_percent,
    )

    try:
        health_results = collect_checks(health_arguments)
        active_incidents = manager.list_active()
        failed_checks = [result for result in health_results if not result.healthy]
        overall = "HEALTHY" if not failed_checks and not active_incidents else "ATTENTION NEEDED"
        hostname = subprocess.run(
            ["hostname"],
            text=True,
            capture_output=True,
            check=False,
        ).stdout.strip() or "harrisserver"

        sections = [
            collect_platform_section(health_results),
            collect_postgresql_section(),
            collect_sync_section(),
            collect_health_freshness_section(),
            collect_backup_section(Path(arguments.backup_dir), Path(arguments.restore_log)),
            collect_incident_section(manager),
        ]
        report = render_report(hostname, overall, sections)
        subject = (
            "Harris Server Weekly Health: Healthy"
            if overall == "HEALTHY"
            else f"Harris Server Weekly Health: Attention Needed ({len(failed_checks)} failed checks, {len(active_incidents)} active incidents)"
        )

        if arguments.dry_run:
            print(report)
            return 0

        send_alert(subject=subject, body=report, env_file=arguments.env_file)
        logger.info("Weekly health summary sent: %s", overall)
        return 0
    except Exception as error:
        logger.exception("Weekly health summary failed: %s", type(error).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())