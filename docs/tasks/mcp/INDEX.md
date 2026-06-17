# MCP Module

## Status

**v1 Shipped** (2026-06-11), **Quality assessment layer** (2026-06-11)

## What's Built

- MCP server module at `app/source_radar/mcp/` — stdio mode, four tools
- `web_search` — calls `BingSearchProvider`, returns formatted results with title/URL/snippet
- `fetch_url` — Trafilatura → Crawl4AI fallback, URL safety validation, content truncation
- `search_github` — searches GitHub issues/PRs via `GithubSearchProvider.search_issues()`, returns title/URL/state/labels/body
- `search_chinese_platforms` — searches Chinese community platforms via MediaCrawler bridge, returns platform/title/URL/snippet/author/date
- CLI entry: `source-radar mcp`
- Optional dependency: `mcp>=1.0` in `pyproject.toml` under `[project.optional-dependencies] mcp`
- Installer (`engine install`) now includes `--extra mcp` automatically
- 102 tests (61 in `tests/test_mcp_server.py` + 41 in `tests/test_quality.py`)
- SKILL.md tracked in git with MCP setup instructions (step 5)
- README updated with MCP Server section (install, config for Claude Code/MiMoCode/Cursor, tools, security)

## Key Files

- `app/source_radar/mcp/__init__.py` — exports `create_server`, `run_stdio`
- `app/source_radar/mcp/server.py` — MCP server core (~260 lines)
- `app/source_radar/cli.py` — `mcp` subcommand (7 lines added)
- `app/source_radar/engine.py` — installer includes `--extra mcp` in uv sync
- `skills/source-radar/SKILL.md` — MCP setup instructions in step 5
- `tests/test_mcp_server.py` — 54 tests covering server creation, tool listing, URL validation, search/fetch/github format, error handling, truncation, site filter, wiki fallback, Crawl4AI errors, normalize_site

## Design Decisions

- Uses `mcp.server.lowlevel.Server` with decorators (not FastMCP) for more control
- Only does collection, not AI agent flow (bypasses ask/verify/research)
- Four tools: `web_search` (Bing, with optional `site` filter), `fetch_url` (Trafilatura+Crawl4AI), `search_github` (GitHub issues), `search_chinese_platforms` (MediaCrawler bridge)
- `search_github` uses `GithubSearchProvider.search_issues()` — public API, searches `/search/issues` API, sorted by recently updated
- Cache key uses `provider_signature="mcp"` to differentiate from CLI cache
- `_collect_with_fallback` forces Crawl4AI for wiki/forum domains (liquipedia.net, hltv.org, fandom.com, etc.) and extracts main content via BeautifulSoup (`mw-parser-output` / `<main>` / `<article>`)
- `_normalize_site` strips `site:`, `https://`, paths from site parameter; `BingSearchProvider` does post-filtering on results (cn.bing.com ignores `site:` operator)
- URL security: blocks localhost, private IPs, non-http/https schemes
- Output: human-readable text for LLM consumption, structured fields preserved in format
- Error reporting: `CallToolResult(isError=True)` with structured error text (URL, provider, suggestion)
- Quality assessment: `QualityAssessment` (score/signals/reason/suggestions) on `AcquisitionResult` and `AcquisitionTrace`. 6 detectors auto-run after `collect()`: navigation-heavy, language-mismatch, domain-concentration, snippet-only, key-platform-missing, semantic-mismatch. MCP output shows ⚠️/💡 for low/medium quality. Cache uses `_quality_version` to invalidate stale entries.

## Bug Fixes (2026-06-11)

- **CallToolResult isError**: `isError` must be on `CallToolResult`, not `TextContent`. `TextContent` has no `isError` field — MCP SDK silently ignores it, so Claude Code/MiMoCode saw errors but couldn't read the message. Fixed by returning `types.CallToolResult(content=[...], isError=True)`.
- **Empty error messages**: `asyncio.TimeoutError` has no message, so `f"Error: {e}"` became `"Error: "`. Fixed with explicit timeout handler that includes URL, timeout duration, and suggestion.
- **Error messages now include**: URL, provider name, exception type, timeout duration, and actionable suggestions.
- **search_github calling collect()**: Was calling `collect()` which searches repos+code, never issues. Fixed to call `_search_issues()` directly to search `/search/issues` API.

## Bug Fixes (2026-06-17)

- `fetch_search_results` now applies a per-page extraction timeout so one slow result cannot block the whole MCP tool call until the client-level timeout. Timed-out pages are reported inline and remaining results can still be returned.
- MCP restart validation found stale stdio connections remain closed after killing the server process in the current Codex session; client reconnect is required before configured MCP tools can be called again.
- `restart-mcp.ps1` now also kills source-radar bridge helpers and the SearXNG launcher/upstream helper, not just MCP stdio processes, so MCP restarts do not keep talking to stale bridge code.
- SearXNG lazy autostart now checks the bridge-reported search status, not just whether the bridge HTTP endpoint responds. This handles the stale-bridge case where the bridge is alive but the SearXNG upstream has exited.
- `web_search` fallback messaging now distinguishes SearXNG unavailable from SearXNG available-but-empty, matching the existing `fetch_search_results` behavior and avoiding false "SearXNG 未运行" diagnostics.
- `source_status` now distinguishes SearXNG `degraded` from `stopped`: degraded status reports CAPTCHA/limit fix guidance instead of suggesting another `engine start searxng`.
- MCP-side SearXNG failures observed with `results=0` and `CAPTCHA/too many requests` are treated as upstream search-engine exhaustion, not as proof that the local bridge failed to start.

## Search Quality Improvements (2026-06-11)

- **Site filtering**: `web_search` tool accepts optional `site` parameter. `AcquisitionRequest` has `site` field; `BingSearchProvider` does post-filtering on results (cn.bing.com ignores `site:` operator). Fetches more candidates (40) when filter active.
- **Site normalization**: `_normalize_site` strips `site:` prefix, `https://`, paths, lowercases. Prevents `site:site:domain` double-prefix.
- **Wiki/forum Crawl4AI fallback**: `_collect_with_fallback` forces Crawl4AI for known wiki/forum domains regardless of Trafilatura output length.
- **Crawl4AI main content extraction**: `_crawl4ai_text` extracts main content from `cleaned_html` via BeautifulSoup (`mw-parser-output` for MediaWiki, `<main>`, `<article>`). Liquipedia pages yield ~38K article content instead of ~357K navigation menus.
- **Crawl4AI error messages**: Import/runtime errors for wiki domains return clear messages with install instructions instead of silent fallback.

## Known Issues

- ~~English queries to cn.bing.com get polluted by Chinese results~~ → FIXED: English queries now route to bing.com
- ~~No domain-based result ranking~~ → FIXED: trusted domains (fifa.com, reuters.com, espn.com, bbc.com, wikipedia.org, github.com, etc.) get boosted to top
- These are search provider fixes, apply to both CLI and MCP

## Not in v1

- HTTP/SSE mode (stdio only for v1)
- `bypass_cache` parameter (cache reuse only)
- English/Chinese query routing (always uses cn.bing.com)

## Next Steps

- **四层采集架构**：
  - 第一层：通用 provider（Bing、fetch_url、GitHub issues、中文平台）✅ 已有
  - 第二层：质量评估 ✅ 已实现（5 个检测器：navigation-heavy、language-mismatch、domain-concentration、snippet-only、key-platform-missing）
  - 第三层：失败原因+建议 ✅ 已实现（QualityAssessment.suggestions 嵌入 AcquisitionResult）
  - 第四层：少量高价值垂直源（GitHub、中文平台、赛事源）— 后续按需加
  - 当前 site-specific hacks（_CRAWL4AI_DOMAINS、mw-parser-output 提取）是临时方案，第四层到位后清理
- v2: consider HTTP/SSE mode for multi-client scenarios
- 设计文档：`docs/compose/specs/2026-06-11-quality-assessment-design.md`
- 实现计划：`docs/compose/plans/2026-06-11-quality-assessment.md`

## Verified Integrations

- **Claude Code**: configured in `~/.claude.json` under `mcpServers` (full path to uv.exe)
- **MiMoCode**: configured in `~/.config/mimocode/mimocode.json` with env vars for encoding
- **Claude Desktop**: same config format as Claude Code
