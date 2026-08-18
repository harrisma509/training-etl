import sys
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from daily_builder import build_daily_training
from db_writer import upsert_daily_training


class DailyBuilderOtherActivitiesTests(unittest.TestCase):
    def setUp(self):
        self.hr_patcher = patch("daily_builder.fetch_hr_zones", return_value=(100, 200))
        self.rpe_patcher = patch("daily_builder.fetch_activity_detail", return_value={"perceived_exertion": 7})
        self.hr_patcher.start()
        self.rpe_patcher.start()

    def tearDown(self):
        self.rpe_patcher.stop()
        self.hr_patcher.stop()

    def test_main_ride_plus_walk_keeps_main_ride_and_exposes_other_activities(self):
        rows = [
            {
                "id": 101,
                "date_local": "2024-04-01",
                "name": "Long Ride",
                "sport_type": "Ride",
                "activity_category": "ride",
                "moving_sec": 5400,
                "elapsed_sec": 6000,
                "distance_mi": 30.0,
                "elevation_ft": 500,
                "has_heartrate": False,
                "gear_id": "b1",
            },
            {
                "id": 202,
                "date_local": "2024-04-01",
                "name": "Morning Walk",
                "sport_type": "Walk",
                "activity_category": "walk",
                "moving_sec": 1800,
                "elapsed_sec": 2000,
                "distance_mi": 1.5,
                "elevation_ft": 40,
                "has_heartrate": False,
                "gear_id": "",
            },
        ]

        daily, warnings = build_daily_training(rows, "token", 10, gear_display_map={})

        self.assertEqual(len(daily), 1)
        row = daily[0]
        self.assertEqual(row["main_ride_id"], 101)
        self.assertEqual(row["other_activity_count"], 1)
        self.assertEqual(row["other_activity_names"], "Morning Walk (walk)")
        self.assertEqual(
            row["other_activities"],
            [{"activity_id": "202", "name": "Morning Walk", "activity_category": "walk"}],
        )
        self.assertEqual(warnings, [])

    def test_secondary_cycling_activities_are_kept_in_other_activities(self):
        rows = [
            {"id": 11, "date_local": "2024-04-02", "name": "Long Ride", "sport_type": "Ride", "activity_category": "ride", "moving_sec": 4500, "elapsed_sec": 5000, "distance_mi": 28.0, "elevation_ft": 400, "has_heartrate": False, "gear_id": "b1"},
            {"id": 12, "date_local": "2024-04-02", "name": "Recovery Spin", "sport_type": "Ride", "activity_category": "ride", "moving_sec": 2100, "elapsed_sec": 2600, "distance_mi": 12.0, "elevation_ft": 150, "has_heartrate": False, "gear_id": "b1"},
            {"id": 22, "date_local": "2024-04-02", "name": "Strength", "sport_type": "WeightTraining", "activity_category": "strength", "moving_sec": 1200, "elapsed_sec": 1500, "distance_mi": 0.0, "elevation_ft": 0, "has_heartrate": False, "gear_id": ""},
        ]

        daily, _ = build_daily_training(rows, "token", 10, gear_display_map={})
        row = daily[0]

        self.assertEqual(row["main_ride_id"], 11)
        self.assertEqual(row["other_activity_count"], 2)
        self.assertEqual(
            row["other_activities"],
            [
                {"activity_id": "12", "name": "Recovery Spin", "activity_category": "ride"},
                {"activity_id": "22", "name": "Strength", "activity_category": "strength"},
            ],
        )

    def test_no_cycling_activity_keeps_all_rows_in_other_activities(self):
        rows = [
            {"id": 31, "date_local": "2024-04-03", "name": "Walk", "sport_type": "Walk", "activity_category": "walk", "moving_sec": 2400, "elapsed_sec": 2700, "distance_mi": 2.0, "elevation_ft": 50, "has_heartrate": False, "gear_id": ""},
            {"id": 32, "date_local": "2024-04-03", "name": "Mobility", "sport_type": "Yoga", "activity_category": "mobility", "moving_sec": 1200, "elapsed_sec": 1800, "distance_mi": 0.0, "elevation_ft": 0, "has_heartrate": False, "gear_id": ""},
        ]

        daily, _ = build_daily_training(rows, "token", 10, gear_display_map={})
        row = daily[0]

        self.assertEqual(row["main_ride_id"], "")
        self.assertEqual(row["other_activity_count"], 2)
        self.assertEqual(
            row["other_activities"],
            [
                {"activity_id": "31", "name": "Walk", "activity_category": "walk"},
                {"activity_id": "32", "name": "Mobility", "activity_category": "mobility"},
            ],
        )

    def test_multiple_supporting_activities_keep_authoritative_order(self):
        rows = [
            {"id": 40, "date_local": "2024-04-04", "name": "Group Ride", "sport_type": "Ride", "activity_category": "ride", "moving_sec": 5000, "elapsed_sec": 5400, "distance_mi": 32.0, "elevation_ft": 600, "has_heartrate": False, "gear_id": "b1"},
            {"id": 41, "date_local": "2024-04-04", "name": "30 min Chest & Back Strength with Andy Speer", "sport_type": "WeightTraining", "activity_category": "strength", "moving_sec": 1800, "elapsed_sec": 2000, "distance_mi": 0.0, "elevation_ft": 0, "has_heartrate": False, "gear_id": ""},
            {"id": 42, "date_local": "2024-04-04", "name": "Prehab", "sport_type": "WeightTraining", "activity_category": "strength", "moving_sec": 600, "elapsed_sec": 900, "distance_mi": 0.0, "elevation_ft": 0, "has_heartrate": False, "gear_id": ""},
            {"id": 43, "date_local": "2024-04-04", "name": "Morning Walk", "sport_type": "Walk", "activity_category": "walk", "moving_sec": 1200, "elapsed_sec": 1500, "distance_mi": 1.2, "elevation_ft": 30, "has_heartrate": False, "gear_id": ""},
        ]

        daily, _ = build_daily_training(rows, "token", 10, gear_display_map={})
        row = daily[0]

        self.assertEqual(
            row["other_activities"],
            [
                {"activity_id": "41", "name": "30 min Chest & Back Strength with Andy Speer", "activity_category": "strength"},
                {"activity_id": "42", "name": "Prehab", "activity_category": "strength"},
                {"activity_id": "43", "name": "Morning Walk", "activity_category": "walk"},
            ],
        )

    def test_main_ride_only_produces_empty_other_activities_list(self):
        rows = [
            {"id": 50, "date_local": "2024-04-05", "name": "Solo Ride", "sport_type": "Ride", "activity_category": "ride", "moving_sec": 5400, "elapsed_sec": 6000, "distance_mi": 35.0, "elevation_ft": 700, "has_heartrate": False, "gear_id": "b1"}
        ]

        daily, _ = build_daily_training(rows, "token", 10, gear_display_map={})
        row = daily[0]

        self.assertEqual(row["other_activities"], [])
        self.assertEqual(row["other_activity_count"], 0)
        self.assertEqual(row["other_activity_names"], "")

    def test_missing_name_or_category_gets_default_values(self):
        rows = [
            {"id": 60, "date_local": "2024-04-06", "name": None, "sport_type": "Hike", "activity_category": "", "moving_sec": 2000, "elapsed_sec": 2400, "distance_mi": 1.0, "elevation_ft": 20, "has_heartrate": False, "gear_id": ""},
            {"id": 61, "date_local": "2024-04-06", "name": "Another Activity", "sport_type": "Workout", "activity_category": None, "moving_sec": 1500, "elapsed_sec": 1800, "distance_mi": 0.0, "elevation_ft": 0, "has_heartrate": False, "gear_id": ""},
        ]

        daily, _ = build_daily_training(rows, "token", 10, gear_display_map={})
        row = daily[0]

        self.assertEqual(
            row["other_activities"],
            [
                {"activity_id": "60", "name": "", "activity_category": "other"},
                {"activity_id": "61", "name": "Another Activity", "activity_category": "other"},
            ],
        )

    def test_upsert_daily_training_includes_other_activities_in_sql(self):
        class FakeCursor:
            def __init__(self):
                self.calls = []

            def execute(self, sql, params):
                self.calls.append((sql, params))

        cur = FakeCursor()
        row = {
            "date": "2024-04-07",
            "activity_count": 2,
            "other_activity_count": 1,
            "other_activity_names": "Morning Walk (walk)",
            "other_activities": [
                {"activity_id": "202", "name": "Morning Walk", "activity_category": "walk"}
            ],
            "other_miles": 1.5,
            "other_load": 3,
            "other_load_raw": 3.2,
            "total_load": 55,
        }

        upsert_daily_training(cur, [row])

        self.assertEqual(len(cur.calls), 1)
        sql, params = cur.calls[0]
        self.assertIn("other_activities", sql)
        self.assertEqual(params["other_activities"], row["other_activities"])
        self.assertIn("ON CONFLICT (date)", sql)
        self.assertIn("other_activities = EXCLUDED.other_activities", sql)


if __name__ == "__main__":
    unittest.main()
