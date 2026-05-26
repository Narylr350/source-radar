# source-radar

source-radar is a local, AI-friendly CLI and collection engine for Chinese internet source analysis.

It is designed to answer research questions by collecting search/crawler results, compressing them into evidence cards, and asking a built-in AI agent to synthesize what the sources collectively say. Stricter claim verification remains available, but the main product direction is a multi-platform information-analysis agent for Chinese internet sources.

## Goals

- Search and collect from low-cost sources first: web pages, search results, official announcements, and GitHub.
- Normalize collected items into evidence cards with source metadata.
- Use LLMs to synthesize search results from evidence cards, not from unsupported assumptions.
- Keep strict claim verification as a separate workflow for cases that need it.
- Return a clear `no-evidence` result when nothing useful is found.
- Keep restricted or login-gated platforms behind explicit local user configuration.
- Track adapter health so platform breakage is visible before normal verification fails.

## Non-goals

- No web UI or desktop UI in the first version.
- No manual evidence-entry workflow.
- No access-control bypass, anti-detection logic, captcha bypass, or large-scale crawling.
- No vendored copies of incompatible third-party crawler code.
- No claim that an LLM judgement is a final source of truth.

## Planned shape

- Runtime: Python
- Interface: CLI-first local engine
- License: Apache-2.0
- Third-party crawler projects: optional external integrations only

## Current product direction

M6 turns the source-acquisition foundation into a practical information-analysis workflow. The main command is now `ask`: it discovers sources, runs local crawlers and selected bridges when available, sends compact evidence cards to the built-in AI provider, and returns a synthesis centered on the collected search results.

The stricter `verify` workflow still exists for claim checking. Its report can discuss evidence gaps because that is useful for verification. `ask` intentionally avoids a heavy fact-check checklist: it focuses on a concise answer, search-result takeaways, source distribution, disagreements when present, noisy/marketing-like results, and the result list.

M5 established the first trustworthy source-acquisition foundation before deeper judgement polish or Codex/Claude Code skills, MCP servers, or other agent-facing wrappers. The CLI can discover sources, run built-in collectors, call the two selected crawler backends through license-safe bridges, and expose what was searched before asking AI to analyze anything.

The selected external crawler backends are Firecrawl and MediaCrawler. They stay behind local services, APIs, or user-provided bridge processes because of license and platform-boundary reasons. Their source code must not be copied into the Apache-2.0 core. That is a distribution boundary, not a reason to postpone crawler/search capability.

The `health` and `probe` commands are now provider-aware. They report registered built-in providers, search readiness, bridge configuration state, candidate counts, and structured reasons such as missing URL, missing repo, or missing bridge endpoint.

Skill/MCP wrapping is intentionally deferred until the acquisition and analysis contracts are stable enough that an external AI tool will not need constant rewiring.

## Quick Start

```powershell
.\source-radar.ps1 setup
.\source-radar.ps1 ask "小红书和 B 站上有哪些 AI 编程工具实测反馈？"
```

The helper script prepares the local Python environment and wraps the common command so normal use does not require long commands or multiple terminal windows. `ask` defaults to Markdown output and starts supported local services for the run when possible.

For direct Python usage:

```powershell
python -m pip install -e .
python -m source_radar ask "source-radar 是本地 CLI"
python -m source_radar verify "source-radar 是本地 CLI" --format json
python -m source_radar verify "完全未知的断言" --format json
```

The default `ask` workflow runs the built-in information-analysis agent. The agent plans source tools, collects evidence cards, and asks an OpenAI-compatible AI provider for synthesis when one is configured. Without an API key it falls back to deterministic local synthesis. `verify` uses the same acquisition foundation but keeps a stricter verification report.

## Local AI configuration

Run the interactive setup on first use:

```powershell
.\source-radar.ps1 setup
```

For scripted setup:

```powershell
python -m source_radar config set-openai --api-key "<api-key>" --endpoint "http://127.0.0.1:8000/" --model "<model>"
python -m source_radar config show
python -m source_radar config clear-openai
```

The API key is stored in a local user config file by default and must not be committed or pushed to the GitHub remote. `config show` masks the key. Environment variables still work and override the local file: `OPENAI_API_KEY`, `SOURCE_RADAR_OPENAI_ENDPOINT`, and `SOURCE_RADAR_OPENAI_MODEL`. The AI client tries OpenAI Responses first and falls back to Chat Completions for local compatible APIs that only expose `/v1/chat/completions`.

## M6 information analysis

M6 adds the `ask` workflow:

```powershell
.\source-radar.ps1 ask "找一些 RTX 5090 电源兼容问题的中文社区反馈"
python -m source_radar ask "OpenAI-compatible API chat completions endpoint usage" --format json
python -m source_radar ask "本地页面分析" --url "https://example.com/page"
```

The JSON report contains:

- `query`: original question.
- `status`: `analysis-ready`, `no-evidence`, or `ai-error`.
- `analysis.summary`: concise synthesized answer.
- `analysis.key_points`: main takeaways from the collected results.
- `analysis.source_notes`: source distribution and provenance notes.
- `analysis.disagreements`: conflicts or competing viewpoints when the sources show them.
- `analysis.noise_notes`: search-result noise, SEO, marketing, repost, or access caveats.
- `evidence`: compact evidence cards with stable IDs.
- `agent.acquisition`: provider trace showing what was searched and collected.

Markdown output is intentionally light: 综合回答、搜索结果要点、来源分布、分歧/争议、噪音提示、采集过程、结果清单. It does not make “还缺什么/下一步搜什么” the main product surface.

## M2 low-cost sources

M2 adds self-contained low-cost source adapters while preserving the M1 report contract:

```powershell
python -m source_radar verify "page claim" --source web --url "https://example.com/page"
python -m source_radar verify "official claim" --source official --url "https://example.com/news"
python -m source_radar verify "openai/source-radar-example" --source github --repo "openai/source-radar-example"
```

The automated suite tests these adapters with local HTML and JSON fixtures by default, so normal validation does not depend on live platforms.

## M3 health and probe

M3 adds adapter status checks:

```powershell
python -m source_radar probe --source web --url "https://example.com/page"
python -m source_radar probe --source github --repo "openai/openai-python"
python -m source_radar health --format json
python -m source_radar health --format markdown
```

`probe` checks one adapter and reports `ok`, `needs-input`, `no-evidence`, or `error`. `health` summarizes the current adapter set without requiring live network checks by default.

## M4 optional integrations

M4 records optional external integration boundaries without vendoring third-party crawler code:

```powershell
python -m source_radar integrations audit --format json
python -m source_radar integrations audit --format markdown
python -m source_radar integrations status --format json
```

The registry tracks MediaCrawler as `external-only` because of its non-commercial learning/research license, and Firecrawl as `bridge-or-api-only` because AGPL-3.0 source reuse would change the core distribution boundary. `integrations status` reads local provider bridge configuration and reports configured bridges without importing third-party crawler source.

## M5 source acquisition

M5 adds source acquisition for the built-in agent:

- `fixture`, `web`, `official`, and `github` wrap the existing built-in adapters.
- `search` discovers candidate sources through DuckDuckGo Lite.
- `trafilatura` extracts normal web pages locally after `search` finds candidate URLs.
- `crawl4ai` is the local browser-backed fallback for dynamic pages. It is optional because Playwright/Chromium setup is heavier.
- `mediacrawler` is the selected Chinese community platform backend behind a local bridge.
- `firecrawl` is optional cloud/API-backed enhancement. Firecrawl MCP runs locally, but actual Firecrawl collection still needs a Firecrawl API key or compatible API endpoint.

Useful commands:

```powershell
python -m source_radar probe --source search --query "source-radar"
python -m source_radar probe --source trafilatura --query "source-radar"
python -m source_radar probe --source crawl4ai --query "source-radar"
python -m source_radar probe --source firecrawl
python -m source_radar bridge firecrawl --port 3002 --transport mcp
python -m source_radar bridge mediacrawler --port 3003 --api-url "http://127.0.0.1:8080" --platform xhs
python -m source_radar config set-provider --name firecrawl --endpoint "http://127.0.0.1:3002"
python -m source_radar config set-provider --name mediacrawler --endpoint "http://127.0.0.1:3003"
python -m source_radar integrations status --format json
python -m source_radar health --format json
```

`ask` and `verify --source auto` use search for generic questions instead of falling back primarily to the fixture. JSON and Markdown reports include a source-acquisition trace with searched providers, candidate sources, item counts, statuses, and failure reasons.

Install the default local webpage extractor with the app:

```powershell
python -m pip install -e .
```

Install the dynamic browser-backed crawler when needed:

```powershell
python -m pip install -e ".[dynamic]"
crawl4ai-setup
```

With `uv`, the local crawler environment can be prepared with:

```powershell
uv sync --extra dynamic
uv run crawl4ai-setup
```

source-radar sets Crawl4AI's runtime base to the ignored `.source-radar/crawl4ai` directory when no upstream base is configured, so local database/cache files do not need to live in Git-tracked paths.

On Windows, Crawl4AI's dependency tree may require Windows Long Path support. If installation fails with a long-path error, keep using `trafilatura` for default local extraction and fix the OS path setting before enabling Crawl4AI.

For platform and optional cloud/API setup, source-radar includes a small first-party bridge runner:

- `bridge firecrawl` proxies the source-radar bridge contract to Firecrawl MCP by default. Install `firecrawl-mcp`, set `FIRECRAWL_API_KEY` locally, and keep keys out of GitHub. `--transport api` remains available for compatible API endpoints.
- `bridge mediacrawler` proxies the source-radar bridge contract to a user-run MediaCrawler WebUI API. Start MediaCrawler separately with `uv run uvicorn api.main:app --port 8080`, then run the bridge on port `3003`.

The provider config can store the bridge endpoint and an optional local command hint for AI-assisted setup. Local upstream checkouts, runtime data, and credentials may live on the same machine or in ignored workspace directories, but must not be staged, committed, or pushed to GitHub.

For convenience, bridge commands also read ignored local secrets from `.source-radar/local.env`:

```env
SOURCE_RADAR_XHS_COOKIE=
FIRECRAWL_TRANSPORT=mcp
FIRECRAWL_API_KEY=
FIRECRAWL_MCP_COMMAND=npx -y firecrawl-mcp
```

This file is local-only by default.

## M5 AI-callable crawler bridge contract

MediaCrawler and optional Firecrawl bridges are intended for the built-in AI agent to call automatically. Users normally configure a bridge endpoint once, then run `verify`; if the bridge is healthy and its manifest says it supports source discovery, the agent can include it in the acquisition plan. Generic local webpage collection does not require a bridge: the agent can call `trafilatura` and `crawl4ai` directly through the provider layer.

A compatible bridge exposes:

- `GET /manifest`: returns `contract_version`, capabilities such as `search`, and `ai_guidance`.
- `GET /health`: returns readiness status plus `reason`, `message`, optional `fix`, and `retryable`.
- `POST /collect`: accepts `query` and `limit`, then returns `items`, optional `candidates`, warnings, evidence gaps, diagnostics, and repair guidance.

When a bridge is broken, `probe`, `health`, and `verify` acquisition traces surface the reason and fix instead of hiding the failure inside the AI path.

## License and integration policy

The core repository is Apache-2.0. Third-party crawler projects with restrictive or copyleft licenses should not be copied into this repository unless their license is explicitly compatible with the repository's distribution model.

Known constraints to preserve:

- MediaCrawler uses a non-commercial learning/research license, so it should remain an optional external integration or reference, not vendored core code.
- Trafilatura and Crawl4AI are local Python dependencies used through their package APIs.
- Firecrawl uses AGPL-3.0 for its main project, so direct source reuse would introduce AGPL obligations. Firecrawl MCP/API use is optional and cloud/API-backed unless the user provides a compatible endpoint.

Distribution rules:

- If users manually download Firecrawl or MediaCrawler, they are responsible for following those projects' licenses, terms, and platform access rules.
- If source-radar later auto-downloads either backend, the downloader must show the upstream project, version, license, source URL, and any required NOTICE before installation.
- If source-radar is distributed with either backend prepackaged, the distribution must include the upstream license, source offer or source location when required, NOTICE files, and any obligations triggered by that backend's license.
- The Apache-2.0 core must stay usable without those external backends; bridge configuration should be local and explicit.
- README and release notes must state which external backend is used, how it is obtained, and which license boundary applies.

## Development status

This repository currently contains a runnable local CLI with an AI-agent-first `ask` path, a stricter `verify` path, local AI provider configuration, low-cost `web` / `official` / `github` adapters, real search discovery, local Trafilatura/Crawl4AI webpage providers, MediaCrawler bridge support, optional Firecrawl bridge configuration, provider-aware health/probe commands, source-acquisition traces, and optional integration license boundaries. The next work should deepen evidence deduplication, stable citations, and JSON contract stability before building wrapper layers.
