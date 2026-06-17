# cli Module Index

## Current Status

`cli` has three analysis modes: `ask` (单轮综合), `verify` (真假核验), `research` (深度多轮研究). v3 hardening complete: adaptive collection (source=auto, max_tools=3, mediacrawler not default), AI session relevance evaluator with lexical fallback, acquisition cache with cache_age_seconds and provider_signature, verify strictness code-level guard, 10 new AgentTrace fields, elapsed_ms/cache_age_seconds per tool_call, session context for ask/verify (research excluded). Also includes `install`/`install --agent`/`setup-plan` for agent-friendly setup, `engine` series for crawler lifecycle including local SearXNG install/start/stop/status, `bridge searxng` for the required free/self-hosted search bridge, `uninstall` with dry-run, `cookie` with browser capture + `set`/`show` for AI agents, `config test-ai` with model list, and the `source-radar.ps1` helper. All subprocess calls globally patched with CREATE_NO_WINDOW; MediaCrawler auto-patched to use pythonw.exe on Windows. AI config auto-discovered from project-local `.source-radar/config.json`.

## Active Scope

Python-first CLI；自研低成本采集覆盖普通网页、搜索结果、官网/公告、GitHub；定义稳定 adapter 协议；生成标准证据卡；调用 LLM 输出综合信息分析和严格核验判断；支持平台配置和本地 Cookie/Token 边界；提供 adapter health/probe；记录第三方许可证与 optional integration 策略；查不到时输出 no-evidence。

## North Star Contribution

This domain supports the core flow:

用户通过 CLI 输入问题或断言；系统生成检索计划，优先使用低成本采集来源；adapter 输出统一来源项；证据模块清洗去重并压缩成证据卡；LLM 基于证据卡输出综合回答、搜索结果要点、来源分布、分歧/争议和噪音提示；报告模块输出终端摘要、JSON 或 Markdown。

## Implemented Features

- Three analysis modes: `ask` (单轮综合), `verify` (真假核验), `research` (深度多轮研究，Planner→Collect→Dedupe→Synthesize)
- **v3 adaptive collection**: `source=auto` 时 ask/verify 渐进采集，先 search，AI evaluator 决定是否继续，max_tools=3，mediacrawler 不默认运行
- **v3 session context**: ask/verify 支持 `--session`/`--no-session`，AI evaluator 优先 + lexical fallback，默认读最近 10 条/24 小时，session record 含 tools_used/tools_skipped/cache_keys/elapsed_ms
- **v3 acquisition cache**: `cache status/clear/prune`，实时 query 不缓存，只缓存 ok/items-found/candidates-found，CACHE_ADAPTER_VERSION=v3-adaptive-1，provider_signature 维度，cache_age_seconds
- **v3 trace fields**: AgentTrace 新增 context_used/session_id/cache_hit_count/fresh_tool_count/actually_used_tools/skipped_tools/reused_evidence_count/fresh_evidence_count 等 10 个字段，tool_call 含 elapsed_ms/cache_age_seconds/limit
- **v3 verify strictness**: code-level guard `_verify_evidence_needs_more`，仅 search-result 时强制 trafilatura，不自动跑 mediacrawler
- **v3 progress**: ask/verify/research 默认 stderr progress，`--quiet` 关闭，JSON stdout 不被污染
- `research` supports `--max-rounds 2` with evaluator loop (v2), `--local-services`, `--progress`, JSON/Markdown output；research 不接 session context
- `install --agent` for non-interactive AI agent setup; `setup-plan --format json` for structured configuration requirements
- `uninstall` with dry-run default, `--project`/`--skill`/`--user-config`/`--all` scopes
- `cookie set --platform <key> --value "<cookie>"` and `cookie show` for AI agent cookie management
- `engine start/stop mediacrawler` manages API+bridge lifecycle; services survive context exit, stopped via `engine stop`
- `bridge searxng --upstream-url http://127.0.0.1:8080 --port 3004` exposes a SearXNG upstream through the standard source-radar bridge contract.
- `engine install/start/stop/status searxng` manages a local SearXNG checkout, virtualenv, JSON-enabled `settings.yml`, upstream process, bridge process, and provider endpoint config.
- `setup-plan` marks SearXNG bridge as required for real websearch; `ready_for_use` is false until both AI config and SearXNG bridge config/auto-discovery are present.
- `engine install` split into `--core`/`--browser`/`--community`/`--all`; defaults to core only
- `config test-ai --format json` returns model list for AI agent model selection
- AI provider supports Bearer token + `x-api-key` header for Anthropic/Gemini compatibility
- AI config auto-discovered from project-local `.source-radar/config.json`
- All subprocess calls globally patched with `CREATE_NO_WINDOW`; MediaCrawler auto-patched to use `pythonw.exe`
- `_background_python(root)` no-fallback; `_hidden_spawn_opts()` unified across engine/runtime/wrapper
- Skill wrapper `run.py`: doctor, ask/verify/research, UTF-8 encoding, project persistence, global Popen patch
- Cookie import guide: Network request header (primary), Application (backup), manual + security notes
- License boundaries: Trafilatura (GPL-3.0, optional extra), Crawl4AI (Apache-2.0), MediaCrawler (external bridge)
- SearXNG stays external and is consumed through the bridge; the CLI does not vendor or parse SearXNG internals.
- README in Chinese, AI agent install path first, `uv run python -m source_radar install --agent`

## Pending Features

Key workflows to implement or validate:

- Tighten JSON/Markdown contracts for `ask` analysis and `verify` judgement.
- Broaden config beyond the current AI provider settings to platform switches, credential references, search bridge endpoint/command hints, and collection limits.
- Expand provider planning beyond the first search/default bridge behavior when more restricted-platform providers are introduced.
- Run a real local SearXNG smoke test before relying on it for the 6-case black-box search quality suite.
- research 暂不接 session context（已约定），后续可评估是否加入。

## Last Effective Design

- Product context: `docs/context/project-overview.md`
- Architecture context: `docs/context/architecture.md`
- Active design: `docs/tasks/cli/2026-05-23-verify-fixture-design.md`
- Implementation plan: `docs/tasks/cli/2026-05-23-verify-fixture-plan.md`

## Validation

Current automated coverage uses `unittest` and runs in the project `.venv`. It covers CLI help, bridge help including the SearXNG bridge parser, setup-plan required SearXNG semantics, SearXNG engine help wording, cookie help, cookie unknown-platform reporting, `ask` JSON output, `ask` Markdown output, agent-backed `verify` JSON output, Markdown output, progress-capable helper behavior, local AI config setup/set/show/clear, provider config set/show/clear, packaging metadata, evidence-found behavior, no-evidence behavior, local web collection, local official-page collection, provider-aware probe output, health output, integrations audit output, integrations status output, local service wrapping, PowerShell helper wrapping, local API Chat Completions fallback, cookie capture helpers, Playwright capture_cookies (mocked), run_cookie skip/force/summary/interrupt, JSON contract regression (verify, ask, probe, health, integrations, config, bridge collect — 17 tests).

v3 hardening tests (`test_v3_hardening.py`, 39 tests): default progress/quiet, adaptive max_tools, mediacrawler control, verify strictness guard, cache miss/hit/age/realtime/old-entries/version-info/provider-signature, session relevance (lexical follow-up/unrelated/empty/record-strip/no-secrets), AgentTrace defaults and full fields, JSON report trace field presence, research no-session-parameter/structure/max-rounds.

Full suite: 72 base + 39 v3 hardening + 17 contract = 128 core tests passing (plus additional adapter/CLI/bridge/research tests).

## Known Issues

- 第三方项目许可证可能限制集成方式
- 中文平台页面和风控变化快
- 用户 Cookie/Token 涉及本地凭据安全
- LLM 可能过度推断
- 搜索引擎和平台可能限流
- adapter 健康探针需要低成本且不过度访问
- Apache-2.0 核心必须避免复制不兼容源码
- AI evaluator 对 mediacrawler 选择受模型质量影响，简单 query 也可能被选中（取决于模型理解）

## Next Useful Moves

- M7 (per-platform cookie model) and M8 (JSON contract stabilization) are complete.
- v3 hardening is complete. Do not rewrite ask/verify adaptive collection main flow.
- Next useful CLI work is better setup automation, clearer real-provider smoke workflows, and expanding platform adapter coverage.
- Keep `source-radar.ps1` as the human-friendly entrypoint: one command, visible progress, readable default output.
- Keep SearXNG as a bridge-backed search improvement path; avoid adding more brittle search-engine HTML parser code unless bridge/API paths fail.
- Decide whether to add a tracked dev dependency file for `pytest`.

Before closing work in this module, update `Current Status`, `Implemented Features`, `Validation`, `Known Issues`, and `Next Useful Moves` if any of them changed.

## 2026-06-17 Update

- Fixed `source-radar engine start <name>` crashing with `UnboundLocalError` after the MCP preflight branch imported `run_engine_start` inside `main()`.
- Hardened `restart-mcp.ps1` so MCP processes that exit between enumeration and `Stop-Process` are skipped instead of aborting the restart.
- Verified focused coverage for CLI engine start handling, MCP fetch timeout behavior, and restart script safety. Full `unittest discover` was not used as release evidence in this pass because it exceeded 300 seconds.
- Fixed SearXNG lifecycle cleanup: `engine stop searxng` now removes port listeners and orphaned `_start_searxng.py` / `source_radar bridge searxng` helper processes while excluding the current process ancestor chain.
- Fixed SearXNG upstream launch path on Windows by using an absolute launcher path when starting from the SearXNG checkout directory.
- SearXNG engine health checks now use a browser-like User-Agent instead of Python's default urllib User-Agent, matching bridge collect behavior.
