import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DeploymentEntrypointPermissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.powershell = (ROOT / "deploy_training_etl.ps1").read_text(
            encoding="utf-8"
        )
        cls.shell = (ROOT / "deploy_to_server_from_mac.sh").read_text(
            encoding="utf-8"
        )

    def _allowlist(self, content, pattern):
        matches = re.findall(pattern, content, flags=re.DOTALL)
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_both_scripts_keep_one_explicit_operational_entrypoint_allowlist(self):
        powershell_allowlist = self._allowlist(
            self.powershell,
            r"\$OperationalEntrypoints\s*=\s*@\((.*?)\)",
        )
        shell_allowlist = self._allowlist(
            self.shell,
            r"OPERATIONAL_ENTRYPOINTS=\((.*?)\)",
        )

        expected_entries = (
            "check_system_health.py",
            "backup_postgres.sh",
            "backup_test_latest_postgres.sh",
        )
        for entry in expected_entries:
            with self.subTest(entry=entry):
                self.assertEqual(powershell_allowlist.count(entry), 1)
                self.assertEqual(shell_allowlist.count(entry), 1)

        self.assertEqual(powershell_allowlist.count("$WeeklyHealthReportPath"), 1)
        self.assertEqual(shell_allowlist.count("$WEEKLY_HEALTH_REPORT"), 1)
        self.assertEqual(
            self.powershell.count(
                '$WeeklyHealthReportPath = "/opt/training/etl/weekly_health_report.py"'
            ),
            1,
        )
        self.assertEqual(
            self.shell.count(
                'WEEKLY_HEALTH_REPORT="$SERVER_ETL_DIR/weekly_health_report.py"'
            ),
            1,
        )

    def test_both_scripts_normalize_and_chmod_only_allowlisted_entrypoints(self):
        self.assertIn(
            r"sed -i 's/\r$//' __REMOTE_ENTRYPOINTS__",
            self.powershell,
        )
        self.assertIn("chmod 755 __REMOTE_ENTRYPOINTS__", self.powershell)
        self.assertIn(
            r"sed -i 's/\\r\$//' $REMOTE_OPERATIONAL_ENTRYPOINTS",
            self.shell,
        )
        self.assertIn(
            "chmod 755 $REMOTE_OPERATIONAL_ENTRYPOINTS",
            self.shell,
        )
        self.assertNotRegex(self.powershell, r"chmod\s+755[^\r\n]*\*\.py")
        self.assertNotRegex(self.shell, r"chmod\s+755[^\r\n]*\*\.py")

    def test_both_scripts_assert_file_mode_and_exact_shebang_before_cleanup(self):
        powershell_checks = (
            "if ! test -f '__WEEKLY_REPORT__'; then",
            "if ! test -x '__WEEKLY_REPORT__'; then",
            """if [ "$(head -n 1 '__WEEKLY_REPORT__')" != '#!/usr/bin/env python3' ]; then""",
        )
        shell_checks = (
            "if ! test -f '$WEEKLY_HEALTH_REPORT'; then",
            "if ! test -x '$WEEKLY_HEALTH_REPORT'; then",
            """if [ "\\$(head -n 1 '$WEEKLY_HEALTH_REPORT')" != '#!/usr/bin/env python3' ]; then""",
        )
        for check in powershell_checks:
            self.assertIn(check, self.powershell)
        for check in shell_checks:
            self.assertIn(check, self.shell)

        self.assertIn("set -e", self.powershell)
        self.assertIn("set -euo pipefail", self.shell)
        self.assertLess(
            self.powershell.index("if ! test -f '__WEEKLY_REPORT__'; then"),
            self.powershell.rindex("rm -rf '__REMOTE_STAGE__'"),
        )
        self.assertLess(
            self.shell.index("if ! test -f '$WEEKLY_HEALTH_REPORT'; then"),
            self.shell.rindex("rm -rf '$REMOTE_STAGE'"),
        )

    def test_dry_runs_exit_before_upload_or_ssh(self):
        powershell_dry_run_start = self.powershell.index("    if ($DryRun) {")
        powershell_upload = self.powershell.index("    Write-Host \"Uploading archive...\"")
        powershell_dry_run = self.powershell[powershell_dry_run_start:powershell_upload]
        self.assertIn("tar.exe -tzf $LocalArchive", powershell_dry_run)
        self.assertIn("exit 0", powershell_dry_run)
        self.assertNotIn("scp.exe", powershell_dry_run)
        self.assertNotIn("ssh.exe", powershell_dry_run)

        shell_dry_run_start = self.shell.index('if [ "$DRY_RUN" = true ]; then')
        shell_connection = self.shell.index(
            'echo "Checking HarrisServer connection and deployment directories..."'
        )
        shell_dry_run = self.shell[shell_dry_run_start:shell_connection]
        self.assertIn('tar -tzf "$LOCAL_ARCHIVE"', shell_dry_run)
        self.assertIn("exit 0", shell_dry_run)
        self.assertNotIn("scp ", shell_dry_run)
        self.assertNotIn("ssh ", shell_dry_run)


if __name__ == "__main__":
    unittest.main()
