# source-radar

面向外部 AI 的本地信息采集引擎，通过 **MCP Server** 和 **CLI** 提供网页搜索、正文提取、GitHub 检索与中文社区采集能力。

`source-radar` 不负责代替 AI 回答问题，而是把搜索、抓取、缓存、后端状态和失败原因转换为可追踪的信息，供 AI 继续核验和综合。

当前版本：`0.2.0a1`

## 当前能力

| 能力 | 当前实现 |
| --- | --- |
| 网页搜索 | SearXNG 优先的搜索路由，失败和降级状态可见 |
| 网页正文 | Trafilatura 静态抽取，必要时使用 Crawl4AI 浏览器渲染 |
| 搜索并抓取 | 批量搜索后抓取前若干结果正文 |
| GitHub 搜索 | 原生搜索 GitHub Issue 和 Pull Request |
| GitHub 文件 | 按仓库路径或 GitHub URL 获取源码文件 |
| B站搜索 | `BilibiliNativeBackend` 公共视频搜索 |
| 其他中文平台 | MediaCrawler 本地服务：小红书、微博、贴吧、抖音、知乎 |
| 后端状态 | Registry、installer、lifecycle 和健康诊断 |
| 后端管理 | CLI 和 MCP 均可执行 status/start/stop/install |
| MCP transport | stdio 和 SSE |
| 本地缓存 | 搜索、正文、下载、engine、browser profile 和运行状态统一管理 |

### 当前中文平台边界

中文平台目前处于混合实现状态：

```text
B站搜索
→ source-radar BilibiliNativeBackend
→ Bilibili public search API

小红书 / 微博 / 贴吧 / 抖音 / 知乎
→ source-radar MediaCrawler bridge
→ 本地 MediaCrawler 服务
→ platform
```

B站当前只实现视频搜索和基础错误诊断，不包含视频详情、评论、弹幕、字幕或用户空间采集。

## 架构

```text
CLI / MCP Client
        │
        ▼
source-radar
  ├─ Agent / Search Planner
  ├─ Acquisition Kernel
  ├─ Backend Registry
  ├─ Backend Lifecycle Manager
  ├─ Engine Installer
  ├─ Cache / Session / Trace
  └─ Evidence normalization
        │
        ├─ Web search providers
        ├─ Trafilatura
        ├─ Crawl4AI
        ├─ GitHub provider
        ├─ Bilibili native search
        └─ MediaCrawler service adapter
```

后端失败时会尽量返回结构化状态：

```text
status
reason
message
retryable
fix
warnings
diagnostics
```

调用方可以据此区分未安装、未启动、缺少 Cookie、限流、超时和后端错误，而不必只依赖空结果猜测。

## 环境要求

- Windows 10/11
- Python `3.11`～`3.13`
- [uv](https://docs.astral.sh/uv/)
- Git

Crawl4AI、SearXNG 和 MediaCrawler 是可选能力，按使用场景安装。

## 快速开始

```powershell
git clone https://github.com/Narylr350/source-radar.git
cd source-radar
uv sync --extra dev --extra mcp
.\source-radar.ps1 --help
```

`source-radar.ps1` 会固定使用项目内 `.venv`，并把本地配置根目录设置为：

```text
<repo>\.source-radar\
```

### 常用 CLI

```powershell
# 分析问题
.\source-radar.ps1 ask "为什么某个游戏只在特定电脑上蓝屏"

# 核验断言
.\source-radar.ps1 verify "某次更新会导致特定驱动冲突"

# 多轮研究
.\source-radar.ps1 research "调查某个软件故障的社区报告和官方说明"

# 查看环境和后端状态
.\source-radar.ps1 health
.\source-radar.ps1 engine status

# 查看初始化需求
.\source-radar.ps1 setup-plan
```

也可以直接使用安装后的命令：

```powershell
uv run source-radar --help
uv run source-radar ask "问题"
```

## MCP Server

当前 MCP Server 暴露 8 个工具。

| 工具 | 用途 |
| --- | --- |
| `web_search` | 网页搜索，支持 site、分页和跳过缓存 |
| `fetch_url` | 抽取单个网页正文，支持长文分页 |
| `search_github` | 搜索 GitHub Issue 和 Pull Request |
| `search_chinese_platforms` | 搜索中文社区平台 |
| `fetch_github_file` | 获取 GitHub 仓库文件 |
| `fetch_search_results` | 搜索并批量抓取前若干结果正文 |
| `source_status` | 查看 source-radar、后端和缓存状态 |
| `manage_backend` | 管理 SearXNG 或 MediaCrawler 的安装与运行状态 |

### stdio

直接启动：

```powershell
.\source-radar.ps1 mcp
```

MCP 客户端配置示例：

```json
{
  "mcpServers": {
    "source-radar": {
      "command": "powershell.exe",
      "args": [
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "D:\\path\\to\\source-radar\\source-radar.ps1",
        "mcp"
      ]
    }
  }
}
```

初次注册 MCP 时客户端仍需要知道启动脚本的位置；连接成功后，后端管理通过 `manage_backend` 完成，外部 AI 不需要再拼接项目内部 Python 或 `uv` 命令。

### SSE

启动后台 SSE Server：

```powershell
.\start-mcp-sse.ps1
```

默认地址：

```text
http://127.0.0.1:8765/sse
```

指定端口：

```powershell
.\start-mcp-sse.ps1 -Port 64343
```

对应 MCP 配置：

```json
{
  "type": "sse",
  "url": "http://127.0.0.1:64343/sse",
  "headers": {}
}
```

当前实现没有 `/stream` Streamable HTTP endpoint。

### 后端自动启动

MCP 搜索可以按 lifecycle policy 尝试启动已安装的 service backend。可以通过环境变量关闭：

```powershell
$env:SOURCE_RADAR_BACKEND_AUTOSTART = "0"
```

只关闭 SearXNG 自动启动：

```powershell
$env:SOURCE_RADAR_SEARXNG_AUTOSTART = "0"
```

安装始终是显式操作；普通搜索不会自动下载大型组件。

## Engine 管理

查看状态：

```powershell
.\source-radar.ps1 engine list
.\source-radar.ps1 engine status
```

安装核心正文抽取能力：

```powershell
.\source-radar.ps1 engine install --core
```

安装 Playwright 浏览器：

```powershell
.\source-radar.ps1 engine install --browser
```

安装中文社区后端：

```powershell
.\source-radar.ps1 engine install --community
```

安装 SearXNG：

```powershell
.\source-radar.ps1 engine install --searxng
```

安装全部可选组件：

```powershell
.\source-radar.ps1 engine install --all
```

启停服务后端：

```powershell
.\source-radar.ps1 engine start searxng
.\source-radar.ps1 engine stop searxng

.\source-radar.ps1 engine start mediacrawler
.\source-radar.ps1 engine stop mediacrawler
```

查看可复用或可修复内容：

```powershell
.\source-radar.ps1 engine repair
.\source-radar.ps1 engine cleanup
```

`cleanup` 当前只显示 dry-run 候选，不直接删除文件。

### 通过 MCP 管理

连接 MCP 后，外部 AI 可以直接调用：

```text
manage_backend(backend="searxng", action="status")
manage_backend(backend="searxng", action="start")
manage_backend(backend="mediacrawler", action="install")
```

`install` 只在调用方显式指定时执行。

## 中文平台和 Cookie

支持的当前平台 key：

| 平台 | key | 当前路径 |
| --- | --- | --- |
| 小红书 | `xhs` | MediaCrawler bridge |
| 微博 | `wb` | MediaCrawler bridge |
| B站 | `bili` | native search |
| 贴吧 | `tieba` | MediaCrawler bridge |
| 抖音 | `dy` | MediaCrawler bridge |
| 知乎 | `zhihu` | MediaCrawler bridge |

查看 Cookie 状态：

```powershell
.\source-radar.ps1 cookie show
```

打开浏览器捕获指定平台登录态：

```powershell
.\source-radar.ps1 cookie --platform bili
.\source-radar.ps1 cookie --platform xhs
```

强制重新捕获：

```powershell
.\source-radar.ps1 cookie --platform wb --force
```

直接写入 Cookie：

```powershell
.\source-radar.ps1 cookie set --platform bili --value "<cookie>"
```

该方式会把 Cookie 放入命令行参数；需要避免 shell history 时，优先使用浏览器捕获。Cookie 和 browser profile 保存在 `.source-radar/`，不会进入 Git。

B站公共视频搜索可以在没有 Cookie 时尝试，但结果和风控诊断可能受限。其他平台是否需要 Cookie 取决于 MediaCrawler 当前的平台实现和登录状态。

## 本地目录

所有本地下载和运行数据集中到：

```text
.source-radar/
  config.json
  local.env
  engines/
    mediacrawler/
    searxng/
  downloads/
    wheels/
  browser-profiles/
  sessions/
  runtime/
  pids/
  logs/
  cache/
  tmp/
```

设计目的：

- 下载一次，多次复用；
- 固定源码和版本信息可诊断；
- 网络失败后可以 repair；
- 减少散落的 clone、wheel 和浏览器缓存；
- 统一查看、备份和清理本地状态。

以下内容不得提交：

- Cookie、API key 和登录态；
- `.source-radar/` runtime；
- backend 源码 checkout；
- browser profile；
- pid、日志和缓存；
- `.venv/`。

历史 `external/` 路径不参与当前安装、启动或状态判断。

## AI 配置

交互式配置：

```powershell
.\source-radar.ps1 config setup
```

查看配置：

```powershell
.\source-radar.ps1 config show
```

测试 AI Provider：

```powershell
.\source-radar.ps1 config test-ai
```

配置写入 `.source-radar/config.json` 或 `.source-radar/local.env`。不要把凭据写进仓库文件。

AI 用于搜索规划、语义质量判断和综合；backend 安装、生命周期、缓存、参数校验和错误状态由确定性代码管理。

## 主要 CLI 命令

| 命令 | 用途 |
| --- | --- |
| `ask` | 收集来源并分析问题 |
| `verify` | 核验断言并输出证据 |
| `research` | 多轮规划、采集和综合 |
| `install` | 引导式安装与配置 |
| `uninstall` | 清理本地安装和状态 |
| `cache` | 查看或清理采集缓存 |
| `session` | 管理追问上下文 |
| `probe` | 检查单个 provider |
| `health` | 查看整体健康状态 |
| `engine` | 安装、启停和诊断 backend |
| `cookie` | 管理中文平台 Cookie |
| `config` | 管理 AI 和 provider 配置 |
| `mcp` | 启动 stdio 或 SSE MCP Server |
| `integrations` | 查看可选外部集成 |

以本地 CLI 帮助为准：

```powershell
.\source-radar.ps1 --help
.\source-radar.ps1 engine --help
.\source-radar.ps1 mcp --help
```

## 开发

```powershell
git clone https://github.com/Narylr350/source-radar.git
cd source-radar
uv sync --extra dev --extra mcp
```

运行 focused MCP 测试：

```powershell
.venv\Scripts\python.exe -m unittest tests.test_mcp_server tests.test_mcp_stdio tests.test_mcp_autostart -v
```

运行 backend 和 lifecycle 测试：

```powershell
.venv\Scripts\python.exe -m unittest tests.test_backend_registry tests.test_lifecycle_ensure_ready tests.test_engine_installer -v
```

运行全部测试：

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

提交前检查：

```powershell
git status --short --branch
git diff --check
```

## 许可证

source-radar 核心使用 [Apache License 2.0](LICENSE)。

可选第三方组件保留各自的许可证和使用条件，包括 Trafilatura、Crawl4AI、Playwright、SearXNG 和 MediaCrawler。第三方源码和运行环境安装在本地 `.source-radar/engines` 或 `.venv`，不提交到 source-radar Git 仓库。

如果需要分发包含第三方组件的完整安装包，应分别检查对应版本的许可证和分发要求；普通 clone、安装和本地运行不会改变 source-radar 仓库自身的许可证文件。
