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

`install --agent` only installs core engines (Trafilatura + Crawl4AI pip packages). After core completes, proactively ask the user:

> "核心引擎安装完成。是否继续安装增强组件？
> 1. Playwright Chromium 浏览器（动态页面渲染，下载约 150MB）
> 2. MediaCrawler 社区引擎（微博/小红书/B站/贴吧/抖音搜索，需 clone GitHub 仓库）
> 3. 全部安装
> 4. 暂不安装，以后再说"

If the user chooses to install, run the corresponding command:
```bash
uv run python -m source_radar engine install --browser     # choice 1
uv run python -m source_radar engine install --community   # choice 2
uv run python -m source_radar engine install --all         # choice 3
```

Do NOT just print the commands and move on. Actively ask and execute for the user.

Read `setup-plan` JSON. It tells you:
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

### Routing: ask vs verify

Choose the right command based on the user's intent:

**Use `verify` when the user asks a yes/no factual question:**
- "X 是真的吗？" / "X 死了吗？" / "X 发生了吗？"
- "验证一下 X" / "核验 X" / "check if X"
- Any claim that can be confirmed or disproven

**Use `ask` when the user wants open-ended research:**
- "帮我查一下 X" / "搜索 X" / "find information about X"
- "X 是什么？" / "X 的最新进展" / "X 的讨论"
- Tutorials, reviews, comparisons, how-to questions

Rule of thumb: if the answer is "yes/no" or "true/false", use `verify`. If the answer is a summary or explanation, use `ask`.

### Research

```bash
python <skill-dir>/scripts/run.py ask "the user's query"
```

If the user explicitly asks about 小红书/微博/B站/贴吧/抖音/知乎, community discussions, or social platform evidence, add `--local-services`:

```bash
python <skill-dir>/scripts/run.py ask --local-services "query about Chinese social platforms"
```

Do NOT modify the user's original query to trigger platform search. Use the flag.

### Verify claims

```bash
python <skill-dir>/scripts/run.py verify "the claim to check"
```

Same rule for `--local-services` applies for verification of claims involving Chinese community platforms.

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

## Source selection

- **General web search**: Default — uses search engines + Trafilatura + Crawl4AI
- **Chinese community platforms**: Pass `--local-services` to enable MediaCrawler for 小红书/微博/B站/贴吧/抖音/知乎
- **Both**: Pass `--local-services` to include community alongside general web search

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
- **"Playwright 未安装"**: Guide user to run `uv run python -m source_radar engine install --browser`
- **"MediaCrawler 未安装"**: Guide user to run `uv run python -m source_radar engine install --community`
