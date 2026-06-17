# integrations Module Index

## Current Status

`integrations` has M4 external integration registry, M5 provider-bridge-aware status reporting, documented first-party bridge runner boundaries for Firecrawl/MediaCrawler setup, and a required SearXNG bridge path for free/self-hosted real web search.

## Active Scope

Python-first CLI；自研低成本采集覆盖普通网页、搜索结果、官网/公告、GitHub；定义稳定 adapter 协议；生成标准证据卡；调用 LLM 输出综合信息分析和严格核验判断；支持平台配置和本地 Cookie/Token 边界；提供 adapter health/probe；记录第三方许可证与 optional integration 策略；查不到时输出 no-evidence。

## North Star Contribution

This domain supports the core flow:

用户通过 CLI 输入问题或断言；系统生成检索计划，优先使用低成本采集来源；adapter 输出统一来源项；证据模块清洗去重并压缩成证据卡；LLM 基于证据卡输出综合回答、搜索结果要点、来源分布、分歧/争议和噪音提示；报告模块输出终端摘要、JSON 或 Markdown。

## Implemented Features

- MediaCrawler is registered as an optional `external-only` integration.
- Firecrawl is registered as an optional `bridge-or-api-only` integration.
- `integrations status` reports optional bridges as disabled by default.
- `integrations status` reports locally configured provider bridges as `configured` while keeping source code external.
- No third-party crawler source is vendored or imported into the core.
- Firecrawl and MediaCrawler are the selected external crawler backends; SearXNG is the required free/self-hosted search bridge backend for normal real-search use. The integration boundary is not a generic crawler plugin marketplace.
- First-party bridge runners can connect to Firecrawl MCP/API transport and user-run MediaCrawler WebUI API without importing or vendoring their source code.
- `source-radar bridge searxng --upstream-url http://127.0.0.1:8080 --port 3004` adapts SearXNG `/search?format=json` responses into the same bridge contract.
- `source-radar engine install/start/stop/status searxng` manages a local SearXNG checkout, virtualenv, JSON-enabled settings, upstream process, bridge process, and provider endpoint config.
- SearXNG endpoint configuration can be explicit (`SOURCE_RADAR_SEARXNG_ENDPOINT` or `config set-provider --name searxng --endpoint http://127.0.0.1:3004`) or auto-discovered by providers when a healthy bridge is listening on port 3004.
- `integrations status` reports missing SearXNG as `required-missing`; this does not block offline tests but means the real websearch foundation is not ready.
- README and licensing docs state manual install, future auto-download, and prepackaged distribution obligations.

## Pending Features

Key workflows to implement or validate:

- Add richer bridge metadata such as upstream version/fingerprint only after real external services expose it safely through the bridge runner.
- Keep bridge execution separate from Apache-2.0 core source.
- Validate SearXNG lifecycle management with a real local SearXNG install before running the full 6-case black-box quality suite.

## Last Effective Design

- Product context: `docs/context/project-overview.md`
- Architecture context: `docs/context/architecture.md`
- Engineering contract: `docs/engineering/integration-licensing.md`

## Validation

M4/M5 tests cover external integration registry entries, disabled optional bridge status, required-missing SearXNG status, configured bridge status from local provider config, JSON audit output, Markdown audit output, bridge runner contracts including SearXNG response adaptation, SearXNG JSON-disabled health hints, and CLI commands with `unittest`.

2026-06-17 focused validation covered SearXNG bridge User-Agent behavior, Windows launcher path handling, orphaned SearXNG helper cleanup, MCP autostart, degraded source status output, fallback messaging, fetch timeout handling, and restart script safety. A live SearXNG smoke confirmed `engine stop searxng` clears local helper processes and `engine start searxng` relaunches upstream + bridge; current upstream search quality may still degrade to zero results when SearXNG engines report CAPTCHA or too many requests.

## Known Issues

- 第三方项目许可证可能限制集成方式
- 中文平台页面和风控变化快
- 用户 Cookie/Token 涉及本地凭据安全
- LLM 可能过度推断
- 搜索引擎和平台可能限流
- adapter 健康探针需要低成本且不过度访问
- Apache-2.0 核心必须避免复制不兼容源码
- SearXNG 上游必须启用 JSON 输出（通常需要允许 `format=json` / `formats: [html, json]`），否则 bridge health/collect 会失败并提示修复。
- SearXNG can be locally healthy but temporarily unusable when all configured upstream search engines are suspended by CAPTCHA/rate limits; this is an external search-provider condition, not a bridge startup failure.

## Next Useful Moves

- User configuration for external bridge endpoint/command exists locally; the new bridge runners give AI setup flows concrete commands to save and run.
- Keep external integration execution separate from Apache-2.0 core source.
- Add live bridge diagnostics only when they can avoid leaking credentials and avoid vendoring incompatible code.
- Use SearXNG bridge as the next real-search smoke target before adding more search-specific fallback logic.

Before closing work in this module, update `Current Status`, `Implemented Features`, `Validation`, `Known Issues`, and `Next Useful Moves` if any of them changed.
