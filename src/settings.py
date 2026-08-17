import os
from constants import DEFAULT_CHRONIC_C

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
    "OUTPUT_JSON",
    "OUTPUT_CSV",
    "OUTPUT_WEEKLY_JSON",
    "OUTPUT_WEEKLY_CSV",
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
    cfg["OUTPUT_JSON"] = cfg.get("OUTPUT_JSON") or "/tmp/daily_training.json"
    cfg["OUTPUT_CSV"] = cfg.get("OUTPUT_CSV") or "/tmp/daily_training.csv"
    cfg["OUTPUT_WEEKLY_JSON"] = cfg.get("OUTPUT_WEEKLY_JSON") or "/tmp/weekly_training.json"
    cfg["OUTPUT_WEEKLY_CSV"] = cfg.get("OUTPUT_WEEKLY_CSV") or "/tmp/weekly_training.csv"
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