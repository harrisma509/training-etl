import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import sync_training


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