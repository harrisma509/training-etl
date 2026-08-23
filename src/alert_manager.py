#!/usr/bin/env python3
"""Local incident state, deduplication, reminders, and recovery alerts.

This module deliberately stores state outside PostgreSQL so monitoring can
continue when PostgreSQL is unavailable.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from send_alert import send_alert


DEFAULT_STATE_FILE = Path("/opt/training/state/alert_state.json")
DEFAULT_ALERT_ENV_FILE = "/etc/training/alert.env"
DEFAULT_COOLDOWN_HOURS = 6
VALID_SEVERITIES = {"warning", "error", "critical"}
RECOVERY_EMAIL_SEVERITIES = {"critical"}

logger = logging.getLogger(__name__)


@dataclass
class Incident:
    active: bool
    severity: str
    first_seen_utc: str
    last_seen_utc: str
    last_alert_utc: str | None = None
    last_recovery_utc: str | None = None
    alert_count: int = 0
    summary: str = ""


class AlertManager:
    """Manage incident lifecycle and email deduplication using a local JSON file."""

    def __init__(
        self,
        state_file: str | Path = DEFAULT_STATE_FILE,
        alert_env_file: str = DEFAULT_ALERT_ENV_FILE,
        cooldown_hours: int = DEFAULT_COOLDOWN_HOURS,
    ) -> None:
        self.state_file = Path(state_file)
        self.lock_file = self.state_file.with_suffix(self.state_file.suffix + ".lock")
        self.alert_env_file = alert_env_file
        self.cooldown = timedelta(hours=cooldown_hours)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.isoformat(timespec="seconds")

    @staticmethod
    def _parse(value: str | None) -> datetime | None:
        if not value:
            return None
        return datetime.fromisoformat(value)

    @staticmethod
    def _sanitize(value: str, maximum_length: int = 500) -> str:
        cleaned = " ".join(value.split())
        return cleaned[:maximum_length]

    def _load_state(self) -> dict[str, Any]:
        if not self.state_file.exists():
            return {"version": 1, "incidents": {}}

        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Unable to read alert state: {type(error).__name__}") from error

        if not isinstance(data, dict) or not isinstance(data.get("incidents"), dict):
            raise RuntimeError("Alert state has an invalid structure")

        data.setdefault("version", 1)
        return data

    def _save_state(self, state: dict[str, Any]) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(state, indent=2, sort_keys=True) + "\n"

        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.state_file.name}.",
            suffix=".tmp",
            dir=self.state_file.parent,
            text=True,
        )
        temporary_path = Path(temporary_name)

        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self.state_file)
        finally:
            temporary_path.unlink(missing_ok=True)

    def _with_lock(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        lock_handle = self.lock_file.open("a+", encoding="utf-8")
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        return lock_handle

    def _deliver(self, subject: str, body: str) -> bool:
        try:
            send_alert(subject=subject, body=body, env_file=self.alert_env_file)
        except Exception as error:
            logger.error("Alert delivery failed: %s", type(error).__name__)
            return False
        return True

    def report_failure(self, key: str, severity: str, summary: str) -> str:
        """Open/remind an incident. Returns opened, reminded, suppressed, or delivery_failed."""
        if severity not in VALID_SEVERITIES:
            raise ValueError(f"Invalid severity: {severity}")

        key = self._sanitize(key, 100)
        summary = self._sanitize(summary)
        now = self._now()

        with self._with_lock():
            state = self._load_state()
            incidents = state["incidents"]
            existing = incidents.get(key)

            if existing and existing.get("active"):
                incident = Incident(**existing)
                incident.last_seen_utc = self._iso(now)
                incident.summary = summary
                last_alert = self._parse(incident.last_alert_utc)

                if last_alert and now - last_alert < self.cooldown:
                    incidents[key] = asdict(incident)
                    self._save_state(state)
                    logger.warning("Incident still active; duplicate suppressed: %s", key)
                    return "suppressed"

                action = "reminded"
                subject = f"{severity.upper()}: HarrisServer incident remains active"
            else:
                incident = Incident(
                    active=True,
                    severity=severity,
                    first_seen_utc=self._iso(now),
                    last_seen_utc=self._iso(now),
                    summary=summary,
                )
                action = "opened"
                subject = f"{severity.upper()}: HarrisServer incident"

            body = (
                f"Incident: {key}\n"
                f"Severity: {severity}\n"
                f"First seen UTC: {incident.first_seen_utc}\n"
                f"Last seen UTC: {incident.last_seen_utc}\n"
                f"Summary: {summary}\n\n"
                "Operator review is required."
            )

            delivered = self._deliver(subject, body)
            if delivered:
                incident.last_alert_utc = self._iso(now)
                incident.alert_count += 1

            incidents[key] = asdict(incident)
            self._save_state(state)

            if not delivered:
                return "delivery_failed"

            logger.error("Incident %s: %s", action, key)
            return action

    def report_recovery(self, key: str, summary: str = "Service recovered") -> str:
        """Resolve an incident. Returns recovered, inactive, or delivery_failed."""
        key = self._sanitize(key, 100)
        summary = self._sanitize(summary)
        now = self._now()

        with self._with_lock():
            state = self._load_state()
            incidents = state["incidents"]
            existing = incidents.get(key)

            if not existing or not existing.get("active"):
                return "inactive"

            incident = Incident(**existing)
            incident.active = False
            incident.last_seen_utc = self._iso(now)
            incident.last_recovery_utc = self._iso(now)
            incident.summary = summary

            delivered = True
            if incident.severity in RECOVERY_EMAIL_SEVERITIES:
                subject = "RECOVERED: HarrisServer incident"
                body = (
                    f"Incident: {key}\n"
                    f"Severity: {incident.severity}\n"
                    f"First seen UTC: {incident.first_seen_utc}\n"
                    f"Recovered UTC: {incident.last_recovery_utc}\n"
                    f"Summary: {summary}"
                )
                delivered = self._deliver(subject, body)

            incidents[key] = asdict(incident)
            self._save_state(state)

            if not delivered:
                return "delivery_failed"

            logger.info("Incident recovered: %s", key)
            return "recovered"

    def list_active(self) -> dict[str, dict[str, Any]]:
        with self._with_lock():
            state = self._load_state()
            return {
                key: value
                for key, value in state["incidents"].items()
                if value.get("active")
            }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage HarrisServer alert incidents")
    parser.add_argument(
        "--state-file",
        default=os.environ.get("ALERT_STATE_FILE", str(DEFAULT_STATE_FILE)),
    )
    parser.add_argument(
        "--env-file",
        default=os.environ.get("ALERT_ENV_FILE", DEFAULT_ALERT_ENV_FILE),
    )
    parser.add_argument(
        "--cooldown-hours",
        type=int,
        default=DEFAULT_COOLDOWN_HOURS,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    fail_parser = subparsers.add_parser("fail", help="Open or refresh an incident")
    fail_parser.add_argument("--key", required=True)
    fail_parser.add_argument("--severity", choices=sorted(VALID_SEVERITIES), required=True)
    fail_parser.add_argument("--summary", required=True)

    recover_parser = subparsers.add_parser("recover", help="Resolve an incident")
    recover_parser.add_argument("--key", required=True)
    recover_parser.add_argument("--summary", default="Service recovered")

    subparsers.add_parser("list", help="List active incidents")
    return parser


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    arguments = build_parser().parse_args()
    manager = AlertManager(
        state_file=arguments.state_file,
        alert_env_file=arguments.env_file,
        cooldown_hours=arguments.cooldown_hours,
    )

    try:
        if arguments.command == "fail":
            result = manager.report_failure(
                key=arguments.key,
                severity=arguments.severity,
                summary=arguments.summary,
            )
        elif arguments.command == "recover":
            result = manager.report_recovery(
                key=arguments.key,
                summary=arguments.summary,
            )
        else:
            active = manager.list_active()
            print(json.dumps(active, indent=2, sort_keys=True))
            return 0
    except (OSError, RuntimeError, ValueError) as error:
        logger.error("Alert manager failed: %s", error)
        return 1

    print(result)
    return 1 if result == "delivery_failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
