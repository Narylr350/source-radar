import argparse

from .adapters import collect_fixture_items
from .evidence import build_evidence_cards
from .judgement import judge_claim
from .models import VerifyReport
from .reporting import render_json, render_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="source-radar")
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify = subparsers.add_parser("verify", help="verify a claim or query")
    verify.add_argument("claim")
    verify.add_argument("--format", choices=("json", "markdown"), default="json")

    return parser


def run_verify(claim: str, output_format: str) -> str:
    items = collect_fixture_items(claim)
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "verify":
        print(run_verify(args.claim, args.format))
        return 0
    parser.error(f"unknown command: {args.command}")
    return 2
