# health Module Index

## Current Status

`health` has M5 provider-aware probe and platform status reporting. The old M3 adapter smoke semantics are preserved for compatibility, but default health now reports the source-acquisition provider set, bridge readiness, and actionable bridge diagnostics.

## Active Scope

Python-first CLI；自研低成本采集覆盖普通网页、搜索结果、官网/公告、GitHub；定义稳定 adapter 协议；生成标准证据卡；调用 LLM 输出综合信息分析和严格核验判断；支持平台配置和本地 Cookie/Token 边界；提供 adapter health/probe；记录第三方许可证与 optional integration 策略；查不到时输出 no-evidence。

## North Star Contribution

This domain supports the core flow:

用户通过 CLI 输入问题或断言；系统生成检索计划，优先使用低成本采集来源；adapter 输出统一来源项；证据模块清洗去重并压缩成证据卡；LLM 基于证据卡输出综合回答、搜索结果要点、来源分布、分歧/争议和噪音提示；报告模块输出终端摘要、JSON 或 Markdown。

## Implemented Features

- `probe` reports one provider/adapter status as JSON or Markdown.
- `health` aggregates `fixture`, `web`, `official`, `github`, `search`, `firecrawl`, and `mediacrawler` provider statuses by default.
- Status values include `ok`, `needs-input`, `no-evidence`, `disabled`, and `error`.
- Providers that require user input report structured `needs-input` reasons instead of running live checks by default.
- External bridge providers report `disabled` with `missing-endpoint` until a local endpoint is configured.
- Probe details include provider type and candidate count.
- External bridge probes read `/manifest` and `/health` when configured, then expose contract version, capabilities, AI guidance, fix guidance, retryability, warnings, evidence gaps, and diagnostics.
- Probe Markdown shows fix and retryability when available.
- Probe Markdown now shows `Warnings:` and engine diagnostic keys (`captcha_engines`, `timeout_engines`, `other_issues`) when bridge reports degraded status.
- Health Markdown shows `— fix:` hint and engine diagnostic sub-items for degraded probes.
- SearXNG bridge `collect()` now propagates `unresponsive_engines` (CAPTCHA/timeout) as `warnings`, `fix`, `diagnostics` in response payload.
- SearXNG bridge and engine health checks use a browser-like User-Agent for upstream `/search?format=json` requests so diagnostics do not depend on Python urllib's default User-Agent.
- MediaCrawler bridge `collect()` now supports `enable_comments`, `enable_sub_comments`, `max_comments_per_item` payload params. When enabled, reads `comments_*.json` files and returns `community-comment` items alongside `community-post` items.
- First-party bridge runners expose the same `/manifest`, `/health`, and `/collect` routes, so `probe` can validate real Firecrawl/MediaCrawler setup through the stable bridge contract.

## Pending Features

Key workflows to implement or validate:

- Add richer live readiness checks only when a provider can do them cheaply and safely.
- Add credential-reference checks for future restricted-platform providers without leaking secrets.
- Expand provider-specific diagnostics as real bridge implementations mature.

## Last Effective Design

- Product context: `docs/context/project-overview.md`
- Architecture context: `docs/context/architecture.md`
- Engineering contract: `docs/engineering/adapter-health.md`

## Validation

Tests cover provider-aware probe/health behavior, fake providers, disabled external bridge providers, M5 bridge manifest/health diagnostics, bridge runner health behavior, missing input, no-evidence, health aggregation, and JSON/Markdown status rendering with `unittest`. Tests avoid live external platforms by default.

## Known Issues

- 第三方项目许可证可能限制集成方式
- 中文平台页面和风控变化快
- 用户 Cookie/Token 涉及本地凭据安全
- LLM 可能过度推断
- 搜索引擎和平台可能限流
- adapter 健康探针需要低成本且不过度访问
- Apache-2.0 核心必须避免复制不兼容源码
- SearXNG degraded/no-evidence can reflect upstream engine CAPTCHA/rate-limit exhaustion even when the local bridge and upstream process are running correctly.

## Next Useful Moves

- Keep default health low-cost and local-safe.
- Add richer upstream version/fingerprint checks after real bridge runners expose those values safely.
- Use provider health output as a readiness signal, not as proof of claim truth.

Before closing work in this module, update `Current Status`, `Implemented Features`, `Validation`, `Known Issues`, and `Next Useful Moves` if any of them changed.
