import os
import pathlib
import tempfile
import unittest
from unittest.mock import Mock, patch


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

    def test_bridge_health_ignores_external_checkout(self):
        from source_radar.health import BridgeHealth

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            external = root / "external" / "searxng"
            external.mkdir(parents=True)

            def external_exists_only(path):
                return pathlib.Path(path) == external

            with patch("source_radar.health.os.getcwd", return_value=str(root)):
                with patch("source_radar.health.os.path.isdir", side_effect=external_exists_only):
                    with patch("source_radar.health.BridgeHealth.resolve", return_value=""):
                        status = BridgeHealth.check("searxng")

        self.assertEqual(status.status, "missing")
        self.assertEqual(status.fix, "source-radar engine install --searxng")

    def test_bridge_health_requires_target_source_even_when_endpoint_resolves(self):
        from source_radar.health import BridgeHealth

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)

            with patch("source_radar.health.os.getcwd", return_value=str(root)):
                with patch("source_radar.health.BridgeHealth.resolve", return_value="http://127.0.0.1:3004"):
                    status = BridgeHealth.check("searxng")

        self.assertEqual(status.status, "missing")
        self.assertEqual(status.fix, "source-radar engine install --searxng")

    def test_local_services_delegates_to_lifecycle_and_ignores_external_checkout(self):
        from source_radar.runtime import local_services_for_query

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "external" / "MediaCrawler").mkdir(parents=True)
            manager = Mock()
            manager.ensure_ready.return_value = True

            with patch.dict("os.environ", {"SOURCE_RADAR_BILI_COOKIE": "cookie"}, clear=True):
                with patch("source_radar.runtime.load_local_env"):
                    with patch("source_radar.runtime.BackendLifecycleManager", return_value=manager) as manager_cls:
                        with patch("source_radar.runtime.build_default_registry", return_value=Mock()):
                            with patch("source_radar.runtime.BridgeHealth.resolve", return_value="http://127.0.0.1:3003"):
                                with patch("source_radar.runtime._start_service", side_effect=AssertionError("external startup used"), create=True):
                                    with local_services_for_query("bili", enabled=True, root=root):
                                        endpoint = os.environ.get("SOURCE_RADAR_MEDIACRAWLER_ENDPOINT")

        self.assertEqual(manager_cls.call_args.kwargs["project_root"], root.resolve())
        manager.ensure_ready.assert_called_once_with("mediacrawler")
        self.assertEqual(endpoint, "http://127.0.0.1:3003")


if __name__ == "__main__":
    unittest.main()
