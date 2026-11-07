"""Command-line entry point for cover requests: parse, validate, rank, print."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
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
from scheduler.models import Entry, Override, Schedule

# ANSI escape codes: bold green for the covered slot, then reset
HIGHLIGHT = "\033[1;32m"
RESET = "\033[0m"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Find someone to cover part of your on-call shift.")
    parser.add_argument("text", nargs="?", default="", help='the request, e.g. "cinema Friday 7-10pm, can someone cover?"')
    parser.add_argument("--as", dest="requester", required=True, help="who is asking for cover")
    parser.add_argument("--schedule", required=True, help="path to the schedule JSON file")
    parser.add_argument("--overrides", help="path to the overrides JSON file (optional)")
    parser.add_argument("--mock", action="store_true", help="skip the LLM and use --start/--end instead")
    parser.add_argument("--start", help="start of the cover window (ISO 8601), used with --mock")
    parser.add_argument("--end", help="end of the cover window (ISO 8601), used with --mock")
    parser.add_argument("--write", action="store_true", help="write the override to the overrides file without asking")
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


def preview_entries(schedule: Schedule, overrides: list[Override], request: CoverRequest, override: Override) -> list[Entry]:
    """The requester's whole shift around the request, split by the new override.

    e.g. alice 6th 17:00 -> 11th 19:00, charlie 19:00 -> 22:00, alice 22:00 -> 13th 17:00
    """
    # Look far enough either side to capture the requester's full shift
    span = 2 * schedule.handover_interval
    around = render_schedule(schedule, overrides, request.start_at - span, request.end_at + span)
    # validate_request guarantees the requester's entry covers the whole request
    shift = next(e for e in around if e.start_at <= request.start_at < e.end_at)
    pieces = [
        Entry(request.requester, shift.start_at, request.start_at),
        Entry(override.user, override.start_at, override.end_at),
        Entry(request.requester, request.end_at, shift.end_at),
    ]
    # Drop empty pieces, e.g. when the request starts exactly at the shift start
    return [p for p in pieces if p.start_at < p.end_at]


def use_colour() -> bool:
    """Only colour real terminals, so piped output and tests stay plain. Respects NO_COLOR."""
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def confirm(question: str) -> bool:
    """Ask a yes/no question; anything but y/yes (or Ctrl-D) means no."""
    try:
        return input(question).strip().lower() in ("y", "yes")
    except EOFError:
        return False


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
    preview = preview_entries(schedule, overrides, request, override)

    print(f"Cover request: {request.requester}, {format_time(request.start_at)} -> {format_time(request.end_at)}")
    if request.reason:
        print(f"Reason: {request.reason}")
    print("\nSuggested cover:")
    for rank, candidate in enumerate(candidates, start=1):
        print(f"  {rank}. {candidate.user}: {candidate.reason}")
    print("\nProposed override:")
    print(json.dumps(override_to_json(override), indent=2))
    print("\nSchedule preview with the override:")
    colour = use_colour()
    for entry in preview:
        line = f"  {entry.user:<10} {format_time(entry.start_at)} -> {format_time(entry.end_at)}"
        if entry.user == override.user and entry.start_at == override.start_at:
            line += "   <- cover"
            if colour:
                line = f"{HIGHLIGHT}{line}{RESET}"
        print(line)

    # --write skips the question; otherwise ask, but only when a person is at the terminal
    should_write = args.write
    if not should_write and args.overrides and sys.stdin.isatty():
        should_write = confirm(f"\nWrite this override to {args.overrides}? [y/N] ")
    if should_write:
        append_override(args.overrides, override)
        print(f"\nAdded override to {args.overrides}")
    return 0
