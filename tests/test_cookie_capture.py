import os
import pathlib
import tempfile
import unittest
import unittest.mock

from source_radar.cookie_capture import (
    PLATFORM_COOKIE_CONFIG,
    _local_env_path,
    read_local_env,
    write_local_env,
)


class CookieCaptureHelpersTests(unittest.TestCase):
    def test_platform_config_covers_all_cookie_envs(self):
        from source_radar.bridge import PLATFORM_COOKIE_ENVS

        for platform, env_name in PLATFORM_COOKIE_ENVS.items():
            with self.subTest(platform=platform):
                self.assertIn(platform, PLATFORM_COOKIE_CONFIG)
                self.assertEqual(PLATFORM_COOKIE_CONFIG[platform]["env"], env_name)

    def test_platform_config_has_required_fields(self):
        for platform, config in PLATFORM_COOKIE_CONFIG.items():
            with self.subTest(platform=platform):
                self.assertIn("name", config)
                self.assertIn("env", config)
                self.assertIn("login_url", config)
                self.assertTrue(config["login_url"].startswith("https://"))
                self.assertFalse(config["login_url"].endswith("/login.php"))

    def test_read_local_env_empty_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = read_local_env(root=tmp)
            self.assertEqual(result, {})

    def test_read_local_env_parses_key_value_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = pathlib.Path(tmp) / ".source-radar"
            src_dir.mkdir(parents=True)
            env_file = src_dir / "local.env"
            env_file.write_text(
                "SOURCE_RADAR_XHS_COOKIE=test_cookie_value\n"
                "FIRECRAWL_TRANSPORT=mcp\n"
                "# comment line\n"
                "\n"
                "FIRECRAWL_API_KEY=\n",
                encoding="utf-8",
            )
            result = read_local_env(root=tmp)
            self.assertEqual(result["SOURCE_RADAR_XHS_COOKIE"], "test_cookie_value")
            self.assertEqual(result["FIRECRAWL_TRANSPORT"], "mcp")
            self.assertNotIn("FIRECRAWL_API_KEY", result)

    def test_write_local_env_creates_file_and_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_local_env({"KEY_A": "val_a", "KEY_B": "val_b"}, root=tmp)
            path = _local_env_path(tmp)
            self.assertTrue(path.exists())
            content = path.read_text(encoding="utf-8")
            self.assertIn('KEY_A="val_a"', content)
            self.assertIn('KEY_B="val_b"', content)

    def test_write_local_env_preserves_existing_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_local_env({"KEEP_ME": "keep_value"}, root=tmp)
            write_local_env({"NEW_KEY": "new_value"}, root=tmp)
            result = read_local_env(root=tmp)
            self.assertEqual(result["KEEP_ME"], "keep_value")
            self.assertEqual(result["NEW_KEY"], "new_value")

    def test_write_local_env_overwrites_existing_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_local_env({"KEY": "old"}, root=tmp)
            write_local_env({"KEY": "new"}, root=tmp)
            result = read_local_env(root=tmp)
            self.assertEqual(result["KEY"], "new")


class CookieCapturePlaywrightTests(unittest.TestCase):
    def _fake_playwright(self, cookie_dicts):
        """Build a fake sync_playwright that uses launch_persistent_context."""

        class FakeBrowserType:
            def launch(self, channel=None, headless=False):
                return _FakeProbeBrowser()

            def launch_persistent_context(self, user_data_dir, headless=False,
                                          channel=None, viewport=None, args=None):
                return FakeBrowserContext()

        class _FakePage:
            url = "https://example.com/"

            def goto(self, url, wait_until=None):
                pass

            def wait_for_timeout(self, ms):
                pass

        class _FakeProbeBrowser:
            def close(self):
                pass

        class FakeBrowserContext:
            def cookies(self):
                return [
                    {"name": c["name"], "value": c["value"]}
                    for c in cookie_dicts
                ]

            def new_page(self):
                return _FakePage()

            def on(self, event, handler):
                pass

            def close(self):
                pass

        FakeBrowserContext.pages = [_FakePage()]

        FakePlaywright = type("FakePlaywright", (), {"chromium": FakeBrowserType()})

        class FakePW:
            def __enter__(self):
                return FakePlaywright()

            def __exit__(self, *args):
                pass

        return FakePW()

    def test_capture_cookies_returns_cookie_string(self):
        from source_radar.cookie_capture import capture_cookies

        fake = self._fake_playwright([
            {"name": "session", "value": "abc123"},
            {"name": "token", "value": "xyz789"},
        ])

        with unittest.mock.patch("builtins.input", return_value=""):
            with unittest.mock.patch(
                "playwright.sync_api.sync_playwright",
                return_value=fake,
            ):
                result = capture_cookies("https://example.com", "test", "测试")

        self.assertIn("session=abc123", result)
        self.assertIn("token=xyz789", result)

    def test_capture_cookies_empty_when_no_cookies(self):
        from source_radar.cookie_capture import capture_cookies

        fake = self._fake_playwright([])

        with unittest.mock.patch("builtins.input", return_value=""):
            with unittest.mock.patch(
                "playwright.sync_api.sync_playwright",
                return_value=fake,
            ):
                result = capture_cookies("https://example.com", "test", "测试")

        self.assertEqual(result, "")

    def test_capture_cookies_missing_playwright_exits(self):
        from source_radar.cookie_capture import capture_cookies
        import sys as sys_mod

        saved = sys_mod.modules.get("playwright.sync_api")
        try:
            sys_mod.modules["playwright.sync_api"] = None
            with self.assertRaises(SystemExit):
                capture_cookies("https://example.com", "test", "test")
        finally:
            if saved is not None:
                sys_mod.modules["playwright.sync_api"] = saved
            else:
                sys_mod.modules.pop("playwright.sync_api", None)


class RunCookieTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_run_cookie_all_skip_when_all_configured(self):
        from source_radar.cookie_capture import run_cookie

        env_vars = {
            "SOURCE_RADAR_XHS_COOKIE": "fake_xhs",
            "SOURCE_RADAR_WEIBO_COOKIE": "fake_wb",
            "SOURCE_RADAR_BILI_COOKIE": "fake_bili",
            "SOURCE_RADAR_TIEBA_COOKIE": "fake_tieba",
            "SOURCE_RADAR_DOUYIN_COOKIE": "fake_dy",
        }
        with unittest.mock.patch.dict(os.environ, env_vars, clear=True):
            result = run_cookie()
        self.assertIn("无需获取", result)

    def test_run_cookie_force_overrides_skip(self):
        from source_radar.cookie_capture import run_cookie, write_local_env

        write_local_env(
            {"SOURCE_RADAR_XHS_COOKIE": "existing_cookie"}, root=self.tmp.name
        )

        with unittest.mock.patch.dict(
            os.environ, {"SOURCE_RADAR_XHS_COOKIE": "existing_cookie"}
        ):
            with unittest.mock.patch(
                "source_radar.cookie_capture.capture_cookies",
                return_value="new_cookie_value",
            ):
                with unittest.mock.patch(
                    "source_radar.cookie_capture._local_env_path",
                    return_value=pathlib.Path(self.tmp.name)
                    / ".source-radar"
                    / "local.env",
                ):
                    result = run_cookie(platform="xhs", force=True)

        self.assertIn("成功 1", result)
        saved = read_local_env(root=self.tmp.name)
        self.assertEqual(saved["SOURCE_RADAR_XHS_COOKIE"], "new_cookie_value")

    def test_run_cookie_unknown_platform(self):
        from source_radar.cookie_capture import run_cookie

        result = run_cookie(platform="nonexistent")
        self.assertIn("未知平台", result)
        self.assertIn("可用平台", result)

    def test_run_cookie_specific_platform_skip_others(self):
        from source_radar.cookie_capture import run_cookie

        env_vars = {"SOURCE_RADAR_XHS_COOKIE": "existing_xhs"}
        with unittest.mock.patch.dict(os.environ, env_vars, clear=True):
            with unittest.mock.patch(
                "source_radar.cookie_capture.load_local_env",
            ):
                with unittest.mock.patch(
                    "source_radar.cookie_capture.capture_cookies",
                    return_value="wb_cookie_string",
                ) as mock_capture:
                    with unittest.mock.patch(
                        "source_radar.cookie_capture.write_local_env",
                    ) as mock_write:
                        result = run_cookie(platform="wb")

        mock_capture.assert_called_once()
        mock_write.assert_called_once()
        self.assertIn("成功 1", result)

    def test_run_cookie_empty_capture_shows_warning(self):
        from source_radar.cookie_capture import run_cookie

        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            with unittest.mock.patch(
                "source_radar.cookie_capture.load_local_env",
            ):
                with unittest.mock.patch(
                    "source_radar.cookie_capture.capture_cookies",
                    return_value="",
                ):
                    with unittest.mock.patch(
                        "source_radar.cookie_capture.write_local_env",
                    ):
                        result = run_cookie(platform="xhs")

        self.assertIn("未获取 1", result)

    def test_run_cookie_keyboard_interrupt_saves_captured(self):
        from source_radar.cookie_capture import run_cookie

        call_count = [0]

        def mock_capture(login_url, platform_key, platform_name):
            call_count[0] += 1
            if call_count[0] == 1:
                return "cookie_platform_1"
            raise KeyboardInterrupt

        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            with unittest.mock.patch(
                "source_radar.cookie_capture.load_local_env",
            ):
                with unittest.mock.patch(
                    "source_radar.cookie_capture.capture_cookies",
                    side_effect=mock_capture,
                ):
                    with unittest.mock.patch(
                        "source_radar.cookie_capture.write_local_env",
                    ) as mock_write:
                        result = run_cookie()

        mock_write.assert_called_once()
        self.assertIn("成功 1", result)
