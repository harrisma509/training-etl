import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import strava_narrative_backfill as backfill
from strava_client import StravaNetworkError, StravaRequestError


def args(**overrides):
    values = {
        "start_date": date(2012, 1, 1),
        "end_date": date(2026, 9, 23),
        "batch_size": 100,
        "daily_headroom": 400,
        "max_requests": None,
        "activity_id": [],
        "refresh_observed": False,
        "max_retries": 2,
        "retry_base_seconds": 0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.sql = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=()):
        self.sql = sql
        self.params = params

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.cursor_obj = FakeCursor(rows)
        self.commits = 0
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


class BackfillSelectionTests(unittest.TestCase):
    def test_selection_is_newest_first_and_excludes_completed_rows(self):
        rows = [
            {"activity_id": "2", "date_local": date(2026, 1, 2), "description_observed": False, "private_note_observed": True},
            {"activity_id": "1", "date_local": date(2026, 1, 1), "description_observed": True, "private_note_observed": True},
        ]
        conn = FakeConnection(rows)
        selected = backfill.fetch_population_rows(conn, args(), limit=100)
        self.assertEqual([row["activity_id"] for row in selected], ["2", "1"])
        self.assertIn("narrative_observed_at IS NULL", conn.cursor_obj.sql)
        self.assertIn("ORDER BY date_local DESC, activity_id DESC", conn.cursor_obj.sql)

    def test_refresh_observed_removes_checkpoint_predicate(self):
        conn = FakeConnection([])
        backfill.fetch_population_rows(conn, args(refresh_observed=True), limit=100)
        self.assertNotIn("narrative_observed_at IS NULL", conn.cursor_obj.sql)

    def test_preview_has_no_api_calls_or_writes_and_is_json(self):
        scope_rows = [
            {"activity_id": "2", "date_local": date(2026, 1, 2), "description_observed": False, "private_note_observed": False, "narrative_observed_at": None},
            {"activity_id": "1", "date_local": date(2026, 1, 1), "description_observed": True, "private_note_observed": False, "narrative_observed_at": "observed"},
        ]
        conn = FakeConnection(scope_rows)
        output = io.StringIO()
        cli_args = args()
        with patch.object(backfill, "get_db_config", return_value={}), patch.object(
            backfill, "connect_db", return_value=conn
        ), patch.object(backfill, "fetch_activity_detail_with_metadata") as fetch, redirect_stdout(output):
            with patch.object(backfill, "build_parser") as parser:
                parser.return_value.parse_args.return_value = SimpleNamespace(
                    preview=True, apply=False, start_date="2012-01-01", end_date="2026-09-23",
                    batch_size=100, daily_headroom=400, max_requests=None, activity_id=[],
                    refresh_observed=False, max_retries=2, retry_base_seconds=0,
                )
                self.assertEqual(backfill.main([]), 0)
        fetch.assert_not_called()
        record = json.loads(output.getvalue())
        self.assertEqual(record["total_local_in_scope"], 2)
        self.assertEqual(record["eligible_count"], 1)
        self.assertEqual(record["estimated_maximum_calls"], 1)
        self.assertNotIn("name", record)

    def test_population_checkpoint_is_timestamp_not_field_flags(self):
        rows = [
            {"activity_id": "1", "date_local": date(2026, 1, 1), "description_observed": True, "private_note_observed": False, "narrative_observed_at": "observed"},
            {"activity_id": "2", "date_local": date(2026, 1, 2), "description_observed": True, "private_note_observed": True, "narrative_observed_at": None},
        ]
        summary = backfill.population_summary(rows, args())
        self.assertEqual(summary["eligible_count"], 1)
        self.assertEqual(summary["completed_count"], 1)
        self.assertEqual(summary["private_note_unobserved_count"], 1)


class RateBudgetTests(unittest.TestCase):
    def test_read_specific_headers_are_preferred(self):
        budget = backfill.RateBudget(400, sleep_fn=lambda _: None)
        budget.update({
            "overall": {"limit": [400, 4000], "usage": [1, 3999]},
            "read": {"limit": [200, 2000], "usage": [1, 1500]},
        })
        self.assertEqual(budget.safe_read()["limit"], [200, 2000])
        budget.before_request()
        self.assertEqual(budget.requests, 1)

    def test_daily_headroom_and_request_ceiling_stop_before_request(self):
        budget = backfill.RateBudget(400, max_requests=2, sleep_fn=lambda _: None)
        budget.update({"read": {"limit": [200, 2000], "usage": [2, 1600]}})
        with self.assertRaises(backfill.QuotaStop) as context:
            budget.before_request()
        self.assertEqual(context.exception.reason, "daily_headroom_reached")

        budget = backfill.RateBudget(400, max_requests=1, sleep_fn=lambda _: None)
        budget.before_request()
        with self.assertRaises(backfill.QuotaStop) as context:
            budget.before_request()
        self.assertEqual(context.exception.reason, "max_requests_reached")


class RetryTests(unittest.TestCase):
    def test_429_stops_without_retry(self):
        budget = backfill.RateBudget(400, sleep_fn=lambda _: None)
        request = Mock(side_effect=StravaRequestError(429, {"read": {"limit": [200, 2000], "usage": [1, 1600]}}))
        with patch.object(backfill, "fetch_activity_detail_with_metadata", request):
            with self.assertRaises(backfill.QuotaStop) as context:
                backfill.fetch_with_retries("1", {"cfg": {}, "token": "token"}, budget, args(), False)
        self.assertEqual(context.exception.reason, "rate_limited")
        request.assert_called_once()

    def test_transient_5xx_retries_and_then_succeeds(self):
        budget = backfill.RateBudget(400, sleep_fn=lambda _: None)
        request = Mock(side_effect=[StravaRequestError(503), ({"description": None}, {})])
        with patch.object(backfill, "fetch_activity_detail_with_metadata", request), patch(
            "strava_narrative_backfill.time.sleep"
        ):
            detail, retries, _, _ = backfill.fetch_with_retries(
                "1", {"cfg": {}, "token": "token"}, budget, args(), False
            )
        self.assertEqual(detail, {"description": None})
        self.assertEqual(retries, 1)
        self.assertEqual(request.call_count, 2)

    def test_network_retry_exhaustion_preserves_typed_error(self):
        budget = backfill.RateBudget(400, sleep_fn=lambda _: None)
        request = Mock(side_effect=StravaNetworkError("network"))
        with patch.object(backfill, "fetch_activity_detail_with_metadata", request):
            with self.assertRaises(StravaNetworkError):
                backfill.fetch_with_retries(
                    "1", {"cfg": {}, "token": "token"}, budget,
                    args(max_retries=2), False
                )
        self.assertEqual(request.call_count, 3)

    def test_http_retry_exhaustion_preserves_status_and_request_count(self):
        budget = backfill.RateBudget(400, sleep_fn=lambda _: None)
        request = Mock(side_effect=StravaRequestError(503))
        with patch.object(backfill, "fetch_activity_detail_with_metadata", request):
            with self.assertRaises(StravaRequestError) as context:
                backfill.fetch_with_retries(
                    "1", {"cfg": {}, "token": "token"}, budget,
                    args(max_retries=2), False
                )
        self.assertEqual(context.exception.status_code, 503)
        self.assertEqual(request.call_count, 3)

    def test_quota_boundary_is_not_successful(self):
        result = backfill.result_template("1", 1)
        result.update({"request_outcome": "stopped"})
        summary = backfill.summarize(
            [result], {"eligible_count": 2, "fully_observed_count": 0},
            args(), backfill.RateBudget(400), "max_requests_reached",
            selected_count=2,
        )
        self.assertEqual(summary["attempted_count"], 0)
        self.assertEqual(summary["successful_count"], 0)
        self.assertEqual(summary["failed_count"], 0)
        self.assertEqual(summary["quota_stopped_count"], 1)
        self.assertEqual(summary["unprocessed_count"], 1)
        self.assertEqual(summary["overall_status"], "quota_stopped")

    def test_rate_limited_response_counts_as_attempted_but_not_failed(self):
        result = backfill.result_template("1", 1)
        result.update({"request_outcome": "stopped", "failure_class": "rate_limited"})
        summary = backfill.summarize(
            [result], {"eligible_count": 1, "fully_observed_count": 0},
            args(), backfill.RateBudget(400), "rate_limited", selected_count=1,
        )
        self.assertEqual(summary["attempted_count"], 1)
        self.assertEqual(summary["successful_count"], 0)
        self.assertEqual(summary["failed_count"], 0)


class LockTests(unittest.TestCase):
    def test_lock_failure_prevents_work(self):
        class LockCursor(FakeCursor):
            def fetchone(self):
                return {"locked": False}

        conn = FakeConnection([])
        conn.cursor_obj = LockCursor([])
        with patch.object(backfill, "connect_db", return_value=conn):
            with self.assertRaises(backfill.BackfillLockUnavailable):
                backfill.acquire_backfill_lock({})
        self.assertTrue(conn.closed)


if __name__ == "__main__":
    unittest.main()