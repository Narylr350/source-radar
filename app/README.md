# source-radar app

This directory contains the Python CLI implementation.

Planned responsibilities:

- CLI commands such as `verify`, `probe`, `health`, `config`, and `integrations`.
- Adapter contracts for low-cost source collection.
- Evidence-card generation and reporting.
- LLM judgement orchestration.
- Local configuration and credential-reference handling.

The default `verify` path is now the built-in verification agent: it plans a source tool, collects evidence cards, and sends those cards to an OpenAI-compatible AI provider when configured.

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
python -m source_radar config set-openai --api-key "sk-local-..." --endpoint "http://127.0.0.1:9317/" --model "gpt-5.4"
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
