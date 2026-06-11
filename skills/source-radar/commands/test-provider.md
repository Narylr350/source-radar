---
description: "Quick-test an acquisition provider (BingSearch, ExternalBridge/mediacrawler, Trafilatura) with a sample query."
---

# Test Acquisition Provider

Run a quick smoke test of a source-radar acquisition provider.

## Usage

`$ARGUMENTS` format: `<provider> [query]`

Providers:
- `bing` / `search` → `BingSearchProvider`
- `bridge` / `mediacrawler` → `ExternalBridgeProvider('mediacrawler', ...)`
- `trafilatura` → `TrafilaturaProvider`

Default query: `"Python 3.14 新特性"` if none given.

## Commands

### BingSearch

```bash
uv run python -c "
from source_radar.acquisition import BingSearchProvider, AcquisitionRequest
provider = BingSearchProvider()
result = provider.collect(AcquisitionRequest(query='$ARGUMENTS_QUERY', limit=5))
print(f'Status: {result.status}')
print(f'Items: {len(result.items)}')
for item in result.items[:3]:
    print(f'  - {item.title[:60]} | {item.url[:80]}')
"
```

### MediaCrawler Bridge

```bash
uv run python -c "
import time
from source_radar.acquisition import ExternalBridgeProvider, AcquisitionRequest
provider = ExternalBridgeProvider('mediacrawler', 'SOURCE_RADAR_MEDIACRAWLER_ENDPOINT')
t0 = time.time()
result = provider.collect(AcquisitionRequest(query='$ARGUMENTS_QUERY', limit=5))
elapsed = time.time() - t0
print(f'Status: {result.status} ({elapsed:.1f}s)')
print(f'Items: {len(result.items)}')
for item in result.items[:3]:
    print(f'  - {item.title[:60]} | {item.url[:80]}')
"
```

### Trafilatura

```bash
uv run python -c "
import time
from source_radar.acquisition import TrafilaturaProvider, AcquisitionRequest
provider = TrafilaturaProvider()
t0 = time.time()
result = provider.collect(AcquisitionRequest(query='$ARGUMENTS_QUERY', limit=5))
elapsed = time.time() - t0
print(f'Status: {result.status} ({elapsed:.1f}s)')
print(f'Items: {len(result.items)}')
for item in result.items[:3]:
    print(f'  - {item.title[:60]} | {item.url[:80]}')
"
```

## Notes

- Run from the project root.
- MediaCrawler bridge requires the service running (`engine start mediacrawler`).
- Timeout: 30000ms for search, 60000ms for bridge/trafilatura.
- This is a diagnostic tool, not a substitute for the full `ask`/`verify`/`research` workflow.
