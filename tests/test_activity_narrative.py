import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from activity_utils import (
    NARRATIVE_FIELDS,
    NARRATIVE_STATES,
    extract_activity_narrative,
    validate_activity_narrative,
)
from db_writer import upsert_activity_narrative
from strava_narrative_pilot import FAILURE_CLASSES, main, summarize, validate_activity_ids


class NarrativeExtractionTests(unittest.TestCase):
    def test_each_field_state_is_classified_without_normalizing_text(self):
        values = [None, "", " \t", "synthetic \u2603\nsecond line"]
        expected = ["null", "empty", "whitespace_only", "nonempty"]
        for value, state in zip(values, expected):
            narrative = extract_activity_narrative({"description": value})
            self.assertEqual(narrative["description"]["state"], state)
            if state == "nonempty":
                self.assertEqual(narrative["description"]["value"], value)

    def test_private_note_uses_the_same_states(self):
        for value, state in ((None, "null"), ("", "empty"), ("  ", "whitespace_only"), ("note", "nonempty")):
            self.assertEqual(
                extract_activity_narrative({"private_note": value})["private_note"]["state"],
                state,
            )

    def test_omitted_and_malformed_are_distinct(self):
        omitted = extract_activity_narrative({})
        malformed = extract_activity_narrative({"description": 42, "private_note": "valid"})
        self.assertEqual(omitted["description"]["state"], "omitted")
        self.assertEqual(malformed["description"]["state"], "malformed")
        self.assertEqual(malformed["private_note"]["state"], "nonempty")


class NarrativeValidationTests(unittest.TestCase):
    def test_state_definition_is_single_and_complete(self):
        self.assertEqual(
            NARRATIVE_STATES,
            {"omitted", "null", "empty", "whitespace_only", "nonempty", "malformed"},
        )

    def test_unknown_field_and_impossible_patch_are_rejected(self):
        narrative = extract_activity_narrative({})
        narrative["unexpected"] = narrative["description"]
        with self.assertRaises(ValueError):
            validate_activity_narrative(narrative)

        invalid = extract_activity_narrative({})
        invalid["description"] = {"state": "nonempty", "key_observed": False, "value": "x"}
        with self.assertRaises(ValueError):
            validate_activity_narrative(invalid)

    def test_invalid_patch_is_rejected_without_value_in_error(self):
        invalid = extract_activity_narrative({})
        invalid["description"] = {"state": "bad", "key_observed": True, "value": "secret"}
        with self.assertRaises(ValueError) as context:
            validate_activity_narrative(invalid)
        self.assertNotIn("secret", str(context.exception))


class NarrativeWriterTests(unittest.TestCase):
    def setUp(self):
        self.cursor = Mock()
        self.cursor.rowcount = 1

    def test_nonempty_update_is_parameterized(self):
        changed = upsert_activity_narrative(
            self.cursor,
            "123",
            extract_activity_narrative({"description": "synthetic"}),
            "observed",
        )
        self.assertTrue(changed)
        sql, params = self.cursor.execute.call_args.args
        self.assertIn("description = %(description)s", sql)
        self.assertNotIn("synthetic", sql)
        self.assertEqual(params["description"], "synthetic")
        self.assertNotIn("private_note =", sql)

    def test_omitted_fields_cause_no_update(self):
        self.assertFalse(upsert_activity_narrative(self.cursor, "123", extract_activity_narrative({}), "observed"))
        self.cursor.execute.assert_not_called()

    def test_malformed_field_aborts_without_sql(self):
        narrative = extract_activity_narrative({"description": 42, "private_note": "synthetic"})
        self.assertFalse(upsert_activity_narrative(self.cursor, "123", narrative, "observed"))
        self.cursor.execute.assert_not_called()

    def test_unknown_field_is_rejected_before_sql(self):
        narrative = extract_activity_narrative({})
        narrative["description_extra"] = narrative["description"]
        with self.assertRaises(ValueError):
            upsert_activity_narrative(self.cursor, "123", narrative, "observed")
        self.cursor.execute.assert_not_called()


class NarrativePilotTests(unittest.TestCase):
    def test_id_validation_is_deterministic(self):
        self.assertEqual(validate_activity_ids(["1", "1", "2"]), ["1", "2"])
        with self.assertRaises(ValueError):
            validate_activity_ids([])
        with self.assertRaises(ValueError):
            validate_activity_ids(["1", "2", "3", "4"])

    def test_preview_is_json_lines_and_has_no_external_calls(self):
        output = io.StringIO()
        with redirect_stdout(output), patch("strava_narrative_pilot.apply_pilot") as apply:
            self.assertEqual(main(["--activity-id", "1", "--preview"]), 0)
        apply.assert_not_called()
        lines = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[-1]["overall_status"], "preview")
        self.assertEqual(lines[-1]["attempted_count"], 0)
        self.assertNotIn("value", lines[0])

    def test_apply_malformed_detail_does_not_open_database(self):
        cfg = {"STRAVA_CLIENT_ID": "id"}
        fake_connection = Mock()
        with patch("strava_narrative_pilot.get_config", return_value=cfg), patch(
            "strava_narrative_pilot.refresh_access_token", return_value={"access_token": "token"}
        ), patch(
            "strava_narrative_pilot.fetch_activity_detail",
            return_value={"description": 42, "private_note": "synthetic"},
        ), patch("db_writer.connect_db", return_value=fake_connection) as connect:
            from strava_narrative_pilot import apply_pilot

            results = apply_pilot(["1"])

        self.assertEqual(results[0]["failure_class"], "malformed_narrative")
        connect.assert_not_called()
        self.assertEqual(results[0]["persistence_outcome"], "not_attempted")

    def test_summary_counts_are_stable(self):
        results = [
            {"failure_class": None, "persistence_outcome": "updated"},
            {"failure_class": None, "persistence_outcome": "no_observed_fields"},
            {"failure_class": "fetch_failed", "persistence_outcome": "not_attempted"},
        ]
        summary = summarize(results)
        self.assertEqual(summary["requested_count"], 3)
        self.assertEqual(summary["successful_count"], 2)
        self.assertEqual(summary["failed_count"], 1)
        self.assertEqual(summary["updated_count"], 1)
        self.assertEqual(summary["no_observed_fields_count"], 1)
        self.assertTrue(FAILURE_CLASSES)


if __name__ == "__main__":
    unittest.main()
