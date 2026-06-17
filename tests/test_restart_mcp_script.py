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

    def test_restart_script_tolerates_process_exiting_during_restart(self):
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("try {", text)
        self.assertIn("Stop-Process -Id $process.ProcessId", text)
        self.assertIn("already exited", text)

    def test_restart_script_loops_until_no_mcp_processes_remain(self):
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("$maxRounds", text)
        self.assertIn("for ($round = 1", text)
        self.assertIn("Remaining source-radar MCP/helper processes after cleanup", text)
        self.assertIn("Claude Code must reconnect", text)

    def test_restart_script_cleans_source_radar_service_helpers(self):
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("Get-SourceRadarRestartProcesses", text)
        self.assertIn("-m source_radar bridge *", text)
        self.assertIn("_start_searxng.py", text)
        self.assertNotIn("uvicorn", text)


if __name__ == "__main__":
    unittest.main()
