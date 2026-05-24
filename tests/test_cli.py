import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from source_radar.cli import main, run_verify


def run_cli(*args):
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        "app"
        if not existing_pythonpath
        else f"app{os.pathsep}{existing_pythonpath}"
    )
    return subprocess.run(
        [sys.executable, "-m", "source_radar", *args],
        cwd=".",
        env=env,
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
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}, clear=True):
                result = run_cli("verify", "source-radar 是本地 CLI")

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "evidence-found")
        self.assertEqual(payload["evidence"][0]["id"], "ev-001")
        self.assertEqual(payload["agent"]["mode"], "agent")
        self.assertEqual(payload["agent"]["planned_tools"], ["fixture"])
        self.assertEqual(payload["agent"]["ai_status"], "not-configured")
        self.assertIn("source-radar config setup", payload["judgement"]["gaps"][0])

    def test_verify_outputs_markdown_report(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}, clear=True):
                result = run_cli(
                    "verify", "source-radar 是本地 CLI", "--format", "markdown"
                )

        self.assertEqual(result.returncode, 0)
        self.assertIn("# Verification Report", result.stdout)
        self.assertIn("## Agent", result.stdout)
        self.assertIn("ev-001", result.stdout)
        self.assertIn("source-radar config setup", result.stdout)

    def test_config_set_show_and_clear_openai(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}, clear=True):
                set_result = run_cli(
                    "config",
                    "set-openai",
                    "--api-key",
                    "local-key",
                    "--endpoint",
                    "http://127.0.0.1:8000/",
                    "--model",
                    "test-model",
                )
                show_result = run_cli("config", "show")
                clear_result = run_cli("config", "clear-openai")
                show_after_clear = run_cli("config", "show")

        self.assertEqual(set_result.returncode, 0)
        self.assertEqual(clear_result.returncode, 0)
        payload = json.loads(show_result.stdout)
        self.assertEqual(payload["openai"]["configured"], True)
        self.assertEqual(payload["openai"]["api_key"], "loc...key")
        self.assertEqual(payload["openai"]["endpoint"], "http://127.0.0.1:8000/")
        self.assertEqual(payload["openai"]["model"], "test-model")
        self.assertNotIn("local-key", show_result.stdout)
        self.assertEqual(json.loads(show_after_clear.stdout)["openai"]["configured"], False)

    def test_config_set_show_and_clear_provider_bridge(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}, clear=True):
                set_result = run_cli(
                    "config",
                    "set-provider",
                    "--name",
                    "firecrawl",
                    "--endpoint",
                    "http://127.0.0.1:3002",
                )
                show_result = run_cli("config", "show")
                clear_result = run_cli("config", "clear-provider", "--name", "firecrawl")
                show_after_clear = run_cli("config", "show")

        self.assertEqual(set_result.returncode, 0)
        self.assertEqual(clear_result.returncode, 0)
        payload = json.loads(show_result.stdout)
        self.assertEqual(payload["providers"]["firecrawl"]["enabled"], True)
        self.assertEqual(
            payload["providers"]["firecrawl"]["endpoint"],
            "http://127.0.0.1:3002",
        )
        self.assertNotIn("firecrawl", json.loads(show_after_clear.stdout)["providers"])

    def test_config_setup_prompts_for_openai_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            buffer = io.StringIO()
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}, clear=True):
                with patch("builtins.input", side_effect=["http://127.0.0.1:8000/", "test-model"]):
                    with patch("source_radar.cli.getpass", return_value="local-key"):
                        with contextlib.redirect_stdout(buffer):
                            exit_code = main(["config", "setup"])
                show_result = run_cli("config", "show")

        self.assertEqual(exit_code, 0)
        self.assertIn("saved", buffer.getvalue())
        payload = json.loads(show_result.stdout)
        self.assertEqual(payload["openai"]["configured"], True)
        self.assertEqual(payload["openai"]["api_key"], "loc...key")

    def test_verify_can_collect_local_web_page(self):
        with tempfile.TemporaryDirectory() as directory:
            page = pathlib.Path(directory) / "page.html"
            page.write_text(
                "<html><head><title>Local Page</title></head>"
                "<body><p>Local evidence from a normal web page.</p></body></html>",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}, clear=True):
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

    def test_run_verify_default_uses_agent_auto_planning(self):
        with tempfile.TemporaryDirectory() as directory:
            page = pathlib.Path(directory) / "page.html"
            page.write_text(
                "<html><head><title>Auto Page</title></head>"
                "<body><p>Auto-planned web evidence.</p></body></html>",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}, clear=True):
                output = run_verify("auto local page", "json", url=page.as_uri())

        payload = json.loads(output)
        self.assertEqual(payload["agent"]["planned_tools"], ["web"])
        self.assertEqual(payload["evidence"][0]["adapter"], "web")

    def test_verify_can_collect_local_official_page(self):
        with tempfile.TemporaryDirectory() as directory:
            page = pathlib.Path(directory) / "official.html"
            page.write_text(
                "<html><head><title>Official Notice</title></head>"
                "<body><p>Official evidence from an announcement page.</p></body></html>",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}, clear=True):
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
        self.assertEqual(payload["summary"]["total"], "7")
        self.assertEqual([probe["adapter"] for probe in payload["probes"]], [
            "fixture",
            "web",
            "official",
            "github",
            "search",
            "firecrawl",
            "mediacrawler",
        ])

    def test_probe_outputs_markdown_status(self):
        result = run_cli("probe", "--source", "web", "--format", "markdown")

        self.assertEqual(result.returncode, 0)
        self.assertIn("# Adapter Probe", result.stdout)
        self.assertIn("needs-input", result.stdout)

    def test_probe_outputs_external_bridge_status(self):
        result = run_cli("probe", "--source", "firecrawl")

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["adapter"], "firecrawl")
        self.assertEqual(payload["status"], "disabled")
        self.assertEqual(payload["details"]["provider_type"], "external-bridge")

    def test_health_outputs_markdown_status_report(self):
        result = run_cli("health", "--format", "markdown")

        self.assertEqual(result.returncode, 0)
        self.assertIn("# Platform Health", result.stdout)
        self.assertIn("fixture", result.stdout)
        self.assertIn("firecrawl", result.stdout)

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

    def test_cli_replaces_unencodable_output_characters(self):
        with tempfile.TemporaryDirectory() as directory:
            page = pathlib.Path(directory) / "page.html"
            page.write_text(
                "<html><head><title>Encoding</title></head>"
                "<body><p>Replacement character: \ufffd</p></body></html>",
                encoding="utf-8",
            )
            buffer = io.BytesIO()
            stdout = io.TextIOWrapper(buffer, encoding="gbk", errors="strict")

            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "verify",
                        "encoding",
                        "--source",
                        "web",
                        "--url",
                        page.as_uri(),
                    ]
                )

        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
