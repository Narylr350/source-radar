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

## License and integration policy

The core repository is Apache-2.0. Third-party crawler projects with restrictive or copyleft licenses should not be copied into this repository unless their license is explicitly compatible with the repository's distribution model.

Known constraints to preserve:

- MediaCrawler uses a non-commercial learning/research license, so it should remain an optional external integration or reference, not vendored core code.
- Firecrawl uses AGPL-3.0, so direct source reuse would introduce AGPL obligations. Prefer compatible bridges, API calls, or independent implementations.

## Development status

This repository currently contains the public scaffold and license baseline. Detailed AI planning documents are intentionally ignored by git and kept local.
