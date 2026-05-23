import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "source_radar", *args],
        cwd=".",
        text=True,
        capture_output=True,
        check=False,
    )


class CliTests(unittest.TestCase):
    def test_cli_help_lists_verify_command(self):
        result = run_cli("--help")

        self.assertEqual(result.returncode, 0)
        self.assertIn("verify", result.stdout)

    def test_verify_outputs_json_report(self):
        result = run_cli("verify", "source-radar 是本地 CLI")

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "evidence-found")
        self.assertEqual(payload["evidence"][0]["id"], "ev-001")

    def test_verify_outputs_markdown_report(self):
        result = run_cli(
            "verify", "source-radar 是本地 CLI", "--format", "markdown"
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("# Verification Report", result.stdout)
        self.assertIn("ev-001", result.stdout)

    def test_verify_can_collect_local_web_page(self):
        with tempfile.TemporaryDirectory() as directory:
            page = pathlib.Path(directory) / "page.html"
            page.write_text(
                "<html><head><title>Local Page</title></head>"
                "<body><p>Local evidence from a normal web page.</p></body></html>",
                encoding="utf-8",
            )

            result = run_cli(
                "verify",
                "local page",
                "--source",
                "web",
                "--url",
                page.as_uri(),
            )

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "evidence-found")
        self.assertEqual(payload["evidence"][0]["source_type"], "web-page")
        self.assertEqual(payload["evidence"][0]["adapter"], "web")

    def test_verify_can_collect_local_official_page(self):
        with tempfile.TemporaryDirectory() as directory:
            page = pathlib.Path(directory) / "official.html"
            page.write_text(
                "<html><head><title>Official Notice</title></head>"
                "<body><p>Official evidence from an announcement page.</p></body></html>",
                encoding="utf-8",
            )

            result = run_cli(
                "verify",
                "official notice",
                "--source",
                "official",
                "--url",
                page.as_uri(),
            )

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "evidence-found")
        self.assertEqual(payload["evidence"][0]["source_type"], "official-announcement")
        self.assertEqual(payload["evidence"][0]["adapter"], "official")

    def test_probe_outputs_adapter_status(self):
        with tempfile.TemporaryDirectory() as directory:
            page = pathlib.Path(directory) / "page.html"
            page.write_text(
                "<html><head><title>Probe Page</title></head>"
                "<body><p>Probe evidence content.</p></body></html>",
                encoding="utf-8",
            )

            result = run_cli(
                "probe",
                "--source",
                "web",
                "--url",
                page.as_uri(),
            )

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["adapter"], "web")
        self.assertEqual(payload["status"], "ok")

    def test_health_outputs_platform_status_report(self):
        result = run_cli("health")

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["summary"]["total"], "4")
        self.assertEqual([probe["adapter"] for probe in payload["probes"]], [
            "fixture",
            "web",
            "official",
            "github",
        ])

    def test_probe_outputs_markdown_status(self):
        result = run_cli("probe", "--source", "web", "--format", "markdown")

        self.assertEqual(result.returncode, 0)
        self.assertIn("# Adapter Probe", result.stdout)
        self.assertIn("needs-input", result.stdout)

    def test_health_outputs_markdown_status_report(self):
        result = run_cli("health", "--format", "markdown")

        self.assertEqual(result.returncode, 0)
        self.assertIn("# Platform Health", result.stdout)
        self.assertIn("fixture", result.stdout)

    def test_integrations_outputs_license_audit(self):
        result = run_cli("integrations", "audit")

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "restricted")
        self.assertEqual(payload["summary"]["restricted"], "2")

    def test_integrations_outputs_markdown_audit(self):
        result = run_cli("integrations", "audit", "--format", "markdown")

        self.assertEqual(result.returncode, 0)
        self.assertIn("# Integration License Audit", result.stdout)
        self.assertIn("mediacrawler", result.stdout)

    def test_integrations_outputs_optional_bridge_status(self):
        result = run_cli("integrations", "status")

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "disabled")
        self.assertEqual(payload["summary"]["disabled"], "2")


if __name__ == "__main__":
    unittest.main()
