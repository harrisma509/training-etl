"""Pure daily Fitness, Fatigue, and start-of-day Form calculations.

The builder is used by the sync pipeline and by
``rebuild_fitness_fatigue.py``. It accepts sparse authoritative daily loads,
fills the configured calendar interval with zero-load days, and returns
persistence-ready rows. It does not connect to PostgreSQL or perform writes.

Preview the calculated series without writing it:

    python .\\src\\rebuild_fitness_fatigue.py --dry-run

Apply the complete replacement explicitly:

    python .\\src\\rebuild_fitness_fatigue.py --apply

The first 42 calendar days are a zero-initialized v1 warm-up period. Form is
the start-of-day value derived from the prior day's Fitness and Fatigue.
"""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


ZERO = Decimal("0")
OUTPUT_QUANTUM = Decimal("0.01")
logger = logging.getLogger(__name__)


def build_fitness_fatigue(
    daily_load_rows,
    start_date,
    through_date,
    fitness_days,
    fatigue_days,
    model_version,
):
    start = parse_date(start_date)
    end = parse_date(through_date)

    if start > end:
        raise ValueError("start_date must not be after through_date")
    if not isinstance(fitness_days, int) or fitness_days <= 0:
        raise ValueError("fitness_days must be a positive integer")
    if not isinstance(fatigue_days, int) or fatigue_days <= 0:
        raise ValueError("fatigue_days must be a positive integer")
    if not isinstance(model_version, str) or not model_version.strip():
        raise ValueError("model_version must not be blank")

    loads_by_date = {}

    for source_row in sorted(daily_load_rows, key=lambda row: parse_date(row["date"])):
        source_date = parse_date(source_row["date"])

        if source_date < start or source_date > end:
            continue
        if source_date in loads_by_date:
            raise ValueError(f"Duplicate daily load date: {source_date.isoformat()}")

        raw_load = source_row.get("total_load")
        if raw_load is None:
            logger.warning("Null total_load for %s; using zero", source_date)
            raw_load = ZERO
        try:
            load = Decimal(str(raw_load))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Invalid daily load for {source_date.isoformat()}") from exc

        if not load.is_finite() or load < ZERO:
            raise ValueError(f"Invalid daily load for {source_date.isoformat()}: {raw_load!r}")
        if load != load.to_integral_value():
            raise ValueError(f"Invalid non-integer daily load for {source_date.isoformat()}: {raw_load!r}")

        loads_by_date[source_date] = load

    fitness = ZERO
    fatigue = ZERO
    rows = []
    current = start
    fitness_constant = Decimal(fitness_days)
    fatigue_constant = Decimal(fatigue_days)

    while current <= end:
        daily_load = loads_by_date.get(current, ZERO)
        form = fitness - fatigue
        fitness = fitness + (daily_load - fitness) / fitness_constant
        fatigue = fatigue + (daily_load - fatigue) / fatigue_constant

        rows.append({
            "date": current,
            "daily_load": int(daily_load),
            "fitness": quantize(fitness),
            "fatigue": quantize(fatigue),
            "form": quantize(form),
            "model_version": model_version,
        })
        current += timedelta(days=1)

    return rows


def parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise ValueError(f"Invalid date: {value!r}") from exc


def quantize(value):
    return value.quantize(OUTPUT_QUANTUM, rounding=ROUND_HALF_UP)


def validate_fitness_fatigue_rows(rows, start_date, through_date, model_version):
    start = parse_date(start_date)
    end = parse_date(through_date)

    if not rows:
        raise ValueError("Fitness/Fatigue/Form builder generated no rows")
    if rows[0]["date"] != start:
        raise ValueError("Generated series has an unexpected first date")
    if rows[-1]["date"] != end:
        raise ValueError("Generated series has an unexpected last date")

    expected_date = start
    seen_dates = set()

    for row in rows:
        row_date = parse_date(row["date"])
        if row_date in seen_dates:
            raise ValueError(f"Generated duplicate date: {row_date.isoformat()}")
        if row_date != expected_date:
            raise ValueError(f"Generated date gap before {row_date.isoformat()}")
        if row["daily_load"] < 0 or row["fitness"] < ZERO or row["fatigue"] < ZERO:
            raise ValueError(f"Generated invalid values for {row_date.isoformat()}")
        if row["model_version"] != model_version:
            raise ValueError(f"Generated model version mismatch for {row_date.isoformat()}")

        seen_dates.add(row_date)
        expected_date += timedelta(days=1)

    if expected_date != end + timedelta(days=1):
        raise ValueError("Generated series does not cover the requested interval")