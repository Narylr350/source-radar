# source-radar

中文互联网信息分析 CLI —— 自动跨平台搜索、采集、综合，交给 AI 出结论。

## Claude Code Skill（推荐使用方式）

source-radar 的核心使用方式是 **Claude Code Skill**：安装后在对话中直接说"帮我查一下 XX"，Claude Code 自动调用 source-radar 搜索中文互联网，综合结果返回给你。

### 安装 Skill

**第一步：克隆项目**

```powershell
git clone https://github.com/Narylr350/source-radar.git
cd source-radar
```

**第二步：安装 Skill 文件**

将 `skills/source-radar/` 复制到 Claude Code 的技能目录：

```powershell
# Windows (PowerShell)
Copy-Item -Recurse skills/source-radar/ $env:USERPROFILE\.claude\skills\source-radar\

# macOS / Linux
cp -r skills/source-radar/ ~/.claude/skills/source-radar/
```

Claude Code 重启后自动加载。

**第三步：环境初始化**

```powershell
uv run python -m source_radar install
```

这一步会依次：
1. 安装三个爬虫引擎（Trafilatura / Crawl4AI / MediaCrawler）
2. 引导配置 AI（API key、端点、模型，支持 OpenAI 兼容接口）
3. 引导浏览器登录各平台获取 Cookie

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

## Cookie 获取

各中文平台需要登录态才能搜索。运行 `cookie` 命令，会自动打开真实 Chrome 浏览器，依次导航到各平台首页：

```powershell
uv run python -m source_radar cookie
```

流程：浏览器打开 → 你手动登录 → 按 Enter 确认 → 自动捕获 Cookie → 写入 `local.env`

- 已配置的平台自动跳过
- `--force` 强制全部重新获取
- 登录态持久化在 `.source-radar/browser-profiles/`，下次复用

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
| `config setup/set-openai/show/clear-openai` | 管理 AI 配置 |
| `config set-provider/clear-provider` | 管理 Provider 桥配置 |
| `integrations audit/status` | 查看外部集成许可和状态 |

## 开发

```powershell
git clone https://github.com/Narylr350/source-radar.git
cd source-radar
uv sync --extra dynamic
uv run crawl4ai-setup
uv run python -m unittest discover -s tests -v   # 145 tests
```

## 许可证

核心仓库：Apache-2.0。第三方爬虫引擎通过外部集成方式使用，源码不进入核心：

- **Trafilatura**：GPL-3.0，通过 pip 包 API 调用
- **Crawl4AI**：Apache-2.0，通过 pip 包 API 调用
- **MediaCrawler**：非商业学习/研究许可，通过外部 bridge 调用，不 vendor 源码
