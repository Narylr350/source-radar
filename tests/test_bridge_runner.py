import os
import tempfile
import unittest
import urllib.parse
from unittest.mock import patch

from source_radar.bridge import (
    MediaCrawlerBridgeBackend,
    SearXNGBridgeBackend,
    load_local_env,
)


class BridgeRunnerTests(unittest.TestCase):
    def test_searxng_bridge_collects_json_results(self):
        calls = []

        def fake_request(method, url, payload=None, timeout=30):
            calls.append((method, url, payload, timeout))
            self.assertEqual(method, "GET")
            parsed = urllib.parse.urlparse(url)
            query = urllib.parse.parse_qs(parsed.query)
            self.assertEqual(query.get("format"), ["json"])
            self.assertEqual(query.get("q"), ["张雪峰 去世"])
            return {
                "results": [
                    {
                        "title": "张雪峰去世_证券时报",
                        "url": "https://www.stcn.com/article/detail/3696114.html",
                        "content": "证券时报报道，张雪峰去世。",
                        "engine": "bing",
                    },
                    {
                        "title": "无链接结果",
                        "content": "ignored",
                    },
                ]
            }

        backend = SearXNGBridgeBackend(
            upstream_url="http://127.0.0.1:8080",
            request_json=fake_request,
        )

        payload = backend.collect({"query": "张雪峰 去世", "limit": 5})

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["items"][0]["title"], "张雪峰去世_证券时报")
        self.assertEqual(payload["items"][0]["url"], "https://www.stcn.com/article/detail/3696114.html")
        self.assertEqual(payload["items"][0]["source_type"], "search-result")
        self.assertEqual(payload["items"][0]["metadata"]["engine"], "bing")
        self.assertEqual(payload["candidates"][0]["provider"], "searxng")
        self.assertEqual(len(calls), 1)

    def test_searxng_bridge_health_reports_upstream_ready(self):
        def fake_request(method, url, payload=None, timeout=30):
            self.assertEqual(method, "GET")
            self.assertTrue(url.endswith("/search?q=source-radar&format=json"))
            return {"results": []}

        backend = SearXNGBridgeBackend(
            upstream_url="http://127.0.0.1:8080/",
            request_json=fake_request,
        )

        payload = backend.health()

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["reason"], "ready")
        self.assertEqual(payload["diagnostics"]["upstream_url"], "http://127.0.0.1:8080")

    def test_load_local_env_reads_ignored_workspace_secret_file_without_overriding_env(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, ".source-radar", "local.env")
            os.makedirs(os.path.dirname(path))
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("SOURCE_RADAR_XHS_COOKIE=web_session=local\n")

            with patch.dict(os.environ, {}, clear=True):
                load_local_env(directory)

                self.assertEqual(os.environ["SOURCE_RADAR_XHS_COOKIE"], "web_session=local")

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
            ("GET", "http://127.0.0.1:8080/api/data/files/xhs/contents.json?preview=true&limit=50"): {
                "data": [
                    {
                        "title": "小红书实测",
                        "note_url": "https://www.xiaohongshu.com/explore/1",
                        "desc": "真实体验内容",
                        "nickname": "tester",
                        "time": "2026-05-25",
                        "source_keyword": "AI 工具实测",
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
            ("GET", "http://127.0.0.1:8080/api/data/files?platform=weibo&file_type=json"): {
                "files": [{"path": "wb/contents.json", "modified_at": 2}]
            },
            ("GET", "http://127.0.0.1:8080/api/data/files/wb/contents.json?preview=true&limit=50"): {
                "data": [
                    {
                        "title": "微博讣告",
                        "url": "https://weibo.com/status/1",
                        "content": "官方账号发布讣告。",
                        "source_keyword": "张雪峰死了吗",
                    }
                ]
            },
            ("GET", "http://127.0.0.1:8080/api/data/files?platform=xhs&file_type=json"): {
                "files": [{"path": "xhs/contents.json", "modified_at": 1}]
            },
            ("GET", "http://127.0.0.1:8080/api/data/files/xhs/contents.json?preview=true&limit=50"): {
                "data": [
                    {
                        "title": "小红书讨论",
                        "note_url": "https://www.xiaohongshu.com/explore/1",
                        "desc": "网友讨论。",
                        "source_keyword": "张雪峰死了吗",
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
        payload = backend.collect({"query": "张雪峰死了吗", "limit": 2, "platforms": ["wb", "xhs"]})

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

    def test_newest_file_prefers_search_contents(self):
        from source_radar.bridge import _newest_file_path

        payload = {
            "files": [
                {"path": "bili/search_creators_2026-06-12.json", "modified_at": 200},
                {"path": "bili/search_contents_2026-06-12.json", "modified_at": 100},
            ]
        }
        result = _newest_file_path(payload)
        self.assertIn("search_contents", result)

    def test_newest_file_falls_back_when_no_contents(self):
        from source_radar.bridge import _newest_file_path

        payload = {
            "files": [
                {"path": "bili/search_creators_2026-06-12.json", "modified_at": 200},
            ]
        }
        result = _newest_file_path(payload)
        self.assertIn("search_creators", result)

    def test_bridge_tracks_stages(self):
        calls = []
        responses = {
            ("POST", "http://127.0.0.1:8080/api/crawler/start"): {
                "status": "ok",
                "message": "Crawler started successfully",
            },
            ("GET", "http://127.0.0.1:8080/api/crawler/status"): {
                "status": "idle",
            },
            ("GET", "http://127.0.0.1:8080/api/data/files?platform=xhs&file_type=json"): {
                "files": [{"path": "xhs/contents.json", "modified_at": 1}]
            },
            ("GET", "http://127.0.0.1:8080/api/data/files/xhs/contents.json?preview=true&limit=50"): {
                "data": [
                    {
                        "title": "测试",
                        "note_url": "https://www.xiaohongshu.com/explore/1",
                        "desc": "内容",
                        "source_keyword": "test query",
                    }
                ]
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
        backend.collect({"query": "test query", "limit": 2})

        self.assertTrue(len(backend._last_stages) > 0)
        self.assertTrue(any("启动爬虫" in s for s in backend._last_stages))
        self.assertTrue(any("等待完成" in s for s in backend._last_stages))
        self.assertTrue(any("读取结果" in s for s in backend._last_stages))
        self.assertTrue(any("完成" in s for s in backend._last_stages))

    def test_bridge_returns_empty_when_source_keyword_mismatch(self):
        """When source_keyword doesn't match query, should return empty (not stale data)."""
        calls = []
        responses = {
            ("POST", "http://127.0.0.1:8080/api/crawler/start"): {
                "status": "ok", "message": "Crawler started",
            },
            ("GET", "http://127.0.0.1:8080/api/crawler/status"): {
                "status": "idle",
            },
            ("GET", "http://127.0.0.1:8080/api/data/files?platform=xhs&file_type=json"): {
                "files": [{"path": "xhs/contents.json", "modified_at": 1}],
            },
            ("GET", "http://127.0.0.1:8080/api/data/files/xhs/contents.json?preview=true&limit=50"): {
                "data": [
                    {
                        "title": "旧查询结果",
                        "note_url": "https://www.xiaohongshu.com/explore/old",
                        "desc": "This is from a different query",
                        "source_keyword": "old query that doesn't match",
                    },
                ],
            },
        }

        def fake_request(method, url, payload=None, timeout=30):
            calls.append((method, url, payload))
            return responses[(method, url)]

        backend = MediaCrawlerBridgeBackend(
            api_url="http://127.0.0.1:8080",
            platform="xhs",
            login_type="cookie",
            cookies_map={"xhs": "cookie"},
            timeout_seconds=1,
            sleep_seconds=0,
            request_json=fake_request,
        )
        payload = backend.collect({"query": "new query", "limit": 2})
        self.assertEqual(payload["status"], "no-evidence")
        self.assertEqual(len(payload["items"]), 0)


if __name__ == "__main__":
    unittest.main()
