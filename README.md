# source-radar

source-radar is a local, AI-friendly CLI and collection engine for Chinese internet source verification.

It is designed to help verify claims, tutorials, product changes, policy updates, public-person activity, and GitHub project authenticity by turning search and collection results into compact evidence cards for LLM-assisted judgement.

## Goals

- Search and collect from low-cost sources first: web pages, search results, official announcements, and GitHub.
- Normalize collected items into evidence cards with source metadata.
- Use LLMs to judge credibility from evidence cards, not from unsupported assumptions.
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

M5 establishes the first trustworthy source-acquisition foundation before deeper judgement polish or Codex/Claude Code skills, MCP servers, or other agent-facing wrappers. The CLI can now use a unified provider layer to discover sources, run built-in crawler/search providers, call license-safe external bridges, and expose what was searched before asking AI to judge anything.

External crawler projects still stay behind license-safe bridges or local user configuration; their source code should not be vendored into the Apache-2.0 core. That is a distribution boundary, not a reason to postpone crawler/search capability.

The `health` and `probe` commands are now provider-aware. They report registered built-in providers, search readiness, bridge configuration state, candidate counts, and structured reasons such as missing URL, missing repo, or missing bridge endpoint.

Skill/MCP wrapping is intentionally deferred until the acquisition and verification contracts are stable enough that an external AI tool will not need constant rewiring.

## M1 local run

```powershell
python -m pip install -e .
python -m source_radar verify "source-radar 是本地 CLI" --format json
python -m source_radar verify "完全未知的断言" --format json
```

The default `verify` workflow now runs the built-in verification agent. The agent plans a source tool, collects evidence cards, and asks an OpenAI-compatible AI provider for judgement when one is configured. Without an API key it falls back to deterministic local judgement and includes a setup hint in the report.

## Local AI configuration

Run the interactive setup on first use:

```powershell
python -m source_radar config setup
```

For scripted setup:

```powershell
python -m source_radar config set-openai --api-key "<api-key>" --endpoint "http://127.0.0.1:8000/" --model "<model>"
python -m source_radar config show
python -m source_radar config clear-openai
```

The API key is stored in a local user config file, not in the repository. `config show` masks the key. Environment variables still work and override the local file: `OPENAI_API_KEY`, `SOURCE_RADAR_OPENAI_ENDPOINT`, and `SOURCE_RADAR_OPENAI_MODEL`.

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

M5 adds a provider contract and default acquisition providers:

- `fixture`, `web`, `official`, and `github` wrap the existing built-in adapters.
- `search` discovers candidate sources through DuckDuckGo Lite.
- `firecrawl` and `mediacrawler` are external bridge providers that require a local endpoint.

Useful commands:

```powershell
python -m source_radar probe --source search --query "source-radar"
python -m source_radar probe --source firecrawl
python -m source_radar config set-provider --name firecrawl --endpoint "http://127.0.0.1:3002"
python -m source_radar integrations status --format json
python -m source_radar health --format json
```

`verify --source auto` uses search for generic claims instead of falling back primarily to the fixture. JSON and Markdown reports include a source-acquisition trace with searched providers, candidate sources, item counts, statuses, and failure reasons.

## License and integration policy

The core repository is Apache-2.0. Third-party crawler projects with restrictive or copyleft licenses should not be copied into this repository unless their license is explicitly compatible with the repository's distribution model.

Known constraints to preserve:

- MediaCrawler uses a non-commercial learning/research license, so it should remain an optional external integration or reference, not vendored core code.
- Firecrawl uses AGPL-3.0, so direct source reuse would introduce AGPL obligations. Prefer compatible bridges, API calls, or independent implementations.

## Development status

This repository currently contains a runnable local CLI with an AI-agent-first `verify` path, local AI provider configuration, low-cost `web` / `official` / `github` adapters, a real search provider, external bridge provider configuration, provider-aware health/probe commands, source-acquisition traces, and optional integration license boundaries. The next work should deepen evidence deduplication, stable citations, and structured AI judgement before building wrapper layers.
