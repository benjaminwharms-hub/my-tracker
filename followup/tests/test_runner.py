"""End-to-end tests of a daily run, using a fake sender and a fake inbox (no Gmail)."""

import csv
import shutil
from datetime import date, timedelta

import pytest

from followup.config import CLIENTS_DIR, load_config
from followup.jobs import load_jobs
from followup.runner import run_client

HEADER = "job_id,customer_name,customer_email,job_type,job_address,completion_date,status,followup_stage\n"
TODAY = date(2026, 11, 20)


class FakeSender:
    def __init__(self, fail_for=()):
        self.sent = []  # list of (to, subject)
        self.fail_for = set(fail_for)

    def send(self, cfg, email):
        if email.to in self.fail_for:
            raise RuntimeError("Gmail said no")
        self.sent.append((email.to, email.subject))
        return f"msg-{len(self.sent)}"


class FakeInbox:
    def __init__(self, answers=None):
        self.answers = answers or {}  # email -> "replied" / "unsubscribed"

    def check_stop(self, email, since):
        return self.answers.get(email)


@pytest.fixture
def client(tmp_path):
    """A copy of the example client in a temp folder, with our own jobs.csv."""
    shutil.copytree(CLIENTS_DIR / "example_builder", tmp_path / "testco",
                    ignore=shutil.ignore_patterns("send_log.csv", "unsubscribed.csv"))

    def make(jobs_rows):
        (tmp_path / "testco" / "jobs.csv").write_text(HEADER + "".join(r + "\n" for r in jobs_rows), encoding="utf-8")
        return load_config("testco", tmp_path)
    return make


def job(job_id, email, completed, status="complete", stage=""):
    return f"{job_id},Jane Smith,{email},deck,1 Oak St,{completed},{status},{stage}"


def log_rows(cfg):
    if not cfg.log_path.exists():
        return []
    with open(cfg.log_path, newline="") as f:
        return list(csv.DictReader(f))


def days_ago(n):
    return (TODAY - timedelta(days=n)).isoformat()


def test_sends_day1_and_logs_it(client):
    cfg = client([job("J1", "jane@example.com", days_ago(1))])
    sender = FakeSender()
    s = run_client(cfg, TODAY, sender, FakeInbox(), dry_run=False, out=lambda *_: None)
    assert s.sent == 1 and sender.sent[0][0] == "jane@example.com"
    assert log_rows(cfg)[0]["stage"] == "thank_you" and log_rows(cfg)[0]["result"] == "sent"
    rows, _ = load_jobs(cfg.jobs_path)
    assert rows[0]["followup_stage"] == "thank_you"


def test_running_twice_same_day_never_resends(client):
    cfg = client([job("J1", "jane@example.com", days_ago(1))])
    sender = FakeSender()
    run_client(cfg, TODAY, sender, FakeInbox(), dry_run=False, out=lambda *_: None)
    run_client(cfg, TODAY, sender, FakeInbox(), dry_run=False, out=lambda *_: None)
    assert len(sender.sent) == 1


def test_whole_sequence_over_time(client):
    cfg = client([job("J1", "jane@example.com", TODAY.isoformat())])
    sender = FakeSender()
    for d in range(0, 120):  # simulate one run every day for 4 months
        run_client(cfg, TODAY + timedelta(days=d), sender, FakeInbox(), dry_run=False, out=lambda *_: None)
    subjects = [subj for _, subj in sender.sent]
    assert len(subjects) == 4
    assert subjects[2] == "A quick favour, Jane?"
    rows, _ = load_jobs(cfg.jobs_path)
    assert rows[0]["followup_stage"] == "done"


def test_same_person_two_jobs_gets_each_stage_once(client):
    cfg = client([job("J1", "jane@example.com", days_ago(1)), job("J2", "JANE@example.com", days_ago(1))])
    sender = FakeSender()
    run_client(cfg, TODAY, sender, FakeInbox(), dry_run=False, out=lambda *_: None)
    assert len(sender.sent) == 1


def test_reply_stops_sequence(client):
    cfg = client([job("J1", "jane@example.com", days_ago(7), stage="thank_you")])
    sender = FakeSender()
    s = run_client(cfg, TODAY, sender, FakeInbox({"jane@example.com": "replied"}), dry_run=False, out=lambda *_: None)
    assert sender.sent == [] and s.stopped == 1
    rows, _ = load_jobs(cfg.jobs_path)
    assert rows[0]["followup_stage"] == "stopped_replied"


def test_unsubscribe_blocks_future_jobs_too(client):
    cfg = client([job("J1", "jane@example.com", days_ago(7), stage="thank_you")])
    run_client(cfg, TODAY, FakeSender(), FakeInbox({"jane@example.com": "unsubscribed"}), dry_run=False, out=lambda *_: None)
    # A new job for the same person, later on:
    cfg = client([job("J9", "jane@example.com", days_ago(1))])
    sender = FakeSender()
    run_client(cfg, TODAY, sender, FakeInbox(), dry_run=False, out=lambda *_: None)
    assert sender.sent == []


def test_not_complete_is_ignored(client):
    cfg = client([job("J1", "jane@example.com", days_ago(1), status="in progress")])
    sender = FakeSender()
    run_client(cfg, TODAY, sender, FakeInbox(), dry_run=False, out=lambda *_: None)
    assert sender.sent == []


def test_blank_completion_date_becomes_today(client):
    cfg = client([job("J1", "jane@example.com", "")])
    run_client(cfg, TODAY, FakeSender(), FakeInbox(), dry_run=False, out=lambda *_: None)
    rows, _ = load_jobs(cfg.jobs_path)
    assert rows[0]["completion_date"] == TODAY.isoformat() and rows[0]["followup_stage"] == "started"


def test_send_error_is_logged_and_other_jobs_continue(client):
    cfg = client([job("J1", "bad@example.com", days_ago(1)), job("J2", "ok@example.com", days_ago(1))])
    sender = FakeSender(fail_for={"bad@example.com"})
    s = run_client(cfg, TODAY, sender, FakeInbox(), dry_run=False, out=lambda *_: None)
    assert [to for to, _ in sender.sent] == ["ok@example.com"]
    assert len(s.errors) == 1
    assert any(r["result"] == "error" and "Gmail said no" in r["detail"] for r in log_rows(cfg))
    # The failed one is retried the next day (it was never marked as sent).
    sender2 = FakeSender()
    run_client(cfg, TODAY + timedelta(days=1), sender2, FakeInbox(), dry_run=False, out=lambda *_: None)
    assert [to for to, _ in sender2.sent] == ["bad@example.com"]


def test_bad_row_is_reported_not_sent(client):
    cfg = client([job("J1", "not-an-email", days_ago(1))])
    sender = FakeSender()
    s = run_client(cfg, TODAY, sender, FakeInbox(), dry_run=False, out=lambda *_: None)
    assert sender.sent == [] and "doesn't look valid" in s.errors[0]


def test_dry_run_changes_no_files(client):
    cfg = client([job("J1", "jane@example.com", days_ago(1))])
    before = cfg.jobs_path.read_text()
    sender = FakeSender()
    s = run_client(cfg, TODAY, sender, FakeInbox(), dry_run=True, out=lambda *_: None)
    assert s.sent == 1  # it "sent" (to the fake/printing sender)...
    assert cfg.jobs_path.read_text() == before  # ...but nothing on disk changed
    assert not cfg.log_path.exists()


def test_stage_column_counts_as_sent(client):
    # An existing customer added part-way through: followup_stage already says check_in.
    cfg = client([job("J1", "jane@example.com", days_ago(10), stage="check_in")])
    sender = FakeSender()
    run_client(cfg, TODAY, sender, FakeInbox(), dry_run=False, out=lambda *_: None)
    assert sender.sent == []  # day 10: thank_you and check_in count as done, review is due on day 14
