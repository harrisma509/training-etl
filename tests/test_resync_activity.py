import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

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


if __name__ == "__main__":
    unittest.main()
