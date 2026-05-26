import json
import os
import tempfile
import unittest
from unittest.mock import patch

from source_radar.bridge import (
    FirecrawlBridgeBackend,
    MediaCrawlerBridgeBackend,
    load_local_env,
)


class BridgeRunnerTests(unittest.TestCase):
    def test_load_local_env_reads_ignored_workspace_secret_file_without_overriding_env(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, ".source-radar", "local.env")
            os.makedirs(os.path.dirname(path))
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("SOURCE_RADAR_XHS_COOKIE=web_session=local\n")
                handle.write("FIRECRAWL_API_KEY=from-file\n")

            with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "from-env"}, clear=True):
                load_local_env(directory)

                self.assertEqual(os.environ["SOURCE_RADAR_XHS_COOKIE"], "web_session=local")
                self.assertEqual(os.environ["FIRECRAWL_API_KEY"], "from-env")

    def test_firecrawl_bridge_collect_calls_search_api_and_parses_items(self):
        requests = []

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps(
                    {
                        "data": [
                            {
                                "title": "Firecrawl Result",
                                "url": "https://example.test/firecrawl",
                                "description": "Firecrawl search snippet.",
                            }
                        ]
                    }
                ).encode("utf-8")

        def fake_urlopen(request, timeout=30):
            requests.append(request)
            return Response()

        backend = FirecrawlBridgeBackend(
            api_url="https://api.firecrawl.dev",
            api_key="fc-key",
            transport="api",
        )
        with patch("source_radar.bridge.urlopen", side_effect=fake_urlopen):
            payload = backend.collect({"query": "firecrawl docs", "limit": 3})

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["items"][0]["title"], "Firecrawl Result")
        self.assertEqual(payload["items"][0]["source_type"], "web-page")
        self.assertEqual(
            requests[0].full_url,
            "https://api.firecrawl.dev/v1/search",
        )
        self.assertEqual(requests[0].headers["Authorization"], "Bearer fc-key")
        self.assertEqual(
            json.loads(requests[0].data.decode("utf-8")),
            {"query": "firecrawl docs", "limit": 3},
        )

    def test_firecrawl_api_bridge_allows_self_hosted_without_api_key(self):
        requests = []

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self):
                return json.dumps({"data": []}).encode("utf-8")

        def fake_urlopen(request, timeout=30):
            requests.append(request)
            return Response()

        backend = FirecrawlBridgeBackend(api_url="https://api.firecrawl.dev", api_key="", transport="api")

        with patch("source_radar.bridge.urlopen", side_effect=fake_urlopen):
            payload = backend.collect({"query": "claim"})

        self.assertEqual(payload["status"], "no-evidence")
        self.assertNotIn("Authorization", requests[0].headers)

    def test_firecrawl_mcp_bridge_calls_search_tool_and_parses_items(self):
        calls = []

        def fake_mcp_call(command, tool_name, arguments, env, timeout):
            calls.append((command, tool_name, arguments, env, timeout))
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "success": True,
                                "data": {
                                    "web": [
                                        {
                                            "title": "MCP Result",
                                            "url": "https://example.test/mcp",
                                            "description": "MCP search snippet.",
                                        }
                                    ]
                                },
                            }
                        ),
                    }
                ]
            }

        backend = FirecrawlBridgeBackend(
            api_url="",
            api_key="fc-key",
            transport="mcp",
            mcp_command="node firecrawl-mcp",
            timeout_seconds=12,
            mcp_call=fake_mcp_call,
        )

        payload = backend.collect({"query": "firecrawl mcp", "limit": 2})

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["items"][0]["title"], "MCP Result")
        self.assertEqual(payload["items"][0]["source_type"], "web-page")
        self.assertEqual(calls[0][0], "node firecrawl-mcp")
        self.assertEqual(calls[0][1], "firecrawl_search")
        self.assertEqual(calls[0][2], {"query": "firecrawl mcp", "limit": 2})
        self.assertEqual(calls[0][3]["FIRECRAWL_API_KEY"], "fc-key")
        self.assertEqual(calls[0][4], 12)

    def test_firecrawl_mcp_bridge_reports_missing_auth_or_self_host_url(self):
        backend = FirecrawlBridgeBackend(api_url="", api_key="", transport="mcp")

        payload = backend.collect({"query": "claim"})

        self.assertEqual(payload["status"], "needs-input")
        self.assertEqual(payload["reason"], "auth-missing")
        self.assertIn("FIRECRAWL_API_KEY", payload["fix"])

    def test_mediacrawler_bridge_collect_starts_task_and_reads_preview_file(self):
        calls = []
        responses = {
            ("GET", "http://127.0.0.1:8080/api/health"): {
                "status": "ok",
                "message": "ready",
            },
            ("POST", "http://127.0.0.1:8080/api/crawler/start"): {
                "status": "ok",
                "message": "Crawler started successfully",
            },
            ("GET", "http://127.0.0.1:8080/api/crawler/status"): {
                "status": "idle",
            },
            ("GET", "http://127.0.0.1:8080/api/data/files?platform=xhs&file_type=json"): {
                "files": [
                    {
                        "path": "xhs/contents.json",
                        "modified_at": 123,
                    }
                ]
            },
            ("GET", "http://127.0.0.1:8080/api/data/files/xhs/contents.json?preview=true&limit=2"): {
                "data": [
                    {
                        "title": "小红书实测",
                        "note_url": "https://www.xiaohongshu.com/explore/1",
                        "desc": "真实体验内容",
                        "nickname": "tester",
                        "time": "2026-05-25",
                    }
                ],
                "total": 1,
            },
        }

        def fake_request(method, url, payload=None, timeout=30):
            calls.append((method, url, payload))
            return responses[(method, url)]

        backend = MediaCrawlerBridgeBackend(
            api_url="http://127.0.0.1:8080",
            platform="xhs",
            login_type="cookie",
            cookies_map={"xhs": "web_session=local"},
            timeout_seconds=1,
            sleep_seconds=0,
            request_json=fake_request,
        )
        payload = backend.collect({"query": "AI 工具实测", "limit": 2})

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["items"][0]["title"], "小红书实测")
        self.assertEqual(payload["items"][0]["url"], "https://www.xiaohongshu.com/explore/1")
        self.assertEqual(payload["items"][0]["source_type"], "community-post")
        self.assertEqual(calls[0][2]["keywords"], "AI 工具实测")
        self.assertEqual(calls[0][2]["save_option"], "json")
        self.assertEqual(calls[0][2]["cookies"], "web_session=local")

    def test_mediacrawler_bridge_collects_multiple_platforms_in_order(self):
        calls = []
        responses = {
            ("POST", "http://127.0.0.1:8080/api/crawler/start"): {
                "status": "ok",
                "message": "Crawler started successfully",
            },
            ("GET", "http://127.0.0.1:8080/api/crawler/status"): {
                "status": "idle",
            },
            ("GET", "http://127.0.0.1:8080/api/data/files?platform=wb&file_type=json"): {
                "files": [{"path": "wb/contents.json", "modified_at": 2}]
            },
            ("GET", "http://127.0.0.1:8080/api/data/files/wb/contents.json?preview=true&limit=2"): {
                "data": [
                    {
                        "title": "微博讣告",
                        "url": "https://weibo.com/status/1",
                        "content": "官方账号发布讣告。",
                    }
                ]
            },
            ("GET", "http://127.0.0.1:8080/api/data/files?platform=xhs&file_type=json"): {
                "files": [{"path": "xhs/contents.json", "modified_at": 1}]
            },
            ("GET", "http://127.0.0.1:8080/api/data/files/xhs/contents.json?preview=true&limit=2"): {
                "data": [
                    {
                        "title": "小红书讨论",
                        "note_url": "https://www.xiaohongshu.com/explore/1",
                        "desc": "网友讨论。",
                    }
                ]
            },
        }

        def fake_request(method, url, payload=None, timeout=30):
            calls.append((method, url, payload))
            return responses[(method, url)]

        backend = MediaCrawlerBridgeBackend(
            api_url="http://127.0.0.1:8080",
            platform="weibo,xhs",
            login_type="cookie",
            cookies_map={"wb": "weibo-cookie", "xhs": "xhs-cookie"},
            timeout_seconds=1,
            sleep_seconds=0,
            request_json=fake_request,
        )
        payload = backend.collect({"query": "张雪峰死了吗", "limit": 2})

        started_platforms = [
            call[2]["platform"]
            for call in calls
            if call[0] == "POST" and call[1].endswith("/api/crawler/start")
        ]
        self.assertEqual(started_platforms, ["wb", "xhs"])
        self.assertEqual(payload["status"], "ok")
        self.assertEqual([item["metadata"]["platform"] for item in payload["items"]], ["wb", "xhs"])

    def test_mediacrawler_bridge_health_reports_missing_cookies(self):
        backend = MediaCrawlerBridgeBackend(
            api_url="http://127.0.0.1:8080",
            login_type="cookie",
            cookies="",
        )

        payload = backend.health()

        self.assertEqual(payload["status"], "needs-input")
        self.assertEqual(payload["reason"], "missing-cookies")
        self.assertFalse(payload["retryable"])

    def test_mediacrawler_bridge_health_reports_unreachable_api(self):
        def fake_request(method, url, payload=None, timeout=30):
            raise OSError("refused")

        backend = MediaCrawlerBridgeBackend(
            api_url="http://127.0.0.1:8080",
            cookies="some-cookie",
            request_json=fake_request,
        )

        payload = backend.health()

        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["reason"], "service-unreachable")
        self.assertEqual(payload["retryable"], True)


if __name__ == "__main__":
    unittest.main()
