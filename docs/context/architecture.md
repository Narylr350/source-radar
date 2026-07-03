# Architecture

## Current Direction

`source-radar` is a single Python application. The current baseline is `.ai/PROJECT.md`.

The project is moving from a bridge-first collection wrapper to a native acquisition engine with:

- `AcquisitionKernel` — one small interface used by CLI and MCP for source collection.
- `BackendRegistry` — records backend type, install source, version/commit, local path reference, status, and diagnostics.
- `BackendLifecycleManager` — owns startup, prewarm, warm lease, readiness, idle stop, failure circuit breaking, and fallback.
- `EngineInstaller` — owns downloads, local-source checkouts, runtime directories, repair, and registry writeback.

The first minimal backend seam now lives under `app/source_radar/backends/`:

- `registry.py` defines structured backend records and default backend metadata.
- `lifecycle.py` defines pure lifecycle state transitions for warm leases, idle cooling, and failure cooldown.
- `paths.py` centralizes initial backend runtime path construction.

`engine status` and MCP `source_status` now expose the registry metadata while legacy service probes remain compatible.

The first minimal `AcquisitionKernel` interface is implemented in `app/source_radar/acquisition.py`. MCP `web_search`, `fetch_url`, and `fetch_search_results` now enter search/fetch through that seam while preserving the existing `dispatch_search` and `fetch_with_fallback` behavior.

## Runtime Layout

Backend source, downloads, logs, pids, browser profiles, and runtime data should converge under `.source-radar/`:

```text
.source-radar/
  engines/
  downloads/
  runtime/
  pids/
  logs/
  config.json
```

Do not add new scattered runtime roots such as `external/`, user-global Playwright caches, or ad-hoc bridge directories. Detailed layout and migration rules live in `docs/engineering/runtime-layout.md`.

## Compatibility

Public CLI and MCP entry points should remain stable while the internals migrate:

- `ask`
- `verify`
- `research`
- `mcp`
- `engine install/status/start/stop`
- `source_status`
- `search_chinese_platforms`

Legacy bridge backends may remain as fallback during migration, but new code should not make bridge-first behavior the main path.

## Documentation Rule

`.ai/PROJECT.md` is the primary project baseline. Keep only small canonical docs here when they help future implementation. Old task logs, plans, and workflow indexes should not be recreated.
