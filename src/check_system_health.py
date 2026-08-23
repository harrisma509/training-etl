#!/usr/bin/env python3
"""Silent HarrisServer health checks with deduplicated failure alerts.

Run this script as root from cron. Healthy checks do not send email.
Failures and recoveries are delegated to alert_manager.py.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from alert_manager import AlertManager


DEFAULT_BACKUP_DIR = Path("/mnt/harrisnas/backups")
DEFAULT_STATE_FILE = Path("/opt/training/state/alert_state.json")
DEFAULT_ALERT_ENV_FILE = "/etc/training/alert.env"
DEFAULT_BACKUP_MAX_AGE_HOURS = 26.0
DEFAULT_SYNC_MAX_AGE_HOURS = 3.0
DEFAULT_DISK_WARNING_PERCENT = 85.0
DEFAULT_DISK_CRITICAL_PERCENT = 95.0

logger = logging.getLogger("harrisserver.health")


@dataclass(frozen=True)
class CheckResult:
    key: str
    healthy: bool
    severity: str
    summary: str


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
        raise RuntimeError(f"Required command is unavailable: {name}")
    return path


def check_postgresql() -> CheckResult:
    try:
        pg_isready = require_command("pg_isready")
        result = run_command(
            [pg_isready, "-h", "127.0.0.1", "-p", "5432", "-d", "training"],
            timeout=10,
        )
        healthy = result.returncode == 0
        summary = (
            "PostgreSQL is accepting connections"
            if healthy
            else "PostgreSQL is not accepting connections on 127.0.0.1:5432"
        )
        return CheckResult("postgres_unavailable", healthy, "critical", summary)
    except Exception as error:
        return CheckResult(
            "postgres_unavailable",
            False,
            "critical",
            f"PostgreSQL health check failed: {type(error).__name__}",
        )


def check_container(container_name: str) -> CheckResult:
    key = f"container_{container_name.replace('-', '_')}_stopped"
    try:
        docker = require_command("docker")
        result = run_command(
            [docker, "inspect", "--format", "{{.State.Running}}", container_name],
            timeout=15,
        )
        healthy = result.returncode == 0 and result.stdout.strip().lower() == "true"
        summary = (
            f"Container {container_name} is running"
            if healthy
            else f"Container {container_name} is not running or cannot be inspected"
        )
        return CheckResult(key, healthy, "critical", summary)
    except Exception as error:
        return CheckResult(
            key,
            False,
            "critical",
            f"Container check failed for {container_name}: {type(error).__name__}",
        )


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
        raise RuntimeError("PostgreSQL query failed")
    return result.stdout.strip()


def check_sync_freshness(max_age_hours: float) -> CheckResult:
    sql = """
        SELECT EXTRACT(
            EPOCH FROM (
                CURRENT_TIMESTAMP - MAX(run_at_utc)
            )
        ) / 3600.0
        FROM sync_run_log
        WHERE status = 'ok';
    """
    try:
        raw_value = psql_scalar(sql)
        if not raw_value:
            return CheckResult(
                "sync_stale",
                False,
                "error",
                "No completed synchronization request was found",
            )
        age_hours = float(raw_value)
        healthy = age_hours <= max_age_hours
        summary = (
            f"Last completed sync is {age_hours:.1f} hours old"
            if healthy
            else f"Last completed sync is stale at {age_hours:.1f} hours old"
        )
        return CheckResult("sync_stale", healthy, "error", summary)
    except Exception as error:
        return CheckResult(
            "sync_stale",
            False,
            "error",
            f"Sync freshness check failed: {type(error).__name__}",
        )


def check_stuck_sync() -> CheckResult:
    sql = """
        SELECT COUNT(*)
        FROM sync_request
        WHERE status IN ('pending', 'running')
          AND requested_at_utc < CURRENT_TIMESTAMP - INTERVAL '30 minutes';
    """
    try:
        count = int(psql_scalar(sql))
        healthy = count == 0
        summary = (
            "No stale pending or running sync requests"
            if healthy
            else f"Found {count} sync request(s) stuck for more than 30 minutes"
        )
        return CheckResult("sync_request_stuck", healthy, "error", summary)
    except Exception as error:
        return CheckResult(
            "sync_request_stuck",
            False,
            "error",
            f"Stuck-sync check failed: {type(error).__name__}",
        )


def check_backup_mount(backup_dir: Path) -> CheckResult:
    try:
        findmnt = require_command("findmnt")
        result = run_command(
            [findmnt, "-rn", "-T", str(backup_dir), "-o", "FSTYPE,SOURCE"],
            timeout=10,
        )
        fields = result.stdout.strip().split(maxsplit=1)
        filesystem = fields[0] if fields else ""
        source = fields[1] if len(fields) > 1 else ""
        healthy = result.returncode == 0 and filesystem in {"nfs", "nfs4"}
        summary = (
            f"HarrisNAS backup mount is available ({filesystem}, {source})"
            if healthy
            else f"HarrisNAS backup directory is not backed by NFS: {backup_dir}"
        )
        return CheckResult("harrisnas_mount_missing", healthy, "critical", summary)
    except Exception as error:
        return CheckResult(
            "harrisnas_mount_missing",
            False,
            "critical",
            f"HarrisNAS mount check failed: {type(error).__name__}",
        )


def newest_backup(backup_dir: Path) -> Path | None:
    backups = [path for path in backup_dir.glob("pg_training_*.sql.gz") if path.is_file()]
    return max(backups, key=lambda path: path.stat().st_mtime, default=None)


def check_backup_freshness(backup_dir: Path, max_age_hours: float) -> CheckResult:
    try:
        backup = newest_backup(backup_dir)
        if backup is None:
            return CheckResult(
                "backup_stale",
                False,
                "critical",
                f"No PostgreSQL backup files were found in {backup_dir}",
            )
        age_hours = (datetime.now(timezone.utc).timestamp() - backup.stat().st_mtime) / 3600.0
        healthy = age_hours <= max_age_hours and backup.stat().st_size > 0
        summary = (
            f"Latest backup {backup.name} is {age_hours:.1f} hours old"
            if healthy
            else f"Latest backup is stale or empty: {backup.name}, {age_hours:.1f} hours old"
        )
        return CheckResult("backup_stale", healthy, "critical", summary)
    except Exception as error:
        return CheckResult(
            "backup_stale",
            False,
            "critical",
            f"Backup freshness check failed: {type(error).__name__}",
        )


def check_root_disk(warning_percent: float, critical_percent: float) -> CheckResult:
    try:
        usage = shutil.disk_usage("/")
        used_percent = usage.used / usage.total * 100.0
        healthy = used_percent < warning_percent
        severity = "critical" if used_percent >= critical_percent else "warning"
        summary = f"Root filesystem usage is {used_percent:.1f}%"
        return CheckResult("root_disk_high", healthy, severity, summary)
    except Exception as error:
        return CheckResult(
            "root_disk_high",
            False,
            "warning",
            f"Root disk check failed: {type(error).__name__}",
        )


def check_systemd_service(service: str, key: str, severity: str) -> CheckResult:
    try:
        systemctl = require_command("systemctl")
        result = run_command([systemctl, "is-active", "--quiet", service], timeout=10)
        healthy = result.returncode == 0
        summary = (
            f"Systemd service {service} is active"
            if healthy
            else f"Systemd service {service} is not active"
        )
        return CheckResult(key, healthy, severity, summary)
    except Exception as error:
        return CheckResult(
            key,
            False,
            severity,
            f"Service check failed for {service}: {type(error).__name__}",
        )


def collect_checks(arguments: argparse.Namespace) -> list[CheckResult]:
    backup_dir = Path(arguments.backup_dir)
    results = [
        check_postgresql(),
        check_container("training-web"),
        check_container("training-runner"),
        check_backup_mount(backup_dir),
        check_backup_freshness(backup_dir, arguments.backup_max_age_hours),
        check_root_disk(arguments.disk_warning_percent, arguments.disk_critical_percent),
        check_systemd_service("nut-monitor.service", "nut_monitor_inactive", "error"),
    ]

    if results[0].healthy:
        results.extend(
            [
                check_sync_freshness(arguments.sync_max_age_hours),
                check_stuck_sync(),
            ]
        )
    else:
        logger.warning("Skipping database-dependent sync checks because PostgreSQL is unavailable")

    return results


def apply_results(manager: AlertManager, results: list[CheckResult]) -> int:
    failures = 0

    for result in results:
        if result.healthy:
            action = manager.report_recovery(result.key, result.summary)
            logger.info("PASS %-30s %s (%s)", result.key, result.summary, action)
        else:
            failures += 1
            action = manager.report_failure(result.key, result.severity, result.summary)
            logger.error("FAIL %-30s %s (%s)", result.key, result.summary, action)

    return failures


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check HarrisServer operational health")
    parser.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))
    parser.add_argument("--state-file", default=str(DEFAULT_STATE_FILE))
    parser.add_argument("--env-file", default=DEFAULT_ALERT_ENV_FILE)
    parser.add_argument("--backup-max-age-hours", type=float, default=DEFAULT_BACKUP_MAX_AGE_HOURS)
    parser.add_argument("--sync-max-age-hours", type=float, default=DEFAULT_SYNC_MAX_AGE_HOURS)
    parser.add_argument("--disk-warning-percent", type=float, default=DEFAULT_DISK_WARNING_PERCENT)
    parser.add_argument("--disk-critical-percent", type=float, default=DEFAULT_DISK_CRITICAL_PERCENT)
    return parser


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    arguments = build_parser().parse_args()

    if os.geteuid() != 0:
        logger.error("Run check_system_health.py as root so Docker and PostgreSQL checks are noninteractive")
        return 2

    manager = AlertManager(
        state_file=arguments.state_file,
        alert_env_file=arguments.env_file,
    )

    try:
        results = collect_checks(arguments)
        failures = apply_results(manager, results)
    except Exception as error:
        logger.exception("Health-check framework failed: %s", type(error).__name__)
        return 2

    if failures:
        logger.error("Health check completed with %d failure(s)", failures)
        return 1

    logger.info("Health check completed successfully: %d checks passed", len(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())