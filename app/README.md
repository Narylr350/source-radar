# source-radar app

This directory contains the Python CLI implementation.

Planned responsibilities:

- CLI commands such as `ask`, `verify`, `probe`, `health`, `config`, and `integrations`.
- Adapter contracts for low-cost source collection.
- Evidence-card generation and reporting.
- LLM synthesis and judgement orchestration.
- Local configuration and credential-reference handling.

The default research path is now `ask`: it plans source tools, collects evidence cards, and sends those cards to an OpenAI-compatible AI provider for search-result synthesis when configured. `verify` remains available for stricter claim checking.

## Current Direction

Do not build Codex/Claude Code skills, MCP servers, or other AI-agent wrappers next. M6 makes the CLI information-analysis engine useful from the command line:

- real source discovery instead of fixture-heavy fallback behavior;
- crawler/search provider interfaces that call safe built-in collectors and the MediaCrawler bridge;
- multi-source planning for web, official sources, GitHub, and later restricted platforms;
- `ask` reports that focus on comprehensive search-result synthesis rather than evidence-gap checklists;
- structured analysis with summary, key points, source notes, disagreements, noise notes, and evidence cards;
- simple local commands through `source-radar.ps1` so users do not have to paste long commands or keep multiple windows open.

External crawler projects must remain outside the Apache-2.0 core unless their licenses are compatible, but source acquisition itself is foundational. External AI wrappers should wait until this core contract is stable.

The `health` and `probe` commands are now provider-aware and report crawler/search provider readiness, bridge configuration, candidate counts, and structured missing-input reasons.

## First Runnable Workflow

Normal local use:

```powershell
.\source-radar.ps1 setup
.\source-radar.ps1 ask "找一些中文社区里的 AI 工具实测反馈"
```

The deterministic smoke path remains fixture-backed for local validation:

```powershell
python -m pip install -e .
python -m source_radar ask "source-radar 是本地 CLI"
python -m source_radar verify "source-radar 是本地 CLI" --format json
python -m source_radar verify "source-radar 是本地 CLI" --format markdown
```

After installation, `pyproject.toml` also exposes a `source-radar` console script. On Windows, the user scripts directory must be on `PATH` before that command name is available directly.

Without AI configuration, `ask` still returns a structured fallback synthesis and `verify` still returns a structured fallback judgement with a setup hint.

## Local AI Configuration

First-time interactive setup:

```powershell
.\source-radar.ps1 setup
```

Scripted setup and inspection:

```powershell
python -m source_radar config set-openai --api-key "<api-key>" --endpoint "http://127.0.0.1:8000/" --model "<model>"
python -m source_radar config show
python -m source_radar config clear-openai
```

The config command stores provider settings in the local user config file by default. API keys must not be staged, committed, or pushed to GitHub, and `config show` masks secrets. Environment variables `OPENAI_API_KEY`, `SOURCE_RADAR_OPENAI_ENDPOINT`, and `SOURCE_RADAR_OPENAI_MODEL` override the local file. Local OpenAI-compatible APIs may expose only Chat Completions; the provider tries Responses first and falls back to `/v1/chat/completions`.

## M6 Information Analysis

`ask` is the main M6 workflow:

```powershell
.\source-radar.ps1 ask "小红书和 B 站上有哪些 AI 编程工具实测反馈？"
python -m source_radar ask "本地页面分析" --url "https://example.com/page"
python -m source_radar ask "OpenAI-compatible API chat completions endpoint usage" --format json
```

The report model is `SynthesisReport`. It contains the original query, `analysis-ready` / `no-evidence` / `ai-error` status, compact evidence cards, acquisition trace, and an `InformationAnalysis` payload with `summary`, `key_points`, `source_notes`, `disagreements`, and `noise_notes`.

Markdown output uses a light structure: 综合回答、搜索结果要点、来源分布、分歧/争议、噪音提示、采集过程、结果清单. It intentionally does not center the experience on “还缺什么” or “建议下一步搜什么”.

## M2 Source Adapters

The `verify` command can also collect from low-cost source adapters:

```powershell
python -m source_radar verify "page claim" --source web --url "https://example.com/page"
python -m source_radar verify "official claim" --source official --url "https://example.com/news"
python -m source_radar verify "openai/source-radar-example" --source github --repo "openai/source-radar-example"
```

Available M2 sources:

- `fixture`: deterministic local smoke baseline from M1.
- `web`: normal HTML page extraction using the Python standard library.
- `official`: HTML announcement/page extraction marked as `official-announcement`.
- `github`: GitHub repository metadata via the GitHub REST API.

Tests use local HTML and JSON fixtures. Live network checks should be treated as manual smoke validation.

## M3 Health And Probe

Adapter status commands:

```powershell
python -m source_radar probe --source web --url "https://example.com/page"
python -m source_radar probe --source official --url "https://example.com/news"
python -m source_radar probe --source github --repo "openai/openai-python"
python -m source_radar health --format json
python -m source_radar health --format markdown
```

Status values:

- `ok`: adapter returned usable source items.
- `needs-input`: adapter requires a URL, repo, credentials, or other user-provided input.
- `no-evidence`: adapter ran but returned no usable source items.
- `error`: adapter failed with a structured reason and message.

## M4 Optional Integrations

Integration commands:

```powershell
python -m source_radar integrations audit --format json
python -m source_radar integrations audit --format markdown
python -m source_radar integrations status --format json
```

The M4 registry is intentionally a boundary and audit layer. It records MediaCrawler as an optional external integration, but does not copy or import its source code into the Apache-2.0 core.

## M5 Source Acquisition

Provider-aware commands:

```powershell
python -m source_radar probe --source search --query "source-radar"
python -m source_radar probe --source trafilatura --query "source-radar"
python -m source_radar probe --source crawl4ai --query "source-radar"
python -m source_radar bridge mediacrawler --port 3003 --api-url "http://127.0.0.1:8080" --platform xhs
python -m source_radar config set-provider --name mediacrawler --endpoint "http://127.0.0.1:3003"
python -m source_radar health --format json
```

Default providers are `fixture`, `web`, `official`, `github`, `search`, `trafilatura`, `crawl4ai`, and `mediacrawler`. Trafilatura and Crawl4AI are local generic webpage providers; MediaCrawler is the selected Chinese community backend. External bridge providers are configured locally and stay outside tracked core source; local upstream checkouts may live in ignored workspace directories. `ask` and `verify` reports include source-acquisition traces so callers can see searched providers, candidate sources, item counts, and failure reasons.

Crawl4AI uses the ignored `.source-radar/crawl4ai` runtime directory by default when `CRAWL4_AI_BASE_DIRECTORY` is not already set. For a local `uv` setup, run `uv sync --extra dynamic` and `uv run crawl4ai-setup`.

The built-in `bridge` command is the easiest AI-assisted setup target for platform services:

- `bridge mediacrawler` exposes the source-radar bridge contract and calls a separately running MediaCrawler WebUI API. Start MediaCrawler with `uv run uvicorn api.main:app --port 8080` from the MediaCrawler checkout first.

These bridge runners are source-radar-owned compatibility wrappers. They do not vendor MediaCrawler source and should be launched as local processes.

Bridge commands read ignored local secrets from `.source-radar/local.env` when present. Common keys are `SOURCE_RADAR_XHS_COOKIE` and other platform cookie env vars.

## M5 AI-Callable Crawler Bridges

MediaCrawler bridge is for the built-in agent to call. A bridge endpoint is treated as a base URL and must expose:

- `GET /manifest` for `contract_version`, capabilities, and AI guidance.
- `GET /health` for readiness, diagnostics, fix guidance, and retryability.
- `POST /collect` for actual crawler/search collection.

The supported contract version is `source-radar.bridge.v1`. Normal users should not need to think about these routes during `ask`; they matter when `probe`, `health`, or `agent.acquisition` needs to explain what broke and how to fix it.

License handling is explicit: this app does not vendor MediaCrawler source into the Apache-2.0 core. If a user installs it manually, uses an auto-download helper later, or receives a prepackaged distribution, the upstream project name, version, license, source location, and NOTICE obligations must be shown and preserved.
