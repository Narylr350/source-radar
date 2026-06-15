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

from source_radar.cli import main, run_ask, run_verify


def run_cli(*args):
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        "app"
        if not existing_pythonpath
        else f"app{os.pathsep}{existing_pythonpath}"
    )
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-m", "source_radar", *args],
        cwd=".",
        env=env,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


class CliTests(unittest.TestCase):
    def test_cli_help_lists_verify_command(self):
        result = run_cli("--help")

        self.assertEqual(result.returncode, 0)
        self.assertIn("verify", result.stdout)
        self.assertIn("ask", result.stdout)
        self.assertIn("setup", result.stdout)

    def test_bridge_help_lists_selected_crawler_backends(self):
        result = run_cli("bridge", "--help")

        self.assertEqual(result.returncode, 0)
        self.assertIn("mediacrawler", result.stdout)
        self.assertIn("searxng", result.stdout)

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
        self.assertIn("# 核验报告", result.stdout)
        self.assertIn("## 可信度", result.stdout)
        self.assertIn("## 采集过程", result.stdout)
        self.assertIn("ev-001", result.stdout)
        self.assertIn("source-radar config setup", result.stdout)

    def test_ask_outputs_json_synthesis_report(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}, clear=True):
                result = run_cli("ask", "source-radar 是本地 CLI", "--format", "json")

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "analysis-ready")
        self.assertEqual(payload["agent"]["mode"], "analysis")
        self.assertEqual(payload["analysis"]["disagreements"], [])
        self.assertIn("summary", payload["analysis"])
        self.assertIn("key_points", payload["analysis"])
        self.assertNotIn("suggestion", payload["analysis"])

    def test_ask_outputs_markdown_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}, clear=True):
                result = run_cli("ask", "source-radar 是本地 CLI")

        self.assertEqual(result.returncode, 0)
        self.assertIn("# 综合信息分析", result.stdout)
        self.assertIn("## 综合回答", result.stdout)
        self.assertIn("## 搜索结果要点", result.stdout)
        self.assertNotIn("## Evidence Gaps", result.stdout)

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
                    "mediacrawler",
                    "--endpoint",
                    "http://127.0.0.1:8080",
                )
                show_result = run_cli("config", "show")
                clear_result = run_cli("config", "clear-provider", "--name", "mediacrawler")
                show_after_clear = run_cli("config", "show")

        self.assertEqual(set_result.returncode, 0)
        self.assertEqual(clear_result.returncode, 0)
        payload = json.loads(show_result.stdout)
        self.assertEqual(payload["providers"]["mediacrawler"]["enabled"], True)
        self.assertEqual(
            payload["providers"]["mediacrawler"]["endpoint"],
            "http://127.0.0.1:8080",
        )
        self.assertNotIn("mediacrawler", json.loads(show_after_clear.stdout)["providers"])

    def test_config_setup_prompts_for_openai_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            buffer = io.StringIO()
            # 2 OpenAI (endpoint + model)
            inputs = ["http://127.0.0.1:8000/", "test-model"]
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}, clear=True):
                with patch("builtins.input", side_effect=inputs):
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

    def test_run_ask_accepts_local_url_without_long_command(self):
        with tempfile.TemporaryDirectory() as directory:
            page = pathlib.Path(directory) / "page.html"
            page.write_text(
                "<html><head><title>Ask Page</title></head>"
                "<body><p>Ask synthesis evidence.</p></body></html>",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}, clear=True):
                output = run_ask("ask local page", "json", url=page.as_uri())

        payload = json.loads(output)
        self.assertEqual(payload["agent"]["planned_tools"], ["web"])
        self.assertEqual(payload["evidence"][0]["adapter"], "web")
        self.assertEqual(payload["status"], "analysis-ready")

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
        self.assertEqual(payload["summary"]["total"], "11")
        self.assertEqual([probe["adapter"] for probe in payload["probes"]], [
            "fixture",
            "web",
            "official",
            "github",
            "github-search",
            "search",
            "search-baidu",
            "trafilatura",
            "crawl4ai",
            "searxng",
            "mediacrawler",
        ])

    def test_probe_outputs_markdown_status(self):
        result = run_cli("probe", "--source", "web", "--format", "markdown")

        self.assertEqual(result.returncode, 0)
        self.assertIn("# Adapter Probe", result.stdout)
        self.assertIn("needs-input", result.stdout)

    def test_probe_outputs_external_bridge_status(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}):
                result = run_cli("probe", "--source", "mediacrawler")

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["adapter"], "mediacrawler")
        self.assertIn(payload["status"], ("disabled", "error"))
        self.assertEqual(payload["details"]["provider_type"], "external-bridge")

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
        self.assertEqual(payload["summary"]["restricted"], "1")
        self.assertEqual(payload["summary"]["required"], "1")

    def test_integrations_outputs_markdown_audit(self):
        result = run_cli("integrations", "audit", "--format", "markdown")

        self.assertEqual(result.returncode, 0)
        self.assertIn("# Integration License Audit", result.stdout)
        self.assertIn("mediacrawler", result.stdout)
        self.assertIn("searxng", result.stdout)

    def test_integrations_outputs_optional_bridge_status(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}):
                result = run_cli("integrations", "status")

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "missing-required")
        self.assertEqual(payload["summary"]["disabled"], "1")
        self.assertEqual(payload["summary"]["required-missing"], "1")

    def test_setup_plan_marks_searxng_as_required(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"SOURCE_RADAR_CONFIG_DIR": directory}, clear=True):
                result = run_cli("setup-plan")

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        by_key = {item["key"]: item for item in payload["required_inputs"]}
        self.assertEqual(payload["ready_for_use"], False)
        self.assertEqual(by_key["searxng_bridge"]["required"], True)
        self.assertEqual(by_key["searxng_bridge"]["status"], "missing")

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

    def test_cookie_help_appears_in_help(self):
        result = run_cli("--help")

        self.assertEqual(result.returncode, 0)
        self.assertIn("cookie", result.stdout)

    def test_cookie_unknown_platform_reports_message(self):
        result = run_cli("cookie", "--platform", "nonexistent-platform")

        self.assertEqual(result.returncode, 0)
        self.assertIn("未知平台", result.stdout)

    def test_cookie_subcommand_help(self):
        result = run_cli("cookie", "--help")

        self.assertEqual(result.returncode, 0)
        self.assertIn("--platform", result.stdout)
        self.assertIn("--force", result.stdout)

    def test_engine_help_appears(self):
        result = run_cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("engine", result.stdout)

    def test_engine_list(self):
        result = run_cli("engine", "list")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Trafilatura", result.stdout)
        self.assertIn("Crawl4AI", result.stdout)
        self.assertIn("MediaCrawler", result.stdout)

    def test_engine_status(self):
        result = run_cli("engine", "status")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Trafilatura", result.stdout)

    def test_engine_start_stop_invalid(self):
        result = run_cli("engine", "start", "nonexistent")
        self.assertIn("未知引擎", result.stdout)

        result = run_cli("engine", "stop", "nonexistent")
        self.assertIn("未知引擎", result.stdout)

    def test_engine_start_library_noop(self):
        result = run_cli("engine", "start", "trafilatura")
        self.assertIn("无需启动", result.stdout)


if __name__ == "__main__":
    unittest.main()
