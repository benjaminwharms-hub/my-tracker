"""Tests for the "what's due today" rules in followup/sequence.py."""

from datetime import date

import pytest

from followup.config import Stage
from followup.sequence import FINISH, SEND, WAIT, days_since, decide

STAGES = [
    Stage("thank_you", 1, "a.txt"),
    Stage("check_in", 7, "b.txt"),
    Stage("review_request", 14, "c.txt"),
    Stage("referral", 90, "d.txt"),
]
GRACE = 7


def test_days_since():
    assert days_since(date(2026, 11, 13), date(2026, 11, 20)) == 7


@pytest.mark.parametrize("days", [-3, 0])
def test_waits_before_day_one(days):
    assert decide(STAGES, days, set(), GRACE).action == WAIT


@pytest.mark.parametrize("days, stage", [(1, "thank_you"), (7, "check_in"), (14, "review_request"), (90, "referral")])
def test_sends_on_the_right_day(days, stage):
    already = {s.name for s in STAGES if s.day < days}
    d = decide(STAGES, days, already, GRACE)
    assert d.action == SEND and d.stage.name == stage and d.skipped == []


def test_waits_between_stages():
    assert decide(STAGES, 3, {"thank_you"}, GRACE).action == WAIT


def test_never_resends_a_stage():
    # Day 2, thank-you already sent: nothing to do.
    assert decide(STAGES, 2, {"thank_you"}, GRACE).action == WAIT


def test_late_entry_sends_only_latest_stage():
    # The job was entered 20 days after completion: send the review request
    # only (6 days late), and skip thank-you and check-in.
    d = decide(STAGES, 20, set(), GRACE)
    assert d.action == SEND and d.stage.name == "review_request"
    assert [s.name for s in d.skipped] == ["thank_you", "check_in"]


def test_too_late_waits_for_next_stage():
    # Day 30: review request is 16 days late, so wait for day 90.
    d = decide(STAGES, 30, set(), GRACE)
    assert d.action == WAIT
    assert "review_request" in [s.name for s in d.skipped]


def test_finish_after_last_stage_sent():
    assert decide(STAGES, 95, {s.name for s in STAGES}, GRACE).action == FINISH


def test_last_stage_too_late_finishes_without_sending():
    # A job from two years ago, marked complete today, gets nothing.
    d = decide(STAGES, 700, set(), GRACE)
    assert d.action == FINISH and d.stage is None


def test_grace_boundary():
    assert decide(STAGES, 7 + GRACE, {"thank_you"}, GRACE).action == SEND  # exactly at the limit
    assert decide(STAGES, 7 + GRACE + 1, {"thank_you"}, GRACE).stage.name == "review_request"
