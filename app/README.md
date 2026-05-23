# source-radar app

This directory is reserved for the first Python CLI implementation.

Planned responsibilities:

- CLI commands such as `verify`, `probe`, `health`, `config`, and `integrations`.
- Adapter contracts for low-cost source collection.
- Evidence-card generation and reporting.
- LLM judgement orchestration.
- Local configuration and credential-reference handling.

The first implementation is intentionally small and fixture-backed.

## First Runnable Workflow

The initial implementation provides a fixture-backed `verify` command:

```powershell
$env:PYTHONPATH = "app"
python -m source_radar verify "source-radar 是本地 CLI" --format json
python -m source_radar verify "source-radar 是本地 CLI" --format markdown
```

This workflow uses local fixture data only. It does not access real platforms yet.
