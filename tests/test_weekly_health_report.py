import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
from types import ModuleType, SimpleNamespace
from unittest.mock import call, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _stub_module(name, **attributes):
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


with patch.dict(
    sys.modules,
    {
        "alert_manager": _stub_module("alert_manager", AlertManager=object),
        "check_system_health": _stub_module(
            "check_system_health",
            collect_checks=lambda *args, **kwargs: [],
        ),
        "send_alert": _stub_module(
            "send_alert",
            send_alert=lambda *args, **kwargs: None,
        ),
    },
):
    import weekly_health_report as report


NO_UPGRADES = """\
Reading package lists...
Building dependency tree...
Reading state information...
0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.
"""

ORDINARY_UPGRADES = """\
Inst curl [8.5.0-2ubuntu10.2] (8.5.0-2ubuntu10.3 Ubuntu:24.04/noble-updates [amd64])
Inst libc6 [2.39-0ubuntu8.4] (2.39-0ubuntu8.5 Ubuntu:24.04/noble-updates [amd64])
2 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.
"""

MIXED_UPGRADES = """\
Inst curl [8.5.0-2ubuntu10.2] (8.5.0-2ubuntu10.3 Ubuntu:24.04/noble-updates [amd64])
Inst openssl [3.0.13-0ubuntu3.4] (3.0.13-0ubuntu3.5 Ubuntu:24.04/noble-security [amd64]) []
2 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.
"""

LIVE_UBUNTU_26_04_OUTPUT = """\
2 upgraded, 0 newly installed, 0 to remove and 2 not upgraded.
Inst ubuntu-pro-client-l10n [37.2ubuntu0.1] (38ubuntu0~26.04 Ubuntu:26.04/resolute-updates [amd64]) []
Inst ubuntu-pro-client [37.2ubuntu0.1] (38ubuntu0~26.04 Ubuntu:26.04/resolute-updates [amd64])
Conf ubuntu-pro-client-l10n (38ubuntu0~26.04 Ubuntu:26.04/resolute-updates [amd64]) []
Conf ubuntu-pro-client (38ubuntu0~26.04 Ubuntu:26.04/resolute-updates [amd64])
"""

FWUPD_NO_UPDATES = '{"Devices":[]}'
FWUPD_DBX_UPDATES = json.dumps(
    {
        "Devices": [
            {
                "DeviceId": "UEFI-dbX-target",
                "Flags": ["needs-reboot"],
                "Releases": [
                    {"Version": "2024", "Urgency": "low"},
                    {"Version": "2025", "Urgency": "high"},
                    {"Version": "2026", "Urgency": "medium"},
                ],
            }
        ]
    }
)


class StubHttpResponse:
    def __init__(self, status, body):
        self.status = status
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self.body


def json_http_response(payload, status=200):
    return StubHttpResponse(status, json.dumps(payload).encode("utf-8"))


def http_error(status, payload=None):
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    return HTTPError(
        "http://127.0.0.1/health-probe",
        status,
        "synthetic response",
        None,
        io.BytesIO(body),
    )


def normalized_forecast(freshness="fresh"):
    return {
        "location_id": 1,
        "display_name": "Synthetic Saved Location",
        "timezone_name": "Etc/UTC",
        "generated_at": "2026-01-01T12:00:00Z",
        "available_start_date": "2026-01-01",
        "available_end_date": "2026-01-02",
        "freshness": freshness,
        "daily": [
            {"date": "2026-01-01", "condition": "clear"},
            {"date": "2026-01-02", "condition": "cloudy"},
        ],
    }


class GeoapifyProbeScriptTests(unittest.TestCase):
    def run_probe(self, side_effect, *, key="synthetic-test-secret"):
        stdout = io.StringIO()
        env = {} if key is None else {"GEOAPIFY_API_KEY": key}
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(urllib.request, "urlopen") as opener,
            patch("time.sleep") as sleep,
            patch("sys.stdout", stdout),
        ):
            if isinstance(side_effect, (list, tuple, BaseException)):
                opener.side_effect = side_effect
            else:
                opener.return_value = side_effect
            exec(report.GEOAPIFY_PROBE_SCRIPT, {})
        return json.loads(stdout.getvalue()), opener, sleep, stdout.getvalue()

    def test_valid_probe_prints_only_sanitized_status(self):
        response = json_http_response(
            {
                "results": [
                    {
                        "name": "Synthetic Provider Result",
                        "formatted": "Synthetic Address",
                        "lat": 39.0,
                        "lon": -105.0,
                    }
                ]
            }
        )
        result, opener, _, output = self.run_probe(response)
        request = opener.call_args.args[0]
        query = parse_qs(urlsplit(request.full_url).query)

        self.assertEqual(result, {"status": "healthy"})
        self.assertEqual(query["text"], ["Denver Union Station"])
        self.assertEqual(query["format"], ["json"])
        self.assertEqual(query["limit"], ["1"])
        self.assertEqual(opener.call_args.kwargs["timeout"], 10)
        self.assertFalse(
            "synthetic-test-secret" in output,
            "probe output must not contain the configured key",
        )
        self.assertNotIn("Synthetic Provider Result", output)
        self.assertNotIn("Synthetic Address", output)
        self.assertNotIn("39.0", output)

    def test_missing_key_does_not_make_a_provider_request(self):
        result, opener, _, output = self.run_probe(None, key=None)
        self.assertEqual(result, {"status": "missing_key"})
        opener.assert_not_called()
        self.assertFalse(
            "synthetic-test-secret" in output,
            "probe output must not contain key values",
        )

    def test_unauthorized_responses_do_not_retry_or_expose_error_url(self):
        for status in (401, 403):
            with self.subTest(status=status):
                result, opener, sleep, output = self.run_probe(
                    http_error(status),
                )
                self.assertEqual(result, {"status": "unauthorized"})
                self.assertEqual(opener.call_count, 1)
                sleep.assert_not_called()
                self.assertFalse(
                    "synthetic-test-secret" in output,
                    "probe output must not contain key values",
                )

    def test_timeout_rate_limit_and_server_error_retry_once(self):
        scenarios = (
            (TimeoutError("synthetic timeout"), "timeout"),
            (http_error(429), "rate_limited"),
            (http_error(503), "provider_unavailable"),
        )
        for first_error, expected_status in scenarios:
            with self.subTest(expected_status=expected_status):
                result, opener, sleep, _ = self.run_probe(
                    [first_error, first_error],
                )
                self.assertEqual(result, {"status": expected_status})
                self.assertEqual(opener.call_count, 2)
                sleep.assert_called_once_with(2)

    def test_invalid_json_and_empty_results_are_sanitized(self):
        scenarios = (
            (StubHttpResponse(200, b"synthetic-complete-provider-body"), "invalid_json"),
            (json_http_response({"results": []}), "empty_results"),
        )
        for response, expected_status in scenarios:
            with self.subTest(expected_status=expected_status):
                result, _, _, output = self.run_probe(response)
                self.assertEqual(result, {"status": expected_status})
                self.assertNotIn("synthetic-complete-provider-body", output)


class LocationHealthTests(unittest.TestCase):
    def collect(self, payload, geoapify_status="healthy", *, status=200):
        with (
            patch.object(
                report,
                "urlopen",
                return_value=json_http_response(payload, status),
            ),
            patch.object(report, "_run_geoapify_probe", return_value=geoapify_status),
        ):
            return report.collect_location_health()

    def test_coordinate_free_saved_locations_and_provider_pass(self):
        result = self.collect(
            {
                "locations": [
                    {
                        "location_id": 41,
                        "display_name": "Synthetic Saved Location",
                        "timezone_name": "Etc/UTC",
                    },
                    {"location_id": 42, "display_name": "Synthetic Second Location"},
                ]
            }
        )
        rendered = "\n".join(result.section.lines)
        self.assertEqual(result.severity, "PASS")
        self.assertEqual(result.section.title, "Location and Geoapify health")
        self.assertEqual(
            result.section.lines,
            [
                "Geoapify API: Available",
                "Saved-location API: Available",
                "Saved locations: 2",
            ],
        )
        self.assertNotIn("Coordinate privacy: Passed", rendered)
        self.assertNotIn("Synthetic Saved Location", rendered)
        self.assertNotIn("Etc/UTC", rendered)

    def test_nested_coordinates_and_application_errors_fail(self):
        scenarios = (
            (
                {"locations": [{"metadata": {"Latitude": "synthetic-latitude"}}]},
                "coordinate_leak",
                "❌ FAIL: Location coordinates were exposed",
            ),
            (
                {"locations": [{"metadata": {"LONGITUDE": "synthetic-longitude"}}]},
                "coordinate_leak",
                "❌ FAIL: Location coordinates were exposed",
            ),
            (
                {"locations": [], "metadata": {"Error": "synthetic"}},
                "application_error_field",
                "❌ FAIL: Saved-location privacy contract failed",
            ),
            (
                {"locations": [], "metadata": {"DETAIL": "synthetic"}},
                "application_error_field",
                "❌ FAIL: Saved-location privacy contract failed",
            ),
        )
        for payload, expected_category, expected_failure in scenarios:
            with self.subTest(expected_category=expected_category, payload=payload):
                result = self.collect(payload)
                rendered = "\n".join(result.section.lines)
                self.assertEqual(result.severity, "FAIL")
                self.assertIn(
                    f"Saved-location failure category: {expected_category}",
                    rendered,
                )
                self.assertIn(expected_failure, rendered)
                self.assertNotIn("Coordinate privacy:", rendered)
                self.assertNotIn("synthetic-latitude", rendered)
                self.assertNotIn("synthetic-longitude", rendered)

    def test_saved_location_http_failures_and_invalid_shapes_fail(self):
        scenarios = (
            (http_error(503), "http_503"),
            (TimeoutError("synthetic timeout"), "timeout"),
            (json_http_response({"unexpected": []}), "invalid_response"),
        )
        for failure, expected_category in scenarios:
            with self.subTest(expected_category=expected_category):
                with (
                    patch.object(report, "urlopen") as opener,
                    patch.object(report, "_run_geoapify_probe", return_value="healthy"),
                ):
                    if isinstance(failure, BaseException):
                        opener.side_effect = failure
                    else:
                        opener.return_value = failure
                    result = report.collect_location_health()
                self.assertEqual(result.severity, "FAIL")
                self.assertIn(
                    f"Saved-location failure category: {expected_category}",
                    result.section.lines,
                )

    def test_invalid_saved_location_response_fails_without_body_output(self):
        response_body_marker = "synthetic-secret-response-body"
        with (
            patch.object(
                report,
                "urlopen",
                return_value=StubHttpResponse(200, response_body_marker.encode()),
            ),
            patch.object(report, "_run_geoapify_probe", return_value="healthy"),
        ):
            result = report.collect_location_health()
        rendered = "\n".join(result.section.lines)
        self.assertEqual(result.severity, "FAIL")
        self.assertIn("invalid_json", rendered)
        self.assertNotIn(response_body_marker, rendered)

    def test_provider_degradation_warns_when_saved_locations_remain_healthy(self):
        result = self.collect(
            {"locations": [{"location_id": 41, "display_name": "Synthetic"}]},
            geoapify_status="rate_limited",
        )
        self.assertEqual(result.severity, "WARN")
        self.assertIn("saved locations remain healthy", result.dashboard_line)
        self.assertIn("Saved-location API: Available", result.section.lines)

    def test_missing_key_and_unavailable_container_fail(self):
        for status in ("missing_key", "container_unavailable"):
            with self.subTest(status=status):
                result = self.collect({"locations": []}, geoapify_status=status)
                self.assertEqual(result.severity, "FAIL")
                self.assertIn(f"Geoapify failure category: {status}", result.section.lines)

    def test_geoapify_parent_ignores_child_stderr(self):
        saved = {"locations": []}
        command_result = CompletedProcess(
            ["docker", "exec", "training-web"],
            0,
            '{"status":"healthy"}',
            "synthetic-secret-stderr",
        )
        with (
            patch.object(report, "urlopen", return_value=json_http_response(saved)),
            patch.object(report, "run_command", return_value=command_result) as run,
        ):
            result = report.collect_location_health()
        self.assertEqual(result.severity, "PASS")
        self.assertEqual(run.call_args.args[0][:4], ["docker", "exec", "training-web", "python"])
        self.assertNotIn("synthetic-secret-stderr", "\n".join(result.section.lines))

    def test_unavailable_geoapify_container_is_a_failure(self):
        with (
            patch.object(report, "urlopen", return_value=json_http_response({"locations": []})),
            patch.object(
                report,
                "run_command",
                return_value=CompletedProcess(["docker"], 1, "", "synthetic-secret-stderr"),
            ),
        ):
            result = report.collect_location_health()
        self.assertEqual(result.severity, "FAIL")
        rendered = "\n".join(result.section.lines)
        self.assertIn("container_unavailable", rendered)
        self.assertNotIn("synthetic-secret-stderr", rendered)


class WeatherHealthTests(unittest.TestCase):
    def collect_with_payload(self, payload):
        with patch.object(
            report,
            "urlopen",
            return_value=json_http_response(payload),
        ):
            return report.collect_weather_health()

    def test_fresh_and_stale_normalized_forecasts_map_to_pass_and_warn(self):
        fresh = self.collect_with_payload(normalized_forecast("fresh"))
        stale = self.collect_with_payload(normalized_forecast("stale"))
        self.assertEqual(fresh.severity, "PASS")
        self.assertIn("Forecast freshness: Fresh", fresh.section.lines)
        self.assertIn("Forecast days available: 2", fresh.section.lines)
        self.assertNotIn(
            "Response privacy contract: Passed",
            "\n".join(fresh.section.lines),
        )
        self.assertEqual(stale.severity, "WARN")
        self.assertEqual(
            stale.dashboard_line,
            "⚠ WARN: Weather API is serving stale cached data",
        )
        self.assertNotIn(
            "Response privacy contract: Passed",
            "\n".join(stale.section.lines),
        )

    def test_two_temporary_failures_then_success_use_bounded_delays(self):
        transient = http_error(503, {"detail": report.TEMPORARY_WEATHER_ERROR})
        with (
            patch.object(
                report,
                "urlopen",
                side_effect=[
                    transient,
                    http_error(503, {"detail": report.TEMPORARY_WEATHER_ERROR}),
                    json_http_response(normalized_forecast()),
                ],
            ) as opener,
            patch.object(report.time, "sleep") as sleep,
        ):
            result = report.collect_weather_health()
        self.assertEqual(result.severity, "PASS")
        self.assertEqual(opener.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(2), call(5)])

    def test_temporary_unavailable_exhaustion_fails_after_three_attempts(self):
        transient = {"detail": report.TEMPORARY_WEATHER_ERROR}
        with (
            patch.object(
                report,
                "urlopen",
                side_effect=[http_error(503, transient) for _ in range(3)],
            ) as opener,
            patch.object(report.time, "sleep") as sleep,
        ):
            result = report.collect_weather_health()
        self.assertEqual(result.severity, "FAIL")
        self.assertIn("Failure category: temporary_unavailable", result.section.lines)
        self.assertEqual(opener.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(2), call(5)])
        self.assertNotIn(report.TEMPORARY_WEATHER_ERROR, "\n".join(result.section.lines))

    def test_timeout_rate_limit_and_server_error_use_three_attempts(self):
        scenarios = (
            (TimeoutError("synthetic timeout"), "timeout"),
            (http_error(429), "rate_limited"),
            (http_error(503), "http_503"),
        )
        for failure, expected_category in scenarios:
            with self.subTest(expected_category=expected_category):
                with (
                    patch.object(report, "urlopen", side_effect=[failure] * 3) as opener,
                    patch.object(report.time, "sleep") as sleep,
                ):
                    result = report.collect_weather_health()
                self.assertEqual(result.severity, "FAIL")
                self.assertIn(
                    f"Failure category: {expected_category}",
                    result.section.lines,
                )
                self.assertEqual(opener.call_count, 3)
                self.assertEqual(sleep.call_args_list, [call(2), call(5)])

    def test_404_and_422_fail_without_retry(self):
        for status in (404, 422):
            with self.subTest(status=status):
                with (
                    patch.object(report, "urlopen", side_effect=http_error(status)) as opener,
                    patch.object(report.time, "sleep") as sleep,
                ):
                    result = report.collect_weather_health()
                self.assertEqual(result.severity, "FAIL")
                self.assertIn(f"Failure category: http_{status}", result.section.lines)
                self.assertEqual(opener.call_count, 1)
                sleep.assert_not_called()

    def test_invalid_shapes_and_forbidden_nested_fields_fail_without_retry(self):
        empty_daily = normalized_forecast()
        empty_daily["daily"] = []
        wrong_location = normalized_forecast()
        wrong_location["location_id"] = 2
        coordinate_leak = normalized_forecast()
        coordinate_leak["daily"][0]["metadata"] = {
            "Latitude": "synthetic-latitude"
        }
        raw_provider_field = normalized_forecast()
        raw_provider_field["daily"][0]["temperature_2m_max"] = 10
        application_error = normalized_forecast()
        application_error["daily"][0]["metadata"] = {"DETAIL": "synthetic"}
        invalid_freshness = normalized_forecast()
        invalid_freshness["freshness"] = ["fresh"]
        invalid_date_range = normalized_forecast()
        invalid_date_range["available_start_date"] = 1
        scenarios = (
            (empty_daily, "empty_daily"),
            (wrong_location, "location_id_mismatch"),
            (coordinate_leak, "coordinate_leak"),
            (raw_provider_field, "raw_provider_field"),
            (application_error, "application_error_field"),
            (invalid_freshness, "invalid_response"),
            (invalid_date_range, "invalid_response"),
            ({"location_id": 1, "daily": []}, "invalid_response"),
        )
        for payload, expected_category in scenarios:
            with self.subTest(expected_category=expected_category):
                with (
                    patch.object(
                        report,
                        "urlopen",
                        return_value=json_http_response(payload),
                    ) as opener,
                    patch.object(report.time, "sleep") as sleep,
                ):
                    result = report.collect_weather_health()
                self.assertEqual(result.severity, "FAIL")
                self.assertIn(
                    f"Failure category: {expected_category}",
                    result.section.lines,
                )
                if expected_category == "coordinate_leak":
                    self.assertIn(
                        "❌ FAIL: Weather location coordinates were exposed",
                        result.section.lines,
                    )
                elif expected_category == "raw_provider_field":
                    self.assertIn(
                        "❌ FAIL: Raw weather-provider data was exposed",
                        result.section.lines,
                    )
                elif expected_category == "application_error_field":
                    self.assertIn(
                        "❌ FAIL: Weather response privacy contract failed",
                        result.section.lines,
                    )
                opener.assert_called_once()
                sleep.assert_not_called()

    def test_invalid_json_and_complete_response_body_are_not_rendered(self):
        marker = "synthetic-complete-weather-response"
        with patch.object(
            report,
            "urlopen",
            return_value=StubHttpResponse(200, marker.encode("utf-8")),
        ):
            result = report.collect_weather_health()
        rendered = "\n".join(result.section.lines)
        self.assertEqual(result.severity, "FAIL")
        self.assertIn("Failure category: invalid_json", rendered)
        self.assertNotIn(marker, rendered)

    def test_display_name_timezone_and_forecast_dates_are_not_rendered(self):
        result = self.collect_with_payload(normalized_forecast())
        rendered = "\n".join(result.section.lines)
        self.assertNotIn("Synthetic Saved Location", rendered)
        self.assertNotIn("Etc/UTC", rendered)
        self.assertNotIn("2026-01-01", rendered)
        self.assertNotIn("2026-01-02", rendered)


class AptSimulationParsingTests(unittest.TestCase):
    def test_no_upgrades_reports_zero_counts(self):
        self.assertEqual(report._parse_apt_upgrade_simulation(NO_UPGRADES), (0, 0))

    def test_ordinary_upgrades_are_counted_but_not_security_updates(self):
        self.assertEqual(
            report._parse_apt_upgrade_simulation(ORDINARY_UPGRADES),
            (2, 0),
        )

    def test_security_pocket_actions_are_counted_from_inst_lines(self):
        self.assertEqual(
            report._parse_apt_upgrade_simulation(MIXED_UPGRADES),
            (2, 1),
        )

    def test_live_ubuntu_26_04_output_counts_two_ordinary_upgrades(self):
        self.assertEqual(
            report._parse_apt_upgrade_simulation(LIVE_UBUNTU_26_04_OUTPUT),
            (2, 0),
        )

    def test_not_upgraded_phased_packages_are_not_counted(self):
        self.assertEqual(
            report._parse_apt_upgrade_simulation(LIVE_UBUNTU_26_04_OUTPUT),
            (2, 0),
        )

    def test_summary_prose_does_not_create_package_actions(self):
        output = """\
The following packages will be upgraded:
  curl openssl
0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.
"""
        self.assertEqual(report._parse_apt_upgrade_simulation(output), (0, 0))

    def test_malformed_or_inconsistent_simulation_is_unavailable(self):
        malformed = "Inst curl without an action summary\n"
        inconsistent = (
            "Inst curl [1] (2 Ubuntu:24.04/noble-updates [amd64])\n"
            "0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.\n"
        )
        self.assertEqual(
            report._parse_apt_upgrade_simulation(malformed),
            (None, None),
        )
        self.assertEqual(
            report._parse_apt_upgrade_simulation(inconsistent),
            (None, None),
        )

    def test_action_without_ubuntu_archive_metadata_has_unknown_security_status(self):
        output = """\
Inst local-package [1] (2 [amd64])
1 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.
"""
        self.assertEqual(
            report._parse_apt_upgrade_simulation(output),
            (1, None),
        )

    def test_ambiguous_ubuntu_archive_metadata_has_unknown_security_status(self):
        output = """\
Inst package [1] (2 Ubuntu:26.04/resolute-updates Ubuntu:26.04/resolute-security [amd64])
1 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.
"""
        self.assertEqual(
            report._parse_apt_upgrade_simulation(output),
            (1, None),
        )

    def test_malformed_trailing_annotation_is_unavailable(self):
        for annotation in (" [", " []]", " [] extra"):
            output = (
                "Inst package [1] "
                f"(2 Ubuntu:26.04/resolute-updates [amd64]){annotation}\n"
                "1 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.\n"
            )
            with self.subTest(annotation=annotation):
                self.assertEqual(
                    report._parse_apt_upgrade_simulation(output),
                    (None, None),
                )


class OSMaintenanceCollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.os_release_path = self.root / "os-release"
        self.reboot_path = self.root / "reboot-required"
        self.os_release_path.write_text(
            'NAME="Ubuntu"\nPRETTY_NAME="Ubuntu 24.04.3 LTS"\n',
            encoding="utf-8",
        )
        self.kernel = SimpleNamespace(release="6.8.0-86-generic")

    def tearDown(self):
        self.temp_dir.cleanup()

    def collect(
        self,
        output=NO_UPGRADES,
        returncode=0,
        firmware_output=FWUPD_NO_UPDATES,
        firmware_returncode=0,
        fwupd_command_unavailable=False,
        fwupd_timeout=False,
    ):
        def require_command(name):
            if name == "apt-get":
                return "/usr/bin/apt-get"
            if name == "fwupdmgr" and not fwupd_command_unavailable:
                return "/usr/bin/fwupdmgr"
            raise RuntimeError(f"{name} unavailable")

        def execute(command, timeout=20):
            if command[0] == "/usr/bin/apt-get":
                return CompletedProcess(command, returncode, output, "")
            if fwupd_timeout:
                raise TimeoutExpired(command, timeout)
            return CompletedProcess(
                command,
                firmware_returncode,
                firmware_output,
                "",
            )

        with (
            patch.object(report.os, "uname", return_value=self.kernel, create=True),
            patch.object(report, "require_command", side_effect=require_command) as required,
            patch.object(report, "run_command", side_effect=execute) as run,
        ):
            result = report.collect_os_maintenance_section(
                self.os_release_path,
                self.reboot_path,
            )
        return result, required, run

    def assert_lines(self, result, expected):
        self.assertEqual(result.section.title, "OS maintenance")
        self.assertEqual(result.section.lines, expected)

    def test_healthy_zero_upgrade_state_and_metadata(self):
        result, required, run = self.collect()
        self.assertFalse(result.requires_attention)
        self.assertTrue(result.status_available)
        self.assert_lines(
            result,
            [
                "OS release: Ubuntu 24.04.3 LTS",
                "Running kernel: 6.8.0-86-generic",
                "Upgradeable packages: 0",
                "Security updates: 0",
                "Firmware updates: 0",
                "Reboot required: No",
            ],
        )
        self.assertEqual(
            [call.args[0] for call in required.call_args_list],
            ["apt-get", "fwupdmgr"],
        )
        self.assertEqual(run.call_count, 2)
        run.assert_any_call(
            ["/usr/bin/apt-get", "-s", "upgrade"],
            timeout=report.APT_UPGRADE_TIMEOUT_SECONDS,
        )
        run.assert_any_call(
            ["/usr/bin/fwupdmgr", "get-updates", "--json"],
            timeout=report.FWUPDMGR_TIMEOUT_SECONDS,
        )

    def test_fwupd_multiple_releases_count_once_and_report_highest_urgency(self):
        result, _, _ = self.collect(firmware_output=FWUPD_DBX_UPDATES)
        self.assertTrue(result.requires_attention)
        self.assertTrue(result.status_available)
        self.assertEqual(
            result.section.lines[4],
            "Firmware updates: 1 (highest urgency: High; reboot after install: Yes)",
        )
        self.assertEqual(result.section.lines[5], "Reboot required: No")
        self.assertEqual(
            report._os_maintenance_dashboard_line(result),
            "⚠ ATTENTION: OS maintenance requires attention",
        )

    def test_low_urgency_fwupd_update_requires_attention(self):
        firmware_output = json.dumps(
            {
                "Devices": [
                    {
                        "DeviceId": "low-urgency-device",
                        "Releases": [{"Version": "1.0", "Urgency": "low"}],
                    }
                ]
            }
        )
        result, _, _ = self.collect(firmware_output=firmware_output)
        self.assertTrue(result.requires_attention)
        self.assertTrue(result.status_available)
        self.assertEqual(
            result.section.lines[4],
            "Firmware updates: 1 (highest urgency: Low; reboot after install: No)",
        )
        self.assertEqual(result.section.lines[5], "Reboot required: No")

    def test_fwupd_shutdown_requirement_is_reported_in_firmware_detail(self):
        firmware_output = json.dumps(
            {
                "Devices": [
                    {
                        "DeviceId": "shutdown-device",
                        "Flags": ["needs-shutdown"],
                        "Releases": [{"Version": "1.0", "Urgency": "medium"}],
                    }
                ]
            }
        )
        result, _, _ = self.collect(firmware_output=firmware_output)
        self.assertTrue(result.requires_attention)
        self.assertEqual(
            result.section.lines[4],
            "Firmware updates: 1 (highest urgency: Medium; reboot after install: No; shutdown after install: Yes)",
        )

    def test_fwupd_command_and_output_failures_are_unavailable(self):
        scenarios = [
            ("missing command", {"fwupd_command_unavailable": True}),
            ("timeout", {"fwupd_timeout": True}),
            ("nonzero exit", {"firmware_returncode": 1}),
            ("malformed JSON", {"firmware_output": "not JSON"}),
            ("missing Devices", {"firmware_output": "{}"}),
            ("invalid device", {"firmware_output": '{"Devices":[{}]}'}),
            (
                "invalid urgency",
                {
                    "firmware_output": json.dumps(
                        {
                            "Devices": [
                                {
                                    "DeviceId": "invalid-urgency",
                                    "Releases": [
                                        {"Version": "1.0", "Urgency": "urgent"}
                                    ],
                                }
                            ]
                        }
                    )
                },
            ),
            (
                "invalid flags",
                {
                    "firmware_output": json.dumps(
                        {
                            "Devices": [
                                {
                                    "DeviceId": "invalid-flags",
                                    "Flags": "needs-reboot",
                                    "Releases": [{"Version": "1.0"}],
                                }
                            ]
                        }
                    )
                },
            ),
        ]
        for name, options in scenarios:
            with self.subTest(name=name):
                result, _, _ = self.collect(**options)
                self.assertTrue(result.requires_attention)
                self.assertFalse(result.status_available)
                self.assertEqual(result.section.lines[4], "Firmware updates: Unavailable")
                self.assertEqual(
                    report._os_maintenance_dashboard_line(result),
                    "❌ FAIL: OS maintenance status could not be determined",
                )

    def test_ordinary_upgrades_remain_informational(self):
        result, _, _ = self.collect(output=ORDINARY_UPGRADES)
        self.assertFalse(result.requires_attention)
        self.assertEqual(result.section.lines[2:4], [
            "Upgradeable packages: 2",
            "Security updates: 0",
        ])

    def test_live_ordinary_updates_do_not_require_attention(self):
        result, _, _ = self.collect(output=LIVE_UBUNTU_26_04_OUTPUT)
        self.assertFalse(result.requires_attention)
        self.assertTrue(result.status_available)
        self.assertEqual(
            report._os_maintenance_dashboard_line(result),
            "✅ PASS: OS maintenance is current",
        )
        self.assertEqual(result.section.lines[2:4], [
            "Upgradeable packages: 2",
            "Security updates: 0",
        ])

    def test_security_updates_require_attention(self):
        result, _, _ = self.collect(output=MIXED_UPGRADES)
        self.assertTrue(result.requires_attention)
        self.assertTrue(result.status_available)
        self.assertEqual(
            report._os_maintenance_dashboard_line(result),
            "⚠ ATTENTION: OS maintenance requires attention",
        )
        self.assertEqual(result.section.lines[2:4], [
            "Upgradeable packages: 2",
            "Security updates: 1",
        ])

    def test_reboot_marker_requires_attention(self):
        self.reboot_path.touch()
        result, _, _ = self.collect()
        self.assertTrue(result.requires_attention)
        self.assertTrue(result.status_available)
        self.assertEqual(
            report._os_maintenance_dashboard_line(result),
            "⚠ ATTENTION: OS maintenance requires attention",
        )
        self.assertEqual(result.section.lines[-1], "Reboot required: Yes")

    def test_os_release_missing_and_malformed_are_unavailable(self):
        missing = report._read_os_release(self.root / "missing-os-release")
        self.os_release_path.write_text('PRETTY_NAME="unterminated\n', encoding="utf-8")
        malformed = report._read_os_release(self.os_release_path)
        self.assertEqual(missing, "Unavailable")
        self.assertEqual(malformed, "Unavailable")

    def test_unavailable_kernel_is_rendered_without_attention_by_itself(self):
        def require_command(name):
            return (
                "/usr/bin/apt-get"
                if name == "apt-get"
                else "/usr/bin/fwupdmgr"
            )

        def execute(command, timeout=20):
            output = NO_UPGRADES if command[0] == "/usr/bin/apt-get" else FWUPD_NO_UPDATES
            return CompletedProcess(command, 0, output, "")

        with (
            patch.object(
                report.os,
                "uname",
                side_effect=OSError("not available"),
                create=True,
            ),
            patch.object(report, "require_command", side_effect=require_command),
            patch.object(report, "run_command", side_effect=execute),
        ):
            result = report.collect_os_maintenance_section(
                self.os_release_path,
                self.reboot_path,
            )
        self.assertFalse(result.requires_attention)
        self.assertTrue(result.status_available)
        self.assertEqual(result.section.lines[1], "Running kernel: Unavailable")

    def test_apt_get_unavailable_causes_attention_and_unavailable_counts(self):
        with (
            patch.object(report.os, "uname", return_value=self.kernel, create=True),
            patch.object(
                report,
                "require_command",
                side_effect=RuntimeError("apt-get unavailable"),
            ),
        ):
            result = report.collect_os_maintenance_section(
                self.os_release_path,
                self.reboot_path,
            )
        self.assertTrue(result.requires_attention)
        self.assertFalse(result.status_available)
        self.assertEqual(
            report._os_maintenance_dashboard_line(result),
            "❌ FAIL: OS maintenance status could not be determined",
        )
        self.assertEqual(result.section.lines[2:4], [
            "Upgradeable packages: Unavailable",
            "Security updates: Unavailable",
        ])

    def test_nonzero_apt_simulation_causes_attention_and_unavailable_counts(self):
        result, _, _ = self.collect(returncode=1)
        self.assertTrue(result.requires_attention)
        self.assertFalse(result.status_available)
        self.assertEqual(result.section.lines[2:4], [
            "Upgradeable packages: Unavailable",
            "Security updates: Unavailable",
        ])

    def test_apt_simulation_timeout_causes_attention_and_unavailable_counts(self):
        with (
            patch.object(report.os, "uname", return_value=self.kernel, create=True),
            patch.object(report, "require_command", return_value="/usr/bin/apt-get"),
            patch.object(
                report,
                "run_command",
                side_effect=TimeoutExpired(["apt-get", "-s", "upgrade"], 120),
            ),
        ):
            result = report.collect_os_maintenance_section(
                self.os_release_path,
                self.reboot_path,
            )
        self.assertTrue(result.requires_attention)
        self.assertFalse(result.status_available)
        self.assertEqual(result.section.lines[2:4], [
            "Upgradeable packages: Unavailable",
            "Security updates: Unavailable",
        ])

    def test_malformed_apt_simulation_causes_attention(self):
        result, _, _ = self.collect(output="unexpected apt output\n")
        self.assertTrue(result.requires_attention)
        self.assertFalse(result.status_available)
        self.assertEqual(result.section.lines[2:4], [
            "Upgradeable packages: Unavailable",
            "Security updates: Unavailable",
        ])

    def test_unknown_security_classification_causes_attention(self):
        output = """\
Inst local-package [1] (2 [amd64])
1 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.
"""
        result, _, _ = self.collect(output=output)
        self.assertTrue(result.requires_attention)
        self.assertFalse(result.status_available)
        self.assertEqual(result.section.lines[2:4], [
            "Upgradeable packages: 1",
            "Security updates: Unavailable",
        ])

    def test_reboot_marker_filesystem_error_is_unavailable_and_attention(self):
        original_stat = Path.stat

        def stat_with_marker_error(path, *args, **kwargs):
            if path == self.reboot_path:
                raise PermissionError("cannot inspect marker")
            return original_stat(path, *args, **kwargs)

        with patch.object(Path, "stat", stat_with_marker_error):
            result, _, _ = self.collect()
        self.assertTrue(result.requires_attention)
        self.assertFalse(result.status_available)
        self.assertEqual(
            report._os_maintenance_dashboard_line(result),
            "❌ FAIL: OS maintenance status could not be determined",
        )
        self.assertEqual(result.section.lines[-1], "Reboot required: Unavailable")


class WeeklyReportIntegrationTests(unittest.TestCase):
    def platform_results(self):
        return [
            SimpleNamespace(
                key="postgres_unavailable",
                healthy=True,
                summary="PostgreSQL is accepting connections",
            ),
            SimpleNamespace(
                key="container_training_web_stopped",
                healthy=True,
                summary="Container training-web is running",
            ),
            SimpleNamespace(
                key="container_training_runner_stopped",
                healthy=True,
                summary="Container training-runner is running",
            ),
            SimpleNamespace(
                key="harrisnas_mount_missing",
                healthy=True,
                summary="HarrisNAS backup mount is available (nfs4, 192.0.2.10:/synthetic/export)",
            ),
        ]

    def run_main(
        self,
        maintenance,
        dry_run=True,
        health_results=None,
        active_incidents=None,
        location_health=None,
        weather_health=None,
    ):
        sections = {
            "postgresql": report.SummarySection("PostgreSQL", ["Online"]),
            "sync": report.SummarySection("Synchronization", ["No issues"]),
            "freshness": report.SummarySection("Health-data freshness", ["Fresh"]),
            "backup": report.SummarySection("Backups and recovery", ["Present"]),
        }
        location_health = location_health or report.ServiceHealthResult(
            "PASS",
            "✅ PASS: Location services are healthy",
            report.SummarySection("Location and Geoapify health", ["Saved locations: 2"]),
        )
        weather_health = weather_health or report.ServiceHealthResult(
            "PASS",
            "✅ PASS: Weather API is healthy",
            report.SummarySection("Weather API health", ["Forecast days available: 2"]),
        )
        argv = ["weekly_health_report.py"]
        if dry_run:
            argv.append("--dry-run")
        if health_results is None:
            health_results = self.platform_results()
        if active_incidents is None:
            active_incidents = {}
        stdout = io.StringIO()
        with (
            patch.object(report.os, "geteuid", return_value=0, create=True),
            patch.object(report, "AlertManager") as manager_class,
            patch.object(
                manager_class.return_value,
                "list_active",
                return_value=active_incidents,
            ),
            patch.object(
                report,
                "collect_checks",
                return_value=health_results,
            ),
            patch.object(
                report,
                "collect_os_maintenance_section",
                return_value=maintenance,
            ),
            patch.object(
                report,
                "collect_location_health",
                return_value=location_health,
            ),
            patch.object(
                report,
                "collect_weather_health",
                return_value=weather_health,
            ),
            patch.object(report, "collect_postgresql_section", return_value=sections["postgresql"]),
            patch.object(report, "collect_sync_section", return_value=sections["sync"]),
            patch.object(report, "collect_health_freshness_section", return_value=sections["freshness"]),
            patch.object(report, "collect_backup_section", return_value=sections["backup"]),
            patch.object(
                report.subprocess,
                "run",
                return_value=CompletedProcess(["hostname"], 0, "harrisserver\n", ""),
            ),
            patch.object(report, "send_alert") as send_alert,
            patch.object(sys, "argv", argv),
            patch("sys.stdout", stdout),
        ):
            exit_code = report.main()
        body = stdout.getvalue()
        return exit_code, body, send_alert

    def test_ordinary_upgrades_can_keep_report_healthy_and_dry_run_sends_no_email(self):
        maintenance = report.OSMaintenanceResult(
            report.SummarySection(
                "OS maintenance",
                [
                    "OS release: Ubuntu 24.04.3 LTS",
                    "Running kernel: 6.8.0-86-generic",
                    "Upgradeable packages: 2",
                    "Security updates: 0",
                    "Firmware updates: 0",
                    "Reboot required: No",
                ],
            ),
            False,
            True,
        )
        health_results = self.platform_results()
        nas_result = health_results[-1]
        original_nas_summary = nas_result.summary
        backup_result = SimpleNamespace(
            key="backup_stale",
            healthy=True,
            summary="Latest backup pg_training_20261101_020001.sql.gz is 13.7 hours old",
        )
        health_results.append(backup_result)
        original_backup_summary = backup_result.summary
        ups_result = SimpleNamespace(
            key="nut_monitor_inactive",
            healthy=True,
            severity="error",
            summary="Systemd service nut-monitor.service is active",
        )
        health_results.append(ups_result)
        original_ups_summary = ups_result.summary
        exit_code, body, send_alert = self.run_main(
            maintenance,
            health_results=health_results,
        )
        self.assertEqual(exit_code, 0)
        self.assertIn("Overall: HEALTHY", body)
        runner_check = "✅ PASS: Container training-runner is running"
        os_check = "✅ PASS: OS maintenance is current"
        backup_check = "✅ PASS: HarrisNAS backup mount is available"
        latest_backup_check = "✅ PASS: Latest backup is 13.7 hours old"
        ups_check = "✅ PASS: UPS power monitoring is active"
        location_check = "✅ PASS: Location services are healthy"
        weather_check = "✅ PASS: Weather API is healthy"
        self.assertLess(body.index(runner_check), body.index(os_check))
        self.assertLess(body.index(os_check), body.index(location_check))
        self.assertLess(body.index(location_check), body.index(weather_check))
        self.assertLess(body.index(weather_check), body.index(backup_check))
        self.assertLess(body.index(backup_check), body.index(latest_backup_check))
        self.assertLess(body.index(latest_backup_check), body.index(ups_check))
        self.assertEqual(
            original_nas_summary,
            "HarrisNAS backup mount is available (nfs4, 192.0.2.10:/synthetic/export)",
        )
        self.assertEqual(nas_result.summary, original_nas_summary)
        self.assertIn(latest_backup_check, body)
        self.assertNotIn("pg_training_20261101_020001.sql.gz", body)
        self.assertEqual(backup_result.summary, original_backup_summary)
        self.assertIn(ups_check, body)
        self.assertNotIn("Systemd service nut-monitor.service is active", body)
        self.assertEqual(ups_result.key, "nut_monitor_inactive")
        self.assertEqual(ups_result.severity, "error")
        self.assertEqual(ups_result.summary, original_ups_summary)
        self.assertNotIn("nfs4", body)
        self.assertNotIn("192.0.2.10", body)
        self.assertNotIn("/synthetic/export", body)
        self.assertEqual(body.count("\nOS maintenance\n"), 1)
        self.assertIn("- OS release: Ubuntu 24.04.3 LTS", body)
        detailed_section = body.index("\nOS maintenance\n")
        self.assertLess(body.index("Platform health"), detailed_section)
        self.assertLess(detailed_section, body.index("\nPostgreSQL\n"))
        self.assertLess(
            body.index("\nSynchronization\n"),
            body.index("\nLocation and Geoapify health\n"),
        )
        self.assertLess(
            body.index("\nLocation and Geoapify health\n"),
            body.index("\nWeather API health\n"),
        )
        self.assertLess(
            body.index("\nWeather API health\n"),
            body.index("\nHealth-data freshness\n"),
        )
        send_alert.assert_not_called()

    def test_backup_detail_section_retains_filename_and_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            backup_dir = Path(temp_dir) / "backups"
            backup_dir.mkdir()
            restore_log = Path(temp_dir) / "restore.log"
            now = report.datetime.now(report.timezone.utc).timestamp()

            for index in range(14):
                older_backup = backup_dir / f"pg_training_older_{index}.sql.gz"
                older_backup.touch()
                old_timestamp = now - (15 + index) * 3600
                os.utime(older_backup, (old_timestamp, old_timestamp))

            latest_backup = backup_dir / "pg_training_20261101_020001.sql.gz"
            latest_backup.touch()
            with latest_backup.open("wb") as backup_file:
                backup_file.truncate(1671 * 1024)
            latest_timestamp = now - 13.7 * 3600
            os.utime(latest_backup, (latest_timestamp, latest_timestamp))
            restore_log.write_text(
                "SUCCESS: Backup restored and validated.\n",
                encoding="utf-8",
            )

            section = report.collect_backup_section(backup_dir, restore_log)

        self.assertEqual(
            section.lines,
            [
                "Latest backup: pg_training_20261101_020001.sql.gz",
                "Backup age: 13.7 hours",
                "Backup size: 1671 KB",
                "Backups retained: 15",
                "Latest recorded restore validation: PASSED",
            ],
        )

    def test_missing_backup_failure_wording_remains_actionable(self):
        maintenance = report.OSMaintenanceResult(
            report.SummarySection("OS maintenance", ["Security updates: 0"]),
            False,
            True,
        )
        backup_result = SimpleNamespace(
            key="backup_stale",
            healthy=False,
            summary="No PostgreSQL backup files were found in /mnt/synthetic/backups",
        )
        health_results = self.platform_results()
        health_results.append(backup_result)

        exit_code, body, send_alert = self.run_main(
            maintenance,
            health_results=health_results,
        )

        self.assertEqual(exit_code, 0)
        self.assertIn(
            "❌ FAIL: No PostgreSQL backup files were found in /mnt/synthetic/backups",
            body,
        )
        self.assertIn("Overall: ATTENTION NEEDED", body)
        send_alert.assert_not_called()

    def test_inactive_ups_service_remains_actionable_and_requires_attention(self):
        maintenance = report.OSMaintenanceResult(
            report.SummarySection("OS maintenance", ["Security updates: 0"]),
            False,
            True,
        )
        ups_result = SimpleNamespace(
            key="nut_monitor_inactive",
            healthy=False,
            severity="error",
            summary="Systemd service nut-monitor.service is not active",
        )
        health_results = self.platform_results()
        health_results.append(ups_result)

        exit_code, body, send_alert = self.run_main(
            maintenance,
            health_results=health_results,
        )

        self.assertEqual(exit_code, 0)
        self.assertIn(
            "❌ FAIL: Systemd service nut-monitor.service is not active",
            body,
        )
        self.assertIn("Overall: ATTENTION NEEDED", body)
        self.assertEqual(ups_result.key, "nut_monitor_inactive")
        self.assertEqual(
            ups_result.summary,
            "Systemd service nut-monitor.service is not active",
        )
        send_alert.assert_not_called()

    def test_failed_nas_dashboard_wording_remains_actionable(self):
        maintenance = report.OSMaintenanceResult(
            report.SummarySection("OS maintenance", ["Security updates: 0"]),
            False,
            True,
        )
        health_results = self.platform_results()
        health_results[-1].healthy = False
        health_results[-1].summary = (
            "HarrisNAS backup directory is not backed by NFS: /mnt/synthetic"
        )
        exit_code, body, send_alert = self.run_main(
            maintenance,
            health_results=health_results,
        )
        self.assertEqual(exit_code, 0)
        self.assertIn(
            "❌ FAIL: HarrisNAS backup directory is not backed by NFS: /mnt/synthetic",
            body,
        )
        self.assertIn("Overall: ATTENTION NEEDED", body)
        send_alert.assert_not_called()

    def test_any_location_or_weather_warning_or_failure_requires_attention(self):
        healthy_location = report.ServiceHealthResult(
            "PASS",
            "✅ PASS: Location services are healthy",
            report.SummarySection("Location and Geoapify health", []),
        )
        healthy_weather = report.ServiceHealthResult(
            "PASS",
            "✅ PASS: Weather API is healthy",
            report.SummarySection("Weather API health", []),
        )
        scenarios = (
            (
                report.ServiceHealthResult(
                    "WARN",
                    "⚠ WARN: Location setup provider is unavailable; saved locations remain healthy",
                    report.SummarySection("Location and Geoapify health", []),
                ),
                healthy_weather,
            ),
            (
                healthy_location,
                report.ServiceHealthResult(
                    "WARN",
                    "⚠ WARN: Weather API is serving stale cached data",
                    report.SummarySection("Weather API health", []),
                ),
            ),
            (
                report.ServiceHealthResult(
                    "FAIL",
                    "❌ FAIL: Location service health check failed",
                    report.SummarySection("Location and Geoapify health", []),
                ),
                healthy_weather,
            ),
            (
                healthy_location,
                report.ServiceHealthResult(
                    "FAIL",
                    "❌ FAIL: Weather API health check failed",
                    report.SummarySection("Weather API health", []),
                ),
            ),
        )
        maintenance = report.OSMaintenanceResult(
            report.SummarySection("OS maintenance", ["Security updates: 0"]),
            False,
            True,
        )
        for location, weather in scenarios:
            with self.subTest(location=location.severity, weather=weather.severity):
                exit_code, _, send_alert = self.run_main(
                    maintenance,
                    dry_run=False,
                    location_health=location,
                    weather_health=weather,
                )
                self.assertEqual(exit_code, 0)
                self.assertEqual(
                    send_alert.call_args.kwargs["subject"],
                    "Harris Server Weekly Health: Attention Needed",
                )
                self.assertIn(
                    "Overall: ATTENTION NEEDED",
                    send_alert.call_args.kwargs["body"],
                )

    def test_cli_overrides_keep_the_approved_production_defaults(self):
        defaults = report.build_parser().parse_args([])
        override = report.build_parser().parse_args(
            [
                "--training-web-base-url",
                "http://127.0.0.1:9999",
                "--weather-location-id",
                "7",
            ]
        )
        self.assertEqual(defaults.training_web_base_url, "http://127.0.0.1:8088")
        self.assertEqual(defaults.weather_location_id, 1)
        self.assertEqual(override.training_web_base_url, "http://127.0.0.1:9999")
        self.assertEqual(override.weather_location_id, 7)

    def test_security_plus_reboot_produce_one_attention_section_and_subject(self):
        maintenance = report.OSMaintenanceResult(
            report.SummarySection(
                "OS maintenance",
                [
                    "OS release: Ubuntu 24.04.3 LTS",
                    "Running kernel: 6.8.0-86-generic",
                    "Upgradeable packages: 2",
                    "Security updates: 1",
                    "Firmware updates: 0",
                    "Reboot required: Yes",
                ],
            ),
            True,
            True,
        )
        exit_code, _, send_alert = self.run_main(maintenance, dry_run=False)
        self.assertEqual(exit_code, 0)
        body = send_alert.call_args.kwargs["body"]
        self.assertIn("Overall: ATTENTION NEEDED", body)
        self.assertIn(
            "⚠ ATTENTION: OS maintenance requires attention",
            body,
        )
        self.assertEqual(body.count("\nOS maintenance\n"), 1)
        self.assertEqual(
            send_alert.call_args.kwargs["subject"],
            "Harris Server Weekly Health: Attention Needed",
        )

    def test_firmware_updates_require_attention_in_the_existing_dashboard_line(self):
        maintenance = report.OSMaintenanceResult(
            report.SummarySection(
                "OS maintenance",
                [
                    "Security updates: 0",
                    "Firmware updates: 1 (highest urgency: High; reboot after install: Yes)",
                    "Reboot required: No",
                ],
            ),
            True,
            True,
        )
        exit_code, body, send_alert = self.run_main(maintenance)
        self.assertEqual(exit_code, 0)
        self.assertIn("Overall: ATTENTION NEEDED", body)
        self.assertEqual(
            body.count("⚠ ATTENTION: OS maintenance requires attention"),
            1,
        )
        self.assertEqual(
            body.count(
                "- Firmware updates: 1 (highest urgency: High; reboot after install: Yes)"
            ),
            1,
        )
        self.assertNotIn("\nFirmware\n", body)
        self.assertLess(
            body.index("✅ PASS: Container training-runner is running"),
            body.index("⚠ ATTENTION: OS maintenance requires attention"),
        )
        self.assertLess(
            body.index("⚠ ATTENTION: OS maintenance requires attention"),
            body.index("✅ PASS: HarrisNAS backup mount is available"),
        )
        send_alert.assert_not_called()

    def test_email_path_uses_exact_attention_subject(self):
        maintenance = report.OSMaintenanceResult(
            report.SummarySection("OS maintenance", ["Security updates: 1"]),
            True,
            True,
        )
        exit_code, body, send_alert = self.run_main(maintenance, dry_run=False)
        self.assertEqual(exit_code, 0)
        send_alert.assert_called_once()
        self.assertEqual(
            send_alert.call_args.kwargs["subject"],
            "Harris Server Weekly Health: Attention Needed",
        )
        self.assertIn(
            "Overall: ATTENTION NEEDED",
            send_alert.call_args.kwargs["body"],
        )

    def test_healthy_email_path_uses_exact_subject(self):
        maintenance = report.OSMaintenanceResult(
            report.SummarySection("OS maintenance", ["Security updates: 0"]),
            False,
            True,
        )
        exit_code, _, send_alert = self.run_main(maintenance, dry_run=False)
        self.assertEqual(exit_code, 0)
        send_alert.assert_called_once()
        self.assertEqual(
            send_alert.call_args.kwargs["subject"],
            "Harris Server Weekly Health: Healthy",
        )

    def test_subject_strings_are_locked(self):
        self.assertEqual(
            report.build_subject("HEALTHY"),
            "Harris Server Weekly Health: Healthy",
        )
        self.assertEqual(
            report.build_subject("ATTENTION NEEDED"),
            "Harris Server Weekly Health: Attention Needed",
        )

    def test_unavailable_os_status_renders_fail_and_keeps_overall_attention(self):
        maintenance = report.OSMaintenanceResult(
            report.SummarySection(
                "OS maintenance",
                [
                    "OS release: Ubuntu 26.04.1 LTS",
                    "Running kernel: 7.0.0-38-generic",
                    "Upgradeable packages: Unavailable",
                    "Security updates: Unavailable",
                    "Firmware updates: Unavailable",
                    "Reboot required: No",
                ],
            ),
            True,
            False,
        )
        exit_code, body, send_alert = self.run_main(maintenance)
        self.assertEqual(exit_code, 0)
        self.assertIn(
            "❌ FAIL: OS maintenance status could not be determined",
            body,
        )
        self.assertIn("Overall: ATTENTION NEEDED", body)
        self.assertIn("\nOS maintenance\n", body)
        self.assertIn("PostgreSQL", body)
        send_alert.assert_not_called()

    def test_platform_failure_and_active_incident_still_require_attention(self):
        maintenance = report.OSMaintenanceResult(
            report.SummarySection(
                "OS maintenance",
                ["Security updates: 0", "Firmware updates: 0"],
            ),
            False,
            True,
        )
        failed_results = self.platform_results()
        failed_results[0].healthy = False
        failed_results[0].summary = "PostgreSQL is unavailable"
        scenarios = [
            ("platform failure", failed_results, {}),
            ("active incident", self.platform_results(), {"incident": {"severity": "warning", "summary": "Active"}}),
        ]
        for name, health_results, active_incidents in scenarios:
            with self.subTest(name=name):
                exit_code, body, _ = self.run_main(
                    maintenance,
                    health_results=health_results,
                    active_incidents=active_incidents,
                )
                self.assertEqual(exit_code, 0)
                self.assertIn("Overall: ATTENTION NEEDED", body)
