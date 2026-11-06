"""Unit and scenario tests for the scheduling algorithm."""

from datetime import datetime, timedelta, timezone

from scheduler.core import base_user_at, merge_adjacent, on_call_at, render_schedule
from scheduler.models import Entry, Override, Schedule


def t(day: int, hour: int = 0) -> datetime:
    """A UTC time in November 2026, so tests stay short and readable."""
    return datetime(2026, 11, day, hour, tzinfo=timezone.utc)


# alice: 6th 17:00 -> 13th 17:00, bob: -> 20th 17:00, charlie: -> 27th 17:00, then alice again
SCHEDULE = Schedule(("alice", "bob", "charlie"), t(6, 17), timedelta(days=7))


def render(overrides, start, end, schedule=SCHEDULE):
    """Run the scheduler and return simple (user, start, end) tuples."""
    return [(e.user, e.start_at, e.end_at) for e in render_schedule(schedule, overrides, start, end)]


# --- Unit tests -------------------------------------------------------------

def test_base_user_at_exact_handover_belongs_to_next_user():
    assert base_user_at(SCHEDULE, t(13, 17)) == "bob"
    assert base_user_at(SCHEDULE, t(13, 17) - timedelta(seconds=1)) == "alice"


def test_base_user_at_before_rota_is_none():
    assert base_user_at(SCHEDULE, t(1)) is None


def test_on_call_at_override_start_inclusive_end_exclusive():
    overrides = [Override("charlie", t(9, 17), t(9, 22))]
    assert on_call_at(SCHEDULE, overrides, t(9, 17)) == "charlie"
    assert on_call_at(SCHEDULE, overrides, t(9, 22)) == "alice"


def test_merge_adjacent_chain_of_same_user():
    entries = [Entry("alice", t(1), t(2)), Entry("alice", t(2), t(3)),
               Entry("alice", t(3), t(4)), Entry("bob", t(4), t(5))]
    assert merge_adjacent(entries) == [Entry("alice", t(1), t(4)), Entry("bob", t(4), t(5))]


def test_merge_adjacent_needs_touching_times():
    entries = [Entry("alice", t(1), t(2)), Entry("alice", t(3), t(4))]
    assert merge_adjacent(entries) == entries


def test_merge_adjacent_different_users_stay_separate():
    entries = [Entry("alice", t(1), t(2)), Entry("bob", t(2), t(3))]
    assert merge_adjacent(entries) == entries


# --- Scenarios: base rota ---------------------------------------------------

def test_readme_example():
    overrides = [Override("charlie", t(9, 17), t(9, 22))]
    assert render(overrides, t(6, 17), t(20, 17)) == [
        ("alice", t(6, 17), t(9, 17)),
        ("charlie", t(9, 17), t(9, 22)),
        ("alice", t(9, 22), t(13, 17)),
        ("bob", t(13, 17), t(20, 17)),
    ]


def test_no_overrides():
    assert render([], t(6, 17), t(20, 17)) == [
        ("alice", t(6, 17), t(13, 17)),
        ("bob", t(13, 17), t(20, 17)),
    ]


def test_window_clips_mid_shift():
    assert render([], t(8), t(15)) == [
        ("alice", t(8), t(13, 17)),
        ("bob", t(13, 17), t(15)),
    ]


def test_window_starts_before_rota():
    assert render([], t(1), t(14)) == [
        ("alice", t(6, 17), t(13, 17)),
        ("bob", t(13, 17), t(14)),
    ]


def test_window_entirely_before_rota():
    assert render([], t(1), t(5)) == []


def test_rotation_wraps_around():
    assert render([], t(20, 17), t(30)) == [
        ("charlie", t(20, 17), t(27, 17)),
        ("alice", t(27, 17), t(30)),
    ]


def test_single_user_shifts_merge():
    solo = Schedule(("alice",), t(6, 17), timedelta(days=7))
    assert render([], t(6, 17), t(30), schedule=solo) == [("alice", t(6, 17), t(30))]


# --- Scenarios: overrides ---------------------------------------------------

def test_override_crossing_handover():
    overrides = [Override("dave", t(12), t(14))]
    assert render(overrides, t(10), t(16)) == [
        ("alice", t(10), t(12)),
        ("dave", t(12), t(14)),
        ("bob", t(14), t(16)),
    ]


def test_override_for_same_user_merges():
    overrides = [Override("alice", t(8), t(9))]
    assert render(overrides, t(6, 17), t(13, 17)) == [("alice", t(6, 17), t(13, 17))]


def test_override_partly_outside_window_is_clipped():
    overrides = [Override("dave", t(9), t(12))]
    assert render(overrides, t(7), t(10)) == [
        ("alice", t(7), t(9)),
        ("dave", t(9), t(10)),
    ]


def test_override_fully_outside_window_is_ignored():
    overrides = [Override("dave", t(15), t(16))]
    assert render(overrides, t(7), t(10)) == [("alice", t(7), t(10))]


def test_override_starting_exactly_at_handover():
    overrides = [Override("dave", t(13, 17), t(14, 17))]
    assert render(overrides, t(6, 17), t(20, 17)) == [
        ("alice", t(6, 17), t(13, 17)),
        ("dave", t(13, 17), t(14, 17)),
        ("bob", t(14, 17), t(20, 17)),
    ]


def test_back_to_back_overrides():
    overrides = [Override("dave", t(8), t(9)), Override("erin", t(9), t(10))]
    assert render(overrides, t(7), t(11)) == [
        ("alice", t(7), t(8)),
        ("dave", t(8), t(9)),
        ("erin", t(9), t(10)),
        ("alice", t(10), t(11)),
    ]


def test_override_covering_whole_window():
    overrides = [Override("dave", t(7), t(20))]
    assert render(overrides, t(8), t(10)) == [("dave", t(8), t(10))]