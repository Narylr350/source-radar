# Tech Stack

## Runtime

- Python 3.11+
- `uv` + setuptools
- Standard-library `unittest`
- Single package under `app/source_radar/`

## Current Migration Focus

The next implementation work should keep CLI/MCP surfaces stable while adding:

- backend registry data model;
- backend lifecycle state machine;
- unified `.source-radar/` runtime/cache layout;
- native/local-source community backend slice.

## Validation Baseline

Use targeted tests for the touched area. Current useful subsets:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_mcp_server -v
.venv\Scripts\python.exe -m unittest tests.test_acquisition_m5 tests.test_agent_flow tests.test_stability_regression -v
```

New backend registry/lifecycle/installer work should add focused `unittest` coverage before wiring into CLI/MCP.
