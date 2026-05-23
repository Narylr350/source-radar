import json
import os
import subprocess
import sys
import unittest


def run_cli(*args):
    env = os.environ.copy()
    env["PYTHONPATH"] = "app"
    return subprocess.run(
        [sys.executable, "-m", "source_radar", *args],
        cwd=os.getcwd(),
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


if __name__ == "__main__":
    unittest.main()
