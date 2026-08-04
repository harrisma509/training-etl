"""
Weekly Audit configuration.

This module contains constants used by the weekly audit ETL:
- audit date scope
- status labels
- G/Y/R weighted scoring weights
- gate item definitions
- critical risk item definitions
- audit item ordering and labels
- knee prehab/rehab/maintenance phase dates

Do not put database logic or scoring functions here.
Changing values in this file changes audit behavior.
"""

from datetime import date

AUDIT_MIN_WEEK_START = date(date.today().year, 1, 1)
KNEE_SURGERY_DATE = date(2026, 11, 19)
PREHAB_START_DATE = date(date.today().year, 8, 1)
SURGERY_GRACE_DAYS = 14
REHAB_END_DATE = date(2027, 5, 19)

STATUS_GREEN = "🟩 Green"
STATUS_YELLOW = "🟨 Yellow"
STATUS_RED = "🟥 Red"

GRADE_WEIGHTS = {
    "load": 25,
    "tid_pyramidal": 20,
    "hard_day_isolation": 15,
    "recovery_signals": 15,
    "strength_core": 12,
    "chain_72_hour": 8,
    "weight_band": 5,
}

GATE_ITEM_KEYS = {"prehab_knee"}
CRITICAL_ITEM_KEYS = {"load", "tid_pyramidal", "hard_day_isolation", "recovery_signals"}
STATUS_MULTIPLIERS = {
    STATUS_GREEN: 1.0,
    STATUS_YELLOW: 0.65,
    STATUS_RED: 0.0,
}

AUDIT_ITEMS = [
    ("load", "Load"),
    ("tid_pyramidal", "TID / Pyramidal"),
    ("weight_band", "Weight band"),
    ("hard_day_isolation", "Hard day isolation"),
    ("recovery_signals", "Recovery signals"),
    ("strength_core", "Strength & core"),
    ("chain_72_hour", "72-hour chain rule"),
    ("prehab_knee", "PreHab knee"),
]
