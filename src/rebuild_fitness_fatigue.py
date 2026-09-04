"""Preview or apply the complete daily Fitness/Fatigue/Form series.

Usage from the repository root::

    python .\\src\\rebuild_fitness_fatigue.py --dry-run
    python .\\src\\rebuild_fitness_fatigue.py --apply

Exactly one mode is required. ``--dry-run`` uses a read-only transaction and
does not call the replacement helper. ``--apply`` deletes and reinserts the
complete series, verifies the result, and commits only after all checks pass.
"""

import argparse
import logging
import sys

from db_writer import (
    connect_db,
    prepare_fitness_fatigue,
    replace_fitness_fatigue,
)
from logging_config import configure_logging
from settings import get_db_config

logger = logging.getLogger(__name__)


def parse_args(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true", help="calculate and print without database writes")
    modes.add_argument("--apply", action="store_true", help="replace and commit the model series")
    return parser.parse_args(args)


def print_summary(mode, model_rows, model_config, through_date, source_count):
    latest = model_rows[-1]
    zero_days = sum(1 for row in model_rows if row["daily_load"] == 0)
    positive_days = len(model_rows) - zero_days

    print(f"Mode: {mode}")
    print(f"Model version: {model_config['model_version']}")
    print(f"Reliable start date: {model_config['start_date']}")
    print(f"Through date: {through_date}")
    print(f"Timezone: {model_config['app_timezone']}")
    print(f"Fitness time constant: {model_config['fitness_days']} days")
    print(f"Fatigue time constant: {model_config['fatigue_days']} days")
    print(f"Source activity-day count: {source_count}")
    print(f"Generated calendar-day count: {len(model_rows)}")
    print(f"Zero-load calendar-day count: {zero_days}")
    print(f"Positive-load calendar-day count: {positive_days}")
    print(f"First generated date: {model_rows[0]['date']}")
    print(f"Last generated date: {latest['date']}")
    print(f"Current Fitness: {latest['fitness']}")
    print(f"Current Fatigue: {latest['fatigue']}")
    print(f"Current Form: {latest['form']}")

    print("\nDate        Load   Fitness   Fatigue   Form")
    for row in reversed(model_rows[-14:]):
        print(
            f"{row['date']}  {row['daily_load']:>4}  "
            f"{row['fitness']:>8}  {row['fatigue']:>8}  {row['form']:>7}"
        )


def verify_persisted_rows(cur, model_rows, model_version):
    cur.execute(
        """
        SELECT
            COUNT(*) AS row_count,
            MIN("date") AS first_date,
            MAX("date") AS last_date,
            COUNT(*) FILTER (WHERE model_version IS DISTINCT FROM %s) AS wrong_versions
        FROM public.daily_fitness_fatigue
        """,
        (model_version,),
    )
    row = cur.fetchone()
    if isinstance(row, dict):
        values = row
    else:
        values = dict(zip(("row_count", "first_date", "last_date", "wrong_versions"), row))

    if values["row_count"] != len(model_rows):
        raise RuntimeError("Persisted row count does not match generated row count")
    if values["first_date"] != model_rows[0]["date"]:
        raise RuntimeError("Persisted first date does not match generated first date")
    if values["last_date"] != model_rows[-1]["date"]:
        raise RuntimeError("Persisted last date does not match generated last date")
    if values["wrong_versions"] != 0:
        raise RuntimeError("Persisted model version verification failed")


def run(args):
    cfg = get_db_config()
    mode = "DRY RUN" if args.dry_run else "APPLY"
    logger.info("Fitness/Fatigue/Form CLI mode=%s", mode)

    with connect_db(cfg) as conn:
        try:
            with conn.cursor() as cur:
                if args.dry_run:
                    cur.execute("SET TRANSACTION READ ONLY")
                model_rows, model_config, through_date, source_rows = prepare_fitness_fatigue(cur)

                if args.apply:
                    replace_fitness_fatigue(cur, model_rows)
                    verify_persisted_rows(cur, model_rows, model_config["model_version"])
                    conn.commit()
                    logger.info("Fitness/Fatigue/Form apply committed")
                    print_summary(mode, model_rows, model_config, through_date, len(source_rows))
                    print("Transaction committed")
                else:
                    print_summary(mode, model_rows, model_config, through_date, len(source_rows))
                    print("No database writes occurred")
        except Exception:
            if args.apply:
                conn.rollback()
                logger.exception("Fitness/Fatigue/Form apply rolled back")
            raise
        finally:
            if args.dry_run:
                conn.rollback()


def main(argv=None):
    configure_logging("training-runner-fitness-fatigue")
    args = parse_args(argv)
    try:
        run(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())