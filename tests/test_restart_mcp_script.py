import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "restart-mcp.ps1"


class RestartMcpScriptTests(unittest.TestCase):
    def test_restart_script_has_safe_matching_and_dry_run(self):
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("param(", text)
        self.assertIn("[switch]$DryRun", text)
        self.assertIn("source-radar*mcp", text)
        self.assertIn("source_radar*mcp", text)
        self.assertIn("$_.ProcessId -ne $selfPid", text)
        self.assertIn("restart-mcp.ps1", text)
        self.assertIn("if ($DryRun)", text)
        self.assertNotIn('$ErrorActionPreference = "SilentlyContinue"', text)


if __name__ == "__main__":
    unittest.main()
