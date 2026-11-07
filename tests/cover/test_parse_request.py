import pytest
from scheduler.cover.logic import CoverError
from scheduler.cover.parse_request import parse_output

def test_parse_output_builds_request():
    r = parse_output({"start_at": "2026-11-11T19:00:00Z", "end_at": "2026-11-11T22:00:00Z", "reason": "cinema"}, "alice")
    assert (r.requester, r.start_at.hour, r.end_at.hour, r.reason) == ("alice", 19, 22, "cinema")

def test_parse_output_rejects_missing_times():
    with pytest.raises(CoverError, match="couldn't work out"):
        parse_output({"start_at": "", "end_at": "", "reason": ""}, "alice")

def test_parse_output_rejects_garbage_time():
    with pytest.raises(CoverError, match="invalid time"):
        parse_output({"start_at": "Friday", "end_at": "2026-11-11T22:00:00Z", "reason": ""}, "alice")