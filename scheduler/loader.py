"""Reading input files and converting timestamps"""

import json 
from datetime import datetime, timedelta, timezone 
from pathlib import Path 

from scheduler.models import Override, Schedule

class InputError(Exception): 
    """Raised when an input file or flag is invalid"""

def parse_time(value: str) -> datetime:
    """Parse an ISO timestamp into a UTC datetime""" 
    try: 
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError): 
        raise InputError(f"invalid timestamp: {value!r}") from None
    
    if dt.tzinfo is None: 
        raise InputError(f"timestamp must include a timezone: {value!r}")

    return dt.astimezone(timezone.utc) 

def format_time(dt: datetime) -> str: 
    """Format a datetime like 2026-11-06T17:00:00Z"""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _read_json(path: str): 
    try: 
        return json.loads(Path(path).read_text())
    except FileNotFoundError: 
        raise InputError(f"file not found: {path}") from None
    except json.JSONDecodeError as e: 
        raise InputError(f"invalid JSON in {path}: {e}") from None


def load_schedule(path: str) -> Schedule: 
    data = _read_json(path) 
    try: 
        return Schedule(
            users=tuple(data["users"]), 
            handover_start_at=parse_time(data["handover_start_at"]),
            handover_interval=timedelta(days=data["handover_interval_days"])
        )
    except KeyError as e: 
        raise InputError(f"schedule in {path} is missing field {e}") from None

def load_overrides(path: str | None) -> list[Override]: 
    if path is None: 
        return [] 
    data = _read_json(path)
    if not isinstance(data, list):
        raise InputError(f"overrides in {path} must be a JSON array")
    try: 
        return [
            Override(
                user=item["user"], 
                start_at=parse_time(item["start_at"]),
                end_at=parse_time(item["end_at"])
            )
            for item in data
        ]
    except KeyError as e: 
        raise InputError(f"an override in {path} is missing field {e}") from None