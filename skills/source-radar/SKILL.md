---
name: source-radar
description: >
  Chinese internet research and fact-checking CLI. Use when the user wants to search, research, verify claims, or find information on Chinese platforms (小红书/微博/B站/贴吧/抖音/知乎). Triggers include: "查一下", "搜索", "验证", "核验", "有没有关于...的讨论", "X上说Y是真的吗", "帮我查", "搜一下". Use for any research task involving Chinese-language sources, community discussions, product reviews, tutorials, or fact verification.
---

# Source Radar

Search and analyze the Chinese internet using source-radar.

## Initialization flow for AI agents

When installing source-radar for the user, NEVER run `uv sync` directly. Follow this flow:

### 1. Clone and run agent-mode install

```bash
git clone https://github.com/Narylr350/source-radar.git
cd source-radar
uv run python -m source_radar install --agent
```

`install --agent` installs engine dependencies but does NOT prompt for input. It won't block waiting for user input.

### 2. Check what's needed

```bash
uv run python -m source_radar setup-plan --format json
```

Read the JSON output. It tells you:
- `required_inputs`: What MUST be configured (AI config — required)
- `optional_inputs`: What CAN be configured (cookies, engines)
- For each input: what commands to run to apply values

### 3. AI configuration (REQUIRED)

AI configuration is mandatory — without it source-radar cannot complete ask/verify.

If AI config is missing, ask the user for:
- API key
- Endpoint (default: https://api.openai.com/)

First apply with a temporary model, then fetch the model list so the user can choose:

```bash
uv run python -m source_radar config set-openai --api-key "<key>" --endpoint "<endpoint>" --model "gpt-4.1-mini"
uv run python -m source_radar config test-ai --format json
```

The JSON output contains `available_models` — show this list to the user and ask which model they want. Then update:

```bash
uv run python -m source_radar config set-openai --api-key "<key>" --endpoint "<endpoint>" --model "<chosen_model>"
```

Verify with:
```bash
uv run python -m source_radar config test-ai
```

Do NOT proceed to ask/verify until `config test-ai` passes.

**Security note:** The API key is stored in a local config file. The file permissions are set to owner-only (600/chmod on Unix, icacls on Windows). Remind users that the key is stored in plaintext and they can use environment variables (`OPENAI_API_KEY`) instead if they prefer not to persist to disk.

### 4. Cookies (optional)

Ask the user whether they want Chinese community platform access. If yes:
- They can send you Cookie strings from their browser's Network tab
- Write them with: `uv run python -m source_radar cookie set --platform <key> --value "<cookie>"`
- Or guide them to run `uv run python -m source_radar cookie` themselves

### 5. Verify

```bash
uv run python -m source_radar config test-ai
uv run python -m source_radar engine list
```

### Manual setup (for humans)

If the user is installing manually (not through you), tell them:
```bash
git clone https://github.com/Narylr350/source-radar.git && cd source-radar
uv run python -m source_radar install
```

## How to use

### Research

When the user asks to search or research something, use `scripts/run.py ask`:

```bash
python <skill-dir>/scripts/run.py ask "the user's query"
```

Add community platform names (小红书/微博/B站/贴吧/抖音) to the query to trigger platform search.

### Verify claims

```bash
python <skill-dir>/scripts/run.py verify "the claim to check"
```

### Service management

```bash
python <skill-dir>/scripts/run.py start    # start MediaCrawler
python <skill-dir>/scripts/run.py stop     # stop it
python <skill-dir>/scripts/run.py status   # check engine health
```

## Workflow

First time or if commands fail, run a health check:

```bash
python <skill-dir>/scripts/run.py doctor
```

Doctor checks every prerequisite: project root, uv, Python version, CLI, AI config, cookies, engine status. If it reports missing setup, guide the user through the printed commands before proceeding.

If doctor passes, run research or verification directly. `ask` and `verify` auto-run a lightweight check first — if the environment is not ready they will print setup guidance instead of failing with errors.

1. **Check**: `scripts/run.py doctor` shows what's ready and what's missing
2. **Research**: `scripts/run.py ask "query"` (auto-checks environment first)
3. **Verify**: `scripts/run.py verify "claim"` (auto-checks environment first)
4. **Report results**: Summarize key findings in Chinese. Include notable sources and disagreements.
5. **Cleanup**: Optionally `stop` services when done.

## Query types

- **Community/social**: Include 小红书/微博/B站/贴吧/抖音/知乎 in the query → triggers MediaCrawler
- **General web**: No platform keywords → uses search engines + Trafilatura + Crawl4AI
- **Mixed**: Combine both for broad coverage

## AI configuration

source-radar needs an OpenAI-compatible API key to run AI synthesis. If the user hasn't configured it yet:

### If user provides API key in conversation

Save it directly via CLI (no interactive prompts needed):

```bash
uv run python -m source_radar config set-openai --api-key "sk-xxx" --endpoint "https://api.openai.com/" --model "gpt-4.1-mini"
```

For non-OpenAI endpoints (local models, proxies), include `--endpoint` and `--model`:

```bash
uv run python -m source_radar config set-openai --api-key "sk-local-xxx" --endpoint "http://127.0.0.1:9317/" --model "gemini-3.5-flash"
```

### Interactive setup (user doesn't know the flow)

Guide them to run `uv run python -m source_radar config setup` — it will prompt for API key, endpoint, and automatically fetch available models to choose from.

### Check current config

```bash
uv run python -m source_radar config show
```

## Troubleshooting

- **"AI 未配置"**: Ask user for their API key and endpoint, then run `config set-openai` above. Or guide to `uv run python -m source_radar config setup`.
- **"Cookie 未配置"**: Guide user to run `uv run python -m source_radar cookie`
- **"Playwright 未安装"**: Guide user to run `uv run python -m source_radar engine install`
- **"MediaCrawler 未安装"**: Guide user to run `uv run python -m source_radar engine install`
