import io
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

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

    def collect(self, output=NO_UPGRADES, returncode=0):
        with (
            patch.object(report.os, "uname", return_value=self.kernel, create=True),
            patch.object(report, "require_command", return_value="/usr/bin/apt-get") as required,
            patch.object(
                report,
                "run_command",
                return_value=CompletedProcess(
                    args=["/usr/bin/apt-get", "-s", "upgrade"],
                    returncode=returncode,
                    stdout=output,
                    stderr="",
                ),
            ) as run,
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
                "Reboot required: No",
            ],
        )
        required.assert_called_once_with("apt-get")
        run.assert_called_once_with(
            ["/usr/bin/apt-get", "-s", "upgrade"],
            timeout=report.APT_UPGRADE_TIMEOUT_SECONDS,
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
        with (
            patch.object(
                report.os,
                "uname",
                side_effect=OSError("not available"),
                create=True,
            ),
            patch.object(report, "require_command", return_value="/usr/bin/apt-get"),
            patch.object(
                report,
                "run_command",
                return_value=CompletedProcess([], 0, NO_UPGRADES, ""),
            ),
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
                summary="HarrisNAS backup mount is available (nfs, nas)",
            ),
        ]

    def run_main(
        self,
        maintenance,
        dry_run=True,
        health_results=None,
        active_incidents=None,
    ):
        sections = {
            "postgresql": report.SummarySection("PostgreSQL", ["Online"]),
            "sync": report.SummarySection("Synchronization", ["No issues"]),
            "freshness": report.SummarySection("Health-data freshness", ["Fresh"]),
            "backup": report.SummarySection("Backups and recovery", ["Present"]),
        }
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
                    "Reboot required: No",
                ],
            ),
            False,
            True,
        )
        exit_code, body, send_alert = self.run_main(maintenance)
        self.assertEqual(exit_code, 0)
        self.assertIn("Overall: HEALTHY", body)
        runner_check = "✅ PASS: Container training-runner is running"
        os_check = "✅ PASS: OS maintenance is current"
        backup_check = "✅ PASS: HarrisNAS backup mount is available (nfs, nas)"
        self.assertLess(body.index(runner_check), body.index(os_check))
        self.assertLess(body.index(os_check), body.index(backup_check))
        self.assertEqual(body.count("\nOS maintenance\n"), 1)
        self.assertIn("- OS release: Ubuntu 24.04.3 LTS", body)
        detailed_section = body.index("\nOS maintenance\n")
        self.assertLess(body.index("Platform health"), detailed_section)
        self.assertLess(detailed_section, body.index("\nPostgreSQL\n"))
        send_alert.assert_not_called()

    def test_security_plus_reboot_produce_one_attention_section_and_subject(self):
        maintenance = report.OSMaintenanceResult(
            report.SummarySection(
                "OS maintenance",
                [
                    "OS release: Ubuntu 24.04.3 LTS",
                    "Running kernel: 6.8.0-86-generic",
                    "Upgradeable packages: 2",
                    "Security updates: 1",
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
            report.SummarySection("OS maintenance", ["Security updates: 0"]),
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
