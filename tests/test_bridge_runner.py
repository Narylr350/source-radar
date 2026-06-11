import os
import tempfile
import unittest
from unittest.mock import patch

from source_radar.bridge import (
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
            ("GET", "http://127.0.0.1:8080/api/data/files?platform=xiaohongshu&file_type=json"): {
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
            ("GET", "http://127.0.0.1:8080/api/data/files?platform=xiaohongshu&file_type=json"): {
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


if __name__ == "__main__":
    unittest.main()
