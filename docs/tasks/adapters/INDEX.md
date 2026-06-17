# adapters Module Index

## Current Status

`adapters` has fixture, web, official, GitHub, search, Baidu fallback search, required SearXNG bridge search, Trafilatura, Crawl4AI, and AI-callable external bridge providers wrapped by the acquisition provider layer used by both M6 `ask` analysis and strict `verify`.

## Active Scope

Python-first CLI；自研低成本采集覆盖普通网页、搜索结果、官网/公告、GitHub；定义稳定 adapter 协议；生成标准证据卡；调用 LLM 输出综合信息分析和严格核验判断；支持平台配置和本地 Cookie/Token 边界；提供 adapter health/probe；记录第三方许可证与 optional integration 策略；查不到时输出 no-evidence。

## North Star Contribution

This domain supports the core flow:

用户通过 CLI 输入问题或断言；系统生成检索计划，优先使用低成本采集来源；adapter 输出统一来源项；证据模块清洗去重并压缩成证据卡；LLM 基于证据卡输出综合回答、搜索结果要点、来源分布、分歧/争议和噪音提示；报告模块输出终端摘要、JSON 或 Markdown。

## Implemented Features

- Fixture collection returns a local README-backed source item for matching source-radar claims.
- Unknown claims return no source items, enabling stable no-evidence behavior.
- `web` extracts title and useful text from normal HTML pages.
- `official` extracts HTML announcement/page content and marks it as `official-announcement`.
- `github` extracts repository metadata from GitHub REST API shape.
- M3 health checks report adapter status without requiring live checks by default.
- M5 acquisition providers expose these adapters through a unified provider contract with status, candidates, item counts, and failure reasons.
- `search` discovers candidate sources and converts them into source items for generic claims.
- `search-baidu` is available as a fallback for Chinese search cases where the primary search provider fails entity handling, while still reporting search quality through the provider contract.
- `searxng` is the required external bridge provider for free/self-hosted real websearch. It prefers a configured `SOURCE_RADAR_SEARXNG_ENDPOINT` / provider config endpoint and auto-discovers `http://127.0.0.1:3004` when the bridge health check passes.
- `dispatch_search()` is the shared websearch path used by MCP and other callers that need consistent SearXNG -> Bing -> Baidu fallback behavior.
- `dispatch_search()` preserves SearXNG degraded/no-evidence warnings when it falls back to Bing/Baidu, so callers can explain upstream CAPTCHA/rate-limit exhaustion instead of presenting fallback results without context.
- `trafilatura` and `crawl4ai` local generic crawler providers collect normal and dynamic web pages after search discovery.
- Crawl4AI stores its database/cache under an ignored local `.source-radar/crawl4ai` runtime directory when no upstream base directory is configured.
- `firecrawl`, `mediacrawler`, and `searxng` external bridge providers keep third-party source outside the core repository.
- External bridges now use `source-radar.bridge.v1` manifest/health/collect routes so the built-in agent can call healthy bridges and report actionable diagnostics when they fail.
- First-party bridge runners adapt optional Firecrawl MCP search results, MediaCrawler WebUI API output files, and SearXNG JSON search results into source-radar source items.
- M6 `ask` uses the same providers for comprehensive information analysis, with local service startup available through `--local-services` / `source-radar.ps1 ask`.

## Pending Features

Key workflows to implement or validate:

- Evidence deduplication, compression, stable citations, and richer source metadata.
- More real provider coverage for restricted Chinese platforms through local-safe config and bridge boundaries.
- Real SearXNG smoke testing and possible engine lifecycle wrapping once the bridge behavior is validated locally.

## Last Effective Design

- Product context: `docs/context/project-overview.md`
- Architecture context: `docs/context/architecture.md`
- Active design: `docs/tasks/cli/2026-05-23-verify-fixture-design.md`

## Validation

Tests cover deterministic fixture collection, local HTML extraction for web and official sources, GitHub JSON metadata extraction, search provider parsing with mocked HTML, Baidu parser/fallback behavior, Trafilatura/Crawl4AI provider behavior, AI-callable external bridge behavior with mocked manifest/health/collect endpoints, bridge runner adaptation for Firecrawl, MediaCrawler, and SearXNG, no-evidence behavior, dispatch search auto-discovery/fallback behavior including SearXNG warning preservation, required SearXNG setup/status semantics, and provider-aware probe/health statuses with `unittest`. Tests do not require live network access; local smoke verification also confirmed real Trafilatura, Crawl4AI, and MediaCrawler bridge collection.

## Known Issues

- 第三方项目许可证可能限制集成方式
- 中文平台页面和风控变化快
- 用户 Cookie/Token 涉及本地凭据安全
- LLM 可能过度推断
- 搜索引擎和平台可能限流
- adapter 健康探针需要低成本且不过度访问
- Apache-2.0 核心必须避免复制不兼容源码
- SearXNG bridge quality depends on the configured upstream engines and JSON format availability.

## Next Useful Moves

- M6 keeps the M5 provider foundation and adds a user-facing `ask` analysis path over it.
- Preserve no-evidence semantics when real collection returns no usable items.
- Next adapter work should focus on richer evidence metadata and additional real providers without breaking license boundaries.
- Prefer improving web search through bridge-backed engines such as SearXNG before adding more first-party HTML parsers.

Before closing work in this module, update `Current Status`, `Implemented Features`, `Validation`, `Known Issues`, and `Next Useful Moves` if any of them changed.
