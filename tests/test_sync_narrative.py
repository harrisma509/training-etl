import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import sync_training
from db_writer import fetch_recent_narrative_refresh_ids


class Connection:
    def __init__(self):
        self.committed = False
        self.cursor_value = Mock()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        class CursorContext:
            def __enter__(_,):
                return self.cursor_value

            def __exit__(_, *args):
                return False

        return CursorContext()

    def commit(self):
        self.committed = True


class SyncNarrativeTests(unittest.TestCase):
    def test_new_activity_ids_are_text_compatible_and_deduplicated(self):
        rows = [{"id": 2}, {"id": "1"}, {"id": 2}, {"id": "3"}]
        self.assertEqual(
            sync_training.identify_new_activity_ids(rows, {"1"}),
            ["2", "3"],
        )

    def test_no_new_activity_ids_means_no_detail_work(self):
        rows = [{"id": "1"}, {"id": "1"}]
        self.assertEqual(sync_training.identify_new_activity_ids(rows, {1}), [])

    def test_recent_refresh_selector_uses_local_two_day_window_and_cutoff(self):
        cursor = Mock()
        cursor.fetchall.return_value = [{"activity_id": "9"}, {"activity_id": "8"}]
        connection = Connection()
        connection.cursor_value = cursor
        observed_at = datetime(2026, 9, 25, 0, 30, tzinfo=timezone.utc)

        with patch("db_writer.connect_db", return_value=connection):
            result = fetch_recent_narrative_refresh_ids(
                {"DB_HOST": "test"}, observed_at, excluded_ids=[7]
            )

        self.assertEqual(result, ["9", "8"])
        sql, params = cursor.execute.call_args.args
        self.assertIn("date_local BETWEEN %s AND %s", sql)
        self.assertIn("narrative_observed_at <= %s", sql)
        self.assertIn("ORDER BY date_local DESC, activity_id DESC", sql)
        self.assertIn("LIMIT %s", sql)
        self.assertEqual(str(params[0]), "2026-09-23")
        self.assertEqual(str(params[1]), "2026-09-24")
        self.assertEqual(params[2], observed_at - timedelta(hours=1.5))
        self.assertEqual(params[3], ["7"])
        self.assertEqual(params[4], 10)

    def test_narrative_enrichment_accepts_one_run_timestamp(self):
        connection = Connection()
        run_timestamp = "run timestamp"
        with patch.object(
            sync_training,
            "fetch_activity_detail",
            return_value={"description": "synthetic"},
        ), patch.object(sync_training, "connect_db", return_value=connection), patch.object(
            sync_training, "upsert_activity_narrative", return_value=True
        ) as writer:
            sync_training.enrich_new_activity_narratives(
                {"DB_HOST": "test"}, "token", ["1"], observed_at=run_timestamp
            )

        self.assertEqual(writer.call_args.kwargs["observed_at"], run_timestamp)

    def test_each_new_activity_is_enriched_once_and_failures_are_isolated(self):
        connections = [Connection(), Connection()]
        details = [
            {"description": "synthetic", "private_note": None},
            RuntimeError("detail unavailable"),
            {"description": "later"},
        ]

        def fetch_detail(*_):
            value = details.pop(0)
            if isinstance(value, Exception):
                raise value
            return value

        with patch.object(sync_training, "fetch_activity_detail", side_effect=fetch_detail) as fetch, patch.object(
            sync_training, "connect_db", side_effect=connections
        ), patch.object(sync_training, "upsert_activity_narrative", return_value=True) as writer:
            result = sync_training.enrich_new_activity_narratives(
                {"DB_HOST": "test"}, "token", ["1", "2", "3"]
            )

        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(writer.call_count, 2)
        self.assertEqual(result["detail_requests_attempted"], 3)
        self.assertEqual(result["narrative_inspections_succeeded"], 2)
        self.assertEqual(result["narrative_inspections_failed"], 1)
        self.assertTrue(all(connection.committed for connection in connections))

    def test_malformed_detail_is_failed_without_opening_database(self):
        with patch.object(
            sync_training, "fetch_activity_detail", return_value={"description": 42}
        ), patch.object(sync_training, "connect_db") as connect, patch.object(
            sync_training, "upsert_activity_narrative"
        ) as writer:
            result = sync_training.enrich_new_activity_narratives(
                {"DB_HOST": "test"}, "token", ["1"]
            )

        connect.assert_not_called()
        writer.assert_not_called()
        self.assertEqual(result["narrative_inspections_succeeded"], 0)
        self.assertEqual(result["narrative_inspections_failed"], 1)


if __name__ == "__main__":
    unittest.main()