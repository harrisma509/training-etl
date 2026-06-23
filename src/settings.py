import os

from constants import DEFAULT_CHRONIC_C


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
        "DAYS_BACK",
        "OUTPUT_JSON",
        "OUTPUT_CSV",
        "LOAD_CHRONIC_C",
        "GEAR_MAP_CSV",
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
    cfg["LOAD_CHRONIC_C"] = float(cfg.get("LOAD_CHRONIC_C") or DEFAULT_CHRONIC_C)
    cfg["GEAR_MAP_CSV"] = cfg.get("GEAR_MAP_CSV") or "/config/gear_map.csv"

    return cfg