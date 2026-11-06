"""End-to-end tests: run main() with real files, check output and exit codes."""

import json

from scheduler.cli import main

SCHEDULE = {
    "users": ["alice", "bob", "charlie"],
    "handover_start_at": "2026-11-06T17:00:00Z",
    "handover_interval_days": 7,
}


def write(path, data):
    path.write_text(json.dumps(data))
    return str(path)


def run(capsys, *args):
    """Call main() and return (exit code, stdout, stderr)."""
    code = main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_readme_example_end_to_end(tmp_path, capsys):
    schedule = write(tmp_path / "schedule.json", SCHEDULE)
    overrides = write(tmp_path / "overrides.json", [
        {"user": "charlie", "start_at": "2026-11-09T17:00:00Z", "end_at": "2026-11-09T22:00:00Z"}
    ])

    code, out, _ = run(capsys, "--schedule", schedule, "--overrides", overrides,
                       "--from", "2026-11-06T17:00:00Z", "--until", "2026-11-20T17:00:00Z")

    assert code == 0
    assert json.loads(out) == [
        {"user": "alice", "start_at": "2026-11-06T17:00:00Z", "end_at": "2026-11-09T17:00:00Z"},
        {"user": "charlie", "start_at": "2026-11-09T17:00:00Z", "end_at": "2026-11-09T22:00:00Z"},
        {"user": "alice", "start_at": "2026-11-09T22:00:00Z", "end_at": "2026-11-13T17:00:00Z"},
        {"user": "bob", "start_at": "2026-11-13T17:00:00Z", "end_at": "2026-11-20T17:00:00Z"},
    ]


def test_overrides_flag_is_optional(tmp_path, capsys):
    schedule = write(tmp_path / "schedule.json", SCHEDULE)
    code, out, _ = run(capsys, "--schedule", schedule,
                       "--from", "2026-11-06T17:00:00Z", "--until", "2026-11-13T17:00:00Z")
    assert code == 0
    assert json.loads(out) == [
        {"user": "alice", "start_at": "2026-11-06T17:00:00Z", "end_at": "2026-11-13T17:00:00Z"}
    ]


def test_empty_result_prints_empty_array(tmp_path, capsys):
    schedule = write(tmp_path / "schedule.json", SCHEDULE)
    code, out, _ = run(capsys, "--schedule", schedule,
                       "--from", "2026-11-01T00:00:00Z", "--until", "2026-11-02T00:00:00Z")
    assert code == 0
    assert json.loads(out) == []


def test_timezone_offsets_are_converted_to_utc(tmp_path, capsys):
    schedule = write(tmp_path / "schedule.json", SCHEDULE)
    code, out, _ = run(capsys, "--schedule", schedule,
                       "--from", "2026-11-06T18:00:00+01:00", "--until", "2026-11-07T18:00:00+01:00")
    assert code == 0
    assert json.loads(out) == [
        {"user": "alice", "start_at": "2026-11-06T17:00:00Z", "end_at": "2026-11-07T17:00:00Z"}
    ]


def test_from_after_until_is_error(tmp_path, capsys):
    schedule = write(tmp_path / "schedule.json", SCHEDULE)
    code, out, err = run(capsys, "--schedule", schedule,
                         "--from", "2026-11-20T17:00:00Z", "--until", "2026-11-06T17:00:00Z")
    assert code == 1
    assert out == ""
    assert "error" in err


def test_missing_file_is_error(tmp_path, capsys):
    code, _, err = run(capsys, "--schedule", str(tmp_path / "nope.json"),
                       "--from", "2026-11-06T17:00:00Z", "--until", "2026-11-13T17:00:00Z")
    assert code == 1
    assert "not found" in err


def test_invalid_json_is_error(tmp_path, capsys):
    bad = tmp_path / "schedule.json"
    bad.write_text("{not json")
    code, _, err = run(capsys, "--schedule", str(bad),
                       "--from", "2026-11-06T17:00:00Z", "--until", "2026-11-13T17:00:00Z")
    assert code == 1
    assert "invalid JSON" in err


def test_timestamp_without_timezone_is_error(tmp_path, capsys):
    schedule = write(tmp_path / "schedule.json", SCHEDULE)
    code, _, err = run(capsys, "--schedule", schedule,
                       "--from", "2026-11-06T17:00:00", "--until", "2026-11-13T17:00:00Z")
    assert code == 1
    assert "timezone" in err