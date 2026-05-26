import pathlib
import subprocess
import tomllib
import unittest


class PackagingTests(unittest.TestCase):
    def test_pyproject_declares_source_radar_console_script(self):
        pyproject = pathlib.Path("pyproject.toml")
        config = tomllib.loads(pyproject.read_text(encoding="utf-8"))

        self.assertEqual(
            config["tool"]["setuptools"]["package-dir"][""], "app"
        )
        self.assertEqual(
            config["project"]["scripts"]["source-radar"],
            "source_radar.cli:main",
        )

    def test_powershell_helper_wraps_setup_and_ask(self):
        helper = pathlib.Path("source-radar.ps1")
        content = helper.read_text(encoding="utf-8")

        self.assertIn("uv sync --extra dynamic", content)
        self.assertIn("crawl4ai-setup", content)
        self.assertIn("--local-services", content)
        self.assertIn('"source_radar", "ask"', content)
        self.assertIn("PythonArgs", content)
        self.assertIn("SOURCE_RADAR_CONFIG_DIR", content)
        self.assertIn("PYTHONIOENCODING", content)

    def test_powershell_helper_ask_invokes_cli(self):
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                ".\\source-radar.ps1",
                "ask",
                "source-radar",
            ],
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("source-radar", result.stdout)
        self.assertTrue(result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
