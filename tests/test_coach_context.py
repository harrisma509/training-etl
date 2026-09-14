import unittest
from datetime import date
from unittest.mock import Mock

from coach_context import _audit_history, _commentary, _daily


class CoachContextDailyTests(unittest.TestCase):
    def test_daily_uses_inclusive_calendar_window_and_preserves_sparse_rows(self):
        cursor = Mock()
        cursor.fetchall.return_value = [
            {
                "date": date(2026, 9, 13),
                "other_activities": [{"name": str(index)} for index in range(25)],
                "main_ride_rpe": -1,
            },
            {
                "date": date(2026, 9, 10),
                "other_activities": None,
                "main_ride_rpe": 7,
            },
        ]

        rows = _daily(cursor, date(2026, 9, 13), 28)

        params = cursor.execute.call_args.args[1]
        self.assertEqual(params, (date(2026, 8, 17), date(2026, 9, 13)))
        self.assertEqual([row["date"] for row in rows], [date(2026, 9, 13), date(2026, 9, 10)])
        self.assertIsNone(rows[0]["main_ride_rpe"])
        self.assertEqual(len(rows[0]["other_activities"]), 20)
        self.assertIsNone(rows[1]["other_activities"])

    def test_daily_window_is_inclusive_for_minimum_and_maximum_values(self):
        for daily_days, expected_start in (
            (7, date(2026, 9, 7)),
            (365, date(2025, 9, 14)),
        ):
            cursor = Mock()
            cursor.fetchall.return_value = []
            _daily(cursor, date(2026, 9, 13), daily_days)
            self.assertEqual(cursor.execute.call_args.args[1], (expected_start, date(2026, 9, 13)))


class CoachContextWeeklyBoundsTests(unittest.TestCase):
    def test_audit_history_uses_configured_limit_and_deterministic_item_order(self):
        cursor = Mock()
        cursor.fetchall.side_effect = [
            [{"week_start": date(2026, 9, 7)}],
            [{"week_start": date(2026, 9, 7), "item_key": "load", "status": "green", "summary": "ok", "sort_order": 1}],
        ]

        rows = _audit_history(cursor, date(2026, 9, 8), 52)

        self.assertEqual(cursor.execute.call_args_list[0].args[1], (date(2026, 9, 8), 52))
        self.assertEqual(cursor.execute.call_args_list[1].args[1], ([date(2026, 9, 7)],))
        self.assertEqual(rows[0]["items"][0]["item_key"], "load")

    def test_commentary_uses_configured_limit_and_matching_date_window(self):
        cursor = Mock()
        cursor.fetchall.return_value = []

        _commentary(cursor, date(2026, 9, 7), 104)

        self.assertEqual(
            cursor.execute.call_args.args[1],
            (date(2026, 9, 7), date(2024, 9, 9), 104),
        )


if __name__ == "__main__":
    unittest.main()
