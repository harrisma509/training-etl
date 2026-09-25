import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import resync_activity
from resync_activity import compute_rebuild_plan, week_start_for_date


class ResyncActivityTests(unittest.TestCase):
    def test_week_start_for_date_uses_monday_week_boundary(self):
        self.assertEqual(week_start_for_date("2024-04-03"), "2024-04-01")
        self.assertEqual(week_start_for_date("2024-04-08"), "2024-04-08")

    def test_compute_rebuild_plan_handles_same_week_and_cross_week_changes(self):
        self.assertEqual(
            compute_rebuild_plan("2024-04-03", "2024-04-03"),
            {"dates": ["2024-04-03"], "week_starts": ["2024-04-01"]},
        )

        self.assertEqual(
            compute_rebuild_plan("2024-04-03", "2024-04-09"),
            {
                "dates": ["2024-04-03", "2024-04-09"],
                "week_starts": ["2024-04-01", "2024-04-08"],
            },
        )

    def test_detail_row_reuses_one_payload_for_normalization(self):
        detail = {"id": 123, "description": "synthetic"}
        with patch.object(resync_activity, "fetch_activity_detail", return_value=detail) as fetch, patch.object(
            resync_activity, "normalize_activity", return_value={"id": "123"}
        ) as normalize:
            payload, row = resync_activity.fetch_activity_detail_row("token", "123")

        fetch.assert_called_once_with("token", "123")
        normalize.assert_called_once_with(detail)
        self.assertIs(payload, detail)
        self.assertEqual(row, {"id": "123"})

    def test_narrative_only_resync_does_not_rebuild_aggregates(self):
        class CursorContext:
            def __init__(self, cursor):
                self.cursor = cursor

            def __enter__(self):
                return self.cursor

            def __exit__(self, *_):
                return False

        class Connection:
            def __init__(self, cursor):
                self.cursor_value = cursor
                self.committed = False

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def cursor(self):
                return CursorContext(self.cursor_value)

            def commit(self):
                self.committed = True

            def rollback(self):
                pass

        cursor = Mock()
        cursor.fetchone.return_value = {
            "activity_id": "123",
            "date_local": "2024-04-03",
            "name": "Same",
            "sport_type": "Walk",
            "activity_category": "walk",
            "moving_sec": 100,
            "elapsed_sec": 100,
            "distance_mi": 1.0,
            "elevation_ft": 10.0,
            "has_heartrate": False,
            "average_hr": None,
            "max_hr": None,
            "gear_id": None,
            "bike_name": None,
        }
        connection = Connection(cursor)
        detail = {"id": 123, "description": "synthetic"}
        refreshed = dict(cursor.fetchone.return_value)
        refreshed.pop("bike_name")

        with patch.object(resync_activity, "refresh_access_token", return_value={"access_token": "token"}), patch.object(
            resync_activity, "fetch_activity_detail", return_value=detail
        ) as fetch, patch.object(resync_activity, "normalize_activity", return_value=refreshed), patch.object(
            resync_activity.psycopg, "connect", return_value=connection
        ), patch.object(resync_activity, "upsert_strava_activities") as structured, patch.object(
            resync_activity, "upsert_activity_narrative", return_value=True
        ) as narrative, patch.object(resync_activity, "fetch_gear_display_map", return_value={}):
            result = resync_activity.resync_activity(
                {"DB_HOST": "test", "DB_PORT": 5432, "DB_NAME": "test", "DB_USER": "test", "DB_PASSWORD": "test"},
                "123",
            )

        fetch.assert_called_once_with("token", 123)
        structured.assert_called_once_with(cursor, [refreshed])
        narrative.assert_called_once()
        self.assertFalse(result["daily_rebuilt"])
        self.assertFalse(result["weekly_rebuilt"])
        self.assertTrue(connection.committed)


if __name__ == "__main__":
    unittest.main()
