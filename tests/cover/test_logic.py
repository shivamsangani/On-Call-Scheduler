"""Tests for the cover-request logic: validation, ranking and the proposed override."""

from datetime import datetime, timedelta, timezone

import pytest

from scheduler.cover.logic import (
    CoverError,
    CoverRequest,
    propose_override,
    rank_candidates,
    validate_request,
)
from scheduler.models import Override, Schedule


def t(day: int, hour: int = 0) -> datetime:
    """A UTC time in November 2026."""
    return datetime(2026, 11, day, hour, tzinfo=timezone.utc)


# alice: 6th 17:00 -> 13th 17:00, bob: -> 20th 17:00, charlie: -> 27th 17:00
SCHEDULE = Schedule(("alice", "bob", "charlie"), t(6, 17), timedelta(days=7))
NOW = t(1)


def request(requester="alice", start=t(11, 19), end=t(11, 22)):
    return CoverRequest(requester, start, end, "cinema")


# --- validate_request ---------------------------------------------------------


def test_valid_request_passes():
    validate_request(SCHEDULE, [], request(), NOW)


def test_rejects_when_requester_not_on_call():
    with pytest.raises(CoverError, match="bob"):
        validate_request(SCHEDULE, [], request(start=t(13, 19), end=t(13, 22)), NOW)


def test_rejects_request_spanning_a_handover():
    with pytest.raises(CoverError, match="not on call for that whole window"):
        validate_request(SCHEDULE, [], request(start=t(13, 16), end=t(13, 18)), NOW)


def test_rejects_when_an_override_already_covers_the_window():
    overrides = [Override("charlie", t(11, 18), t(11, 23))]
    with pytest.raises(CoverError, match="charlie"):
        validate_request(SCHEDULE, overrides, request(), NOW)


def test_rejects_request_before_rota_starts():
    with pytest.raises(CoverError, match="no one"):
        validate_request(SCHEDULE, [], request(start=t(2), end=t(3)), NOW)


def test_rejects_user_not_on_rota():
    with pytest.raises(CoverError, match="not on this rota"):
        validate_request(SCHEDULE, [], request(requester="zed"), NOW)


def test_rejects_request_in_the_past():
    with pytest.raises(CoverError, match="past"):
        validate_request(SCHEDULE, [], request(), now=t(12))


def test_rejects_end_before_start():
    with pytest.raises(CoverError, match="end"):
        validate_request(SCHEDULE, [], request(start=t(11, 22), end=t(11, 19)), NOW)


# --- rank_candidates ----------------------------------------------------------


def test_fewest_hours_ranks_first():
    # ±14 days around 11 Nov: charlie only has 20th 17:00 -> 25th 22:00 (125h), bob a full week (168h)
    ranked = rank_candidates(SCHEDULE, [], request())
    assert [(c.user, c.hours_on_call) for c in ranked] == [("charlie", 125.0), ("bob", 168.0)]


def test_requester_is_never_a_candidate():
    ranked = rank_candidates(SCHEDULE, [], request())
    assert "alice" not in [c.user for c in ranked]


def test_existing_overrides_count_towards_hours():
    # charlie already covered 10 hours of alice's week, so 135h vs bob's 168h
    overrides = [Override("charlie", t(8, 0), t(8, 10))]
    ranked = rank_candidates(SCHEDULE, overrides, request())
    assert ranked[0].user == "charlie"
    assert ranked[0].hours_on_call == 135.0


def test_rested_candidate_wins_a_tie_on_hours():
    # Daily rota; alice wants all of the 4th covered.
    # charlie (3rd) and bob (5th) each have 12h in the ±1 day window after the overrides,
    # but bob is on call within 12h of the request and charlie isn't, so charlie wins
    # even though "bob" comes first alphabetically.
    daily = Schedule(("alice", "bob", "charlie"), t(1), timedelta(days=1))
    # day 1 alice, 2 bob, 3 charlie, 4 alice, 5 bob
    overrides = [Override("alice", t(3, 12), t(4)), Override("alice", t(5, 12), t(6))]
    ranked = rank_candidates(daily, overrides, request(start=t(4), end=t(5)), fairness_days=1, rest_hours=12)
    assert [(c.user, c.hours_on_call, c.rested) for c in ranked] == [
        ("charlie", 12.0, True),
        ("bob", 12.0, False),
    ]


def test_alphabetical_breaks_a_full_tie():
    # ±1 day around the request is entirely alice's week, so everyone else has 0h and is rested
    rota = Schedule(("alice", "dave", "bob", "charlie"), t(6, 17), timedelta(days=7))
    ranked = rank_candidates(rota, [], request(), fairness_days=1)
    assert [c.user for c in ranked] == ["bob", "charlie", "dave"]


def test_single_user_rota_has_no_candidates():
    solo = Schedule(("alice",), t(6, 17), timedelta(days=7))
    with pytest.raises(CoverError, match="no one else"):
        rank_candidates(solo, [], request())


def test_duplicate_users_appear_once():
    rota = Schedule(("alice", "bob", "bob"), t(6, 17), timedelta(days=7))
    ranked = rank_candidates(rota, [], request())
    assert [c.user for c in ranked] == ["bob"]


# --- propose_override ---------------------------------------------------------


def test_proposed_override_uses_top_candidate_and_request_window():
    req = request()
    top = rank_candidates(SCHEDULE, [], req)[0]
    assert propose_override(req, top) == Override("charlie", t(11, 19), t(11, 22))
