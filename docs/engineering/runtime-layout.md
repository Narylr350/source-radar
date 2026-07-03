# Runtime Layout

This document defines where source-radar runtime files should live while the project moves from bridge-first services to managed backends.

## Current Inventory

Observed local runtime roots:

| Current path | Contents | Target treatment |
|---|---|---|
| `.source-radar/browser-profiles/` | browser login/profile state | move under `.source-radar/runtime/browser-profiles/` |
| `.source-radar/cache/` | acquisition cache | keep under `.source-radar/runtime/cache/` or `.source-radar/cache/` only through compatibility helper |
| `.source-radar/crawl4ai/` | Crawl4AI runtime/database/cache | move under `.source-radar/runtime/crawl4ai/` |
| `.source-radar/pids/` | managed process pid files | keep as `.source-radar/pids/` |
| `.source-radar/sessions/` | session context | move under `.source-radar/runtime/sessions/` or keep through compatibility helper |
| `.source-radar/tmp/` | temporary files | move under `.source-radar/runtime/tmp/` |
| `.source-radar/source-radar.log` | application log | move under `.source-radar/logs/source-radar.log` |
| `.source-radar/local.env` | local secrets/cookies | keep local-only; do not commit; may remain at root for compatibility |
| `external/MediaCrawler` | local upstream checkout | move to `.source-radar/engines/mediacrawler/source` |
| `external/searxng` | local upstream checkout | move to `.source-radar/engines/searxng/source` |
| `.venv/` | project Python environment | keep as development environment, not backend runtime |

## Target Layout

```text
.source-radar/
  config.json
  local.env
  engines/
    mediacrawler/
      source/
      venv/
      metadata.json
    searxng/
      source/
      venv/
      metadata.json
    crawl4ai/
      metadata.json
  downloads/
    archives/
    wheels/
    manifests/
  runtime/
    browser-profiles/
    cache/
    crawl4ai/
    sessions/
    tmp/
  pids/
  logs/
```

## Ownership

- `EngineInstaller` owns `engines/` and `downloads/`.
- `BackendRegistry` owns backend metadata references, not raw secrets.
- `BackendLifecycleManager` owns `pids/`, lifecycle state, warm leases, and cooling-down records.
- Acquisition/cache code owns `runtime/cache/`.
- Browser-backed collectors own `runtime/browser-profiles/` and `runtime/crawl4ai/`.
- Logs go to `logs/`.
- Secrets remain local-only in `local.env`, environment variables, or future credential storage.

## Compatibility Rules

Migration must be non-destructive:

1. New helpers should prefer the target path.
2. If the target path is absent and the legacy path exists, use the legacy path and report a migration hint.
3. `engine repair` or a dedicated migration command may later move data after checking that destination paths are inside `.source-radar/`.
4. Do not delete `external/` or browser profiles automatically; they may contain user login state or expensive checkouts.
5. Do not put `.venv/` under `.source-radar/`; it is the project development/runtime environment, not a backend engine checkout.

## Path Helper Requirement

Before implementation, add a small path module or equivalent helpers so callers do not hand-build runtime paths. Required helpers:

- project root resolution;
- `.source-radar` root;
- engine source path by backend key;
- engine venv path by backend key;
- download cache paths;
- runtime cache/session/tmp paths;
- browser profile path by platform;
- pid path by backend key;
- log path.

Callers should stop hardcoding `external/MediaCrawler`, `external/searxng`, `.source-radar/crawl4ai`, `.source-radar/cache`, and `.source-radar/source-radar.log` once the helper exists.

## Test Targets

Focused tests should verify:

- target paths are under `.source-radar/`;
- legacy `external/MediaCrawler` and `external/searxng` fallback is recognized but marked legacy;
- pid paths remain under `.source-radar/pids/`;
- Crawl4AI base directory uses `.source-radar/runtime/crawl4ai` after migration;
- acquisition cache uses a single helper-controlled root;
- no new backend code hardcodes `external/` or raw `.source-radar/<feature>` paths outside the helper.
