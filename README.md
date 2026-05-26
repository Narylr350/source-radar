# source-radar

中文互联网信息分析 CLI —— 自动跨平台搜索、采集、综合，交给 AI 出结论。

## 解决什么问题

在中文互联网上搜资料、找观点、核验消息时，你需要同时查搜索引擎、社区平台（小红书/微博/B站/贴吧/抖音/知乎）、技术站点和 GitHub。source-radar 帮你一键完成这些平台的搜索和采集，把结果压缩成证据卡，再让 AI 综合出答案。

## 安装

```powershell
# 克隆仓库
git clone https://github.com/Narylr350/source-radar.git
cd source-radar

# 一键安装（引擎 + AI 配置 + Cookie 获取引导）
uv run python -m source_radar install
```

前置要求：Python >= 3.11、[uv](https://docs.astral.sh/uv/)、Git。

## 快速开始

```powershell
# 研究问题
uv run python -m source_radar ask "RTX 5090 电源兼容问题的中文社区反馈"

# 核验消息
uv run python -m source_radar verify "某产品宣布涨价 30%" --progress

# 查看引擎状态
uv run python -m source_radar engine list
```

或用 PowerShell 快捷入口：

```powershell
.\source-radar.ps1 ask "小红书和 B 站上有哪些 AI 编程工具实测？"
```

## 命令一览

| 命令 | 作用 |
|------|------|
| `install` | 一键安装：引擎 + AI 配置 + Cookie 获取 |
| `ask <问题>` | 综合信息分析，返回 Markdown 报告 |
| `verify <断言>` | 严格核验，返回证据卡和可信度判断 |
| `cookie` | 打开浏览器引导登录各平台，自动捕获 Cookie |
| `engine list` | 列出爬虫引擎状态 |
| `engine start/stop` | 启停服务型引擎（MediaCrawler） |
| `engine install` | 安装全部爬虫引擎依赖 |
| `probe --source <name>` | 检查单个采集源是否就绪 |
| `health` | 查看整体健康状态 |
| `config` | 管理 AI/Provider 配置 |
| `integrations` | 查看外部集成许可和状态 |

## 工作原理

```
用户输入问题
  → agent 规划采集源：search / mediacrawler / trafilatura / crawl4ai
  → 各 provider 并行搜索和采集
  → 结果清洗去重，压缩为证据卡
  → AI 基于证据卡输出：综合回答、关键要点、来源分布、分歧争议、噪音提示
```

### 三个引擎

| 引擎 | 类型 | 用途 |
|------|------|------|
| Trafilatura | library | 通用网页正文抽取，轻量快速 |
| Crawl4AI | library | 浏览器渲染动态页面，处理 JS 页面 |
| MediaCrawler | service | 中文社区平台搜索（小红书/微博/B站/贴吧/抖音/知乎） |

## AI 配置

```powershell
# 交互式配置
uv run python -m source_radar config setup

# 命令行配置
uv run python -m source_radar config set-openai --api-key "sk-xxx" --endpoint "https://api.openai.com/" --model "gpt-4.1-mini"

# 查看配置（密钥已脱敏）
uv run python -m source_radar config show
```

支持任何 OpenAI 兼容 API（本地模型、第三方代理等）。

## Cookie 获取

运行 `source-radar cookie` 会依次打开真实 Chrome 浏览器，导航到各平台首页，你手动登录后按 Enter 即可自动捕获 Cookie。已配置的平台自动跳过，支持 `--force` 强制更新。

Cookie 保存在 `.source-radar/local.env`（Git 已忽略），格式与 MediaCrawler 兼容。

## 开发

```powershell
# 运行测试
uv run python -m unittest discover -s tests -v

# 当前测试覆盖：145 个
```

## 许可证

核心仓库：Apache-2.0。第三方爬虫引擎通过外部集成方式使用，源码不进入核心：

- **Trafilatura**：GPL-3.0，通过 pip 包 API 调用
- **Crawl4AI**：Apache-2.0，通过 pip 包 API 调用
- **MediaCrawler**：非商业学习/研究许可，通过外部 bridge 调用，不 vendor 源码

## Claude Code Skill

项目包含 Claude Code 技能文件（`~/.claude/skills/source-radar/`），安装后可直接在对话中说"帮我查一下..."触发自动搜索。
