# Backend Contracts

## Backend Types

- `native`: in-process Python backend with no managed child process.
- `local-source`: source-radar-managed local checkout or archive under `.source-radar/engines`.
- `service`: managed local service process.
- `legacy-bridge`: existing bridge path kept only for fallback during migration.
- `external`: user-managed backend; source-radar only probes it.

## Lifecycle Policies

- `disabled`
- `on-demand`
- `warm`
- `always-on`
- `external`

Lifecycle states:

- `stopped`
- `starting`
- `warming`
- `ready`
- `degraded`
- `failed`
- `cooling_down`

Every managed backend should expose a start budget, readiness probe, idle timeout, retry/failure metadata, and fallback information. Readiness should test real capability where possible, not only open ports.

## Minimal Implementation

The initial contract seam is implemented in `app/source_radar/backends/`:

- `registry.py`: `BackendRecord`, `BackendInstall`, `BackendDiagnostics`, `BackendRegistry`, and `build_default_registry`.
- `lifecycle.py`: `BackendLifecycleManager` pure state transitions for `ready`, `cooling_down`, idle timeout, and failure cooldown.
- `paths.py`: initial `.source-radar/` backend path helpers.

`engine list/status` and MCP `source_status` include registry fields such as backend key, backend type, lifecycle policy, lifecycle state, install path references, start budget, idle timeout, diagnostics, and fallback.

## Diagnostics

Backend results and status output should preserve:

- status and reason;
- human message;
- retryability;
- fix guidance;
- warnings;
- diagnostics;
- fallback path;
- raw backend counts when safe.

## Runtime Paths

Backends must not invent their own filesystem roots. Use the runtime layout in `docs/engineering/runtime-layout.md`; implementation should centralize path construction in a helper before migrating existing hardcoded paths.
