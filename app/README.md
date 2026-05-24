# source-radar app

This directory contains the Python CLI implementation.

Planned responsibilities:

- CLI commands such as `verify`, `probe`, `health`, `config`, and `integrations`.
- Adapter contracts for low-cost source collection.
- Evidence-card generation and reporting.
- LLM judgement orchestration.
- Local configuration and credential-reference handling.

The default `verify` path is now the built-in verification agent: it plans a source tool, collects evidence cards, and sends those cards to an OpenAI-compatible AI provider when configured.

## Current Direction

Do not build Codex/Claude Code skills, MCP servers, or other AI-agent wrappers next. M5 makes the CLI verification engine more trustworthy by giving it a real source-acquisition foundation:

- real source discovery instead of fixture-heavy fallback behavior;
- crawler/search provider interfaces that call safe built-in collectors or license-safe external bridges;
- multi-source planning for web, official sources, GitHub, and later restricted platforms;
- evidence deduplication, compression, and stable citation IDs;
- structured AI judgement with conclusion, supporting evidence, conflicts, gaps, and uncertainty;
- product-quality JSON and Markdown reports.

External crawler projects must remain outside the Apache-2.0 core unless their licenses are compatible, but source acquisition itself is foundational. External AI wrappers should wait until this core contract is stable.

The `health` and `probe` commands are now provider-aware and report crawler/search provider readiness, bridge configuration, candidate counts, and structured missing-input reasons.

## First Runnable Workflow

The initial smoke path remains fixture-backed for deterministic local validation:

```powershell
python -m pip install -e .
python -m source_radar verify "source-radar 是本地 CLI" --format json
python -m source_radar verify "source-radar 是本地 CLI" --format markdown
```

After installation, `pyproject.toml` also exposes a `source-radar` console script. On Windows, the user scripts directory must be on `PATH` before that command name is available directly.

Without AI configuration, `verify` still returns a structured report through the local fallback judgement and includes a setup hint.

## Local AI Configuration

First-time interactive setup:

```powershell
python -m source_radar config setup
```

Scripted setup and inspection:

```powershell
python -m source_radar config set-openai --api-key "<api-key>" --endpoint "http://127.0.0.1:8000/" --model "<model>"
python -m source_radar config show
python -m source_radar config clear-openai
```

The config command stores provider settings in the local user config file. API keys are not stored in the repository, and `config show` masks secrets. Environment variables `OPENAI_API_KEY`, `SOURCE_RADAR_OPENAI_ENDPOINT`, and `SOURCE_RADAR_OPENAI_MODEL` override the local file.

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

The M4 registry is intentionally a boundary and audit layer. It records MediaCrawler and Firecrawl as optional external integrations, but does not copy or import their source code into the Apache-2.0 core.

## M5 Source Acquisition

Provider-aware commands:

```powershell
python -m source_radar probe --source search --query "source-radar"
python -m source_radar probe --source firecrawl
python -m source_radar config set-provider --name firecrawl --endpoint "http://127.0.0.1:3002"
python -m source_radar config clear-provider --name firecrawl
python -m source_radar health --format json
```

Default providers are `fixture`, `web`, `official`, `github`, `search`, `firecrawl`, and `mediacrawler`. External bridge providers are configured locally and stay outside the repository source tree. `verify` reports include source-acquisition traces so callers can see searched providers, candidate sources, item counts, and failure reasons.

## M5.1 AI-Callable Bridges

External bridges are for the built-in verification agent to call. A bridge endpoint is treated as a base URL and must expose:

- `GET /manifest` for `contract_version`, capabilities, and AI guidance.
- `GET /health` for readiness, diagnostics, fix guidance, and retryability.
- `POST /collect` for actual crawler/search collection.

The supported contract version is `source-radar.bridge.v1`. Normal users should not need to think about these routes during `verify`; they matter when `probe`, `health`, or `verify.agent.acquisition` needs to explain what broke and how to fix it.
