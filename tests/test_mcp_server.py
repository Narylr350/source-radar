import asyncio
import unittest
from unittest.mock import patch, MagicMock

from mcp import types


class TestMCPServerCreation(unittest.TestCase):
    def test_create_server_returns_server(self):
        from source_radar.mcp.server import create_server
        from mcp.server.lowlevel import Server
        server = create_server()
        self.assertIsInstance(server, Server)

    def test_server_name(self):
        from source_radar.mcp.server import create_server
        server = create_server()
        self.assertEqual(server.name, "source-radar")


class TestToolsList(unittest.TestCase):
    def test_lists_four_tools(self):
        from source_radar.mcp.server import create_server
        server = create_server()

        async def get_tools():
            handler = server.request_handlers[types.ListToolsRequest]
            result = await handler(types.ListToolsRequest(method="tools/list", params=None))
            return result.root.tools

        tools = asyncio.run(get_tools())
        names = [t.name for t in tools]
        self.assertIn("web_search", names)
        self.assertIn("fetch_url", names)
        self.assertIn("search_github", names)
        self.assertIn("search_chinese_platforms", names)
        self.assertEqual(len(names), 4)

    def test_web_search_schema(self):
        from source_radar.mcp.server import create_server
        server = create_server()

        async def get_tools():
            handler = server.request_handlers[types.ListToolsRequest]
            result = await handler(types.ListToolsRequest(method="tools/list", params=None))
            return result.root.tools

        tools = asyncio.run(get_tools())
        search_tool = next(t for t in tools if t.name == "web_search")
        self.assertIn("query", search_tool.inputSchema["properties"])
        self.assertIn("limit", search_tool.inputSchema["properties"])
        self.assertIn("query", search_tool.inputSchema["required"])

    def test_fetch_url_schema(self):
        from source_radar.mcp.server import create_server
        server = create_server()

        async def get_tools():
            handler = server.request_handlers[types.ListToolsRequest]
            result = await handler(types.ListToolsRequest(method="tools/list", params=None))
            return result.root.tools

        tools = asyncio.run(get_tools())
        fetch_tool = next(t for t in tools if t.name == "fetch_url")
        self.assertIn("url", fetch_tool.inputSchema["properties"])
        self.assertIn("max_chars", fetch_tool.inputSchema["properties"])
        self.assertIn("url", fetch_tool.inputSchema["required"])


class TestURLValidation(unittest.TestCase):
    def test_allows_http(self):
        from source_radar.mcp.server import _validate_url
        self.assertIsNone(_validate_url("http://example.com"))

    def test_allows_https(self):
        from source_radar.mcp.server import _validate_url
        self.assertIsNone(_validate_url("https://example.com/path?q=1"))

    def test_blocks_ftp(self):
        from source_radar.mcp.server import _validate_url
        self.assertIsNotNone(_validate_url("ftp://example.com"))

    def test_blocks_file(self):
        from source_radar.mcp.server import _validate_url
        self.assertIsNotNone(_validate_url("file:///etc/passwd"))

    def test_blocks_localhost(self):
        from source_radar.mcp.server import _validate_url
        self.assertIsNotNone(_validate_url("http://localhost:8080"))

    def test_blocks_127_0_0_1(self):
        from source_radar.mcp.server import _validate_url
        self.assertIsNotNone(_validate_url("http://127.0.0.1"))

    def test_blocks_10_private(self):
        from source_radar.mcp.server import _validate_url
        self.assertIsNotNone(_validate_url("http://10.0.0.1"))

    def test_blocks_192_168_private(self):
        from source_radar.mcp.server import _validate_url
        self.assertIsNotNone(_validate_url("http://192.168.1.1"))

    def test_blocks_172_16_private(self):
        from source_radar.mcp.server import _validate_url
        self.assertIsNotNone(_validate_url("http://172.16.0.1"))

    def test_blocks_0_0_0_0(self):
        from source_radar.mcp.server import _validate_url
        self.assertIsNotNone(_validate_url("http://0.0.0.0"))

    def test_blocks_ipv6_loopback(self):
        from source_radar.mcp.server import _validate_url
        self.assertIsNotNone(_validate_url("http://[::1]"))

    def test_blocks_dot_local(self):
        from source_radar.mcp.server import _validate_url
        self.assertIsNotNone(_validate_url("http://myhost.local"))

    def test_blocks_empty_hostname(self):
        from source_radar.mcp.server import _validate_url
        self.assertIsNotNone(_validate_url("http://"))


class TestSearchFormat(unittest.TestCase):
    def test_format_search_results_basic(self):
        from source_radar.mcp.server import _format_search_results
        results = [
            {"title": "Test Title", "url": "https://example.com", "snippet": "A snippet."},
        ]
        text = _format_search_results("test query", results, cached=False)
        self.assertIn("test query", text)
        self.assertIn("1 条", text)
        self.assertIn("Test Title", text)
        self.assertIn("https://example.com", text)
        self.assertIn("A snippet.", text)
        self.assertNotIn("[cached]", text)

    def test_format_search_results_cached(self):
        from source_radar.mcp.server import _format_search_results
        text = _format_search_results("q", [{"title": "T", "url": "U", "snippet": "S"}], cached=True)
        self.assertIn("[cached]", text)


class TestFetchFormat(unittest.TestCase):
    def test_format_fetch_result(self):
        from source_radar.mcp.server import _format_fetch_result
        text = _format_fetch_result(
            "https://example.com", "Hello world", 5000, "trafilatura", 8000, False,
        )
        self.assertIn("https://example.com", text)
        self.assertIn("trafilatura", text)
        self.assertIn("5000", text)
        self.assertIn("Hello world", text)
        self.assertNotIn("cached", text)

    def test_format_fetch_result_cached(self):
        from source_radar.mcp.server import _format_fetch_result
        text = _format_fetch_result(
            "https://example.com", "Content", 100, "trafilatura", 8000, True,
        )
        self.assertIn("cached", text)


class TestNormalizeSite(unittest.TestCase):
    def test_plain_hostname(self):
        from source_radar.mcp.server import _normalize_site
        self.assertEqual(_normalize_site("hltv.org"), "hltv.org")

    def test_strips_site_prefix(self):
        from source_radar.mcp.server import _normalize_site
        self.assertEqual(_normalize_site("site:hltv.org"), "hltv.org")

    def test_strips_https(self):
        from source_radar.mcp.server import _normalize_site
        self.assertEqual(_normalize_site("https://hltv.org"), "hltv.org")

    def test_strips_path(self):
        from source_radar.mcp.server import _normalize_site
        self.assertEqual(_normalize_site("hltv.org/events/123"), "hltv.org")

    def test_strips_site_prefix_and_url(self):
        from source_radar.mcp.server import _normalize_site
        self.assertEqual(_normalize_site("site:https://hltv.org/events"), "hltv.org")

    def test_empty_returns_none(self):
        from source_radar.mcp.server import _normalize_site
        self.assertIsNone(_normalize_site(""))
        self.assertIsNone(_normalize_site("  "))

    def test_lowercases(self):
        from source_radar.mcp.server import _normalize_site
        self.assertEqual(_normalize_site("HLTV.ORG"), "hltv.org")


class TestWebSearchTool(unittest.TestCase):
    @patch("source_radar.mcp.server.put_cached_result")
    @patch("source_radar.mcp.server.get_cached_result", return_value=(None, 0))
    def test_web_search_returns_results(self, mock_get, mock_put):
        from source_radar.mcp.server import handle_search
        from source_radar.acquisition import AcquisitionResult, CandidateSource

        fake_result = AcquisitionResult(
            provider="search", provider_type="search", status="ok",
            reason="candidates-found", message="ok",
            candidates=[
                CandidateSource(title="T1", url="https://a.com", snippet="S1", provider="search", source_type="search-result"),
                CandidateSource(title="T2", url="https://b.com", snippet="S2", provider="search", source_type="search-result"),
            ],
        )

        async def run():
            with patch("source_radar.mcp.server.BingSearchProvider") as MockProvider:
                MockProvider.return_value.collect.return_value = fake_result
                return await handle_search({"query": "test"})

        result = asyncio.run(run())
        self.assertFalse(result.isError)
        text = result.content[0].text
        self.assertIn("T1", text)
        self.assertIn("T2", text)
        self.assertIn("https://a.com", text)
        self.assertIn("2 条", text)

    @patch("source_radar.mcp.server.put_cached_result")
    @patch("source_radar.mcp.server.get_cached_result", return_value=(None, 0))
    def test_web_search_no_results(self, mock_get, mock_put):
        from source_radar.mcp.server import handle_search
        from source_radar.acquisition import AcquisitionResult

        fake_result = AcquisitionResult(
            provider="search", provider_type="search", status="no-evidence",
            reason="no-candidates", message="No results.",
            candidates=[],
        )

        async def run():
            with patch("source_radar.mcp.server.BingSearchProvider") as MockProvider:
                MockProvider.return_value.collect.return_value = fake_result
                return await handle_search({"query": "xyz"})

        result = asyncio.run(run())
        self.assertFalse(result.isError)
        self.assertIn("未找到", result.content[0].text)

    def test_web_search_empty_query(self):
        from source_radar.mcp.server import handle_search

        async def run():
            return await handle_search({"query": ""})

        result = asyncio.run(run())
        self.assertTrue(result.isError)
        self.assertIn("query is required", result.content[0].text)

    @patch("source_radar.mcp.server.put_cached_result")
    @patch("source_radar.mcp.server.get_cached_result", return_value=(None, 0))
    def test_web_search_error(self, mock_get, mock_put):
        from source_radar.mcp.server import handle_search
        from source_radar.acquisition import AcquisitionResult

        fake_result = AcquisitionResult(
            provider="search", provider_type="search", status="error",
            reason="ConnectionError", message="Connection timed out",
        )

        async def run():
            with patch("source_radar.mcp.server.BingSearchProvider") as MockProvider:
                MockProvider.return_value.collect.return_value = fake_result
                return await handle_search({"query": "test"})

        result = asyncio.run(run())
        self.assertTrue(result.isError)
        self.assertIn("Connection timed out", result.content[0].text)

    @patch("source_radar.mcp.server.put_cached_result")
    @patch("source_radar.mcp.server.get_cached_result", return_value=(None, 0))
    def test_web_search_with_site_filter(self, mock_get, mock_put):
        from source_radar.mcp.server import handle_search
        from source_radar.acquisition import AcquisitionResult, CandidateSource

        fake_result = AcquisitionResult(
            provider="search", provider_type="search", status="ok",
            reason="candidates-found", message="ok",
            candidates=[
                CandidateSource(title="HLTV", url="https://hltv.org/events/123", snippet="S1", provider="search", source_type="search-result"),
            ],
        )

        captured = {}

        async def run():
            with patch("source_radar.mcp.server.BingSearchProvider") as MockProvider:
                MockProvider.return_value.collect.return_value = fake_result
                result = await handle_search({"query": "CS2 Major 2026", "site": "hltv.org"})
                captured["args"] = MockProvider.return_value.collect.call_args
                return result

        result = asyncio.run(run())
        self.assertFalse(result.isError)
        req = captured["args"][0][0]
        self.assertEqual(req.site, "hltv.org")
        self.assertEqual(req.query, "CS2 Major 2026")

    @patch("source_radar.mcp.server.put_cached_result")
    @patch("source_radar.mcp.server.get_cached_result", return_value=(None, 0))
    def test_web_search_with_page(self, mock_get, mock_put):
        from source_radar.mcp.server import handle_search
        from source_radar.acquisition import AcquisitionResult, CandidateSource

        fake_result = AcquisitionResult(
            provider="search", provider_type="search", status="ok",
            reason="candidates-found", message="ok",
            candidates=[
                CandidateSource(title="T1", url="https://a.com", snippet="S1", provider="search", source_type="search-result"),
            ],
        )

        captured = {}

        async def run():
            with patch("source_radar.mcp.server.BingSearchProvider") as MockProvider:
                MockProvider.return_value.collect.return_value = fake_result
                result = await handle_search({"query": "test", "page": 2})
                captured["args"] = MockProvider.return_value.collect.call_args
                return result

        result = asyncio.run(run())
        self.assertFalse(result.isError)
        req = captured["args"][0][0]
        self.assertEqual(req.page, 2)

    def test_web_search_schema_includes_site_and_page(self):
        from source_radar.mcp.server import create_server
        server = create_server()

        async def get_tools():
            handler = server.request_handlers[types.ListToolsRequest]
            result = await handler(types.ListToolsRequest(method="tools/list", params=None))
            return result.root.tools

        tools = asyncio.run(get_tools())
        search_tool = next(t for t in tools if t.name == "web_search")
        self.assertIn("site", search_tool.inputSchema["properties"])
        self.assertIn("page", search_tool.inputSchema["properties"])


class TestFetchUrlTool(unittest.TestCase):
    @patch("source_radar.mcp.server.put_cached_result")
    @patch("source_radar.mcp.server.get_cached_result", return_value=(None, 0))
    def test_fetch_url_returns_content(self, mock_get, mock_put):
        from source_radar.mcp.server import handle_fetch
        from source_radar.acquisition import AcquisitionResult, SourceItem

        fake_result = AcquisitionResult(
            provider="trafilatura", provider_type="generic-crawler", status="ok",
            reason="items-found", message="ok",
            items=[SourceItem(
                source_type="web-page", title="Page", url="https://example.com",
                snippet="S", adapter="trafilatura",
                raw_content="A" * 500, raw_content_length=500,
                metadata={"extractor": "trafilatura"},
            )],
        )

        async def run():
            with patch("source_radar.mcp.server._collect_with_fallback", return_value=fake_result):
                return await handle_fetch({"url": "https://example.com"})

        result = asyncio.run(run())
        self.assertFalse(result.isError)
        text = result.content[0].text
        self.assertIn("trafilatura", text)
        self.assertIn("500", text)
        self.assertIn("A" * 500, text)

    def test_fetch_url_blocks_localhost(self):
        from source_radar.mcp.server import handle_fetch

        async def run():
            return await handle_fetch({"url": "http://localhost/x"})

        result = asyncio.run(run())
        self.assertTrue(result.isError)
        self.assertIn("local", result.content[0].text.lower())

    def test_fetch_url_blocks_private_ip(self):
        from source_radar.mcp.server import handle_fetch

        async def run():
            return await handle_fetch({"url": "http://192.168.1.1/admin"})

        result = asyncio.run(run())
        self.assertTrue(result.isError)

    def test_fetch_url_blocks_file_scheme(self):
        from source_radar.mcp.server import handle_fetch

        async def run():
            return await handle_fetch({"url": "file:///etc/passwd"})

        result = asyncio.run(run())
        self.assertTrue(result.isError)

    def test_fetch_url_empty_url(self):
        from source_radar.mcp.server import handle_fetch

        async def run():
            return await handle_fetch({"url": ""})

        result = asyncio.run(run())
        self.assertTrue(result.isError)

    @patch("source_radar.mcp.server.put_cached_result")
    @patch("source_radar.mcp.server.get_cached_result", return_value=(None, 0))
    def test_fetch_url_truncation(self, mock_get, mock_put):
        from source_radar.mcp.server import handle_fetch
        from source_radar.acquisition import AcquisitionResult, SourceItem

        long_content = "X" * 20000
        fake_result = AcquisitionResult(
            provider="trafilatura", provider_type="generic-crawler", status="ok",
            reason="items-found", message="ok",
            items=[SourceItem(
                source_type="web-page", title="Page", url="https://example.com",
                snippet="S", adapter="trafilatura",
                raw_content=long_content, raw_content_length=20000,
                metadata={"extractor": "trafilatura"},
            )],
        )

        async def run():
            with patch("source_radar.mcp.server._collect_with_fallback", return_value=fake_result):
                return await handle_fetch({"url": "https://example.com", "max_chars": 1000})

        result = asyncio.run(run())
        self.assertFalse(result.isError)
        text = result.content[0].text
        self.assertIn("1000", text)
        content_start = text.index("\n\n") + 2
        content = text[content_start:]
        self.assertLessEqual(len(content), 1000 + 10)

    @patch("source_radar.mcp.server.put_cached_result")
    @patch("source_radar.mcp.server.get_cached_result", return_value=(None, 0))
    def test_fetch_url_no_content(self, mock_get, mock_put):
        from source_radar.mcp.server import handle_fetch
        from source_radar.acquisition import AcquisitionResult

        fake_result = AcquisitionResult(
            provider="trafilatura", provider_type="generic-crawler", status="no-evidence",
            reason="no-usable-items", message="No content.",
            items=[],
        )

        async def run():
            with patch("source_radar.mcp.server._collect_with_fallback", return_value=fake_result):
                return await handle_fetch({"url": "https://example.com"})

        result = asyncio.run(run())
        self.assertTrue(result.isError)
        self.assertIn("无法提取", result.content[0].text)

    def test_fetch_url_unknown_tool(self):
        from source_radar.mcp.server import create_server
        server = create_server()

        async def run():
            handler = server.request_handlers[types.CallToolRequest]
            req = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(name="nonexistent_tool", arguments={}),
            )
            return await handler(req)

        result = asyncio.run(run())
        self.assertTrue(result.root.isError)
        self.assertIn("Unknown tool", result.root.content[0].text)


class TestWikiDomainFallback(unittest.TestCase):
    def test_wiki_domain_triggers_crawl4ai_fallback(self):
        from source_radar.mcp.server import _collect_with_fallback
        from source_radar.acquisition import AcquisitionRequest, AcquisitionResult, SourceItem

        nav_content = "Navigation\nHome\nAbout\nContact\n" + "Menu item\n" * 50
        trafilatura_result = AcquisitionResult(
            provider="trafilatura", provider_type="generic-crawler", status="ok",
            reason="items-found", message="ok",
            items=[SourceItem(
                source_type="web-page", title="Liquipedia", url="https://liquipedia.net/counterstrike/Main_Page",
                snippet="S", adapter="trafilatura",
                raw_content=nav_content, raw_content_length=len(nav_content),
                metadata={"extractor": "trafilatura"},
            )],
        )
        real_content = "IEM Cologne Major 2026 is a Counter-Strike 2 Major tournament held in Cologne, Germany."
        crawl4ai_result = AcquisitionResult(
            provider="crawl4ai", provider_type="generic-crawler", status="ok",
            reason="items-found", message="ok",
            items=[SourceItem(
                source_type="web-page", title="Liquipedia", url="https://liquipedia.net/counterstrike/Main_Page",
                snippet="S", adapter="crawl4ai",
                raw_content=real_content, raw_content_length=len(real_content),
            )],
        )

        request = AcquisitionRequest(query="", url="https://liquipedia.net/counterstrike/Main_Page", limit=1)

        with patch("source_radar.mcp.server.TrafilaturaProvider") as MockTraf:
            MockTraf.return_value.collect.return_value = trafilatura_result
            with patch("source_radar.acquisition.Crawl4AIProvider") as MockCrawl:
                MockCrawl.return_value.collect.return_value = crawl4ai_result
                result = _collect_with_fallback(request)

        self.assertEqual(result.items[0].metadata.get("extractor"), "crawl4ai")
        self.assertIn("IEM Cologne", result.items[0].raw_content)

    def test_non_wiki_domain_stays_with_trafilatura(self):
        from source_radar.mcp.server import _collect_with_fallback
        from source_radar.acquisition import AcquisitionRequest, AcquisitionResult, SourceItem

        good_content = "This is a normal article with plenty of real content. " * 20
        trafilatura_result = AcquisitionResult(
            provider="trafilatura", provider_type="generic-crawler", status="ok",
            reason="items-found", message="ok",
            items=[SourceItem(
                source_type="web-page", title="Article", url="https://example.com/article",
                snippet="S", adapter="trafilatura",
                raw_content=good_content, raw_content_length=len(good_content),
                metadata={"extractor": "trafilatura"},
            )],
        )

        request = AcquisitionRequest(query="", url="https://example.com/article", limit=1)

        with patch("source_radar.mcp.server.TrafilaturaProvider") as MockTraf:
            MockTraf.return_value.collect.return_value = trafilatura_result
            result = _collect_with_fallback(request)

        self.assertEqual(result.items[0].metadata.get("extractor"), "trafilatura")

    def test_wiki_domain_crawl4ai_import_error(self):
        from source_radar.mcp.server import _collect_with_fallback
        from source_radar.acquisition import AcquisitionRequest, AcquisitionResult, SourceItem

        nav_content = "Navigation\n" + "Menu\n" * 50
        trafilatura_result = AcquisitionResult(
            provider="trafilatura", provider_type="generic-crawler", status="ok",
            reason="items-found", message="ok",
            items=[SourceItem(
                source_type="web-page", title="HLTV", url="https://hltv.org/events",
                snippet="S", adapter="trafilatura",
                raw_content=nav_content, raw_content_length=len(nav_content),
                metadata={"extractor": "trafilatura"},
            )],
        )

        request = AcquisitionRequest(query="", url="https://hltv.org/events", limit=1)

        with patch("source_radar.mcp.server.TrafilaturaProvider") as MockTraf:
            MockTraf.return_value.collect.return_value = trafilatura_result
            with patch("source_radar.acquisition.Crawl4AIProvider", side_effect=ImportError("No module")):
                result = _collect_with_fallback(request)

        self.assertEqual(result.status, "error")
        self.assertIn("Crawl4AI", result.message)
        self.assertIn("not installed", result.message)

    def test_wiki_domain_crawl4ai_runtime_error(self):
        from source_radar.mcp.server import _collect_with_fallback
        from source_radar.acquisition import AcquisitionRequest, AcquisitionResult, SourceItem

        nav_content = "Navigation\n" + "Menu\n" * 50
        trafilatura_result = AcquisitionResult(
            provider="trafilatura", provider_type="generic-crawler", status="ok",
            reason="items-found", message="ok",
            items=[SourceItem(
                source_type="web-page", title="HLTV", url="https://hltv.org/events",
                snippet="S", adapter="trafilatura",
                raw_content=nav_content, raw_content_length=len(nav_content),
                metadata={"extractor": "trafilatura"},
            )],
        )

        request = AcquisitionRequest(query="", url="https://hltv.org/events", limit=1)

        with patch("source_radar.mcp.server.TrafilaturaProvider") as MockTraf:
            MockTraf.return_value.collect.return_value = trafilatura_result
            with patch("source_radar.acquisition.Crawl4AIProvider") as MockCrawl:
                MockCrawl.return_value.collect.side_effect = RuntimeError("Browser not found")
                result = _collect_with_fallback(request)

        self.assertEqual(result.status, "error")
        self.assertIn("Crawl4AI", result.message)
        self.assertIn("Browser not found", result.message)


class TestSearchGithubTool(unittest.TestCase):
    def test_lists_four_tools(self):
        from source_radar.mcp.server import create_server
        server = create_server()

        async def get_tools():
            handler = server.request_handlers[types.ListToolsRequest]
            result = await handler(types.ListToolsRequest(method="tools/list", params=None))
            return result.root.tools

        tools = asyncio.run(get_tools())
        names = [t.name for t in tools]
        self.assertIn("search_github", names)
        self.assertEqual(len(names), 4)

    def test_search_github_schema(self):
        from source_radar.mcp.server import create_server
        server = create_server()

        async def get_tools():
            handler = server.request_handlers[types.ListToolsRequest]
            result = await handler(types.ListToolsRequest(method="tools/list", params=None))
            return result.root.tools

        tools = asyncio.run(get_tools())
        gh_tool = next(t for t in tools if t.name == "search_github")
        self.assertIn("query", gh_tool.inputSchema["properties"])
        self.assertIn("limit", gh_tool.inputSchema["properties"])
        self.assertIn("query", gh_tool.inputSchema["required"])

    @patch("source_radar.mcp.server.put_cached_result")
    @patch("source_radar.mcp.server.get_cached_result", return_value=(None, 0))
    def test_search_github_returns_results(self, mock_get, mock_put):
        from source_radar.mcp.server import handle_search_github

        fake_issues = [
            {
                "title": "Bug: crash on startup",
                "html_url": "https://github.com/foo/bar/issues/1",
                "state": "open",
                "body": "App crashes when launching on Windows",
                "labels": [{"name": "bug"}],
            },
        ]

        async def run():
            with patch("source_radar.mcp.server.GithubSearchProvider") as MockProvider:
                MockProvider.return_value.search_issues.return_value = fake_issues
                return await handle_search_github({"query": "crash"})

        result = asyncio.run(run())
        self.assertFalse(result.isError)
        text = result.content[0].text
        self.assertIn("Bug: crash on startup", text)
        self.assertIn("https://github.com/foo/bar/issues/1", text)
        self.assertIn("1 条", text)
        self.assertIn("Issue open", text)
        self.assertIn("bug", text)

    def test_search_github_empty_query(self):
        from source_radar.mcp.server import handle_search_github

        async def run():
            return await handle_search_github({"query": ""})

        result = asyncio.run(run())
        self.assertTrue(result.isError)
        self.assertIn("query is required", result.content[0].text)

    @patch("source_radar.mcp.server.put_cached_result")
    @patch("source_radar.mcp.server.get_cached_result", return_value=(None, 0))
    def test_search_github_no_results(self, mock_get, mock_put):
        from source_radar.mcp.server import handle_search_github

        async def run():
            with patch("source_radar.mcp.server.GithubSearchProvider") as MockProvider:
                MockProvider.return_value.search_issues.return_value = []
                return await handle_search_github({"query": "xyznonexistent"})

        result = asyncio.run(run())
        self.assertFalse(result.isError)
        self.assertIn("未找到", result.content[0].text)

    @patch("source_radar.mcp.server.put_cached_result")
    @patch("source_radar.mcp.server.get_cached_result", return_value=(None, 0))
    def test_search_github_error(self, mock_get, mock_put):
        from source_radar.mcp.server import handle_search_github

        async def run():
            with patch("source_radar.mcp.server.GithubSearchProvider") as MockProvider:
                MockProvider.return_value.search_issues.side_effect = Exception("API rate limit exceeded")
                return await handle_search_github({"query": "test"})

        result = asyncio.run(run())
        self.assertTrue(result.isError)
        self.assertIn("API rate limit exceeded", result.content[0].text)


class TestSearchChinesePlatformsTool(unittest.TestCase):
    def test_lists_four_tools(self):
        from source_radar.mcp.server import create_server
        server = create_server()

        async def get_tools():
            handler = server.request_handlers[types.ListToolsRequest]
            result = await handler(types.ListToolsRequest(method="tools/list", params=None))
            return result.root.tools

        tools = asyncio.run(get_tools())
        names = [t.name for t in tools]
        self.assertIn("search_chinese_platforms", names)
        self.assertEqual(len(names), 4)

    def test_search_chinese_platforms_schema(self):
        from source_radar.mcp.server import create_server
        server = create_server()

        async def get_tools():
            handler = server.request_handlers[types.ListToolsRequest]
            result = await handler(types.ListToolsRequest(method="tools/list", params=None))
            return result.root.tools

        tools = asyncio.run(get_tools())
        tool = next(t for t in tools if t.name == "search_chinese_platforms")
        self.assertIn("query", tool.inputSchema["properties"])
        self.assertIn("platforms", tool.inputSchema["properties"])
        self.assertIn("limit", tool.inputSchema["properties"])
        self.assertIn("query", tool.inputSchema["required"])

    @patch("source_radar.mcp.server.put_cached_result")
    @patch("source_radar.mcp.server.get_cached_result", return_value=(None, 0))
    def test_search_chinese_platforms_returns_results(self, mock_get, mock_put):
        from source_radar.mcp.server import handle_search_chinese_platforms
        from source_radar.acquisition import AcquisitionResult, SourceItem

        fake_result = AcquisitionResult(
            provider="mediacrawler", provider_type="external-bridge", status="ok",
            reason="items-found", message="ok",
            items=[SourceItem(
                source_type="community-post", title="超频体验分享",
                url="https://www.xiaohongshu.com/abc123",
                snippet="9800X3D 超频到 5.7GHz，温度控制在 80 度以内",
                adapter="mediacrawler",
                metadata={"platform": "xhs", "author": "科技宅小明", "published_at": "2026-06-10"},
            )],
        )

        captured = {}

        async def run():
            with patch("source_radar.mcp.server.ExternalBridgeProvider") as MockBridge:
                MockBridge.return_value.status.return_value = AcquisitionResult(
                    provider="mediacrawler", provider_type="external-bridge",
                    status="ok", reason="ready", message="ok",
                )
                MockBridge.return_value.collect.return_value = fake_result
                result = await handle_search_chinese_platforms({"query": "9800X3D 超频"})
                captured["collect_args"] = MockBridge.return_value.collect.call_args
                return result

        result = asyncio.run(run())
        self.assertFalse(result.isError)
        text = result.content[0].text
        self.assertIn("超频体验分享", text)
        self.assertIn("小红书", text)
        self.assertIn("科技宅小明", text)

    def test_search_chinese_platforms_empty_query(self):
        from source_radar.mcp.server import handle_search_chinese_platforms

        async def run():
            return await handle_search_chinese_platforms({"query": ""})

        result = asyncio.run(run())
        self.assertTrue(result.isError)
        self.assertIn("query is required", result.content[0].text)

    @patch("source_radar.mcp.server.put_cached_result")
    @patch("source_radar.mcp.server.get_cached_result", return_value=(None, 0))
    def test_search_chinese_platforms_bridge_down(self, mock_get, mock_put):
        from source_radar.mcp.server import handle_search_chinese_platforms
        from source_radar.acquisition import AcquisitionResult

        async def run():
            with patch("source_radar.mcp.server.ExternalBridgeProvider") as MockBridge:
                MockBridge.return_value.status.return_value = AcquisitionResult(
                    provider="mediacrawler", provider_type="external-bridge",
                    status="error", reason="service-unreachable",
                    message="Bridge not running",
                )
                return await handle_search_chinese_platforms({"query": "test"})

        result = asyncio.run(run())
        self.assertTrue(result.isError)
        self.assertIn("bridge", result.content[0].text.lower())

    @patch("source_radar.mcp.server.put_cached_result")
    @patch("source_radar.mcp.server.get_cached_result", return_value=(None, 0))
    def test_search_chinese_platforms_with_platforms_filter(self, mock_get, mock_put):
        from source_radar.mcp.server import handle_search_chinese_platforms
        from source_radar.acquisition import AcquisitionResult

        fake_result = AcquisitionResult(
            provider="mediacrawler", provider_type="external-bridge", status="ok",
            reason="items-found", message="ok", items=[],
        )

        captured = {}

        async def run():
            with patch("source_radar.mcp.server.ExternalBridgeProvider") as MockBridge:
                MockBridge.return_value.status.return_value = AcquisitionResult(
                    provider="mediacrawler", provider_type="external-bridge",
                    status="ok", reason="ready", message="ok",
                )
                MockBridge.return_value.collect.return_value = fake_result
                result = await handle_search_chinese_platforms({"query": "test", "platforms": ["xhs", "wb"]})
                captured["collect_args"] = MockBridge.return_value.collect.call_args
                return result

        result = asyncio.run(run())
        self.assertFalse(result.isError)
        req = captured["collect_args"][0][0]
        self.assertEqual(req.platforms, ["xhs", "wb"])


class TestCLIMCPCommand(unittest.TestCase):
    def test_parser_accepts_mcp(self):
        from source_radar.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["mcp"])
        self.assertEqual(args.command, "mcp")


if __name__ == "__main__":
    unittest.main()
