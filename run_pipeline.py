#!/usr/bin/env python3
"""CLI for the LinkedIn → ResumeUp → Easy Apply pipeline."""

from __future__ import annotations

import argparse
import json
import os
import sys

from dotenv import load_dotenv

from application_orchestrator import (
    check_pipeline_setup,
    export_queue_csv,
    get_application_history,
    run_apply_from_queue,
    run_search_and_tailor,
)
from application_store import update_application_status
from constants import DEFAULT_MIN_MATCH_SCORE, DEFAULT_SEARCH_LIMIT


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, indent=2))


def cmd_doctor(_args: argparse.Namespace) -> int:
    load_dotenv()
    result = check_pipeline_setup()
    _print_json(result)
    return 0 if result["ready"] else 1


def cmd_search(args: argparse.Namespace) -> int:
    load_dotenv()
    result = run_search_and_tailor(
        keywords=args.keywords,
        location=args.location,
        easy_apply_only=not args.include_non_easy_apply,
        remote_only=args.remote_only,
        limit=args.limit,
        min_match_score=args.min_match_score,
        file_path=args.resume,
        resume_id=args.resume_id,
        target_score=args.target_score,
        daily_cap=args.daily_cap,
        dedupe_company_title=not args.no_dedupe,
    )
    _print_json(result)
    return 0 if result.get("success") else 1


def cmd_queue(args: argparse.Namespace) -> int:
    load_dotenv()
    result = get_application_history(status=args.status, limit=args.limit)
    _print_json(result)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    load_dotenv()
    result = export_queue_csv(output_path=args.output, status=args.status)
    _print_json(result)
    return 0 if result.get("success") else 1


def cmd_approve(args: argparse.Namespace) -> int:
    load_dotenv()
    application = update_application_status(args.application_id, "approved")
    if application is None:
        _print_json({"success": False, "message": f"Not found: {args.application_id}"})
        return 1
    _print_json({"success": True, "application": application.to_dict()})
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    load_dotenv()
    result = run_apply_from_queue(
        application_id=args.application_id,
        require_approval=not args.submit,
        submit=args.submit,
        max_custom_questions=args.max_custom_questions,
        use_llm=not args.no_llm,
    )
    _print_json(result)
    return 0 if result.get("success") else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="LinkedIn job search → ResumeUp tailor → Easy Apply queue",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Check env, profile, and defaults")
    doctor.set_defaults(func=cmd_doctor)

    search = subparsers.add_parser("search", help="Search LinkedIn and tailor resumes")
    search.add_argument("keywords", help="Job search keywords")
    search.add_argument("--location", default="", help="Location filter")
    search.add_argument("--resume", help="Path to base resume PDF/DOCX")
    search.add_argument("--resume-id", help="Existing ResumeUp resume ID")
    search.add_argument("--limit", type=int, default=DEFAULT_SEARCH_LIMIT)
    search.add_argument("--min-match-score", type=float, default=DEFAULT_MIN_MATCH_SCORE)
    search.add_argument("--target-score", type=int, default=95)
    search.add_argument("--daily-cap", type=int, default=None)
    search.add_argument("--remote-only", action="store_true")
    search.add_argument("--include-non-easy-apply", action="store_true")
    search.add_argument("--no-dedupe", action="store_true")
    search.set_defaults(func=cmd_search)

    queue = subparsers.add_parser("queue", help="Show application review queue")
    queue.add_argument("--status", help="Filter by status (tailored, approved, applied, ...)")
    queue.add_argument("--limit", type=int, default=50)
    queue.set_defaults(func=cmd_queue)

    export = subparsers.add_parser("export", help="Export queue to CSV")
    export.add_argument("--output", default="applications_queue.csv")
    export.add_argument("--status")
    export.set_defaults(func=cmd_export)

    approve = subparsers.add_parser("approve", help="Approve a tailored application")
    approve.add_argument("application_id")
    approve.set_defaults(func=cmd_approve)

    apply_cmd = subparsers.add_parser("apply", help="Run Easy Apply for a queued job")
    apply_cmd.add_argument("application_id")
    apply_cmd.add_argument("--submit", action="store_true", help="Submit after pre-fill")
    apply_cmd.add_argument("--max-custom-questions", type=int, default=None)
    apply_cmd.add_argument("--no-llm", action="store_true")
    apply_cmd.set_defaults(func=cmd_apply)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
