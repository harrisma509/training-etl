import contextlib
import io
import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import strava_structured_data_backfill as backfill
from activity_utils import normalize_activity
from db_writer import update_structured_activity_data


class FakeConnection:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.commits = 0
        self.closed = False
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        self.connection.executed.append((sql, params))

    def fetchone(self):
        return {"locked": True}

    def fetchall(self):
        return list(self.connection.rows)


class StructuredBackfillTests(unittest.TestCase):
    def setUp(self):
        self.args = backfill.validate_args(
            backfill.build_parser().parse_args(
                ["--apply", "--start-date", "2024-01-01", "--end-date", "2024-01-31"]
            )
        )
        self.db_cfg = {"DB_HOST": "test"}
        self.strava_cfg = {"STRAVA_CLIENT_ID": "id"}
        self.scope_rows = [
            {"activity_id": "1", "date_local": date(2024, 1, 10), "summary_observed_at": None},
            {"activity_id": "2", "date_local": date(2024, 1, 11), "summary_observed_at": datetime.now(timezone.utc)},
        ]

    def test_preview_is_local_only_and_reports_coverage_and_estimate(self):
        db_conn = FakeConnection()
        with patch.object(backfill, "get_db_config", return_value=self.db_cfg), patch.object(
            backfill, "connect_db", return_value=db_conn
        ), patch.object(backfill, "fetch_scope_rows", return_value=self.scope_rows), patch.object(
            backfill, "refresh_access_token"
        ) as refresh, patch.object(backfill, "fetch_activity_page_with_metadata") as fetch:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = backfill.main([
                    "--preview",
                    "--start-date", "2024-01-01",
                    "--end-date", "2024-01-31",
                ])

        self.assertEqual(result, 0)
        payload = __import__("json").loads(output.getvalue())
        self.assertEqual(payload["local_rows_in_scope"], 2)
        self.assertEqual(payload["local_rows_observed_before"], 1)
        self.assertEqual(payload["local_rows_unobserved_before"], 1)
        self.assertEqual(payload["local_date_min"], "2024-01-10")
        self.assertEqual(payload["local_date_max"], "2024-01-11")
        self.assertEqual(payload["estimated_provider_pages"], 1)
        refresh.assert_not_called()
        fetch.assert_not_called()

    def test_lock_contention_exits_before_refresh_or_provider_call(self):
        with patch.object(backfill, "acquire_backfill_lock", side_effect=backfill.BackfillLockUnavailable), patch.object(
            backfill, "refresh_access_token"
        ) as refresh, patch.object(backfill, "fetch_activity_page_with_metadata") as fetch:
            with self.assertRaises(backfill.BackfillLockUnavailable):
                backfill.apply_backfill(self.args, self.strava_cfg, self.db_cfg)
        refresh.assert_not_called()
        fetch.assert_not_called()

    def test_apply_acquires_lock_before_refresh_and_provider_call(self):
        events = []
        lock = Mock()
        scope_rows = self.scope_rows

        def acquire(_cfg):
            events.append("lock")
            return lock

        def refresh(_cfg):
            events.append("refresh")
            return {"access_token": "token"}

        def fetcher(*_args, **kwargs):
            events.append(("fetch", kwargs["before"], kwargs["after"], kwargs["page"]))
            return [], {"read": {"limit": [200, 2000], "usage": [1, 2]}}

        with patch.object(backfill, "acquire_backfill_lock", side_effect=acquire), patch.object(
            backfill, "release_backfill_lock"
        ) as release, patch.object(backfill, "refresh_access_token", side_effect=refresh), patch.object(
            backfill, "connect_db", return_value=FakeConnection()
        ), patch.object(backfill, "fetch_scope_rows", return_value=scope_rows), patch.object(
            backfill, "persist_page", return_value=0
        ):
            summary, pages = backfill.apply_backfill(
                self.args,
                self.strava_cfg,
                self.db_cfg,
                now_fn=lambda: datetime(2024, 2, 1, 12, tzinfo=timezone.utc),
                page_fetcher=fetcher,
            )

        self.assertEqual(events[0], "lock")
        self.assertEqual(events[1], "refresh")
        self.assertEqual(events[2][0], "fetch")
        release.assert_called_once_with(lock)
        self.assertEqual(summary["stopped_reason"], "empty_page")
        self.assertEqual(pages[0]["provider_row_count"], 0)

    def test_one_page_pilot_uses_exactly_one_request_and_stable_bounds(self):
        args = backfill.validate_args(
            backfill.build_parser().parse_args(["--apply", "--max-pages", "1"])
        )
        calls = []
        lock = Mock()

        def fetcher(*_args, **kwargs):
            calls.append(kwargs)
            return [{"id": "1"}], {}

        with patch.object(backfill, "acquire_backfill_lock", return_value=lock), patch.object(
            backfill, "release_backfill_lock"
        ), patch.object(backfill, "refresh_access_token", return_value={"access_token": "token"}), patch.object(
            backfill, "connect_db", return_value=FakeConnection()
        ), patch.object(backfill, "fetch_scope_rows", return_value=self.scope_rows), patch.object(
            backfill, "persist_page", return_value=1
        ):
            summary, pages = backfill.apply_backfill(
                args,
                self.strava_cfg,
                self.db_cfg,
                now_fn=lambda: datetime(2026, 9, 30, 12, tzinfo=timezone.utc),
                page_fetcher=fetcher,
            )

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["page"], 1)
        self.assertEqual(calls[0]["after"], backfill.epoch_at_start(date(2012, 1, 1)))
        self.assertEqual(calls[0]["before"], int(datetime(2026, 9, 30, 12, tzinfo=timezone.utc).timestamp()))
        self.assertEqual(summary["pages_requested"], 1)
        self.assertEqual(pages[0]["persisted_count"], 1)

    def test_full_pagination_keeps_fixed_before_and_stops_on_short_page(self):
        pages = [[{"id": str(index)} for index in range(1, 201)], [{"id": "201"}]]
        calls = []

        def fetcher(*_args, **kwargs):
            calls.append(kwargs.copy())
            return pages.pop(0), {}

        local_rows = [
            {"activity_id": str(index), "date_local": date(2024, 1, 1), "summary_observed_at": None}
            for index in range(1, 202)
        ]
        with patch.object(backfill, "acquire_backfill_lock", return_value=Mock()), patch.object(
            backfill, "release_backfill_lock"
        ), patch.object(backfill, "refresh_access_token", return_value={"access_token": "token"}), patch.object(
            backfill, "connect_db", return_value=FakeConnection()
        ), patch.object(backfill, "fetch_scope_rows", return_value=local_rows), patch.object(
            backfill, "persist_page", side_effect=lambda _cfg, rows: len(rows)
        ):
            summary, _ = backfill.apply_backfill(
                self.args,
                self.strava_cfg,
                self.db_cfg,
                now_fn=lambda: datetime(2024, 2, 1, tzinfo=timezone.utc),
                page_fetcher=fetcher,
            )

        self.assertEqual(len(calls), 2)
        self.assertEqual({call["before"] for call in calls}, {calls[0]["before"]})
        self.assertEqual({call["after"] for call in calls}, {calls[0]["after"]})
        self.assertEqual(summary["pages_completed"], 2)
        self.assertEqual(summary["stopped_reason"], "short_page")
        self.assertEqual(summary["matched_local_rows"], 201)

    def test_empty_page_stops_and_provider_only_rows_are_counted(self):
        calls = []

        def fetcher(*_args, **kwargs):
            calls.append(kwargs["page"])
            return [{"id": "999", "name": "must not appear"}], {}

        with patch.object(backfill, "acquire_backfill_lock", return_value=Mock()), patch.object(
            backfill, "release_backfill_lock"
        ), patch.object(backfill, "refresh_access_token", return_value={"access_token": "token"}), patch.object(
            backfill, "connect_db", return_value=FakeConnection()
        ), patch.object(backfill, "fetch_scope_rows", return_value=self.scope_rows), patch.object(
            backfill, "persist_page", return_value=0
        ):
            summary, pages = backfill.apply_backfill(
                self.args, self.strava_cfg, self.db_cfg, page_fetcher=fetcher
            )

        self.assertEqual(calls, [1])
        self.assertEqual(pages[0]["provider_only_count"], 1)
        self.assertEqual(summary["provider_only_rows"], 1)
        self.assertEqual(summary["local_only_rows"], 2)
        self.assertEqual(summary["local_rows_in_scope"], 2)

    def test_matching_normalizes_integral_float_and_skips_malformed_without_persisting_it(self):
        provider_rows = [
            {"id": "1", "utc_offset": -21600.0},
            {"id": "2", "utc_offset": 1.5},
        ]
        normalized_rows = []

        def persist(_cfg, rows):
            normalized_rows.extend(rows)
            return len(rows)

        with patch.object(backfill, "acquire_backfill_lock", return_value=Mock()), patch.object(
            backfill, "release_backfill_lock"
        ), patch.object(backfill, "refresh_access_token", return_value={"access_token": "token"}), patch.object(
            backfill, "connect_db", return_value=FakeConnection()
        ), patch.object(
            backfill, "fetch_scope_rows", return_value=self.scope_rows
        ), patch.object(backfill, "persist_page", side_effect=persist):
            summary, pages = backfill.apply_backfill(
                self.args,
                self.strava_cfg,
                self.db_cfg,
                page_fetcher=lambda *_args, **_kwargs: (provider_rows, {}),
            )

        self.assertEqual(summary["normalization_failures"], 1)
        self.assertEqual(pages[0]["normalized_count"], 1)
        self.assertEqual(pages[0]["persisted_count"], 1)
        self.assertEqual(normalized_rows[0]["utc_offset_seconds"], -21600)
        self.assertTrue(normalized_rows[0]["_summary_activity_observed"])

    def test_page_database_failure_stops_before_next_provider_request(self):
        calls = []
        pages = [[{"id": "1"} for _ in range(200)], [{"id": "2"}]]

        def fetcher(*_args, **kwargs):
            calls.append(kwargs["page"])
            return pages.pop(0), {}

        local_rows = [
            {"activity_id": "1", "date_local": date(2024, 1, 1), "summary_observed_at": None}
        ]
        with patch.object(backfill, "acquire_backfill_lock", return_value=Mock()), patch.object(
            backfill, "release_backfill_lock"
        ), patch.object(backfill, "refresh_access_token", return_value={"access_token": "token"}), patch.object(
            backfill, "connect_db", return_value=FakeConnection()
        ), patch.object(backfill, "fetch_scope_rows", return_value=local_rows), patch.object(
            backfill, "persist_page", side_effect=RuntimeError("database failed")
        ):
            summary, pages_result = backfill.apply_backfill(
                self.args, self.strava_cfg, self.db_cfg, page_fetcher=fetcher
            )

        self.assertEqual(calls, [1])
        self.assertEqual(summary["stopped_reason"], "persistence_failed")
        self.assertEqual(pages_result[0]["persistence_failure_count"], 200)

    def test_persistence_uses_one_bounded_transaction_and_structured_only_writer(self):
        connection = FakeConnection()
        row = normalize_activity({"id": "1", "utc_offset": -21600.0}, summary_observed=True)
        with patch.object(backfill, "connect_db", return_value=connection), patch.object(
            backfill, "update_structured_activity_data", return_value=1
        ) as writer:
            self.assertEqual(backfill.persist_page(self.db_cfg, [row]), 1)
        writer.assert_called_once_with(connection.cursor().__enter__() if False else unittest.mock.ANY, [row])
        self.assertEqual(connection.commits, 1)

    def test_structured_writer_excludes_core_narrative_and_raw_payload_fields(self):
        cursor = Mock()
        cursor.rowcount = 1
        row = normalize_activity({"id": "1", "utc_offset": -21600.0}, summary_observed=True)
        self.assertEqual(update_structured_activity_data(cursor, [row]), 1)
        sql, params = cursor.execute.call_args.args
        self.assertIn("summary_observed_at", sql)
        self.assertIn("utc_offset_seconds", sql)
        for excluded in ("\n            name =", "description", "private_note", "raw_json", "daily_training"):
            self.assertNotIn(excluded, sql)
        self.assertNotIn("raw_json", params)

    def test_429_stops_immediately_and_prefers_read_rate_headers(self):
        error = backfill.StravaRequestError(429, {"read": {"limit": [200, 2000], "usage": [10, 20]}})
        with patch.object(backfill, "acquire_backfill_lock", return_value=Mock()), patch.object(
            backfill, "release_backfill_lock"
        ), patch.object(backfill, "refresh_access_token", return_value={"access_token": "token"}), patch.object(
            backfill, "connect_db", return_value=FakeConnection()
        ), patch.object(backfill, "fetch_scope_rows", return_value=self.scope_rows), patch.object(
            backfill, "persist_page"
        ), patch.object(backfill, "fetch_activity_page_with_metadata", side_effect=error):
            summary, pages = backfill.apply_backfill(self.args, self.strava_cfg, self.db_cfg)
        self.assertEqual(summary["stopped_reason"], "rate_limited")
        self.assertEqual(pages[0]["failure_class"], "rate_limited")
        self.assertEqual(pages[0]["rate_limits"]["limit"], [200, 2000])

    def test_apply_output_is_sanitized_and_excludes_narrative_and_payload_fields(self):
        args = ["--apply", "--max-pages", "1"]
        with patch.object(backfill, "get_db_config", return_value=self.db_cfg), patch.object(
            backfill, "get_config", return_value=self.strava_cfg
        ), patch.object(backfill, "connect_db", return_value=FakeConnection()), patch.object(
            backfill, "fetch_scope_rows", return_value=self.scope_rows
        ), patch.object(backfill, "acquire_backfill_lock", return_value=Mock()), patch.object(
            backfill, "release_backfill_lock"
        ), patch.object(backfill, "refresh_access_token", return_value={"access_token": "token"}), patch.object(
            backfill,
            "fetch_activity_page_with_metadata",
            return_value=([{"id": "1", "name": "hidden", "description": "hidden"}], {}),
        ), patch.object(backfill, "persist_page", return_value=1):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(backfill.main(args), 0)
        text = output.getvalue()
        self.assertNotIn("hidden", text)
        self.assertNotIn("description", text)
        self.assertNotIn("raw_json", text)
        self.assertNotIn("token", text)


if __name__ == "__main__":
    unittest.main()
