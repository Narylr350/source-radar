import argparse
import sys

from .adapters import (
    collect_fixture_items,
    collect_github_repo,
    collect_official_page,
    collect_web_page,
)
from .evidence import build_evidence_cards
from .health import build_health_report, probe_adapter
from .integrations import audit_integrations, build_integration_status_report
from .judgement import judge_claim
from .models import VerifyReport
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
        choices=("fixture", "web", "official", "github"),
        default="fixture",
    )
    verify.add_argument("--url", help="URL for web or official source collection")
    verify.add_argument("--repo", help="GitHub owner/repository slug or URL")

    probe = subparsers.add_parser("probe", help="probe one source adapter")
    probe.add_argument("--source", choices=("fixture", "web", "official", "github"), required=True)
    probe.add_argument("--url", help="URL for web or official adapter probing")
    probe.add_argument("--repo", help="GitHub owner/repository slug or URL")
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

    return parser


def collect_items(source: str, claim: str, url: str | None, repo: str | None):
    if source == "web":
        if not url:
            raise ValueError("--url is required when --source web")
        return collect_web_page(url)
    if source == "official":
        if not url:
            raise ValueError("--url is required when --source official")
        return collect_official_page(url)
    if source == "github":
        target_repo = repo or claim
        return collect_github_repo(target_repo)
    return collect_fixture_items(claim)


def run_verify(
    claim: str,
    output_format: str,
    source: str = "fixture",
    url: str | None = None,
    repo: str | None = None,
) -> str:
    items = collect_items(source, claim, url, repo)
    evidence = build_evidence_cards(items)
    judgement = judge_claim(claim, evidence)
    report = VerifyReport(
        claim=claim,
        status=judgement.status,
        evidence=evidence,
        judgement=judgement,
    )
    if output_format == "markdown":
        return render_markdown(report)
    return render_json(report)


def run_probe(source: str, output_format: str, url: str | None, repo: str | None) -> str:
    result = probe_adapter(source, url=url, repo=repo)
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
        write_output(run_probe(args.source, args.format, args.url, args.repo))
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
    parser.error(f"unknown command: {args.command}")
    return 2
