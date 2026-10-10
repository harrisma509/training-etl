import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from weekly_builder import build_weekly_training


DENVER = ZoneInfo("America/Denver")


def activity_day(day, load):
    return {
        "date": day,
        "total_load": load,
        "main_ride_load": load,
        "other_load": 0,
        "ride_count": 1 if load else 0,
        "walk_count": 0,
        "hike_count": 0,
        "strength_count": 0,
        "mobility_count": 0,
        "ski_count": 0,
        "run_count": 0,
        "other_count": 0,
        "main_ride_band": "Endurance",
    }


class WeeklyBuilderCurrentWeekTests(unittest.TestCase):
    def test_empty_history_returns_only_the_current_week_with_unknown_calculations(self):
        rows = build_weekly_training([], as_of=date(2026, 10, 10))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["week_start"], "2026-10-05")
        self.assertEqual(rows[0]["week_end"], "2026-10-11")
        self.assertEqual(rows[0]["total_load"], 0)
        self.assertEqual(rows[0]["activity_days"], 0)
        self.assertIsNone(rows[0]["chronic_daily_c"])
        self.assertIsNone(rows[0]["chronic_weekly_cw"])
        self.assertIsNone(rows[0]["ac_ratio"])
        self.assertIsNone(rows[0]["ramp_pct"])
        self.assertEqual(rows[0]["ramp_pct_display"], "")
        self.assertIsNone(rows[0]["remaining_to_20pct_ramp"])
        self.assertIsNone(rows[0]["status_level"])
        self.assertIsNone(rows[0]["status_text"])

    def test_current_empty_week_uses_available_chronic_history_but_no_interpretation(self):
        daily_rows = [
            activity_day("2026-09-08", 100),
            activity_day("2026-09-15", 100),
            activity_day("2026-09-22", 100),
            activity_day("2026-09-29", 100),
        ]

        rows = build_weekly_training(daily_rows, as_of=date(2026, 10, 10))
        current = rows[-1]

        self.assertEqual(current["week_start"], "2026-10-05")
        self.assertEqual(current["total_load"], 0)
        self.assertEqual(current["chronic_daily_c"], 14.3)
        self.assertEqual(current["chronic_weekly_cw"], 100.1)
        self.assertIsNone(current["ac_ratio"])
        self.assertIsNone(current["ramp_pct"])
        self.assertIsNone(current["status_level"])
        self.assertIsNone(current["status_text"])

    def test_activity_backed_and_internal_empty_weeks_are_preserved_without_future_weeks(self):
        rows = build_weekly_training(
            [
                activity_day("2026-09-14", 100),
                activity_day("2026-10-02", 100),
            ],
            as_of=date(2026, 10, 10),
        )

        self.assertEqual(
            [row["week_start"] for row in rows],
            ["2026-09-14", "2026-09-21", "2026-09-28", "2026-10-05"],
        )
        self.assertEqual(rows[0]["total_load"], 100)
        self.assertEqual(rows[1]["total_load"], 0)
        self.assertEqual(rows[-1]["total_load"], 0)
        self.assertEqual(rows[-1]["week_end"], "2026-10-11")

    def test_later_activity_updates_the_same_current_week_with_normal_calculations(self):
        prior_rows = [
            activity_day("2026-09-08", 100),
            activity_day("2026-09-15", 100),
            activity_day("2026-09-22", 100),
            activity_day("2026-09-29", 100),
        ]
        as_of = date(2026, 10, 10)

        before_activity = build_weekly_training(prior_rows, as_of=as_of)
        after_activity = build_weekly_training(
            prior_rows + [activity_day("2026-10-06", 50)],
            as_of=as_of,
        )

        self.assertEqual(before_activity[-1]["week_start"], after_activity[-1]["week_start"])
        self.assertEqual(after_activity[-1]["week_start"], "2026-10-05")
        self.assertEqual(after_activity[-1]["total_load"], 50)
        self.assertIsNotNone(after_activity[-1]["ac_ratio"])
        self.assertIsNotNone(after_activity[-1]["ramp_pct"])
        self.assertIsNotNone(after_activity[-1]["status_level"])
        self.assertIsNotNone(after_activity[-1]["status_text"])

    def test_repeated_builds_are_idempotent_for_the_same_as_of_date(self):
        daily_rows = [activity_day("2026-10-02", 100)]
        as_of = date(2026, 10, 10)

        self.assertEqual(
            build_weekly_training(daily_rows, as_of=as_of),
            build_weekly_training(daily_rows, as_of=as_of),
        )

    def test_denver_week_boundary_uses_the_local_calendar(self):
        cases = (
            (
                datetime(2026, 10, 11, 23, 59, 59, tzinfo=DENVER),
                "2026-10-05",
            ),
            (datetime(2026, 10, 12, 0, 0, tzinfo=DENVER), "2026-10-12"),
            (datetime(2026, 10, 13, 12, 0, tzinfo=DENVER), "2026-10-12"),
            (
                datetime(2026, 10, 12, 5, 59, 59, tzinfo=timezone.utc),
                "2026-10-05",
            ),
            (
                datetime(2026, 10, 12, 6, 0, tzinfo=timezone.utc),
                "2026-10-12",
            ),
            (
                datetime(2026, 3, 9, 0, 0, tzinfo=DENVER),
                "2026-03-09",
            ),
        )

        for as_of, expected_week_start in cases:
            with self.subTest(as_of=as_of):
                rows = build_weekly_training([], as_of=as_of)
                self.assertEqual(rows[0]["week_start"], expected_week_start)

    def test_naive_datetime_is_rejected_as_ambiguous(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            build_weekly_training([], as_of=datetime(2026, 10, 12, 0, 0))


if __name__ == "__main__":
    unittest.main()
