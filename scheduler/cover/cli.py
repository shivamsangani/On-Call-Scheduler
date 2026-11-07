"""Command-line entry point for cover requests: parse, validate, rank, print."""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scheduler.core import render_schedule
from scheduler.cover.logic import (
    CoverError,
    CoverRequest,
    propose_override,
    rank_candidates,
    validate_request,
)
from scheduler.loader import InputError, format_time, load_overrides, load_schedule, parse_time
from scheduler.models import Override

# How much of the schedule to show either side of the request in the preview
PREVIEW_PADDING = timedelta(hours=6)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Find someone to cover part of your on-call shift.")
    parser.add_argument("text", nargs="?", default="", help='the request, e.g. "cinema Friday 7-10pm, can someone cover?"')
    parser.add_argument("--as", dest="requester", required=True, help="who is asking for cover")
    parser.add_argument("--schedule", required=True, help="path to the schedule JSON file")
    parser.add_argument("--overrides", help="path to the overrides JSON file (optional)")
    parser.add_argument("--mock", action="store_true", help="skip the LLM and use --start/--end instead")
    parser.add_argument("--start", help="start of the cover window (ISO 8601), used with --mock")
    parser.add_argument("--end", help="end of the cover window (ISO 8601), used with --mock")
    parser.add_argument("--write", action="store_true", help="append the proposed override to the overrides file")
    return parser


def build_request(args: argparse.Namespace, now: datetime) -> CoverRequest:
    """Turn the arguments into a CoverRequest, either from flags (--mock) or via the LLM."""
    if args.mock:
        if not args.start or not args.end:
            raise InputError("--mock needs both --start and --end")
        return CoverRequest(args.requester, parse_time(args.start), parse_time(args.end), args.text)

    if not args.text:
        raise InputError("give the request as text, or use --mock with --start and --end")
    # Imported here so --mock works without the anthropic package installed
    from scheduler.cover.parse_request import parse_with_llm

    return parse_with_llm(args.text, args.requester, now)


def append_override(path: str, override: Override) -> None:
    data = json.loads(Path(path).read_text())
    data.append(override_to_json(override))
    Path(path).write_text(json.dumps(data, indent=2) + "\n")


def override_to_json(override: Override) -> dict:
    return {
        "user": override.user,
        "start_at": format_time(override.start_at),
        "end_at": format_time(override.end_at),
    }


def main(argv: list[str] | None = None, now: datetime | None = None) -> int:
    args = build_parser().parse_args(argv)
    # `now` can be injected by tests; otherwise it's the real current time
    now = now or datetime.now(timezone.utc)

    try:
        if args.write and not args.overrides:
            raise InputError("--write needs --overrides so it knows which file to update")
        schedule = load_schedule(args.schedule)
        overrides = load_overrides(args.overrides)
        request = build_request(args, now)
        validate_request(schedule, overrides, request, now)
        candidates = rank_candidates(schedule, overrides, request)
    except (InputError, CoverError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    override = propose_override(request, candidates[0])
    preview = render_schedule(
        schedule,
        overrides + [override],
        request.start_at - PREVIEW_PADDING,
        request.end_at + PREVIEW_PADDING,
    )

    print(f"Cover request: {request.requester}, {format_time(request.start_at)} -> {format_time(request.end_at)}")
    if request.reason:
        print(f"Reason: {request.reason}")
    print("\nSuggested cover:")
    for rank, candidate in enumerate(candidates, start=1):
        print(f"  {rank}. {candidate.user}: {candidate.reason}")
    print("\nProposed override:")
    print(json.dumps(override_to_json(override), indent=2))
    print("\nSchedule preview with the override:")
    print(json.dumps([
        {"user": e.user, "start_at": format_time(e.start_at), "end_at": format_time(e.end_at)}
        for e in preview
    ], indent=2))

    if args.write:
        append_override(args.overrides, override)
        print(f"\nAdded override to {args.overrides}")
    return 0
