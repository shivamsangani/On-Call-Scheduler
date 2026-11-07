"""Turn a free-text cover request into a CoverRequest using Claude.

The LLM only extracts *when* the cover is needed. Everything it returns is
re-checked by parse_output here and validate_request in logic.py.
"""

import json
import os
from datetime import datetime

import anthropic

from scheduler.cover.logic import CoverError, CoverRequest
from scheduler.loader import InputError, format_time, parse_time

MODEL = "claude-haiku-5-5"

# The exact JSON shape Claude must return (enforced by the API)
SCHEMA = {
    "type": "object",
    "properties": {
        "start_at": {"type": "string", "description": "ISO 8601 UTC, e.g. 2026-11-13T19:00:00Z, or empty if unknown"},
        "end_at": {"type": "string", "description": "ISO 8601 UTC, e.g. 2026-11-13T22:00:00Z, or empty if unknown"},
        "reason": {"type": "string", "description": "a few words, e.g. 'cinema'"},
    },
    "required": ["start_at", "end_at", "reason"],
    "additionalProperties": False,
}


def build_system_prompt(now: datetime) -> str:
    """Give Claude today's date so it can resolve 'Friday' or 'tonight'."""
    return (
        "You extract the time window from an on-call engineer's request for cover.\n"
        f"The current time is {format_time(now)} ({now.strftime('%A')}). All times are UTC.\n"
        "Resolve relative dates ('Friday', 'tonight', 'tomorrow') to the next matching date "
        "on or after the current time.\n"
        "If the message doesn't say when cover is needed, return empty strings for start_at and end_at."
    )


def parse_output(data: dict, requester: str) -> CoverRequest:
    """Convert Claude's JSON into a CoverRequest. Never trust it blindly."""
    if not data.get("start_at") or not data.get("end_at"):
        raise CoverError("couldn't work out when you need cover; try including a day and time")
    try:
        start_at = parse_time(data["start_at"])
        end_at = parse_time(data["end_at"])
    except InputError as e:
        raise CoverError(f"the model returned an invalid time: {e}") from None
    return CoverRequest(requester, start_at, end_at, data.get("reason", ""))


def parse_with_llm(text: str, requester: str, now: datetime) -> CoverRequest:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise CoverError("ANTHROPIC_API_KEY is not set; set it, or use --mock with --start and --end")

    client = anthropic.Anthropic()
    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=build_system_prompt(now),
            messages=[{"role": "user", "content": text}],
            output_config={
                "effort": "low",  # simple extraction, so no deep reasoning needed
                "format": {"type": "json_schema", "schema": SCHEMA},
            },
        )
    except anthropic.AuthenticationError:
        raise CoverError("the API key was rejected; check ANTHROPIC_API_KEY") from None
    except anthropic.APIConnectionError:
        raise CoverError("couldn't reach the Claude API; try --mock") from None
    except anthropic.APIStatusError as e:
        raise CoverError(f"Claude API error ({e.status_code}): {e.message}") from None

    if response.stop_reason == "refusal":
        raise CoverError("the model declined to parse this request")

    text_block = next(b.text for b in response.content if b.type == "text")
    return parse_output(json.loads(text_block), requester)