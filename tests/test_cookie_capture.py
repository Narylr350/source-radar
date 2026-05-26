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
            self.assertIn("KEY_A=val_a", content)
            self.assertIn("KEY_B=val_b", content)

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
        """Build a fake sync_playwright that returns given cookies."""

        browser_self = self

        class FakeBrowser:
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

        class _FakePage:
            def goto(self, url):
                pass

        class FakeBrowserType:
            def launch(self, headless=False):
                return _FakeBrowser()

        class _FakeBrowser:
            def new_context(self):
                return FakeBrowserContext()

            def close(self):
                pass

        class FakePlaywright:
            def __init__(self):
                self.chromium = FakeBrowserType()

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
                result = capture_cookies("https://example.com/login", "test")

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
                result = capture_cookies("https://example.com/login", "test")

        self.assertEqual(result, "")

    def test_capture_cookies_missing_playwright_exits(self):
        from source_radar.cookie_capture import capture_cookies
        import sys as sys_mod

        saved = sys_mod.modules.get("playwright.sync_api")
        try:
            sys_mod.modules["playwright.sync_api"] = None
            with self.assertRaises(SystemExit):
                capture_cookies("https://example.com", "test")
        finally:
            if saved is not None:
                sys_mod.modules["playwright.sync_api"] = saved
            else:
                sys_mod.modules.pop("playwright.sync_api", None)
