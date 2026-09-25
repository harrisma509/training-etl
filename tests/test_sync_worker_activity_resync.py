import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

os.environ.setdefault("ENV_FILE", str(ROOT / "config" / "strava.env.example"))
spec = importlib.util.spec_from_file_location("sync_worker_under_test", SRC / "sync_worker.py")
sync_worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_worker)


class SyncWorkerActivityResyncTests(unittest.TestCase):
    def test_activity_request_dispatches_targeted_resync(self):
        pending = {
            "id": 11,
            "days_back": 1,
            "request_type": "activity_resync",
            "activity_id": 123,
        }
        conn = type("Conn", (), {})()
        conn.committed = False
        conn.close = lambda: None

        with patch.object(sync_worker, "acquire_lock", return_value=True), patch.object(
            sync_worker, "get_pending_request", return_value=pending
        ), patch.object(sync_worker, "run_activity_resync", return_value={"status": "success", "activity_id": 123}) as resync, patch.object(
            sync_worker, "mark_request_running"
        ), patch.object(sync_worker, "mark_request_completed") as completed, patch.object(
            sync_worker, "release_lock"
        ), patch.object(sync_worker, "db_conn", return_value=conn):
            sync_worker.process_once()

        resync.assert_called_once_with(123)
        completed.assert_called_once_with(conn, 11, {"status": "success", "activity_id": 123})


if __name__ == "__main__":
    unittest.main()