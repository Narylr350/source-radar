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
