import pathlib
import os
import json
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch


class SearXNGEngineTests(unittest.TestCase):
    def test_health_check_sets_non_python_user_agent(self):
        from source_radar import engine

        seen = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"results": [], "unresponsive_engines": []}'

        def fake_urlopen(request, timeout=10):
            seen["user_agent"] = request.get_header("User-agent")
            return FakeResponse()

        with patch("source_radar.engine.urllib.request.urlopen", side_effect=fake_urlopen):
            health = engine._searxng_health_check("http://127.0.0.1:8888")

        self.assertEqual(health["status"], "ok")
        self.assertTrue(seen["user_agent"])
        self.assertNotIn("Python-urllib", seen["user_agent"])

    def test_start_upstream_uses_absolute_launcher_path_with_searxng_cwd(self):
        from source_radar import engine

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            searxng = root / "external" / "searxng"
            scripts = searxng / ".venv" / "Scripts"
            scripts.mkdir(parents=True)
            (scripts / "python.exe").write_text("", encoding="utf-8")
            (searxng / "searx").mkdir()

            fake_proc = MagicMock(pid=12345)
            old_cwd = os.getcwd()
            os.chdir(root)
            try:
                with patch("source_radar.engine._root", return_value=pathlib.Path(".")):
                    with patch("source_radar.engine._http_ok", return_value=False):
                        with patch("source_radar.engine._ensure_searxng_settings"):
                            with patch("source_radar.engine.subprocess.Popen", return_value=fake_proc) as popen:
                                ok, _message = engine._searxng_start_upstream()
            finally:
                os.chdir(old_cwd)

            self.assertTrue(ok)
            args = popen.call_args.args[0]
            cwd = popen.call_args.kwargs["cwd"]
            self.assertTrue(pathlib.Path(args[1]).is_absolute())
            self.assertEqual(pathlib.Path(cwd), searxng)

    def test_kill_matching_processes_kills_searxng_orphans(self):
        from source_radar import engine

        listed = json.dumps([
            {"ProcessId": 111, "ParentProcessId": 1, "CommandLine": r"D:\repo\external\searxng\_start_searxng.py"},
            {"ProcessId": 222, "ParentProcessId": 1, "CommandLine": "pythonw -m source_radar bridge searxng --port 3004"},
            {"ProcessId": 333, "ParentProcessId": 1, "CommandLine": "pwsh -Command uv run python -m source_radar engine stop searxng; rg '-m source_radar bridge searxng'"},
            {"ProcessId": os.getpid(), "ParentProcessId": 333, "CommandLine": "python -m unittest"},
        ])
        calls = []

        def fake_run(args, **kwargs):
            calls.append(args)
            if args[0] == "powershell":
                return subprocess.CompletedProcess(args, 0, stdout=listed, stderr="")
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

        with patch("source_radar.engine.sys.platform", "win32"):
            with patch("source_radar.engine.subprocess.run", side_effect=fake_run):
                engine._kill_processes_matching([
                    ["external", "searxng", "_start_searxng.py"],
                    ["-m source_radar bridge searxng"],
                ])

        taskkill_pids = [args[-1] for args in calls if args[0] == "taskkill"]
        self.assertEqual(taskkill_pids, ["111", "222"])
        for args in calls:
            if args[0] == "taskkill":
                self.assertIn("/T", args)


if __name__ == "__main__":
    unittest.main()
