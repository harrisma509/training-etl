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
import re
import shlex
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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
DEFAULT_TRAINING_WEB_BASE_URL = "http://127.0.0.1:8088"
DEFAULT_WEATHER_LOCATION_ID = 1
SERVICE_HTTP_TIMEOUT_SECONDS = 10
GEOAPIFY_PROBE_TIMEOUT_SECONDS = 25
WEATHER_RETRY_DELAYS_SECONDS = (2, 5)
TEMPORARY_WEATHER_ERROR = "Weather forecast is temporarily unavailable."
GEOAPIFY_PROBE_STATUSES = {
    "healthy",
    "missing_key",
    "unauthorized",
    "rate_limited",
    "timeout",
    "provider_unavailable",
    "invalid_json",
    "empty_results",
    "probe_error",
}
WEATHER_RAW_PROVIDER_FIELDS = {
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_probability_max",
    "precipitation_sum",
    "snowfall_sum",
    "wind_speed_10m_max",
    "wind_direction_10m_dominant",
    "wind_gusts_10m_max",
    "sunrise",
    "sunset",
    "temperature_2m",
    "apparent_temperature",
    "precipitation_probability",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
}
APT_UPGRADE_TIMEOUT_SECONDS = 120
FWUPDMGR_TIMEOUT_SECONDS = 120
FWUPD_URGENCY_RANK = {
    "unknown": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

logger = logging.getLogger("harrisserver.weekly")


@dataclass
class SummarySection:
    title: str
    lines: list[str]


@dataclass
class OSMaintenanceResult:
    section: SummarySection
    requires_attention: bool
    status_available: bool


@dataclass(frozen=True)
class FirmwareUpdateSummary:
    target_count: int
    highest_urgency: str
    reboot_required: bool
    shutdown_required: bool


@dataclass
class HealthArguments:
    backup_dir: str
    state_file: str
    env_file: str
    backup_max_age_hours: float
    sync_max_age_hours: float
    disk_warning_percent: float
    disk_critical_percent: float


@dataclass(frozen=True)
class JsonGetResult:
    status_code: int | None
    payload: Any = None
    failure_category: str | None = None


@dataclass(frozen=True)
class ServiceHealthResult:
    severity: str
    dashboard_line: str
    section: SummarySection

    @property
    def requires_attention(self) -> bool:
        return self.severity != "PASS"


GEOAPIFY_PROBE_SCRIPT = r'''
import json
import os
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _http_failure(status):
    if status in (401, 403):
        return "unauthorized", False
    if status == 429:
        return "rate_limited", True
    if 500 <= status <= 599:
        return "provider_unavailable", True
    return "probe_error", False


def _probe():
    key = os.environ.get("GEOAPIFY_API_KEY", "").strip()
    if not key:
        return "missing_key"

    url = "https://api.geoapify.com/v1/geocode/autocomplete?" + urlencode(
        {
            "text": "Denver Union Station",
            "format": "json",
            "limit": 1,
            "apiKey": key,
        }
    )
    for attempt in range(2):
        try:
            request = Request(url, headers={"Accept": "application/json"})
            with urlopen(request, timeout=10) as response:
                status = getattr(response, "status", 200)
                if status != 200:
                    category, retryable = _http_failure(status)
                else:
                    try:
                        payload = json.loads(response.read().decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        return "invalid_json"
                    results = payload.get("results") if isinstance(payload, dict) else None
                    return "healthy" if isinstance(results, list) and results else "empty_results"
        except HTTPError as error:
            category, retryable = _http_failure(error.code)
        except (TimeoutError, socket.timeout):
            category, retryable = "timeout", True
        except URLError as error:
            if isinstance(error.reason, (TimeoutError, socket.timeout)):
                category, retryable = "timeout", True
            else:
                category, retryable = "provider_unavailable", False
        except OSError:
            category, retryable = "provider_unavailable", False

        if retryable and attempt == 0:
            time.sleep(2)
            continue
        return category
    return "probe_error"


try:
    status = _probe()
except Exception:
    status = "probe_error"
print(json.dumps({"status": status}, separators=(",", ":")))
'''


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


def _decode_json_body(body: bytes) -> tuple[bool, Any]:
    try:
        return True, json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False, None


def _is_temporary_weather_error(body: bytes) -> bool:
    valid_json, payload = _decode_json_body(body)
    return (
        valid_json
        and isinstance(payload, dict)
        and payload == {"detail": TEMPORARY_WEATHER_ERROR}
    )


def _http_get_json(
    url: str,
    *,
    timeout: int = SERVICE_HTTP_TIMEOUT_SECONDS,
    detect_temporary_weather_error: bool = False,
) -> JsonGetResult:
    try:
        with urlopen(Request(url), timeout=timeout) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                temporary = (
                    status == 503
                    and detect_temporary_weather_error
                    and _is_temporary_weather_error(response.read())
                )
                category = "temporary_unavailable" if temporary else f"http_{status}"
                return JsonGetResult(status, failure_category=category)
            body = response.read()
    except HTTPError as error:
        temporary = False
        if error.code == 503 and detect_temporary_weather_error:
            try:
                temporary = _is_temporary_weather_error(error.read())
            except OSError:
                temporary = False
        category = (
            "temporary_unavailable"
            if temporary
            else f"http_{error.code}"
        )
        return JsonGetResult(error.code, failure_category=category)
    except (TimeoutError, socket.timeout):
        return JsonGetResult(None, failure_category="timeout")
    except URLError as error:
        if isinstance(error.reason, (TimeoutError, socket.timeout)):
            return JsonGetResult(None, failure_category="timeout")
        return JsonGetResult(None, failure_category="request_error")
    except (OSError, ValueError):
        return JsonGetResult(None, failure_category="request_error")

    valid_json, payload = _decode_json_body(body)
    if not valid_json:
        return JsonGetResult(200, failure_category="invalid_json")
    if detect_temporary_weather_error and _is_temporary_weather_error(body):
        return JsonGetResult(200, failure_category="temporary_unavailable")
    return JsonGetResult(200, payload=payload)


def _contains_forbidden_key(value: Any, forbidden_keys: set[str]) -> bool:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if isinstance(key, str) and key.casefold() in forbidden_keys:
                return True
            if _contains_forbidden_key(nested_value, forbidden_keys):
                return True
    elif isinstance(value, list):
        return any(
            _contains_forbidden_key(item, forbidden_keys)
            for item in value
        )
    return False


def _response_failure_category(response: JsonGetResult) -> str:
    if response.failure_category:
        return response.failure_category
    if response.status_code is None:
        return "request_error"
    return f"http_{response.status_code}"


def _saved_locations_result(
    training_web_base_url: str,
) -> tuple[bool, int | None, str, str | None]:
    response = _http_get_json(
        f"{training_web_base_url.rstrip('/')}/api/saved-locations"
    )
    if response.status_code != 200 or response.failure_category:
        return False, None, "Not verified", _response_failure_category(response)
    if not isinstance(response.payload, dict):
        return False, None, "Not verified", "invalid_response"

    coordinates_present = _contains_forbidden_key(
        response.payload,
        {"latitude", "longitude"},
    )
    coordinate_privacy = "Failed" if coordinates_present else "Passed"
    if coordinates_present:
        return False, None, coordinate_privacy, "coordinate_leak"
    if _contains_forbidden_key(response.payload, {"error", "detail"}):
        return False, None, coordinate_privacy, "application_error_field"
    locations = response.payload.get("locations")
    if not isinstance(locations, list):
        return False, None, coordinate_privacy, "invalid_response"
    return True, len(locations), coordinate_privacy, None


def _run_geoapify_probe() -> str:
    try:
        result = run_command(
            [
                "docker",
                "exec",
                "training-web",
                "python",
                "-c",
                GEOAPIFY_PROBE_SCRIPT,
            ],
            timeout=GEOAPIFY_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "container_unavailable"
    if result.returncode != 0:
        return "container_unavailable"

    if not isinstance(result.stdout, str) or len(result.stdout) > 128:
        return "probe_error"
    try:
        contract = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError):
        return "probe_error"
    status = contract.get("status") if isinstance(contract, dict) else None
    if (
        not isinstance(contract, dict)
        or set(contract) != {"status"}
        or not isinstance(status, str)
        or status not in GEOAPIFY_PROBE_STATUSES
    ):
        return "probe_error"
    return status


def collect_location_health(
    training_web_base_url: str = DEFAULT_TRAINING_WEB_BASE_URL,
) -> ServiceHealthResult:
    saved_available, saved_count, coordinate_privacy, saved_failure = (
        _saved_locations_result(training_web_base_url)
    )
    geoapify_status = _run_geoapify_probe()

    if not saved_available or geoapify_status in {
        "missing_key",
        "container_unavailable",
    }:
        severity = "FAIL"
        dashboard_line = "❌ FAIL: Location service health check failed"
    elif geoapify_status != "healthy":
        severity = "WARN"
        dashboard_line = (
            "⚠ WARN: Location setup provider is unavailable; "
            "saved locations remain healthy"
        )
    else:
        severity = "PASS"
        dashboard_line = "✅ PASS: Location services are healthy"

    lines = [
        f"Geoapify API: {'Available' if geoapify_status == 'healthy' else 'Unavailable'}",
        f"Saved-location API: {'Available' if saved_available else 'Unavailable'}",
        f"Saved locations: {saved_count if saved_count is not None else 'Unavailable'}",
    ]
    if coordinate_privacy == "Failed":
        lines.append("❌ FAIL: Location coordinates were exposed")
    elif saved_failure == "application_error_field":
        lines.append("❌ FAIL: Saved-location privacy contract failed")
    if geoapify_status != "healthy":
        lines.append(f"Geoapify failure category: {geoapify_status}")
    if saved_failure:
        lines.append(f"Saved-location failure category: {saved_failure}")
    return ServiceHealthResult(
        severity,
        dashboard_line,
        SummarySection("Location and Geoapify health", lines),
    )


def _weather_failure_category(response: JsonGetResult) -> str:
    if response.status_code == 429:
        return "rate_limited"
    if response.status_code is not None and 500 <= response.status_code <= 599:
        if response.failure_category == "temporary_unavailable":
            return "temporary_unavailable"
        return f"http_{response.status_code}"
    if response.failure_category:
        return response.failure_category
    if response.status_code is not None and response.status_code != 200:
        return f"http_{response.status_code}"
    return "request_error"


def _weather_retryable(response: JsonGetResult) -> bool:
    return (
        response.failure_category in {"timeout", "temporary_unavailable"}
        or response.status_code == 429
        or (
            response.status_code is not None
            and 500 <= response.status_code <= 599
        )
    )


def _validate_weather_payload(
    payload: Any,
    location_id: int,
) -> tuple[str | None, int | None, str, str | None]:
    if not isinstance(payload, dict):
        return None, None, "Not verified", "invalid_response"

    forbidden_error = _contains_forbidden_key(payload, {"error", "detail"})
    forbidden_coordinates = _contains_forbidden_key(
        payload,
        {"latitude", "longitude"},
    )
    forbidden_provider_fields = _contains_forbidden_key(
        payload,
        WEATHER_RAW_PROVIDER_FIELDS,
    )
    if forbidden_error:
        return None, None, "Failed", "application_error_field"
    if forbidden_coordinates:
        return None, None, "Failed", "coordinate_leak"
    if forbidden_provider_fields:
        return None, None, "Failed", "raw_provider_field"

    if type(payload.get("location_id")) is not int or payload["location_id"] != location_id:
        return None, None, "Passed", "location_id_mismatch"
    freshness = payload.get("freshness")
    if not isinstance(freshness, str) or freshness not in {"fresh", "stale"}:
        return None, None, "Passed", "invalid_response"
    for field in ("available_start_date", "available_end_date"):
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            return None, None, "Passed", "invalid_response"
    daily = payload.get("daily")
    if not isinstance(daily, list):
        return None, None, "Passed", "invalid_response"
    if not daily:
        return freshness, 0, "Passed", "empty_daily"
    return freshness, len(daily), "Passed", None


def collect_weather_health(
    training_web_base_url: str = DEFAULT_TRAINING_WEB_BASE_URL,
    weather_location_id: int = DEFAULT_WEATHER_LOCATION_ID,
) -> ServiceHealthResult:
    url = (
        f"{training_web_base_url.rstrip('/')}/api/weather/locations/"
        f"{weather_location_id}/forecast"
    )
    response: JsonGetResult | None = None
    for delay in (*WEATHER_RETRY_DELAYS_SECONDS, None):
        response = _http_get_json(
            url,
            detect_temporary_weather_error=True,
        )
        if not _weather_retryable(response):
            break
        if delay is None:
            break
        time.sleep(delay)

    assert response is not None
    if response.failure_category or response.status_code != 200:
        failure_category = _weather_failure_category(response)
        freshness = None
        daily_count = None
        privacy = "Not verified"
    else:
        freshness, daily_count, privacy, failure_category = _validate_weather_payload(
            response.payload,
            weather_location_id,
        )

    if failure_category:
        severity = "FAIL"
        dashboard_line = "❌ FAIL: Weather API health check failed"
    elif freshness == "stale":
        severity = "WARN"
        dashboard_line = "⚠ WARN: Weather API is serving stale cached data"
    else:
        severity = "PASS"
        dashboard_line = "✅ PASS: Weather API is healthy"

    lines = [
        f"Forecast API: {'Available' if response.status_code == 200 else 'Unavailable'}",
        f"Forecast freshness: {freshness.title() if freshness else 'Unavailable'}",
        f"Forecast days available: {daily_count if daily_count is not None else 'Unavailable'}",
    ]
    if privacy == "Failed":
        if failure_category == "coordinate_leak":
            lines.append("❌ FAIL: Weather location coordinates were exposed")
        elif failure_category == "raw_provider_field":
            lines.append("❌ FAIL: Raw weather-provider data was exposed")
        else:
            lines.append("❌ FAIL: Weather response privacy contract failed")
    if failure_category:
        lines.append(f"Failure category: {failure_category}")
    return ServiceHealthResult(
        severity,
        dashboard_line,
        SummarySection("Weather API health", lines),
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


def collect_platform_section(
    health_results: list[Any],
    os_maintenance: OSMaintenanceResult,
    location_health: ServiceHealthResult,
    weather_health: ServiceHealthResult,
) -> SummarySection:
    lines = [
        _platform_check_dashboard_line(result)
        for result in health_results
    ]
    runner_index = next(
        (
            index
            for index, result in enumerate(health_results)
            if result.key == "container_training_runner_stopped"
        ),
        None,
    )
    if runner_index is not None:
        insertion_index = runner_index + 1
    else:
        insertion_index = next(
            (
                index
                for index, result in enumerate(health_results)
                if result.key == "harrisnas_mount_missing"
            ),
            len(lines),
        )
    lines[insertion_index:insertion_index] = [
        _os_maintenance_dashboard_line(os_maintenance),
        location_health.dashboard_line,
        weather_health.dashboard_line,
    ]
    return SummarySection(
        "Platform health",
        lines,
    )


def _platform_check_dashboard_line(result: Any) -> str:
    if result.key == "harrisnas_mount_missing" and result.healthy:
        return "✅ PASS: HarrisNAS backup mount is available"
    if result.key == "nut_monitor_inactive" and result.healthy:
        return "✅ PASS: UPS power monitoring is active"
    if result.key == "sync_request_stuck" and result.healthy:
        return "✅ PASS: No stale sync requests"
    if result.key == "backup_stale" and result.healthy:
        match = re.fullmatch(
            r"Latest backup .+ is (\d+(?:\.\d+)?) hours old",
            result.summary,
        )
        if match is not None:
            return f"✅ PASS: Latest backup is {match.group(1)} hours old"
        return "✅ PASS: Latest backup is available"
    return f"{'✅ PASS' if result.healthy else '❌ FAIL'}: {result.summary}"


def _os_maintenance_dashboard_line(result: OSMaintenanceResult) -> str:
    if not result.status_available:
        return "❌ FAIL: OS maintenance status could not be determined"
    if result.requires_attention:
        return "⚠ ATTENTION: OS maintenance requires attention"
    return "✅ PASS: OS maintenance is current"


def _read_os_release(path: Path) -> str:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return "Unavailable"

    for line in content.splitlines():
        if not line.lstrip().startswith("PRETTY_NAME="):
            continue
        try:
            values = shlex.split(line, comments=True, posix=True)
        except ValueError:
            return "Unavailable"
        if len(values) != 1 or not values[0].startswith("PRETTY_NAME="):
            return "Unavailable"
        value = values[0].split("=", 1)[1]
        return value or "Unavailable"
    return "Unavailable"


def _read_running_kernel() -> str:
    try:
        return os.uname().release or "Unavailable"
    except (AttributeError, OSError):
        return "Unavailable"


def _parse_apt_upgrade_simulation(
    output: str,
) -> tuple[int | None, int | None]:
    summary_pattern = re.compile(
        r"^\s*(\d+) upgraded, (\d+) newly installed, "
        r"(\d+) to remove and (\d+) not upgraded\.\s*$"
    )
    summaries = [
        match
        for line in output.splitlines()
        if (match := summary_pattern.fullmatch(line))
    ]
    if len(summaries) != 1:
        return None, None

    actions: list[bool | None] = []
    action_pattern = re.compile(
        r"^\s*Inst\s+\S+(?:\s+\[[^\]]+\])?\s+\(([^()]*)\)"
        r"(?:\s+\[[^\[\]]*\])?\s*$"
    )
    for line in output.splitlines():
        if not re.match(r"^\s*Inst(?:\s|$)", line):
            continue
        action = action_pattern.fullmatch(line)
        if action is None:
            return None, None

        ubuntu_origins = re.findall(
            r"\bUbuntu:[^\s\]]+",
            action.group(1),
            re.IGNORECASE,
        )
        if len(ubuntu_origins) != 1 or "/" not in ubuntu_origins[0]:
            actions.append(None)
            continue

        archive = ubuntu_origins[0].split("/", 1)[1]
        is_security = any(
            component.lower().endswith("-security")
            for component in archive.split("/")
        )
        actions.append(is_security)

    summary = summaries[0]
    expected_actions = int(summary.group(1)) + int(summary.group(2))
    if len(actions) != expected_actions:
        return None, None

    security_count = (
        sum(action is True for action in actions)
        if all(action is not None for action in actions)
        else None
    )
    return len(actions), security_count


def _read_reboot_required(path: Path) -> tuple[str, bool]:
    try:
        path.stat()
    except FileNotFoundError:
        return "No", False
    except OSError:
        return "Unavailable", True
    return "Yes", True


def _parse_fwupd_get_updates(output: str) -> FirmwareUpdateSummary | None:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("Devices"), list):
        return None

    targets: dict[str, tuple[int, bool, bool]] = {}
    for device in payload["Devices"]:
        if not isinstance(device, dict):
            return None
        device_id = device.get("DeviceId")
        releases = device.get("Releases")
        flags = device.get("Flags", [])
        if (
            not isinstance(device_id, str)
            or not device_id.strip()
            or not isinstance(releases, list)
            or not releases
            or not isinstance(flags, list)
            or not all(isinstance(flag, str) for flag in flags)
        ):
            return None

        urgency_rank = 0
        for release in releases:
            if not isinstance(release, dict):
                return None
            urgency = release.get("Urgency", "unknown")
            if not isinstance(urgency, str):
                return None
            urgency = urgency.casefold()
            if urgency not in FWUPD_URGENCY_RANK:
                return None
            urgency_rank = max(urgency_rank, FWUPD_URGENCY_RANK[urgency])

        target_key = device_id.strip().casefold()
        previous_rank, previous_reboot, previous_shutdown = targets.get(
            target_key,
            (0, False, False),
        )
        targets[target_key] = (
            max(previous_rank, urgency_rank),
            previous_reboot or "needs-reboot" in flags,
            previous_shutdown or "needs-shutdown" in flags,
        )

    highest_rank = max((target[0] for target in targets.values()), default=0)
    highest_urgency = next(
        urgency
        for urgency, rank in FWUPD_URGENCY_RANK.items()
        if rank == highest_rank
    )
    return FirmwareUpdateSummary(
        target_count=len(targets),
        highest_urgency=highest_urgency,
        reboot_required=any(target[1] for target in targets.values()),
        shutdown_required=any(target[2] for target in targets.values()),
    )


def _collect_fwupd_updates() -> FirmwareUpdateSummary | None:
    try:
        fwupdmgr = require_command("fwupdmgr")
        result = run_command(
            [fwupdmgr, "get-updates", "--json"],
            timeout=FWUPDMGR_TIMEOUT_SECONDS,
        )
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        logger.warning("Firmware update status unavailable: %s", type(error).__name__)
        return None

    if result.returncode != 0:
        logger.warning(
            "Firmware update status unavailable: fwupdmgr exited with status %s",
            result.returncode,
        )
        return None

    summary = _parse_fwupd_get_updates(result.stdout)
    if summary is None:
        logger.warning("Firmware update status unavailable: unexpected fwupdmgr JSON")
    return summary


def _format_fwupd_updates(summary: FirmwareUpdateSummary | None) -> str:
    if summary is None:
        return "Firmware updates: Unavailable"
    if summary.target_count == 0:
        return "Firmware updates: 0"

    details = [
        f"highest urgency: {summary.highest_urgency.title()}",
        f"reboot after install: {'Yes' if summary.reboot_required else 'No'}",
    ]
    if summary.shutdown_required:
        details.append("shutdown after install: Yes")
    return f"Firmware updates: {summary.target_count} ({'; '.join(details)})"


def collect_os_maintenance_section(
    os_release_path: Path = Path("/etc/os-release"),
    reboot_required_path: Path = Path("/var/run/reboot-required"),
) -> OSMaintenanceResult:
    os_release = _read_os_release(os_release_path)
    kernel = _read_running_kernel()

    try:
        apt_get = require_command("apt-get")
        result = run_command(
            [apt_get, "-s", "upgrade"],
            timeout=APT_UPGRADE_TIMEOUT_SECONDS,
        )
        if result.returncode == 0:
            upgradeable_count, security_count = _parse_apt_upgrade_simulation(
                result.stdout
            )
        else:
            upgradeable_count, security_count = None, None
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        upgradeable_count, security_count = None, None

    reboot_status, reboot_attention = _read_reboot_required(reboot_required_path)
    firmware_updates = _collect_fwupd_updates()
    requires_attention = (
        upgradeable_count is None
        or security_count is None
        or security_count > 0
        or reboot_attention
        or firmware_updates is None
        or firmware_updates.target_count > 0
    )
    status_available = (
        upgradeable_count is not None
        and security_count is not None
        and reboot_status != "Unavailable"
        and firmware_updates is not None
    )
    section = SummarySection(
        "OS maintenance",
        [
            f"OS release: {os_release}",
            f"Running kernel: {kernel}",
            f"Upgradeable packages: {upgradeable_count if upgradeable_count is not None else 'Unavailable'}",
            f"Security updates: {security_count if security_count is not None else 'Unavailable'}",
            _format_fwupd_updates(firmware_updates),
            f"Reboot required: {reboot_status}",
        ],
    )
    return OSMaintenanceResult(section, requires_attention, status_available)


def build_subject(overall: str) -> str:
    return (
        "Harris Server Weekly Health: Healthy"
        if overall == "HEALTHY"
        else "Harris Server Weekly Health: Attention Needed"
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
    parser.add_argument(
        "--training-web-base-url",
        default=DEFAULT_TRAINING_WEB_BASE_URL,
    )
    parser.add_argument(
        "--weather-location-id",
        type=int,
        default=DEFAULT_WEATHER_LOCATION_ID,
    )
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
        os_maintenance = collect_os_maintenance_section()
        location_health = collect_location_health(arguments.training_web_base_url)
        weather_health = collect_weather_health(
            arguments.training_web_base_url,
            arguments.weather_location_id,
        )
        overall = (
            "HEALTHY"
            if not failed_checks
            and not active_incidents
            and not os_maintenance.requires_attention
            and not location_health.requires_attention
            and not weather_health.requires_attention
            else "ATTENTION NEEDED"
        )
        hostname = subprocess.run(
            ["hostname"],
            text=True,
            capture_output=True,
            check=False,
        ).stdout.strip() or "harrisserver"

        sections = [
            collect_platform_section(
                health_results,
                os_maintenance,
                location_health,
                weather_health,
            ),
            os_maintenance.section,
            collect_postgresql_section(),
            collect_sync_section(),
            location_health.section,
            weather_health.section,
            collect_health_freshness_section(),
            collect_backup_section(Path(arguments.backup_dir), Path(arguments.restore_log)),
            collect_incident_section(manager),
        ]
        report = render_report(hostname, overall, sections)
        subject = build_subject(overall)

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