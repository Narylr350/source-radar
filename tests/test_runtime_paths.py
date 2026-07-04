import pathlib
import tempfile
import unittest
from unittest.mock import patch


class RuntimePathHelperTests(unittest.TestCase):
    def test_runtime_helpers_put_cache_sessions_crawl4ai_and_logs_under_runtime_layout(self):
        from source_radar.backends import paths

        root = pathlib.Path("C:/repo")

        self.assertEqual(paths.runtime_cache_path("acquisition", root), root / ".source-radar" / "runtime" / "cache" / "acquisition")
        self.assertEqual(paths.session_dir(root), root / ".source-radar" / "runtime" / "sessions")
        self.assertEqual(paths.crawl4ai_runtime_dir(root), root / ".source-radar" / "runtime" / "crawl4ai")
        self.assertEqual(paths.browser_profile_dir("bilibili", root), root / ".source-radar" / "runtime" / "browser-profiles" / "bilibili")
        self.assertEqual(paths.log_path("source-radar.log", root), root / ".source-radar" / "logs" / "source-radar.log")
        self.assertEqual(paths.pid_path("search.searxng", root), root / ".source-radar" / "pids" / "search-searxng.pid")

    def test_cache_and_session_modules_use_runtime_helpers(self):
        from source_radar import cache, session

        self.assertEqual(cache.CACHE_DIR, pathlib.Path(".source-radar") / "runtime" / "cache" / "acquisition")
        self.assertEqual(session.SESSION_DIR, pathlib.Path(".source-radar") / "runtime" / "sessions")

    def test_cookie_capture_profiles_use_runtime_browser_profile_helper(self):
        from source_radar.cookie_capture import _profile_dir

        self.assertEqual(
            _profile_dir("bili"),
            pathlib.Path(".source-radar") / "runtime" / "browser-profiles" / "bili",
        )

    def test_bridge_health_detects_target_engine_source_before_legacy_path(self):
        from source_radar.health import BridgeHealth

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            target = root / ".source-radar" / "engines" / "searxng" / "source"
            target.mkdir(parents=True)

            def target_exists_only(path):
                return pathlib.Path(path) == target

            with patch("source_radar.health.os.getcwd", return_value=str(root)):
                with patch("source_radar.health.os.path.isdir", side_effect=target_exists_only):
                    with patch("source_radar.health.BridgeHealth.resolve", return_value=""):
                        status = BridgeHealth.check("searxng")

        self.assertEqual(status.status, "stopped")
        self.assertEqual(status.fix, "source-radar engine start searxng")


if __name__ == "__main__":
    unittest.main()
