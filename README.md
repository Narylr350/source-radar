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

## M1 local run

```powershell
python -m pip install -e .
python -m source_radar verify "source-radar 是本地 CLI" --format json
python -m source_radar verify "完全未知的断言" --format json
```

The M1 workflow uses deterministic fixture data. It proves the CLI, evidence-card, no-evidence, judgement, and reporting contract before real network adapters are added in later milestones.

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

The current registry tracks MediaCrawler as `external-only` because of its non-commercial learning/research license, and Firecrawl as `bridge-or-api-only` because AGPL-3.0 source reuse would change the core distribution boundary.

## License and integration policy

The core repository is Apache-2.0. Third-party crawler projects with restrictive or copyleft licenses should not be copied into this repository unless their license is explicitly compatible with the repository's distribution model.

Known constraints to preserve:

- MediaCrawler uses a non-commercial learning/research license, so it should remain an optional external integration or reference, not vendored core code.
- Firecrawl uses AGPL-3.0, so direct source reuse would introduce AGPL obligations. Prefer compatible bridges, API calls, or independent implementations.

## Development status

This repository currently contains the public scaffold, license baseline, and the first fixture-backed Python CLI workflow. Detailed AI planning documents are intentionally ignored by git and kept local.
