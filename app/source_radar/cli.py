import argparse
import json
import sys
from getpass import getpass

from .agent import VerificationAgent
from .acquisition import default_providers
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
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="source-radar")
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify = subparsers.add_parser("verify", help="verify a claim or query")
    verify.add_argument("claim")
    verify.add_argument("--format", choices=("json", "markdown"), default="json")
    verify.add_argument(
        "--source",
        choices=("auto", "fixture", "web", "official", "github"),
        default="auto",
    )
    verify.add_argument("--url", help="URL for web or official source collection")
    verify.add_argument("--repo", help="GitHub owner/repository slug or URL")

    provider_names = tuple(provider.provider for provider in default_providers())
    probe = subparsers.add_parser("probe", help="probe one source provider")
    probe.add_argument("--source", choices=provider_names, required=True)
    probe.add_argument("--url", help="URL for web or official adapter probing")
    probe.add_argument("--repo", help="GitHub owner/repository slug or URL")
    probe.add_argument("--query", help="Query for search or external bridge provider probing")
    probe.add_argument("--format", choices=("json", "markdown"), default="json")

    health = subparsers.add_parser("health", help="show adapter health status")
    health.add_argument("--format", choices=("json", "markdown"), default="json")

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

    config = subparsers.add_parser("config", help="manage local source-radar settings")
    config_subparsers = config.add_subparsers(dest="config_command", required=True)
    setup = config_subparsers.add_parser(
        "setup",
        help="prompt for local AI provider settings",
    )
    setup.set_defaults(config_command="setup")
    set_openai = config_subparsers.add_parser(
        "set-openai",
        help="save local OpenAI-compatible AI provider settings",
    )
    set_openai.add_argument("--api-key", required=True)
    set_openai.add_argument("--endpoint", default="https://api.openai.com/")
    set_openai.add_argument("--model", default="gpt-4.1-mini")
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

    return parser


def run_verify(
    claim: str,
    output_format: str,
    source: str = "auto",
    url: str | None = None,
    repo: str | None = None,
) -> str:
    report = VerificationAgent().verify(
        claim,
        source=source,
        url=url,
        repo=repo,
    )
    if output_format == "markdown":
        return render_markdown(report)
    return render_json(report)


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


def run_config_set_openai(api_key: str, endpoint: str, model: str) -> str:
    save_openai_config(api_key=api_key, endpoint=endpoint, model=model)
    return "OpenAI-compatible AI config saved locally."


def run_config_setup() -> str:
    api_key = getpass("API key: ")
    endpoint = input("Endpoint [https://api.openai.com/]: ").strip()
    model = input("Model [gpt-4.1-mini]: ").strip()
    save_openai_config(
        api_key=api_key,
        endpoint=endpoint or "https://api.openai.com/",
        model=model or "gpt-4.1-mini",
    )
    return "OpenAI-compatible AI config saved locally."


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
    payload = {
        "openai": {
            "configured": bool(openai.get("api_key")),
            "api_key": _mask_secret(openai.get("api_key", "")),
            "endpoint": openai.get("endpoint", ""),
            "model": openai.get("model", ""),
        },
        "providers": providers,
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "verify":
        try:
            output = run_verify(args.claim, args.format, args.source, args.url, args.repo)
        except ValueError as error:
            parser.error(str(error))
        write_output(output)
        return 0
    if args.command == "probe":
        write_output(run_probe(args.source, args.format, args.url, args.repo, args.query))
        return 0
    if args.command == "health":
        write_output(run_health(args.format))
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
                run_config_set_openai(args.api_key, args.endpoint, args.model)
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
    parser.error(f"unknown command: {args.command}")
    return 2
