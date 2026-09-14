import os
import sys
import types
import unittest
from unittest.mock import patch

os.environ["ENV_FILE"] = "/tmp/training-etl-test-no-config"
os.environ["STRAVA_CLIENT_ID"] = "test-client"
os.environ["STRAVA_CLIENT_SECRET"] = "test-secret"
os.environ["STRAVA_REFRESH_TOKEN"] = "test-refresh"
os.environ["TRAINING_API_TOKEN"] = "test-token"


if "fastapi" not in sys.modules:
    fake_fastapi = types.ModuleType("fastapi")

    class FakeFastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda function: function

        post = get

    fake_fastapi.FastAPI = FakeFastAPI
    fake_fastapi.Query = lambda default=None, **kwargs: default
    fake_fastapi.Request = object
    fake_responses = types.ModuleType("fastapi.responses")

    class FakeJSONResponse:
        def __init__(self, content, status_code=200):
            import json

            self.content = content
            self.status_code = status_code
            self.body = json.dumps(content, separators=(",", ":")).encode("utf-8")

    fake_responses.JSONResponse = FakeJSONResponse
    sys.modules["fastapi"] = fake_fastapi
    sys.modules["fastapi.responses"] = fake_responses

from internal_api import _validated_weekly_rows, coach_context_endpoint


class QueryParams:
    def __init__(self, values=None):
        self.values = values or {}

    def getlist(self, name):
        value = self.values.get(name, [])
        return value if isinstance(value, list) else [value]


class Request:
    def __init__(self, values=None, token="test-token"):
        self.query_params = QueryParams(values)
        self.headers = {"X-Internal-Token": token}


class CoachContextApiWeeklyRowsTests(unittest.TestCase):
    def test_omitted_weekly_rows_uses_compatibility_default(self):
        self.assertEqual(_validated_weekly_rows(Request(), None), 26)

    def test_valid_weekly_rows_are_accepted(self):
        for value in (4, 26, 52, 104):
            self.assertEqual(_validated_weekly_rows(Request({"weekly_rows": [str(value)]}), value), value)

    def test_invalid_weekly_rows_are_rejected_before_context_build(self):
        for value in (3, 105, "", "not-an-integer", "26.0", True, 26.0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _validated_weekly_rows(Request({"weekly_rows": [str(value)]}), value)

        with self.assertRaises(ValueError):
            _validated_weekly_rows(Request({"weekly_rows": ["26", "52"]}), 26)

    def test_endpoint_passes_validated_weekly_rows_to_context_builder(self):
        with patch("internal_api.get_db_config", return_value={"test": True}), \
             patch("internal_api.build_coach_context", return_value={"ok": True}) as build:
            result = coach_context_endpoint(Request({"weekly_rows": ["52"]}), daily_days=28, weekly_rows=52)

        self.assertEqual(result, {"ok": True})
        build.assert_called_once_with({"test": True}, 28, 52)

    def test_endpoint_rejects_invalid_weekly_rows_without_context_build(self):
        with patch("internal_api.get_db_config") as get_db_config, \
             patch("internal_api.build_coach_context") as build:
            result = coach_context_endpoint(Request({"weekly_rows": ["105"]}), daily_days=28, weekly_rows=105)

        self.assertEqual(result.status_code, 400)
        self.assertEqual(result.body, b'{"status":"error","error":"Invalid weekly_rows"}')
        get_db_config.assert_not_called()
        build.assert_not_called()


if __name__ == "__main__":
    unittest.main()
