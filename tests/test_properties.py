"""Property-based tests: random schedules, overrides and windows.

Every generated time falls on a whole hour, so a brute-force version that
checks every hour gives an independent "correct answer" to compare against.
"""

from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from scheduler.core import render_schedule
from scheduler.models import Override, Schedule

BASE = datetime(2026, 11, 1, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)
SPAN_HOURS = 24 * 30  # all times fall within 30 days of BASE
NAMES = ["alice", "bob", "charlie", "dave", "erin"]


def hour(n: int) -> datetime:
    return BASE + n * HOUR


@st.composite
def scenarios(draw):
    """A random schedule, non-overlapping overrides after its start, and a window."""
    start_h = draw(st.integers(0, SPAN_HOURS // 2))
    schedule = Schedule(
        users=tuple(draw(st.lists(st.sampled_from(NAMES), min_size=1, max_size=4))),
        handover_start_at=hour(start_h),
        handover_interval=timedelta(days=draw(st.integers(1, 7))),
    )

    # An even number of distinct sorted hours, paired up, gives overrides that never overlap.
    points = sorted(draw(st.sets(st.integers(start_h, SPAN_HOURS), max_size=10)))
    points = points[: len(points) // 2 * 2]
    overrides = [
        Override(draw(st.sampled_from(NAMES)), hour(a), hour(b))
        for a, b in zip(points[::2], points[1::2])
    ]

    window_start, window_end = sorted(draw(st.sets(st.integers(0, SPAN_HOURS), min_size=2, max_size=2)))
    return schedule, overrides, hour(window_start), hour(window_end)


def brute_force(schedule, overrides, window_start, window_end):
    """Ask who is on call every hour and group the answers.

    Deliberately written differently from core.py (counting shifts by walking
    forward instead of dividing) so it is an independent check.
    """
    def who(t):
        for o in overrides:
            if o.start_at <= t < o.end_at:
                return o.user
        if t < schedule.handover_start_at:
            return None
        shift, shift_end = 0, schedule.handover_start_at + schedule.handover_interval
        while shift_end <= t:
            shift += 1
            shift_end += schedule.handover_interval
        return schedule.users[shift % len(schedule.users)]

    entries = []
    t = window_start
    while t < window_end:
        user = who(t)
        if user is not None:
            if entries and entries[-1][0] == user and entries[-1][2] == t:
                entries[-1] = (user, entries[-1][1], t + HOUR)
            else:
                entries.append((user, t, t + HOUR))
        t += HOUR
    return entries


@settings(max_examples=300)
@given(scenarios())
def test_matches_brute_force(scenario):
    result = [(e.user, e.start_at, e.end_at) for e in render_schedule(*scenario)]
    assert result == brute_force(*scenario)


@settings(max_examples=300)
@given(scenarios())
def test_entries_are_sorted_non_overlapping_and_inside_window(scenario):
    _, _, window_start, window_end = scenario
    entries = render_schedule(*scenario)
    for e in entries:
        assert window_start <= e.start_at < e.end_at <= window_end
    for prev, nxt in zip(entries, entries[1:]):
        assert prev.end_at <= nxt.start_at


@settings(max_examples=300)
@given(scenarios())
def test_no_gaps_once_rota_has_started(scenario):
    schedule, _, window_start, window_end = scenario
    entries = render_schedule(*scenario)
    covered_from = max(window_start, schedule.handover_start_at)
    if covered_from >= window_end:
        assert entries == []
        return
    assert entries[0].start_at == covered_from
    assert entries[-1].end_at == window_end
    for prev, nxt in zip(entries, entries[1:]):
        assert prev.end_at == nxt.start_at


@settings(max_examples=300)
@given(scenarios())
def test_neighbouring_entries_have_different_users(scenario):
    entries = render_schedule(*scenario)
    for prev, nxt in zip(entries, entries[1:]):
        assert not (prev.user == nxt.user and prev.end_at == nxt.start_at)


@settings(max_examples=300)
@given(scenarios())
def test_overrides_always_win_inside_the_window(scenario):
    _, overrides, window_start, window_end = scenario
    entries = render_schedule(*scenario)
    for o in overrides:
        start, end = max(o.start_at, window_start), min(o.end_at, window_end)
        if start >= end:
            continue
        assert any(e.user == o.user and e.start_at <= start and end <= e.end_at for e in entries)