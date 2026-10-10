import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from compute_weekly_audit import weekly_rows_for_audit
from weekly_audit_rules import compute_load_item
from weekly_audit_scoring import build_weekly_audit


class WeeklyAuditCurrentEmptyWeekTests(unittest.TestCase):
    def test_open_zero_load_week_is_audited_with_existing_rules(self):
        as_of = date(2026, 10, 10)
        weekly_rows = {
            date(2026, 9, 28): {"total_load": 0},
            date(2026, 10, 5): {"total_load": 0},
        }

        self.assertEqual(
            weekly_rows_for_audit(weekly_rows, as_of),
            weekly_rows,
        )
        item = compute_load_item(weekly_rows[date(2026, 10, 5)])
        audit = build_weekly_audit(date(2026, 10, 5), [item], datetime.now(timezone.utc))
        self.assertEqual(item["status"], "🟨 Yellow")
        self.assertEqual(audit["yellow_count"], 1)
        self.assertEqual(audit["red_count"], 0)
        self.assertEqual(audit["overall_grade"], "R")
        self.assertNotIn("NaN", str(audit))
        self.assertNotIn("Infinity", str(audit))

    def test_open_week_with_activity_and_prior_weeks_remain_auditable(self):
        as_of = date(2026, 10, 10)
        weekly_rows = {
            date(2026, 10, 5): {"total_load": 12},
            date(2026, 9, 28): {"total_load": 0},
        }

        self.assertEqual(
            weekly_rows_for_audit(weekly_rows, as_of),
            weekly_rows,
        )

    def test_aware_as_of_datetime_does_not_exclude_any_persisted_week(self):
        weekly_rows = {
            date(2026, 10, 5): {"total_load": 0},
            date(2026, 10, 12): {"total_load": 0},
        }
        as_of = datetime(2026, 10, 12, 5, 59, tzinfo=timezone.utc)

        self.assertEqual(
            weekly_rows_for_audit(weekly_rows, as_of),
            weekly_rows,
        )


if __name__ == "__main__":
    unittest.main()
