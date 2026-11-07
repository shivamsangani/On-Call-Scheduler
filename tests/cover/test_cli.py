"""End-to-end tests for ./cover-request in --mock mode (no LLM or API key needed)."""

import json
from datetime import datetime, timezone

from scheduler.cover.cli import main

SCHEDULE = {
    "users": ["alice", "bob", "charlie"],
    "handover_start_at": "2026-11-06T17:00:00Z",
    "handover_interval_days": 7,
}
NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def write(path, data):
    path.write_text(json.dumps(data))
    return str(path)


def run(capsys, *args):
    code = main(list(args), now=NOW)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def mock_args(schedule, start="2026-11-11T19:00:00Z", end="2026-11-11T22:00:00Z"):
    return ["cinema", "--as", "alice", "--schedule", schedule, "--mock", "--start", start, "--end", end]


def test_mock_request_suggests_charlie_and_previews_override(tmp_path, capsys):
    schedule = write(tmp_path / "schedule.json", SCHEDULE)
    code, out, err = run(capsys, *mock_args(schedule))

    assert code == 0 and err == ""
    assert "1. charlie" in out and "2. bob" in out
    assert '"user": "charlie"' in out
    assert '"start_at": "2026-11-11T19:00:00Z"' in out
    # The preview shows alice's whole shift, split by charlie's cover
    preview = out.split("Schedule preview with the override:\n")[1].splitlines()
    assert preview == [
        "  alice      2026-11-06T17:00:00Z -> 2026-11-11T19:00:00Z",
        "  charlie    2026-11-11T19:00:00Z -> 2026-11-11T22:00:00Z   <- cover",
        "  alice      2026-11-11T22:00:00Z -> 2026-11-13T17:00:00Z",
    ]
    assert "\033[" not in out  # no colour codes when not printing to a terminal


def test_preview_when_request_starts_at_shift_start(tmp_path, capsys):
    schedule = write(tmp_path / "schedule.json", SCHEDULE)
    code, out, _ = run(capsys, *mock_args(schedule, "2026-11-06T17:00:00Z", "2026-11-06T20:00:00Z"))
    preview = out.split("Schedule preview with the override:\n")[1].splitlines()
    assert code == 0
    assert [line.split()[0] for line in preview] == ["charlie", "alice"]


def test_request_when_not_on_call_fails(tmp_path, capsys):
    schedule = write(tmp_path / "schedule.json", SCHEDULE)
    code, out, err = run(capsys, *mock_args(schedule, "2026-11-13T19:00:00Z", "2026-11-13T22:00:00Z"))
    assert code == 1 and out == ""
    assert "not on call" in err and "bob" in err


def test_mock_without_times_fails(tmp_path, capsys):
    schedule = write(tmp_path / "schedule.json", SCHEDULE)
    code, _, err = run(capsys, "--as", "alice", "--schedule", schedule, "--mock")
    assert code == 1
    assert "--start and --end" in err


def test_prompt_yes_writes_override(tmp_path, capsys, monkeypatch):
    schedule = write(tmp_path / "schedule.json", SCHEDULE)
    overrides = write(tmp_path / "overrides.json", [])
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "y")
    code, out, _ = run(capsys, *mock_args(schedule), "--overrides", overrides)
    assert code == 0 and "Added override" in out
    assert len(json.loads((tmp_path / "overrides.json").read_text())) == 1


def test_prompt_no_leaves_file_alone(tmp_path, capsys, monkeypatch):
    schedule = write(tmp_path / "schedule.json", SCHEDULE)
    overrides = write(tmp_path / "overrides.json", [])
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "")
    code, out, _ = run(capsys, *mock_args(schedule), "--overrides", overrides)
    assert code == 0 and "Added override" not in out
    assert json.loads((tmp_path / "overrides.json").read_text()) == []


def test_write_appends_override_to_file(tmp_path, capsys):
    schedule = write(tmp_path / "schedule.json", SCHEDULE)
    overrides = write(tmp_path / "overrides.json", [])
    code, out, _ = run(capsys, *mock_args(schedule), "--overrides", overrides, "--write")

    assert code == 0
    assert json.loads((tmp_path / "overrides.json").read_text()) == [
        {"user": "charlie", "start_at": "2026-11-11T19:00:00Z", "end_at": "2026-11-11T22:00:00Z"}
    ]


def test_write_without_overrides_file_fails(tmp_path, capsys):
    schedule = write(tmp_path / "schedule.json", SCHEDULE)
    code, _, err = run(capsys, *mock_args(schedule), "--write")
    assert code == 1
    assert "--write needs --overrides" in err
