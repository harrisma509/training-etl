import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from strava_client import fetch_activities


class StravaFetchBoundaryTests(unittest.TestCase):
    def test_days_back_is_rolling_utc_window_that_can_bisect_local_date(self):
        fixed_now = datetime(2024, 4, 8, 6, 30, tzinfo=timezone.utc)
        requests = []

        def fake_http_json(method, url, headers=None, data=None):
            requests.append((method, url))
            return []

        with patch("strava_client.datetime") as clock, patch(
            "strava_client.http_json", side_effect=fake_http_json
        ):
            clock.now.return_value = fixed_now
            fetch_activities("token", 7)

        query = parse_qs(urlparse(requests[0][1]).query)
        self.assertEqual(int(query["after"][0]), int((fixed_now.timestamp() - 7 * 86400)))
        self.assertEqual(int(query["before"][0]), int(fixed_now.timestamp() + 86400))
        self.assertEqual(
            datetime.fromtimestamp(int(query["after"][0]), timezone.utc),
            datetime(2024, 4, 1, 6, 30, tzinfo=timezone.utc),
        )


if __name__ == "__main__":
    unittest.main()
