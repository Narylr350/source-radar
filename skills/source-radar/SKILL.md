---
name: source-radar
description: >
  Chinese internet research and fact-checking CLI. Use when the user wants to search, research, verify claims, or find information on Chinese platforms (小红书/微博/B站/贴吧/抖音/知乎). Triggers include: "查一下", "搜索", "验证", "核验", "有没有关于...的讨论", "X上说Y是真的吗", "帮我查", "搜一下". Use for any research task involving Chinese-language sources, community discussions, product reviews, tutorials, or fact verification.
---

# Source Radar

Search and analyze the Chinese internet using source-radar.

## Tool boundaries (READ THIS FIRST)

When this skill is invoked, source-radar is the PRIMARY research tool.

**Do NOT bypass source-radar:**
- Do NOT call Web Search / WebFetch just because source-radar results look incomplete
- Do NOT supplement source-radar findings with your own search
- If evidence is weak or missing, say exactly that — do not silently fill gaps

**Only use external Web Search when:**
1. source-radar command fails entirely (crash, not "weak results"), OR
2. The user explicitly asks you to use normal web search, OR
3. You clearly label it as fallback outside source-radar

**Command scope:**
- `doctor`, `research`, `ask`, `verify`, `start`, `stop`, `status`, `cookie` are Skill wrapper commands: `python <skill-dir>/scripts/run.py <command>`
- Do NOT run `uv run python -m source_radar doctor` — doctor only exists in the wrapper
- For main CLI commands use `uv run python -m source_radar <command>`

## Initialization flow for AI agents

When installing source-radar for the user, NEVER run `uv sync` directly. Follow this flow:

### 1. Clone and run agent-mode install

```bash
git clone https://github.com/Narylr350/source-radar.git
cd source-radar
uv run python -m source_radar install --agent
```

`install --agent` installs engine dependencies but does NOT prompt for input.

After installing, persist the project path so future sessions can find it:
```bash
export SOURCE_RADAR_HOME="$(pwd)"    # Linux/macOS — add to ~/.bashrc or ~/.zshrc
setx SOURCE_RADAR_HOME "%cd%"        # Windows — persists across sessions
```

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
uv run python -m source_radar config set-ai --api-key "<key>" --endpoint "<endpoint>" --model "gpt-4.1-mini"
uv run python -m source_radar config test-ai --format json
```

The JSON output contains `available_models` — show this list to the user and ask which model they want. Then update:

```bash
uv run python -m source_radar config set-ai --api-key "<key>" --endpoint "<endpoint>" --model "<chosen_model>"
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
- Check configured platform status: `uv run python -m source_radar cookie show`
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

### Routing: ask vs verify vs research

Choose the right command based on the user's intent:

**Use `research` when the user asks a complex open-ended question:**
- "X 怎么弄 / 怎么选 / 怎么超频 / 怎么调 / 怎么配置比较稳"
- "X 值不值得 / 给完整方案 / 帮我整理方案"
- "X 争议怎么回事 / 社区经验汇总 / 对比分析"
- Hardware tuning, buying advice, community experience, full plans

```bash
uv run python -m source_radar research "query" --local-services
```

**research 耗时较长（3-8 分钟），必须使用 `run_in_background: true`，不要设短超时：**

```json
{
  "command": "uv run python -m source_radar research \"query\" --local-services",
  "run_in_background": true,
  "timeout": 600000
}
```

当 `research` 适用时：
- Run exactly ONE `research` command first.
- Do NOT manually rewrite the question into multiple `ask` commands.
- Do NOT call Web Search / WebFetch to supplement.
- If research returns partial-evidence, planner-fallback, or insufficient-evidence, report that status and the gaps. Do not silently do external search.
- **research does NOT support --session.** Session context is for ask/verify only.

**Use `verify` when the user asks a yes/no factual question:**
- "X 是真的吗？" / "X 死了吗？" / "X 发生了吗？"
- Rumor checking, whether a claim is true

```bash
uv run python -m source_radar verify "claim"
```

**Use `ask` for simple one-shot research:**
- "帮我查一下 X" / "搜索 X" / "X 是什么？"
- Simple how-to, quick lookups

```bash
uv run python -m source_radar ask "query"
```

Rule of thumb: complex multi-aspect → `research`. yes/no → `verify`. simple lookup → `ask`.

### Default progress output

`ask`, `verify`, and `research` all show progress on stderr by default (timestamps like `[00:05]`). Use `--quiet` to suppress progress. JSON output on stdout is never polluted by progress messages.

```bash
uv run python -m source_radar ask "query" --quiet --format json
```

### Adaptive collection (ask/verify source=auto)

When `source=auto` (the default), ask and verify use adaptive collection:

1. **Search first**: always starts with a search.
2. **AI evaluator** decides whether evidence is sufficient or a next tool is needed.
3. **max_tools=3**: at most 3 tools run (e.g., search + trafilatura + 1 more).
4. **MediaCrawler is NOT run by default** — only selected for Chinese community controversies, platform opinions, or user experience claims. To enable MediaCrawler, pass `--local-services` (requires the service to be running: `engine start mediacrawler`).
5. **verify mode is stricter**: if all evidence is search-result only, it forces trafilatura for full-text extraction before accepting sufficiency.

The AI evaluator tracks skip_tools (tools it considered but decided not to run) and reason for each skip.

### Session context (ask/verify only)

Ask and verify support session context for follow-up questions:

```bash
uv run python -m source_radar ask "9800x3d 怎么超频" --session oc
uv run python -m source_radar ask "那内存怎么调" --session oc   # recognized as follow-up
```

- **--session <id>**: uses session context (default: "default").
- **--no-session**: disables session context entirely.
- Session reads last 10 records within 24 hours.
- Uses AI relevance evaluator first, falls back to lexical matching if AI fails.
- Session records are trimmed (max snippet 300 chars, max summary 500 chars).
- **Session does NOT store cookies, API keys, or full webpage content.**
- **research does NOT support session context.** It always starts fresh.

```bash
uv run python -m source_radar session status   # show session stats
uv run python -m source_radar session clear --session oc  # clear a session
uv run python -m source_radar session new      # generate new session ID
```

### Acquisition cache

Caches provider.collect() results (NOT final AI answers) for reuse:

```bash
uv run python -m source_radar cache status   # show cache stats
uv run python -m source_radar cache clear    # clear all cache
uv run python -m source_radar cache prune    # prune expired entries
```

- Real-time queries (containing 今天/现在/最新/股价/天气 etc.) are NOT cached.
- Only successful results (ok/items-found/candidates-found) are cached.
- Cache TTL varies by provider: search=6h, trafilatura=24h, mediacrawler=12h.
- Cache entries include elapsed_ms, cache_age_seconds, and provider signature.
- Cache directory: `.source-radar/cache/acquisition/`

### Deep research

research 耗时较长（3-8 分钟），**必须使用 `run_in_background: true`**：

```json
{
  "command": "uv run python -m source_radar research \"complex question\" --max-rounds 2 --local-services",
  "run_in_background": true,
  "timeout": 600000
}
```

`research` handles internally: query decomposition → planning → multiple queries → deduplication → synthesis. Do NOT manually run multiple `ask` commands with rewritten queries for the same research task.

### Simple research

```bash
uv run python -m source_radar ask "simple question"
```

### Verify claims

```bash
uv run python -m source_radar verify "the claim to check"
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
2. **Complex research**: `scripts/run.py research "complex query"` (deep research, auto-checks env)
3. **Simple lookup**: `scripts/run.py ask "query"` (one-shot, auto-checks env)
4. **Verify**: `scripts/run.py verify "claim"` (fact-checking, auto-checks env)
5. **Report results**: Summarize key findings in Chinese. Include notable sources and disagreements.
6. **Cleanup**: Optionally `stop` services when done.

## Source selection

- **General web search**: Default — uses search engines + Trafilatura + Crawl4AI
- **Chinese community platforms**: Pass `--local-services` to enable MediaCrawler for 小红书/微博/B站/贴吧/抖音/知乎
- **Both**: Pass `--local-services` to include community alongside general web search

## AI configuration

source-radar needs an AI API key to run synthesis and evaluation. It supports OpenAI, Anthropic, Google Gemini, and any OpenAI-compatible local model (LM Studio, Ollama, etc.).

### If user provides API key in conversation

Save it directly via CLI (no interactive prompts needed):

**OpenAI or OpenAI-compatible / local model:**
```bash
uv run python -m source_radar config set-ai --api-key "sk-xxx" --endpoint "https://api.openai.com/" --model "gpt-4.1-mini"
```

**Anthropic Claude:**
```bash
uv run python -m source_radar config set-ai --api-key "sk-ant-xxx" --endpoint "https://api.anthropic.com/" --model "claude-3-5-haiku-latest" --provider anthropic
```

**Google Gemini:**
```bash
uv run python -m source_radar config set-ai --api-key "AIzaXXX" --endpoint "https://generativelanguage.googleapis.com/" --model "gemini-2.0-flash" --provider gemini
```

**Local model (LM Studio / Ollama — OpenAI-compatible):**
```bash
uv run python -m source_radar config set-ai --api-key "sk-local" --endpoint "http://127.0.0.1:1234/" --model "llama-3.2-3b"
```

`--provider` choices: `openai` (default, Bearer token), `anthropic` (x-api-key header), `gemini` (/v1beta/models), `x-api-key` (x-api-key header, other providers).

### Interactive setup (user doesn't know the flow)

Guide them to run `uv run python -m source_radar config setup` — it will prompt for provider type, API key, endpoint, and automatically fetch available models to choose from.

### Check current config

```bash
uv run python -m source_radar config show
```

## Troubleshooting

- **"AI 未配置"**: Ask user which AI provider they use (OpenAI / Anthropic / Gemini / local model), then run the appropriate `config set-ai` command above. Or guide to `uv run python -m source_radar config setup`.
- **"Cookie 未配置"**: Guide user to run `uv run python -m source_radar cookie`. To check which platforms are configured: `uv run python -m source_radar cookie show`. To set a specific platform: `uv run python -m source_radar cookie set --platform <key>`.
- **"Playwright 未安装"**: Guide user to run `uv run python -m source_radar engine install --browser`
- **"MediaCrawler 未安装"**: Guide user to run `uv run python -m source_radar engine install --community`
