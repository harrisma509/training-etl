import sys
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from db_writer import (
    fetch_activity_dates,
    fetch_activity_rows_for_dates,
    fetch_all_daily_training_for_weekly,
    fetch_gear_display_names,
    write_training_to_db,
)


class ShapeCursor:
    def __init__(self):
        self.calls = []
        self.description = []
        self.mode = None

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "FROM gear" in sql:
            self.mode = "gear"
        elif "SELECT date_local" in sql:
            self.mode = "activity_dates"
        elif "FROM strava_activities" in sql:
            self.mode = "activity_rows"
        elif "FROM daily_training" in sql:
            self.mode = "daily"
        else:
            self.mode = "other"

    def fetchall(self):
        if self.mode == "gear":
            return [{"gear_id": "b1", "brand": "Acme", "model_year": 2024, "gear_name": "Trail Bike"}]
        if self.mode == "activity_dates":
            return [{"date_local": date(2024, 4, 1)}]
        if self.mode == "activity_rows":
            return []
        if self.mode == "daily":
            self.description = [SimpleNamespace(name=name) for name in (
                "date", "total_load", "main_ride_load", "other_load", "ride_count",
                "walk_count", "hike_count", "strength_count", "mobility_count",
                "ski_count", "run_count", "other_count", "main_ride_band",
            )]
            return [{
                "date": date(2024, 4, 1),
                "total_load": 42,
                "main_ride_load": 30,
                "other_load": 12,
                "ride_count": 1,
                "walk_count": 2,
                "hike_count": 0,
                "strength_count": 0,
                "mobility_count": 0,
                "ski_count": 0,
                "run_count": 0,
                "other_count": 0,
                "main_ride_band": "moderate",
            }]
        return []


class Connection:
    def __init__(self, cursor):
        self.cursor_value = cursor
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def cursor(self):
        class CursorContext:
            def __enter__(_,):
                return self.cursor_value

            def __exit__(_, exc_type, exc_value, traceback):
                return False

        return CursorContext()

    def commit(self):
        self.committed = True


class DbWriterReviewCorrectionTests(unittest.TestCase):
    def test_gear_display_names_read_mapping_values(self):
        cursor = ShapeCursor()
        result = fetch_gear_display_names(cursor, [{"gear_id": "b1"}])
        self.assertEqual(result, {"b1": "2024 Acme Trail Bike"})

    def test_weekly_rows_read_mapping_values(self):
        cursor = ShapeCursor()
        result = fetch_all_daily_training_for_weekly(cursor)
        self.assertEqual(result[0]["date"], date(2024, 4, 1))
        self.assertEqual(result[0]["total_load"], 42)
        self.assertEqual(result[0]["main_ride_band"], "moderate")

    def test_activity_queries_use_schema_compatible_array_types(self):
        cursor = ShapeCursor()
        fetch_activity_dates(cursor, [{"id": 123}])
        self.assertEqual(cursor.calls[-1][1], (["123"],))

        fetch_activity_rows_for_dates(cursor, {"2024-04-01"})
        parameters = cursor.calls[-1][1][0]
        self.assertEqual(parameters, [date(2024, 4, 1)])
        self.assertTrue(all(isinstance(value, date) for value in parameters))

    def test_writer_passes_typed_weekly_values_to_rebuild(self):
        cursor = ShapeCursor()
        connection = Connection(cursor)
        daily_rows = [{"date": "2024-04-01"}]
        weekly_rows = [{"week_start": "2024-04-01"}]
        weekly_builder = MagicMock(return_value=weekly_rows)
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
            "db_writer.rebuild_daily_for_dates", return_value=(daily_rows, [], [])
        ), patch("db_writer.rebuild_fitness_fatigue"), patch(
            "db_writer.build_weekly_training", weekly_builder
        ), patch("db_writer.replace_weekly_training"), patch(
            "db_writer.insert_sync_run_log"
        ):
            result = write_training_to_db(
                cfg,
                [{"id": "123", "date_local": "2024-04-01"}],
                [],
                [],
                [],
                "2024-04-01T00:00:00+00:00",
                access_token="token",
                chronic_c=10,
            )

        weekly_input = weekly_builder.call_args.args[0]
        self.assertEqual(weekly_input[0]["total_load"], 42)
        self.assertIsInstance(weekly_input[0]["ride_count"], int)
        self.assertEqual(result["weekly_rows"], weekly_rows)
        self.assertTrue(connection.committed)

    def test_db_mode_logs_authoritative_writer_result(self):
        import sync_training

        daily_row = {
            "date": "2024-04-01",
            "main_ride_name": "Ride",
            "main_ride_bike_name": "Bike",
            "main_ride_load": 10,
            "other_load": 2,
            "total_load": 12,
            "z4_z5_sec": 0,
        }
        weekly_row = {
            "week_start": "2024-04-01",
            "total_load": 12,
            "ramp_pct_display": "0%",
            "ac_ratio": 1.0,
            "status_level": "ok",
        }
        cfg = {"WRITE_DB": True, "DAYS_BACK": 7, "LOAD_CHRONIC_C": 10}
        sync_training.logger = MagicMock()
        with patch("sync_training.get_config", return_value=cfg), patch(
            "sync_training.refresh_access_token", return_value={"access_token": "token"}
        ), patch("sync_training.fetch_activities", return_value=[]), patch(
            "sync_training.normalize_activity"
        ), patch("sync_training.fetch_gear_display_map") as gear_map, patch(
            "sync_training.build_daily_training"
        ) as bounded_builder, patch(
            "sync_training.write_training_to_db",
            return_value={"daily_rows": [daily_row], "weekly_rows": [weekly_row], "warnings": ["warning"]},
        ):
            sync_training.main()

        gear_map.assert_not_called()
        bounded_builder.assert_not_called()
        sync_training.logger.info.assert_any_call("Daily rows built: %s", 1)
        sync_training.logger.info.assert_any_call("Weekly rows built: %s", 1)
        sync_training.logger.warning.assert_any_call("Warnings: %s", 1)


if __name__ == "__main__":
    unittest.main()
