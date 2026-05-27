import argparse
import json
import os
import pathlib
import sys
from getpass import getpass

from .agent import VerificationAgent
from .acquisition import default_providers
from .bridge import add_bridge_subparsers, load_local_env, run_bridge_from_args
from .cookie_capture import cookie_set, cookie_show, run_cookie
from .uninstall import run_uninstall
from .engine import (
    run_engine_install,
    run_engine_list,
    run_engine_start,
    run_engine_status,
    run_engine_stop,
    run_install,
    run_install_agent,
    run_setup_plan,
)
from .config import (
    clear_openai_config,
    clear_provider_config,
    load_openai_config,
    load_provider_configs,
    save_openai_config,
    save_provider_config,
)
from .health import build_health_report, probe_adapter
from .integrations import audit_integrations, build_integration_status_report
from .reporting import (
    render_health_json,
    render_health_markdown,
    render_integration_audit_json,
    render_integration_audit_markdown,
    render_json,
    render_markdown,
    render_probe_json,
    render_probe_markdown,
    render_synthesis_json,
    render_synthesis_markdown,
)
from .runtime import local_services_for_query


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="source-radar")
    subparsers = parser.add_subparsers(dest="command", required=True)
    provider_names = tuple(provider.provider for provider in default_providers())

    verify = subparsers.add_parser("verify", help="verify a claim or query")
    verify.add_argument("claim")
    verify.add_argument("--format", choices=("json", "markdown"), default="json")
    verify.add_argument(
        "--progress",
        action="store_true",
        help="show progress messages on stderr",
    )
    verify.add_argument(
        "--local-services",
        action="store_true",
        help="start supported local services for this run when possible",
    )
    verify.add_argument(
        "--source",
        choices=("auto", *provider_names),
        default="auto",
    )
    verify.add_argument("--url", help="URL for web or official source collection")
    verify.add_argument("--repo", help="GitHub owner/repository slug or URL")

    research = subparsers.add_parser(
        "research", help="deep research: decompose complex questions, plan, collect, synthesize"
    )
    research.add_argument("query")
    research.add_argument("--format", choices=("json", "markdown"), default="markdown")
    research.add_argument("--max-rounds", type=int, default=1,
                          help="max research rounds (v1: always 1)")
    research.add_argument("--local-services", action="store_true",
                          help="start local services for this run")
    research.add_argument("--progress", action="store_true",
                          help="show progress messages on stderr")

    ask = subparsers.add_parser("ask", help="analyze a question from collected sources")
    ask.add_argument("query")
    ask.add_argument("--format", choices=("json", "markdown"), default="markdown")
    ask.add_argument(
        "--source",
        choices=("auto", *provider_names),
        default="auto",
    )
    ask.add_argument("--url", help="URL for direct webpage analysis")
    ask.add_argument("--repo", help="GitHub owner/repository slug or URL")
    ask.add_argument(
        "--local-services",
        action="store_true",
        help="start supported local services for this run when possible",
    )
    ask.add_argument(
        "--progress",
        action="store_true",
        help="show progress messages on stderr",
    )

    install_cmd = subparsers.add_parser(
        "install",
        help="full guided setup: engines + AI config + cookies",
    )
    install_cmd.add_argument(
        "--agent",
        action="store_true",
        help="non-interactive mode for AI agents: engines only, no prompts",
    )

    uninstall = subparsers.add_parser(
        "uninstall", help="remove source-radar local files"
    )
    uninstall.add_argument("--project", action="store_true", help="remove project-local files (.venv, .source-radar, external/)")
    uninstall.add_argument("--skill", action="store_true", help="remove Claude Code Skill")
    uninstall.add_argument("--user-config", dest="user_config", action="store_true", help="remove user-level config including API key")
    uninstall.add_argument("--all", dest="all_", action="store_true", help="remove project files, skill, and user config")
    uninstall.add_argument("--yes", action="store_true", help="actually delete files (default is dry-run)")

    setup_plan_cmd = subparsers.add_parser(
        "setup-plan",
        help="output initialization requirements for AI agents",
    )
    setup_plan_cmd.add_argument(
        "--format", choices=("json", "text"), default="json",
    )

    setup_shortcut = subparsers.add_parser(
        "setup",
        help="guided local AI setup shortcut",
    )
    setup_shortcut.set_defaults(command="setup")

    probe = subparsers.add_parser("probe", help="probe one source provider")
    probe.add_argument("--source", choices=provider_names, required=True)
    probe.add_argument("--url", help="URL for web or official adapter probing")
    probe.add_argument("--repo", help="GitHub owner/repository slug or URL")
    probe.add_argument("--query", help="Query for search or external bridge provider probing")
    probe.add_argument("--format", choices=("json", "markdown"), default="json")

    health = subparsers.add_parser("health", help="show adapter health status")
    health.add_argument("--format", choices=("json", "markdown"), default="json")

    bridge = subparsers.add_parser(
        "bridge",
        help="run a local source-radar bridge for selected crawler backends",
    )
    add_bridge_subparsers(bridge)

    integrations = subparsers.add_parser(
        "integrations",
        help="inspect optional external integrations",
    )
    integration_subparsers = integrations.add_subparsers(
        dest="integration_command",
        required=True,
    )
    audit = integration_subparsers.add_parser(
        "audit",
        help="show optional integration license boundaries",
    )
    audit.add_argument("--format", choices=("json", "markdown"), default="json")
    status = integration_subparsers.add_parser(
        "status",
        help="show optional integration bridge status",
    )
    status.add_argument("--format", choices=("json", "markdown"), default="json")

    cookie = subparsers.add_parser(
        "cookie",
        help="open browser to capture platform login cookies",
    )
    cookie.add_argument(
        "--platform",
        help="capture cookies for a specific platform only",
    )
    cookie.add_argument(
        "--force",
        action="store_true",
        help="re-capture even if cookies are already configured",
    )
    cookie_subs = cookie.add_subparsers(dest="cookie_subcommand")
    cookie_set_cmd = cookie_subs.add_parser(
        "set", help="write cookie value directly (for AI agent use)"
    )
    cookie_set_cmd.add_argument("--platform", required=True, help="platform key")
    cookie_set_cmd.add_argument("--value", required=True, help="cookie string")
    cookie_subs.add_parser("show", help="show cookie status for all platforms")

    engine = subparsers.add_parser(
        "engine",
        help="manage crawler engines (trafilatura, crawl4ai, mediacrawler)",
    )
    engine_sub = engine.add_subparsers(dest="engine_command", required=True)
    engine_sub.add_parser("list", help="list all engines and their status")
    engine_sub.add_parser("status", help="check engine readiness with fix hints")
    engine_install_cmd = engine_sub.add_parser(
        "install", help="install crawler engine dependencies"
    )
    engine_install_cmd.add_argument("--core", action="store_true", default=True,
                                    help="install core engines (Trafilatura + Crawl4AI)")
    engine_install_cmd.add_argument("--browser", action="store_true",
                                    help="install Playwright Chromium browser")
    engine_install_cmd.add_argument("--community", action="store_true",
                                    help="install MediaCrawler for Chinese community platforms")
    engine_install_cmd.add_argument("--all", dest="all_", action="store_true",
                                    help="install everything (core + browser + community)")

    engine_start = engine_sub.add_parser("start", help="start a service engine")
    engine_start.add_argument("name", help="engine name (e.g. mediacrawler)")
    engine_stop = engine_sub.add_parser("stop", help="stop a service engine")
    engine_stop.add_argument("name", help="engine name (e.g. mediacrawler)")

    config = subparsers.add_parser("config", help="manage local source-radar settings")
    config_subparsers = config.add_subparsers(dest="config_command", required=True)
    setup = config_subparsers.add_parser(
        "setup",
        help="prompt for local AI provider settings",
    )
    setup.set_defaults(config_command="setup")
    set_openai = config_subparsers.add_parser(
        "set-openai",
        help="save local AI provider settings (OpenAI-compatible, Anthropic, Gemini, etc.)",
    )
    set_openai.add_argument("--api-key", required=True)
    set_openai.add_argument("--endpoint", default="https://api.openai.com/")
    set_openai.add_argument("--model", default="gpt-4.1-mini")
    set_openai.add_argument("--provider", default="openai",
                            choices=("openai", "anthropic", "gemini", "x-api-key"),
                            help="API protocol type")
    set_provider = config_subparsers.add_parser(
        "set-provider",
        help="save local crawler/search provider bridge settings",
    )
    set_provider.add_argument("--name", required=True)
    set_provider.add_argument("--endpoint", default="")
    set_provider.add_argument("--command", dest="provider_command", default="")
    config_subparsers.add_parser("show", help="show local settings with secrets masked")
    config_subparsers.add_parser("clear-openai", help="remove local AI credentials")
    clear_provider = config_subparsers.add_parser(
        "clear-provider",
        help="remove local provider bridge settings",
    )
    clear_provider.add_argument("--name", required=True)
    test_ai = config_subparsers.add_parser(
        "test-ai", help="test configured AI endpoint connectivity"
    )
    test_ai.add_argument("--format", choices=("text", "json"), default="text")

    return parser


def run_verify(
    claim: str,
    output_format: str,
    source: str = "auto",
    url: str | None = None,
    repo: str | None = None,
    progress: bool = False,
    local_services: bool = False,
) -> str:
    with local_services_for_query(claim, enabled=local_services):
        report = VerificationAgent().verify(
            claim,
            source=source,
            url=url,
            repo=repo,
            progress=_progress_writer if progress else None,
        )
    if output_format == "markdown":
        return render_markdown(report)
    return render_json(report)


def run_ask(
    query: str,
    output_format: str,
    source: str = "auto",
    url: str | None = None,
    repo: str | None = None,
    local_services: bool = False,
    progress: bool = False,
) -> str:
    with local_services_for_query(query, enabled=local_services):
        report = VerificationAgent().ask(
            query,
            source=source,
            url=url,
            repo=repo,
            progress=_progress_writer if progress else None,
        )
    if output_format == "json":
        return render_synthesis_json(report)
    return render_synthesis_markdown(report)


def run_probe(
    source: str,
    output_format: str,
    url: str | None,
    repo: str | None,
    query: str | None = None,
) -> str:
    result = probe_adapter(
        source,
        url=url,
        repo=repo,
        query=query,
        providers=default_providers(),
    )
    if output_format == "markdown":
        return render_probe_markdown(result)
    return render_probe_json(result)


def run_health(output_format: str) -> str:
    report = build_health_report()
    if output_format == "markdown":
        return render_health_markdown(report)
    return render_health_json(report)


def run_integrations_audit(output_format: str) -> str:
    audit = audit_integrations()
    if output_format == "markdown":
        return render_integration_audit_markdown(audit)
    return render_integration_audit_json(audit)


def run_integrations_status(output_format: str) -> str:
    report = build_integration_status_report()
    if output_format == "markdown":
        return render_integration_audit_markdown(report)
    return render_integration_audit_json(report)


def run_config_set_openai(api_key: str, endpoint: str, model: str, provider: str = "openai") -> str:
    save_openai_config(api_key=api_key, endpoint=endpoint, model=model, provider=provider)
    return f"AI config saved: {endpoint} / {model} ({provider})"


def run_config_setup(root: str | os.PathLike[str] = ".") -> str:
    api_key = getpass("API key: ")
    endpoint = input("Endpoint [https://api.openai.com/]: ").strip()
    endpoint = endpoint or "https://api.openai.com/"

    # Fetch available models
    from .config import fetch_models

    models = fetch_models(endpoint, api_key)
    if models:
        print(f"\n可用模型 ({len(models)} 个):")
        for i, m in enumerate(models):
            print(f"  [{i}] {m}")
        choice = input(f"选择模型编号 [默认 0]: ").strip()
        try:
            model = models[int(choice)]
        except (ValueError, IndexError):
            model = models[0]
    else:
        print("无法获取模型列表，请手动输入模型名")
        model = input("Model [gpt-4.1-mini]: ").strip()
        model = model or "gpt-4.1-mini"

    save_openai_config(api_key=api_key, endpoint=endpoint, model=model)
    lines = [f"AI config saved: {endpoint} / {model}"]

    local_env_path = pathlib.Path(root) / ".source-radar" / "local.env"
    if local_env_path.exists():
        lines.append(f"Bridge credentials: {local_env_path}")
    else:
        lines.append(f"Bridge credentials (optional): {local_env_path}")

    return "\n".join(lines)


def run_config_show() -> str:
    openai = load_openai_config()
    providers = {
        name: {
            "enabled": config.get("enabled", "false") == "true",
            "endpoint": config.get("endpoint", ""),
            "command": config.get("command", ""),
        }
        for name, config in sorted(load_provider_configs().items())
    }
    from .acquisition import _auto_discover_bridge_endpoint

    bridges = {}
    for name in ("firecrawl", "mediacrawler"):
        discovered = _auto_discover_bridge_endpoint(name)
        bridges[name] = {
            "available": bool(discovered),
            "endpoint": discovered or providers.get(name, {}).get("endpoint", ""),
        }
    payload = {
        "openai": {
            "configured": bool(openai.get("api_key")),
            "api_key": _mask_secret(openai.get("api_key", "")),
            "endpoint": openai.get("endpoint", ""),
            "model": openai.get("model", ""),
        },
        "providers": providers,
        "bridges": bridges,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def run_config_clear_openai() -> str:
    clear_openai_config()
    return "OpenAI-compatible AI config cleared."


def run_config_set_provider(name: str, endpoint: str, command: str) -> str:
    save_provider_config(name, endpoint=endpoint, command=command, enabled=True)
    return f"{name} provider config saved locally."


def run_config_clear_provider(name: str) -> str:
    clear_provider_config(name)
    return f"{name} provider config cleared."


def _mask_secret(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 6:
        return "***"
    return f"{secret[:3]}...{secret[-3:]}"


def write_output(output: str) -> None:
    text = output + "\n"
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        safe_text = text.encode(encoding, errors="replace").decode(
            encoding,
            errors="replace",
        )
        sys.stdout.write(safe_text)


def _progress_writer(message: str) -> None:
    sys.stderr.write(f"进度: {message}\n")
    sys.stderr.flush()


def _render_research_markdown(report) -> str:
    lines = [
        "# 深度研究结果",
        "",
        f"问题: {report.query}",
        f"状态: {report.status}",
        f"执行轮数: {report.executed_rounds}",
        "",
        "## 结论",
        report.conclusion or "未能综合出结论",
        "",
    ]
    if report.recommended_steps:
        lines.append("## 推荐方案 / 操作步骤")
        for step in report.recommended_steps:
            lines.append(f"- {step}")
        lines.append("")
    if report.key_findings:
        lines.append("## 关键发现")
        for f in report.key_findings:
            lines.append(f"- {f}")
        lines.append("")

    lines.append("## 信息来源与适用性")
    sp = report.source_profile or {}
    parts = []
    if sp.get("official"): parts.append(f"官方 {sp['official']} 条")
    if sp.get("review"): parts.append(f"评测 {sp['review']} 条")
    if sp.get("community"): parts.append(f"社区经验 {sp['community']} 条")
    if sp.get("video"): parts.append(f"视频 {sp['video']} 条")
    if sp.get("unknown"): parts.append(f"其他 {sp['unknown']} 条")
    lines.append(f"来源构成: {', '.join(parts) if parts else '无'}")
    lines.append(f"社区一致性: {report.consensus}")
    lines.append(f"可迁移性: {report.transferability}")
    lines.append(f"适用方式: {report.applicability}")
    lines.append("")

    if report.gaps:
        lines.append("## 风险与不确定性")
        for g in report.gaps:
            lines.append(f"- {g}")
        lines.append("")

    if report.risk_level in ("medium", "high"):
        lines.append("这不是保稳方案，只能作为起步参考；最终以你自己的验证为准。")
        lines.append("")

    if report.evidence:
        lines.append("## 参考来源")
        for card in report.evidence:
            lines.append(f"- **{card.title}**")
            if card.url:
                lines.append(f"  {card.url}")
            lines.append(f"  类型: {card.source_type} | 适配器: {card.adapter}")
            if card.summary:
                lines.append(f"  {card.summary[:160]}")
        lines.append("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    load_local_env()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "verify":
        try:
            output = run_verify(
                args.claim,
                args.format,
                args.source,
                args.url,
                args.repo,
                args.progress,
                args.local_services,
            )
        except ValueError as error:
            parser.error(str(error))
        write_output(output)
        return 0
    if args.command == "research":
        try:
            with local_services_for_query(args.query, enabled=args.local_services):
                report = VerificationAgent().research(
                    args.query,
                    max_rounds=args.max_rounds,
                    local_services=args.local_services,
                    progress=_progress_writer if args.progress else None,
                )
        except ValueError as error:
            parser.error(str(error))
        if args.format == "json":
            write_output(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        else:
            write_output(_render_research_markdown(report))
        return 0
    if args.command == "ask":
        try:
            output = run_ask(
                args.query,
                args.format,
                args.source,
                args.url,
                args.repo,
                args.local_services,
                args.progress,
            )
        except ValueError as error:
            parser.error(str(error))
        write_output(output)
        return 0
    if args.command == "install":
        if getattr(args, "agent", False):
            write_output(run_install_agent())
        else:
            write_output(run_install())
        return 0
    if args.command == "uninstall":
        write_output(run_uninstall(
            project=args.project,
            skill=args.skill,
            user_config=args.user_config,
            all_=args.all_,
            yes=args.yes,
        ))
        return 0
    if args.command == "setup-plan":
        write_output(run_setup_plan(format=args.format))
        return 0
    if args.command == "setup":
        write_output(run_config_setup())
        return 0
    if args.command == "probe":
        write_output(run_probe(args.source, args.format, args.url, args.repo, args.query))
        return 0
    if args.command == "health":
        write_output(run_health(args.format))
        return 0
    if args.command == "bridge":
        run_bridge_from_args(args)
        return 0
    if args.command == "integrations":
        if args.integration_command == "audit":
            write_output(run_integrations_audit(args.format))
            return 0
        if args.integration_command == "status":
            write_output(run_integrations_status(args.format))
            return 0
    if args.command == "config":
        if args.config_command == "setup":
            write_output(run_config_setup())
            return 0
        if args.config_command == "set-openai":
            write_output(
                run_config_set_openai(args.api_key, args.endpoint, args.model,
                                     provider=getattr(args, "provider", "openai"))
            )
            return 0
        if args.config_command == "set-provider":
            write_output(
                run_config_set_provider(args.name, args.endpoint, args.provider_command)
            )
            return 0
        if args.config_command == "show":
            write_output(run_config_show())
            return 0
        if args.config_command == "clear-openai":
            write_output(run_config_clear_openai())
            return 0
        if args.config_command == "clear-provider":
            write_output(run_config_clear_provider(args.name))
            return 0
        if args.config_command == "test-ai":
            from .config import test_openai_config
            fmt = getattr(args, "format", "text")
            write_output(test_openai_config(format=fmt))
            return 0
    if args.command == "cookie":
        if args.cookie_subcommand == "set":
            write_output(cookie_set(platform=args.platform, value=args.value))
            return 0
        if args.cookie_subcommand == "show":
            write_output(cookie_show())
            return 0
        write_output(run_cookie(platform=args.platform, force=args.force))
        return 0
    if args.command == "engine":
        if args.engine_command == "list":
            write_output(run_engine_list())
            return 0
        if args.engine_command == "status":
            write_output(run_engine_status())
            return 0
        if args.engine_command == "install":
            all_ = getattr(args, "all_", False)
            browser = getattr(args, "browser", False) or all_
            community = getattr(args, "community", False) or all_
            write_output(run_engine_install(browser=browser, community=community))
            return 0
        if args.engine_command == "start":
            write_output(run_engine_start(args.name))
            return 0
        if args.engine_command == "stop":
            write_output(run_engine_stop(args.name))
            return 0
    parser.error(f"unknown command: {args.command}")
    return 2
