import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from db_writer import (
    affected_activity_dates,
    rebuild_daily_for_dates,
    write_training_to_db,
)


DATE = "2024-04-01"


def activity(activity_id, name, sport_type, category, moving, distance, elevation):
    return {
        "activity_id": activity_id,
        "date_local": DATE,
        "name": name,
        "sport_type": sport_type,
        "activity_category": category,
        "moving_sec": moving,
        "elapsed_sec": moving + 300,
        "distance_mi": distance,
        "elevation_ft": elevation,
        "has_heartrate": False,
        "average_hr": None,
        "max_hr": None,
        "gear_id": "b1" if category == "ride" else "",
        "bike_name": "Trail Bike" if category == "ride" else "",
    }


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
        self.deleted_dates = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "DELETE FROM daily_training" in sql:
            self.deleted_dates.append(params[0])

    def fetchall(self):
        return self.rows


class AuthoritativeDailyWriterTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            activity(101, "Long Ride", "Ride", "ride", 3600, 20.0, 300),
            activity(202, "Morning Walk", "Walk", "walk", 900, 1.5, 20),
            activity(203, "Evening Walk", "Walk", "walk", 600, 1.0, 10),
        ]
        self.cursor = FakeCursor(self.rows)
        self.upserted_daily = []
        self.upsert_patch = patch(
            "db_writer.upsert_daily_training",
            side_effect=lambda cur, rows: self.upserted_daily.extend(rows),
        )
        self.hr_patch = patch("daily_builder.fetch_hr_zones", return_value=([100] * 5, [200] * 5))
        self.detail_patch = patch(
            "daily_builder.fetch_activity_detail",
            return_value={"perceived_exertion": 7},
        )
        self.upsert_patch.start()
        self.hr_patch.start()
        self.detail_patch.start()

    def tearDown(self):
        self.detail_patch.stop()
        self.hr_patch.stop()
        self.upsert_patch.stop()

    def test_bounded_fetch_rebuilds_from_all_persisted_rows(self):
        daily, warnings, deleted = rebuild_daily_for_dates(
            self.cursor,
            {DATE},
            access_token="token",
            chronic_c=10,
        )

        row = daily[0]
        self.assertEqual(row["activity_count"], 3)
        self.assertEqual(row["ride_count"], 1)
        self.assertEqual(row["walk_count"], 2)
        self.assertEqual(row["main_ride_id"], "101")
        self.assertEqual(
            row["other_activities"],
            [
                {"activity_id": "202", "name": "Morning Walk", "activity_category": "walk"},
                {"activity_id": "203", "name": "Evening Walk", "activity_category": "walk"},
            ],
        )
        self.assertEqual(row["main_ride_moving_sec"], 3600)
        self.assertEqual(row["other_moving_sec"], 1500)
        self.assertEqual(row["main_ride_miles"], 20.0)
        self.assertEqual(row["other_miles"], 2.5)
        self.assertEqual(row["other_elevation_ft"], 30)
        self.assertGreater(row["total_load"], 0)
        self.assertEqual(warnings, [])
        self.assertEqual(deleted, [])

    def test_repeating_rebuild_is_idempotent(self):
        first = rebuild_daily_for_dates(self.cursor, {DATE}, "token", 10)[0]
        self.upserted_daily.clear()
        second = rebuild_daily_for_dates(self.cursor, {DATE}, "token", 10)[0]
        self.assertEqual(first, second)

    def test_empty_affected_date_deletes_existing_daily_row(self):
        cursor = FakeCursor([])
        daily, _, deleted = rebuild_daily_for_dates(cursor, {DATE}, "token", 10)
        self.assertEqual(daily, [])
        self.assertEqual(deleted, [DATE])
        self.assertEqual(cursor.deleted_dates, [DATE])

    def test_old_and_new_dates_are_both_affected(self):
        moved = {"id": "101", "date_local": "2024-04-02"}
        self.assertEqual(
            affected_activity_dates({"2024-04-01"}, [moved]),
            {"2024-04-01", "2024-04-02"},
        )

    def test_empty_fetch_does_not_rebuild_any_daily_date(self):
        cursor = FakeCursor([])
        daily, warnings, deleted = rebuild_daily_for_dates(cursor, set(), "token", 10)
        self.assertEqual((daily, warnings, deleted), ([], [], []))
        self.assertEqual(cursor.calls, [])

    def test_transaction_failure_does_not_commit(self):
        class Connection:
            def __init__(self):
                self.committed = False
                self.rolled_back = False
                self.cursor_instance = FakeCursor([])

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                if exc_type:
                    self.rolled_back = True
                return False

            def cursor(self):
                class CursorContext:
                    def __enter__(_,):
                        return self.cursor_instance

                    def __exit__(_, exc_type, exc_value, traceback):
                        return False

                return CursorContext()

            def commit(self):
                self.committed = True

        connection = Connection()
        cfg = {
            "WRITE_DB": True,
            "DB_HOST": "test",
            "DB_PORT": 5432,
            "DB_NAME": "test",
            "DB_USER": "test",
            "DB_PASSWORD": "test",
            "DAYS_BACK": 7,
            "LOAD_CHRONIC_C": 10,
        }
        with patch("db_writer.psycopg.connect", return_value=connection), patch(
            "db_writer.upsert_strava_activities"
        ), patch(
            "db_writer.rebuild_daily_for_dates",
            side_effect=RuntimeError("daily rebuild failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "daily rebuild failed"):
                write_training_to_db(
                    cfg,
                    [self.rows[0]],
                    [],
                    [],
                    [],
                    "2024-04-01T00:00:00+00:00",
                    access_token="token",
                    chronic_c=10,
                )

        self.assertFalse(connection.committed)
        self.assertTrue(connection.rolled_back)


if __name__ == "__main__":
    unittest.main()
