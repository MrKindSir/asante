import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.codex.checks import (
    TEST_CHECK_CATEGORIES,
    Runner,
    append_config,
    credentials,
    python_environment_error,
    service_checks,
    tool_run,
)
from scripts.codex.settings import read_values, safe_identifier, safe_limit


class CodexExecutionTests(unittest.TestCase):
    def test_python_scripts_require_the_project_conda_environment_outside_ci(self):
        self.assertIsNone(python_environment_error((3, 12, 0), "/Users/example/.conda/envs/asante-codex", False))
        self.assertIsNone(python_environment_error((3, 12, 0), "/runner/python", True))
        self.assertIn("asante-codex", python_environment_error((3, 9, 6), "/usr/bin", False))
        self.assertIn("conda activate", python_environment_error((3, 13, 5), "/opt/anaconda3", False))

    def test_environment_reader_is_literal_and_allowlisted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("KEEP='literal $value'\nIGNORE=private\n")
            self.assertEqual(read_values(path, {"KEEP"}), {"KEEP": "literal $value"})
            path.write_text("KEEP=$(do-not-execute)\n")
            with self.assertRaises(ValueError):
                read_values(path, {"KEEP"})

    def test_reader_credentials_reuse_existing_keys_and_preserve_application_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            application = root / ".env"
            application.write_text("EXISTING_KEY=keep-this\n")
            with patch("scripts.codex.checks.ROOT", root), patch(
                "scripts.codex.checks.app_values",
                return_value={"ASANTE_POSTGRES_DB": "asante", "ASANTE_MINIO_BUCKETS": "asante-media"},
            ):
                first, existed = credentials()
                self.assertFalse(existed)
                second, existed = credentials()
                self.assertTrue(existed)
                self.assertEqual(first, second)
                self.assertEqual(application.read_text(), "EXISTING_KEY=keep-this\n")
                self.assertFalse((root / ".env.codex").stat().st_mode & 0o077)

    def test_codex_configuration_append_preserves_and_backs_up_existing_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "config.toml"
            original = '# retain comments\n[unrelated]\nenabled = true\n'
            path.write_text(original)
            backup = root / "backup" / "config.toml"
            append_config(path, '[mcp_servers.test]\ncommand = "python3"', backup)
            self.assertTrue(path.read_text().startswith(original.rstrip()))
            self.assertEqual(backup.read_text(), original)

    def test_service_checks_never_recreate_running_api_or_use_shell(self):
        for service in ("api", "asante", "dashboard"):
            for command in service_checks(service):
                self.assertIn("run", command)
                self.assertIn("--no-deps", command)
                self.assertNotIn("up", command)
                self.assertNotIn("sh", command)
                self.assertNotIn("shell=True", command)
        with self.assertRaises(ValueError):
            service_checks("postgres; arbitrary shell")

    def test_api_checks_run_isolated_migration_integration_suite(self):
        checks = service_checks("api")
        self.assertEqual(len(checks), 2)
        self.assertIn("tests.integration.test_database_migrations", checks[1])
        self.assertEqual(TEST_CHECK_CATEGORIES["api-check-2"], ("integration",))

    def test_server_launcher_is_a_fixed_noninteractive_profile(self):
        command = tool_run()
        self.assertIn("codex", command)
        self.assertIn("codex-mcp", command)
        self.assertIn("-T", command)
        self.assertNotIn("--build", command)

    def test_metadata_input_bounds_reject_unsafe_values(self):
        self.assertEqual(safe_identifier("spatial_ref_sys"), "spatial_ref_sys")
        for value in ("public.secret", "table; DROP TABLE x", "", "x" * 64):
            with self.assertRaises(ValueError):
                safe_identifier(value)
        for value in (0, 26, True):
            with self.assertRaises(ValueError):
                safe_limit(value)
        self.assertEqual(safe_limit(25), 25)

    def test_report_redaction_does_not_change_nonsecret_identity(self):
        runner = Runner.__new__(Runner)
        runner.sensitive = ["example-secret"]
        self.assertEqual(
            runner.redact("codex_asante_reader example-secret"),
            "codex_asante_reader [REDACTED]",
        )

    def test_reports_are_saved_by_test_category_below_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = Runner.__new__(Runner)
            runner.results = [
                {"check": "repository-contracts", "exitCode": 0},
                {"check": "live-http-and-services", "exitCode": 0},
            ]
            with patch("scripts.codex.checks.ROOT", root):
                execution = runner.report(True, "all")

            self.assertEqual(execution.parent, root / "logs" / "codex")
            self.assertEqual(
                {path.parent.name for path in (root / "logs" / "tests").glob("*/*.json")},
                {"unit", "functional", "integration", "e2e"},
            )
            self.assertFalse(list((root / "logs").glob("*.json")))


if __name__ == "__main__":
    unittest.main()
