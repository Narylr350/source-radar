# source-radar

中文互联网信息分析 CLI —— 自动跨平台搜索、采集、综合，交给 AI 出结论。

## Claude Code Skill（推荐使用方式）

source-radar 的核心使用方式是 **Claude Code Skill**：安装后在对话中直接说"帮我查一下 XX"，Claude Code 自动调用 source-radar 搜索中文互联网，综合结果返回给你。

### 如果你是 AI Agent（Claude Code / Codex 等）在帮用户安装

**本项目有自己的 Agent 安装协议。不要按通用 Python/uv 项目经验自行推断安装步骤。**

#### 第 1 步：先读 Skill 文档

克隆后第一件事是读取项目的 Agent 安装指南，而不是直接跑 `uv sync`：

```bash
git clone https://github.com/Narylr350/source-radar.git
cd source-radar
python -c "from pathlib import Path; print(Path('skills/source-radar/SKILL.md').read_text(encoding='utf-8'))"
```

重点读 **"Initialization flow for AI agents"** 章节。

#### 第 2 步：安装 Skill 文件 + 非交互引擎安装

```powershell
# 安装 Skill（让后续对话自动触发）
mkdir -p ~/.claude/skills && cp -r skills/source-radar ~/.claude/skills/source-radar   # macOS / Linux
New-Item -ItemType Directory -Force $env:USERPROFILE\.claude\skills | Out-Null; Copy-Item -Recurse -Force skills/source-radar $env:USERPROFILE\.claude\skills\source-radar  # Windows

# 非交互安装引擎依赖（不会卡住，不会问你任何问题）
uv run python -m source_radar install --agent
```

#### 第 3 步：查看配置缺口

```bash
uv run python -m source_radar setup-plan --format json
```

根据返回的 `required_inputs` 向用户索要必需配置。**不要运行交互式 `install`（不带 --agent 的那个）。**

#### 禁止事项

- **不要直接跑 `uv sync` 或 `pip install`**——本项目依赖安装必须通过 `uv run python -m source_radar engine install` 或 `uv run python -m source_radar install --agent`
- **不要根据报错自行推断修复命令**——优先使用 `setup-plan` + `doctor` 的输出作为修复指引
- **不要跳过 Skill 直接凭 Python 经验操作**

### 如果你是真人手动安装

```powershell
git clone https://github.com/Narylr350/source-radar.git
cd source-radar

# 安装 Skill 文件
Copy-Item -Recurse skills/source-radar/ $env:USERPROFILE\.claude\skills\source-radar\

# 交互式一键安装（会问你 API key、打开浏览器等）
uv run python -m source_radar install
```

### 使用 Skill

安装完成后，在 Claude Code 对话中直接说：

```
"帮我查一下 RTX 5090 电源接口问题在中文社区的讨论"
"搜一下小红书和 B 站上关于 Python 教程的评价"
"验证这个消息：XX 产品宣布涨价 30%"
```

Skill 会自动：
1. 检测引擎状态，需要时启动 MediaCrawler
2. 根据问题类型选择合适的采集源
3. 执行搜索、采集、AI 综合
4. 返回分析报告（包含综合回答、关键要点、来源分布、分歧争议、噪音提示）

### Skill 文件结构

```
skills/source-radar/
├── SKILL.md          # 技能描述和触发条件
└── scripts/
    └── run.py        # 命令封装，自动管理服务生命周期
```

`run.py` 支持的命令：

| 命令 | 作用 |
|------|------|
| `run.py ask "问题"` | 综合信息分析 |
| `run.py verify "断言"` | 严格核验 |
| `run.py start` | 启动 MediaCrawler 服务 |
| `run.py stop` | 停止服务 |
| `run.py status` | 查看引擎状态 |
| `run.py cookie` | 获取平台 Cookie |

## 命令行直接使用

不使用 Skill 时，也可以直接调用 CLI：

```powershell
# 一键安装
uv run python -m source_radar install

# 研究问题
uv run python -m source_radar ask "RTX 5090 电源兼容问题的中文社区反馈"

# 核验消息
uv run python -m source_radar verify "某产品宣布涨价 30%" --progress

# 获取 Cookie
uv run python -m source_radar cookie

# 引擎管理
uv run python -m source_radar engine list
uv run python -m source_radar engine start mediacrawler
uv run python -m source_radar engine stop mediacrawler
```

或用 PowerShell 快捷入口：

```powershell
.\source-radar.ps1 setup       # 一键安装
.\source-radar.ps1 ask "..."   # 研究问题
.\source-radar.ps1 verify "..." # 核验消息
```

## 环境要求

| 依赖 | 用途 | 安装 |
|------|------|------|
| Python >= 3.11 | 运行时 | `winget install python` 或 https://python.org |
| uv | 包管理和虚拟环境 | `winget install astral-sh.uv` 或 https://docs.astral.sh/uv/ |
| Git | 克隆仓库和 MediaCrawler | `winget install Git.Git` 或 https://git-scm.com |
| Chrome | Cookie 捕获浏览器（真实 Chrome，非 Chromium） | 系统自带或用 `winget install Google.Chrome` |

项目默认使用阿里云 PyPI 镜像加速下载。如需切换回官方源：

```powershell
$env:UV_INDEX_URL = "https://pypi.org/simple"
```

## AI 配置

支持任何 OpenAI 兼容 API：

```powershell
# 交互式配置
uv run python -m source_radar config setup

# 命令行配置（本地模型示例）
uv run python -m source_radar config set-openai --api-key "sk-local-xxx" --endpoint "http://127.0.0.1:9317/" --model "gemini-3.5-flash"

# 查看配置（密钥已脱敏）
uv run python -m source_radar config show
```

环境变量也可覆盖：`OPENAI_API_KEY` / `SOURCE_RADAR_OPENAI_ENDPOINT` / `SOURCE_RADAR_OPENAI_MODEL`。

配置完成后验证连通性：

```powershell
uv run python -m source_radar config test-ai
```

## Cookie 获取（辅助工具）

中文社区平台需要登录态才能搜索。source-radar 提供浏览器辅助捕获工具，**但不能保证所有平台 100% 成功**——微博、小红书等平台有复杂的风控机制，特定环境、IP、设备指纹可能导致登录页白屏、弹窗空白、二维码不加载等。

### 优先方案：手动导入 Cookie（推荐）

这是最可靠的方式。用你的日常浏览器登录目标平台，从 Network 请求里复制 Cookie。

**从 Network 请求复制：**

1. 打开目标网站并确认已经登录
2. F12 → Network
3. 刷新页面
4. 点一个目标平台自己的请求（如 `weibo.com`、`xiaohongshu.com`）
5. Headers → Request Headers → Cookie，复制整段值
6. 写入 `.source-radar/local.env`

```env
SOURCE_RADAR_XHS_COOKIE="a1=xxx; web_session=xxx; ..."
SOURCE_RADAR_WEIBO_COOKIE="SUB=xxx; SCF=xxx; ..."
SOURCE_RADAR_BILI_COOKIE="SESSDATA=xxx; bili_jct=xxx; ..."
```

Network 里的 Cookie 就是浏览器实际发送的格式（`name=value; name2=value2`），直接用。

**备选：从 Application 手动拼接**

F12 → Application → Storage → Cookies → 选择目标域名，手动把 `name` 和 `value` 拼成 `name1=value1; name2=value2`。不要把 Domain、Path、Expires、HttpOnly 等属性拼进去。

**安全提醒：** Cookie 等同于登录态，不要分享给任何人，不要提交到 Git。`.source-radar/local.env` 应保持本地私有。不建议安装来历不明的 Cookie 浏览器扩展。

### 辅助方案：浏览器自动捕获

如果手动导入不方便，也可以尝试自动捕获（微博等平台可能因风控失败）：

```powershell
uv run python -m source_radar cookie                    # 所有未配置平台
uv run python -m source_radar cookie --platform wb      # 仅微博
uv run python -m source_radar cookie --platform wb --force  # 微博重新获取
```

- 已配置的平台自动跳过（除非 `--force`）
- 登录态持久化在 `.source-radar/browser-profiles/`，下次复用
- 微博最容易卡住，建议单独操作：`source-radar cookie --platform wb`

## 引擎架构

```
用户问题
  → agent 规划采集源
    ├─ search (DuckDuckGo)        → 搜索发现候选 URL
    ├─ trafilatura (GPL-3.0)      → 通用网页正文抽取
    ├─ crawl4ai  (Apache-2.0)     → 浏览器渲染动态页面
    └─ mediacrawler (外部 bridge)  → 中文社区平台搜索
  → 证据卡清洗去重
  → AI 综合输出
```

| 引擎 | 类型 | 用途 |
|------|------|------|
| Trafilatura | pip 包 | 通用网页正文抽取，轻量快速 |
| Crawl4AI | pip 包 + 浏览器 | 动态页面渲染采集 |
| MediaCrawler | 外部独立服务 | 小红书/微博/B站/贴吧/抖音/知乎搜索 |

## 全部 CLI 命令

| 命令 | 作用 |
|------|------|
| `install` | 一键安装：引擎 + AI 配置 + Cookie 获取 |
| `ask <问题>` | 综合信息分析，返回 Markdown 报告 |
| `verify <断言>` | 严格核验，返回证据卡和可信度判断 |
| `cookie` | 打开浏览器引导登录各平台，自动捕获 Cookie |
| `engine list` | 列出爬虫引擎状态 |
| `engine status` | 检查引擎就绪状态 + 修复建议 |
| `engine install` | 安装全部爬虫引擎依赖 |
| `engine start/stop <name>` | 启停服务型引擎 |
| `probe --source <name>` | 检查单个采集源是否就绪 |
| `health` | 查看整体健康状态 |
| `config setup/set-openai/show/clear-openai/test-ai` | 管理并验证 AI 配置 |
| `config set-provider/clear-provider` | 管理 Provider 桥配置 |
| `integrations audit/status` | 查看外部集成许可和状态 |

## 开发

```powershell
git clone https://github.com/Narylr350/source-radar.git
cd source-radar
uv sync --extra dev           # 安装全部可选引擎（含 trafilatura GPL-3.0 + crawl4ai Apache-2.0）
uv run crawl4ai-setup         # 安装 Playwright 浏览器
uv run python -m unittest discover -s tests -v   # 145 tests
```

如果只想要 Apache-2.0 组件，跳过 GPL-3.0：`uv sync --extra crawl4ai`

## 许可证与合规

**核心仓库：Apache-2.0。** 所有第三方引擎均为可选依赖，通过外部集成方式使用，源码不进入 Apache-2.0 核心。

| 组件 | 许可证 | 集成方式 | 合规说明 |
|------|--------|----------|----------|
| source-radar 核心 | Apache-2.0 | — | 自由使用、修改、分发 |
| Crawl4AI | Apache-2.0 | pip 可选包 (`uv sync --extra crawl4ai`) | 与核心兼容 |
| Playwright | Apache-2.0 | pip 包（Crawl4AI 依赖） | 与核心兼容 |
| Trafilatura | **GPL-3.0** | pip 可选包 (`uv sync --extra trafilatura`) | **Copyleft**：使用 Trafilatura 会使你的整体分发受 GPL-3.0 约束 |
| MediaCrawler | 非商业学习/研究 | 外部独立服务（bridge 调用） | 不 vendor 源码，用户自行安装 |
| Firecrawl | AGPL-3.0 | 外部 API/MCP（bridge 调用） | 不 vendor 源码，可选云端服务 |

**关键注意事项：**

- **Trafilatura 是 GPL-3.0**：它不是核心依赖，安装时明确标注许可证。如果你分发包含 Trafilatura 的 source-radar，整体可能需要遵守 GPL-3.0。如果你不需要 GPL 组件，跳过它：`source-radar` 核心在没有 Trafilatura 的情况下仍可通过 Crawl4AI（Apache-2.0）完成网页采集。
- **MediaCrawler 不得进入核心代码**：通过外部 bridge 进程调用，仅读取其 HTTP API。MediaCrawler 源码永远不进入 source-radar 仓库。
- **所有第三方许可文件**应随分发一起提供。自动安装脚本会显示上游项目、版本、许可证和源码 URL。
