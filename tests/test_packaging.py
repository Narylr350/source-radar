import pathlib
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


if __name__ == "__main__":
    unittest.main()
