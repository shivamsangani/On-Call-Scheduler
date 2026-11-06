"""Command-line entry point: parse flags, run the scheduler, print JSON."""

import argparse
import json
import sys

from scheduler.core import render_schedule
from scheduler.loader import InputError, format_time, load_overrides, load_schedule, parse_time


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render an on-call schedule as JSON.")
    parser.add_argument("--schedule", required=True, help="path to the schedule JSON file")
    parser.add_argument("--overrides", help="path to the overrides JSON file (optional)")
    parser.add_argument("--from", dest="from_", required=True, help="start of the window (ISO 8601)")
    parser.add_argument("--until", required=True, help="end of the window (ISO 8601)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        schedule = load_schedule(args.schedule)
        overrides = load_overrides(args.overrides)
        window_start = parse_time(args.from_)
        window_end = parse_time(args.until)
        if window_start >= window_end:
            raise InputError("--from must be before --until")
        entries = render_schedule(schedule, overrides, window_start, window_end)
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    output = [
        {
            "user": entry.user,
            "start_at": format_time(entry.start_at),
            "end_at": format_time(entry.end_at),
        }
        for entry in entries
    ]
    print(json.dumps(output, indent=2))
    return 0