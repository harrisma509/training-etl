"""ETL runtime settings.

Configuration ownership pattern:
- Strava credentials, training API tokens, and database connection settings remain environment-owned ETL process configuration.
- DAYS_BACK is the default sync window used by the ETL process, but the effective window for a queued sync is captured into sync_request.days_back when a request is created.
- AUTO_SYNC_MINUTES and SYNC_WORKER_POLL_SECONDS are scheduler-level process settings that govern the sync worker loop and should not be treated as user-facing app preferences.
- Browser-facing settings should only expose non-secret operational values whose behavior is intentionally UI-managed and server-validated.
"""

import os
from datetime import date
from zoneinfo import ZoneInfo

from constants import DEFAULT_CHRONIC_C
from constants import (
    APP_TIMEZONE,
    FATIGUE_TIME_CONSTANT_DAYS,
    FITNESS_FATIGUE_MODEL_VERSION,
    FITNESS_FATIGUE_START_DATE,
    FITNESS_TIME_CONSTANT_DAYS,
)

class Config(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

def read_env_file(path):
    values = {}

    if not path or not os.path.exists(path):
        return values

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")

    return values


def get_config():
    env_file = os.environ.get("ENV_FILE", "/config/strava.env")
    file_values = read_env_file(env_file)

    keys = [
    "STRAVA_CLIENT_ID",
    "STRAVA_CLIENT_SECRET",
    "STRAVA_REFRESH_TOKEN",
    "TRAINING_API_TOKEN",
    "DAYS_BACK",
    "SYNC_WORKER_POLL_SECONDS",
    "AUTO_SYNC_MINUTES",
    "LOAD_CHRONIC_C",
    "WRITE_DB",
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    ]

    cfg = {}

    for key in keys:
        cfg[key] = os.environ.get(key) or file_values.get(key)

    missing = [
        key
        for key in ["STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET", "STRAVA_REFRESH_TOKEN"]
        if not cfg.get(key)
    ]

    if missing:
        raise SystemExit(f"Missing required config values: {', '.join(missing)}")

    cfg["DAYS_BACK"] = int(cfg.get("DAYS_BACK") or 7)
    cfg["LOAD_CHRONIC_C"] = float(cfg.get("LOAD_CHRONIC_C") or DEFAULT_CHRONIC_C)
    cfg["WRITE_DB"] = str(cfg.get("WRITE_DB") or "false").lower() == "true"
    cfg["DB_HOST"] = cfg.get("DB_HOST") or "training-postgres"
    cfg["DB_PORT"] = cfg.get("DB_PORT") or "5432"
    cfg["DB_NAME"] = cfg.get("DB_NAME") or "training"
    cfg["DB_USER"] = cfg.get("DB_USER") or "training_app"
    cfg["DB_PASSWORD"] = cfg.get("DB_PASSWORD") or ""
    cfg["SYNC_WORKER_POLL_SECONDS"] = int(cfg.get("SYNC_WORKER_POLL_SECONDS") or 60)
    cfg["AUTO_SYNC_MINUTES"] = int(cfg.get("AUTO_SYNC_MINUTES") or 60)

    return Config(cfg)


def get_db_config():
    env_file = os.environ.get("ENV_FILE", "/config/strava.env")
    file_values = read_env_file(env_file)

    keys = [
        "WRITE_DB",
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
    ]

    cfg = {}

    for key in keys:
        cfg[key] = os.environ.get(key) or file_values.get(key)

    cfg["WRITE_DB"] = str(cfg.get("WRITE_DB") or "false").lower() == "true"
    cfg["DB_HOST"] = cfg.get("DB_HOST") or "training-postgres"
    cfg["DB_PORT"] = cfg.get("DB_PORT") or "5432"
    cfg["DB_NAME"] = cfg.get("DB_NAME") or "training"
    cfg["DB_USER"] = cfg.get("DB_USER") or "training_app"
    cfg["DB_PASSWORD"] = cfg.get("DB_PASSWORD") or ""

    return Config(cfg)


def get_fitness_fatigue_config():
    try:
        start_date = date.fromisoformat(FITNESS_FATIGUE_START_DATE)
    except (TypeError, ValueError) as exc:
        raise ValueError("FITNESS_FATIGUE_START_DATE must be an ISO date") from exc

    try:
        ZoneInfo(APP_TIMEZONE)
    except Exception as exc:
        raise ValueError(f"Invalid application timezone: {APP_TIMEZONE}") from exc

    if not isinstance(FITNESS_TIME_CONSTANT_DAYS, int) or FITNESS_TIME_CONSTANT_DAYS <= 0:
        raise ValueError("FITNESS_TIME_CONSTANT_DAYS must be a positive integer")

    if not isinstance(FATIGUE_TIME_CONSTANT_DAYS, int) or FATIGUE_TIME_CONSTANT_DAYS <= 0:
        raise ValueError("FATIGUE_TIME_CONSTANT_DAYS must be a positive integer")

    if not FITNESS_FATIGUE_MODEL_VERSION.strip():
        raise ValueError("FITNESS_FATIGUE_MODEL_VERSION must not be blank")

    return {
        "start_date": start_date,
        "app_timezone": APP_TIMEZONE,
        "fitness_days": FITNESS_TIME_CONSTANT_DAYS,
        "fatigue_days": FATIGUE_TIME_CONSTANT_DAYS,
        "model_version": FITNESS_FATIGUE_MODEL_VERSION,
    }