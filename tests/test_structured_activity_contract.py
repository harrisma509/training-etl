import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from activity_utils import normalize_activity
from db_writer import upsert_strava_activities


class StructuredActivityNormalizationTests(unittest.TestCase):
    def normalize_integer_field(self, field_name, value):
        return normalize_activity({"id": 123, field_name: value})[
            {
                "utc_offset": "utc_offset_seconds",
                "workout_type": "workout_type",
                "max_watts": "max_watts",
                "suffer_score": "relative_effort",
            }[field_name]
        ]

    def test_utc_offset_accepts_integer_valued_numbers(self):
        for value, expected in ((-21600, -21600), (-21600.0, -21600), (7200.0, 7200), (0.0, 0)):
            with self.subTest(value=value):
                normalized = self.normalize_integer_field("utc_offset", value)
                self.assertEqual(normalized, expected)
                self.assertIs(type(normalized), int)

    def test_summary_activity_with_integral_float_utc_offset_normalizes(self):
        row = normalize_activity({
            "id": 123,
            "start_date": "2024-04-03T14:15:00Z",
            "start_date_local": "2024-04-03T08:15:00",
            "timezone": "(GMT-06:00) America/Denver",
            "utc_offset": -21600.0,
        }, summary_observed=True)
        self.assertEqual(row["utc_offset_seconds"], -21600)
        self.assertIs(type(row["utc_offset_seconds"]), int)

    def test_all_approved_integer_fields_accept_integral_floats(self):
        for field_name, expected in (
            ("workout_type", 10),
            ("max_watts", 400),
            ("suffer_score", 82),
        ):
            with self.subTest(field_name=field_name):
                normalized = self.normalize_integer_field(field_name, float(expected))
                self.assertEqual(normalized, expected)
                self.assertIs(type(normalized), int)

    def test_integer_fields_reject_non_integral_nonfinite_bool_and_string_values(self):
        invalid_values = (1.5, float("nan"), float("inf"), float("-inf"), True, False, "1")
        for field_name in ("utc_offset", "workout_type", "max_watts", "suffer_score"):
            for value in invalid_values:
                with self.subTest(field_name=field_name, value=value):
                    with self.assertRaises(ValueError):
                        self.normalize_integer_field(field_name, value)

    def test_utc_offset_range_remains_restricted(self):
        for value in (50400.1, 50401.0, -50400.1, -50401.0):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.normalize_integer_field("utc_offset", value)

    def test_normalizes_approved_fields_and_preserves_zero_false_and_null(self):
        row = normalize_activity({
            "id": 123,
            "start_date": "2024-04-03T14:15:00Z",
            "start_date_local": "2024-04-03T08:15:00",
            "timezone": "(GMT-07:00) America/Denver",
            "utc_offset": -25200,
            "manual": False,
            "trainer": False,
            "commute": False,
            "private": False,
            "flagged": False,
            "workout_type": 0,
            "device_name": None,
            "average_speed": 0,
            "max_speed": 0,
            "average_cadence": 0,
            "average_watts": 0,
            "weighted_average_watts": 0,
            "max_watts": 0,
            "kilojoules": 0,
            "device_watts": False,
            "suffer_score": 0,
            "elev_high": 0,
            "elev_low": 0,
        }, summary_observed=True)

        self.assertEqual(row["start_at_utc"], datetime(2024, 4, 3, 14, 15, tzinfo=timezone.utc))
        self.assertEqual(row["start_at_local"], datetime(2024, 4, 3, 8, 15))
        self.assertEqual(row["utc_offset_seconds"], -25200)
        self.assertEqual(row["workout_type"], 0)
        self.assertIsNone(row["device_name"])
        self.assertEqual(row["average_watts"], 0.0)
        self.assertFalse(row["device_watts"])
        self.assertEqual(row["relative_effort"], 0)
        self.assertTrue(row["_summary_activity_observed"])

    def test_omitted_fields_are_not_present_for_writer_merge(self):
        row = normalize_activity({"id": 123, "start_date_local": "2024-04-03T08:15:00"})
        self.assertIn("start_at_local", row)
        self.assertNotIn("device_name", row)
        self.assertNotIn("average_watts", row)

    def test_invalid_structured_values_fail_before_write(self):
        invalid_values = (
            {"manual": 0},
            {"workout_type": True},
            {"average_watts": float("nan")},
            {"utc_offset": 50401},
            {"start_date": "2024-04-03T14:15:00"},
            {
                "start_date": "2024-04-03T14:15:00Z",
                "start_date_local": "2024-04-04T08:15:00",
                "date_local": "2024-04-03",
            },
        )
        for values in invalid_values:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    normalize_activity({"id": 123, **values})

    def test_writer_preserves_omitted_values_and_allows_explicit_null(self):
        cursor = mock.Mock()
        row = normalize_activity({
            "id": 123,
            "start_date_local": "2024-04-03T08:15:00",
            "device_name": None,
        }, summary_observed=True)
        with mock.patch("db_writer.ensure_gear_records"), mock.patch(
            "db_writer.fetch_gear_display_names", return_value={}
        ):
            upsert_strava_activities(cursor, [row])

        sql, params = cursor.execute.call_args.args
        self.assertIn("device_name = CASE WHEN %(device_name_observed)s", sql)
        self.assertTrue(params["device_name_observed"])
        self.assertIsNone(params["device_name"])
        self.assertFalse(params["average_watts_observed"])
        self.assertTrue(params["summary_activity_observed"])
        self.assertNotIn("_summary_activity_observed", params["raw_json"])
        self.assertIn("2024-04-03T08:15:00", params["raw_json"])


if __name__ == "__main__":
    unittest.main()