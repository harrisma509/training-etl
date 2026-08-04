"""
Shared audit utility helpers.

This module contains small helpers used across the weekly audit ETL,
especially type-boundary helpers for database-returned values.

Postgres numeric values may arrive as Decimal values, and evidence_json
must be JSON serializable before being written to JSONB columns.

Keep this module generic and side-effect free.
"""

import decimal
from datetime import date, datetime


def safe_int(value):
    if value is None:
        return 0
    try:
        return int(round(float(value)))
    except Exception:
        return 0


def normalize_json_value(value):
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: normalize_json_value(subval) for key, subval in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_json_value(item) for item in value]
    return value
