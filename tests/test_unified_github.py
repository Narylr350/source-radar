"""Test that GitHub API calls are unified in acquisition layer."""
import unittest
from unittest.mock import patch, MagicMock
from source_radar.acquisition import GithubSearchProvider


class UnifiedGithubApiTest(unittest.TestCase):
    """GithubSearchProvider should expose a public api_get that returns dict or list."""

    def test_github_provider_has_public_api_get(self):
        """GithubSearchProvider.api_get is a public method."""
        provider = GithubSearchProvider()
        self.assertTrue(hasattr(provider, "api_get"))
        self.assertTrue(callable(provider.api_get))

    def test_api_get_returns_dict_for_file(self):
        """api_get returns dict for a file response."""
        provider = GithubSearchProvider()
        fake_response = MagicMock()
        fake_response.read.return_value = b'{"content": "abc", "encoding": "base64"}'
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = lambda s, *a: None
        with patch("source_radar.acquisition.urlopen", return_value=fake_response):
            result = provider.api_get("https://api.github.com/repos/x/y/contents/README.md")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["content"], "abc")

    def test_api_get_returns_list_for_directory(self):
        """api_get returns list for a directory listing (must not discard list)."""
        provider = GithubSearchProvider()
        fake_response = MagicMock()
        fake_response.read.return_value = b'[{"name": "a.py", "type": "file"}]'
        fake_response.__enter__ = lambda s: s
        fake_response.__exit__ = lambda s, *a: None
        with patch("source_radar.acquisition.urlopen", return_value=fake_response):
            result = provider.api_get("https://api.github.com/repos/x/y/contents/src")
        self.assertIsInstance(result, list)
        self.assertEqual(result[0]["name"], "a.py")

    def test_mcp_fetch_github_file_uses_provider_api_get(self):
        """handle_fetch_github_file should use provider.api_get, not private _github_api_get."""
        from source_radar.mcp import server
        self.assertFalse(hasattr(server, "_github_api_get"))


if __name__ == "__main__":
    unittest.main()
