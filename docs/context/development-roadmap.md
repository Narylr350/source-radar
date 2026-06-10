# Development Roadmap

## Goal Route

先建立可信的来源发现与采集地基，再把主体验做成综合信息分析 agent，最后才考虑 skill / MCP / Claude Code / Codex 等 AI 可调用包装。当前路线重点是：真实搜索/爬虫 provider、license-safe external bridge、多源采集规划、采集过程可观测、证据压缩、稳定引用，以及面向搜索结果综合的 `ask` 报告。

## MVP Definition

Python-first CLI；自研低成本采集覆盖普通网页、搜索结果、官网/公告、GitHub；定义稳定 adapter 协议；生成标准证据卡；调用 LLM 输出综合信息分析和严格核验判断；支持平台配置和本地 Cookie/Token 边界；提供 adapter health/probe；记录第三方许可证与 optional integration 策略；查不到时输出 no-evidence。

## Milestones

- M0: 仓库与完整文档骨架
- M1: 最小 CLI 核验链路（已建立 fixture-backed 本地链路）
- M2: 自研低成本采集与证据卡（已建立 web / official / GitHub adapters）
- M3: adapter health/probe 与平台状态报告（已建立）
- M4: 可选外部集成 bridge 与许可证审计（已建立）
- Core AI agent correction: `verify` 默认内置 agent 主流程，本地 AI provider 配置与 fallback 已建立
- M5: Firecrawl + MediaCrawler source-acquisition foundation（已建立）
  - 真实搜索 / 来源发现已接入 `search` provider，普通 claim 不再主要依赖 fixture fallback
  - crawler/search provider interface 已统一内置 adapter、Firecrawl bridge、MediaCrawler bridge 的采集语义
  - Firecrawl 等 AGPL 项目只能走 API/服务 bridge；MediaCrawler 等受限许可证项目只能走 external/local bridge，不 vendor 源码
  - agent 已能按 claim 类型规划采集 provider，并把采集过程写入 trace
  - verify 报告已记录 searched providers、候选来源、采集成功/失败原因和证据缺口
  - `probe` / `health` 已重定位为 provider-aware 状态检查，报告 provider 配置、候选数和结构化失败原因
  - external bridge endpoint 作为 base URL，约定 `GET /manifest`、`GET /health`、`POST /collect`
  - Firecrawl / MediaCrawler bridge 通过 `source-radar.bridge.v1` manifest 暴露 capabilities 和 AI guidance，供内置 agent 自动选择
  - `source-radar bridge firecrawl` / `source-radar bridge mediacrawler` 提供第一方本机 bridge 运行器，分别调用 Firecrawl MCP 和用户本地 MediaCrawler WebUI API
  - `health` / `probe` / `verify.agent.acquisition` 暴露 reason、fix、retryable、warnings、evidence_gaps、diagnostics，便于外部判断出什么问题和怎么修
  - 测试覆盖 agent 使用真实 `ExternalBridgeProvider` 的模拟 bridge、service-unreachable、auth-missing 等故障路径
  - README 明确手动安装、未来自动下载、预打包分发时必须保留 Firecrawl / MediaCrawler 的 upstream license、version、source URL、NOTICE 和许可证义务
- M6: 综合信息分析 agent（已建立）
  - `ask` 成为主入口：输入问题，自动采集来源，输出综合信息分析报告
  - `verify` 保留严格 claim verification，不再代表唯一主体验
  - AI 输出 `summary`、`key_points`、`source_notes`、`disagreements`、`noise_notes`
  - Markdown 聚焦综合回答、搜索结果要点、来源分布、分歧/争议、噪音提示、采集过程、结果清单
  - `source-radar.ps1 setup` / `source-radar.ps1 ask` 提供易用入口，减少长命令和多窗口启动
  - JSON 面向机器稳定，Markdown 面向人类可读
- M7: 真实平台与配置体验（已完成）
  - 平台开关、Cookie/Token 引用、本地凭据边界
  - 受限平台结构化失败原因和健康探针
  - 更好的错误提示、重试边界和用户操作建议
- M8: 核心接口稳定与回归测试扩展（已完成）
  - 冻结 verify/probe/health/config 的主要 JSON contract
  - 加强端到端 fixture、adapter contract、AI provider mock 和报告回归测试
  - JSON 合约文档: `docs/engineering/json-contract.md`
  - 合约回归测试: `tests/test_json_contract.py` (17 tests, 121 total)
- M9: v3.1 证据保真升级（已完成）
  - EvidenceCard 增加 raw_excerpt（3000 字符）、distilled（AI 结构化提取）、compression 元数据
  - source_fidelity 标注：snippet_only / excerpt / full_or_long_excerpt
  - loss_risk 标注：snippet_only 为 high
  - content_hash 覆盖 raw_content
  - AI distill 机制：自动判断何时做结构化提取
  - distill token budget 限制（最多 12 张卡，18000 字符总预算）
  - AI API 调用重试机制（指数退避 2s→5s→10s，最多 3 次）
  - 搜索引擎从 DuckDuckGo 切换为 Bing
  - MediaCrawler 修复：平台名映射、CDP 超时、bridge 超时
- Deferred: Claude Code skill / Codex skill / MCP 包装
  - 只有在 CLI 核心 contract 稳定后再做，避免 wrapper 跟随核心频繁返工

## Success Metrics

- 一次 CLI 调用能输出结构化证据卡和综合信息分析报告
- 普通网页、官网公告、GitHub 三类低成本来源至少有可运行 adapter
- 至少一个真实搜索/爬虫 provider 或 external bridge 能从普通 claim 发现候选来源
- ask/verify 报告能说明采集 provider、候选来源、成功/失败原因和来源质量提示
- provider-aware `probe` 能检查单个采集 provider 的配置、连通性、凭据需求和最小返回能力
- provider-aware `health` 能汇总真实采集地基状态，而不是只做静态 adapter smoke
- 受限平台能声明未启用、需要凭据或结构化失败原因
- no-evidence 结果稳定且可机器读取
- LLM 综合分析和判断必须引用证据卡 ID
- 浏览器兜底不是默认路径

## Explicit Non-Goals

v1 不做 Web UI 或桌面 UI；不做人工手动补证据入口；不绕过登录、破解访问控制、反检测或验证码；不做大规模批量采集或监控；不直接 vendor MediaCrawler 或 Firecrawl 源码；不把 LLM 判断伪装为最终事实裁定。

## Key Workflow Sequence

- ask: 输入问题并输出综合信息分析报告
- verify: 输入 claim/query 并输出证据卡与严格核验报告
- probe: 对平台 adapter 执行低成本健康检查
- health: 查看平台状态、失败原因和上游更新提示
- config: 管理平台开关、凭据引用和采集限制
- integrations: 配置可选外部 MediaCrawler/Firecrawl 兼容 bridge

## Risks and Open Questions

Risks:

- 第三方项目许可证可能限制集成方式
- 中文平台页面和风控变化快
- 用户 Cookie/Token 涉及本地凭据安全
- LLM 可能过度推断
- 搜索引擎和平台可能限流
- adapter 健康探针需要低成本且不过度访问
- Apache-2.0 核心必须避免复制不兼容源码

Open questions:

- 第一批中文平台 adapter 优先级仍需确认
- 长期采用 optional integration、API bridge、本地服务 bridge、fork bridge 还是自研 adapter 的比例待验证
- 是否需要本地缓存数据库待 MVP 后评估
- 是否输出数值 confidence score 待验证
- skill / MCP / AI-agent wrapper 已延期到核心 CLI contract 稳定后

## Notes

- This roadmap is for high-level delivery direction.
- Keep detailed implementation work in `docs/tasks/` and engineering contracts in `docs/engineering/`.
- Update this file when product scope or milestone meaning changes.
