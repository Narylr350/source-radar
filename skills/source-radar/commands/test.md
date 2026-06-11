---
description: "Run source-radar tests. Supports full suite, specific test file, or specific test class/method."
---

# Run Tests

Run the source-radar test suite using uv.

## Usage

Pass a test target as `$ARGUMENTS`. If empty, runs the full suite.

Examples:
- `$ARGUMENTS` = empty → full suite: `uv run python -m unittest discover -s tests -v`
- `$ARGUMENTS` = `test_v3_hardening` → specific file: `uv run python -m unittest tests.test_v3_hardening -v`
- `$ARGUMENTS` = `test_agent_flow` → specific file: `uv run python -m unittest tests.test_agent_flow -v`
- `$ARGUMENTS` = `test_cli.CliTests.test_config_setup` → specific method

## Command

```bash
uv run python -m unittest $ARGUMENTS -v 2>&1 | tail -20
```

If `$ARGUMENTS` is empty, use the discover form instead:

```bash
uv run python -m unittest discover -s tests -v 2>&1 | grep -E "^(Ran|OK|FAILED|FAIL:)" | tail -20
```

## Notes

- Run from the project root (`D:\Narylr\source-radar`).
- Use `uv run python -m unittest` (not `python tests/...`) for proper module resolution.
- Timeout: 180000ms for full suite, 120000ms for individual files.
- On failure, show the last 20 lines so the user sees error details.
