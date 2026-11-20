"""Tests for followup/gmail_client.py, using a fake Gmail service (no network, no Google account).

The real Google library is used like this:
    service.users().messages().send(userId="me", body={...}).execute()
FakeService copies that shape and records what was asked of it.
"""

import base64
import email
import json
from datetime import date

import pytest

from followup import gmail_client
from followup.config import load_config
from followup.gmail_client import GmailInbox, GmailNotConnected, GmailSender, connect, token_env_var
from followup.templates import build_email


class _Call:
    def __init__(self, result):
        self.result = result

    def execute(self, num_retries=0):
        return self.result


class FakeService:
    def __init__(self, address="office@example.com", inbox=None):
        self.address = address
        self.inbox = inbox or []  # list of dicts: {"id", "from", "subject", "snippet", "headers"}
        self.sent_raw = []
        self.queries = []

    # service.users() -> self, then .getProfile() / .messages()
    def users(self):
        return self

    def getProfile(self, userId):
        return _Call({"emailAddress": self.address})

    def messages(self):
        return self

    def send(self, userId, body):
        self.sent_raw.append(body["raw"])
        return _Call({"id": f"gmail-{len(self.sent_raw)}"})

    def list(self, userId, q, maxResults):
        self.queries.append(q)
        sender = q.split()[0][len("from:"):]
        return _Call({"messages": [{"id": m["id"]} for m in self.inbox if m["from"] == sender]})

    def get(self, userId, id, format, metadataHeaders):
        m = next(m for m in self.inbox if m["id"] == id)
        headers = [{"name": "Subject", "value": m.get("subject", "")}]
        headers += [{"name": k, "value": v} for k, v in m.get("headers", {}).items()]
        return _Call({"snippet": m.get("snippet", ""), "payload": {"headers": headers}})


@pytest.fixture
def cfg():
    return load_config("example_builder")


def test_send_builds_a_proper_email(cfg):
    service = FakeService()
    row = {"customer_name": "Jane Smith", "customer_email": "jane@example.com", "job_type": "deck", "job_address": "1 Oak"}
    msg_id = GmailSender(service).send(cfg, build_email(cfg, cfg.stages[0], row, date(2026, 11, 19)))
    assert msg_id == "gmail-1"

    parsed = email.message_from_bytes(base64.urlsafe_b64decode(service.sent_raw[0]))
    assert parsed["To"] == "jane@example.com"
    assert parsed["From"] == "Sam at Example Builders <office@example.com>"
    assert parsed["List-Unsubscribe"] == "<mailto:office@example.com?subject=unsubscribe>"
    assert "reply STOP" in parsed.get_payload(decode=True).decode()


def test_connect_refuses_wrong_account(cfg):
    with pytest.raises(GmailNotConnected, match="someone-else@gmail.com"):
        connect(cfg, service=FakeService(address="someone-else@gmail.com"))


def test_connect_ok_for_right_account(cfg):
    sender, inbox = connect(cfg, service=FakeService(address="Office@Example.com"))
    assert isinstance(sender, GmailSender) and isinstance(inbox, GmailInbox)


def inbox_with(*messages):
    return GmailInbox(FakeService(inbox=[{"id": str(i), "from": "jane@example.com", **m}
                                         for i, m in enumerate(messages)]))


def test_no_reply():
    assert inbox_with().check_stop("jane@example.com", "2026-11-19") is None


def test_ordinary_reply():
    assert inbox_with({"subject": "Re: Thank you", "snippet": "Thanks, the deck looks great!"}
                      ).check_stop("jane@example.com", "2026-11-19") == "replied"


@pytest.mark.parametrize("subject, snippet", [
    ("Re: Thank you", "STOP"),
    ("Re: Thank you", "stop please"),
    ("unsubscribe", ""),  # what Gmail's own Unsubscribe button sends
    ("Re: check-in", "Please remove me from your list"),
    ("Re: hi", "I'd like to opt out of these"),
])
def test_unsubscribe_replies(subject, snippet):
    assert inbox_with({"subject": subject, "snippet": snippet}
                      ).check_stop("jane@example.com", "2026-11-19") == "unsubscribed"


def test_unsubscribe_wins_over_earlier_reply():
    assert inbox_with({"subject": "Re: hi", "snippet": "thanks!"},
                      {"subject": "Re: hi", "snippet": "STOP"}).check_stop("jane@example.com", "2026-11-19") == "unsubscribed"


@pytest.mark.parametrize("msg", [
    {"subject": "Automatic reply: Thank you", "snippet": "I'm away until Monday"},
    {"subject": "Out of Office", "snippet": "back soon"},
    {"subject": "Re: Thank you", "snippet": "away", "headers": {"Auto-Submitted": "auto-replied"}},
])
def test_auto_replies_are_ignored(msg):
    assert inbox_with(msg).check_stop("jane@example.com", "2026-11-19") is None


def test_word_stop_inside_sentence_is_a_reply_not_unsubscribe():
    assert inbox_with({"subject": "Re: hi", "snippet": "Can you stop by Tuesday to look at the gutter?"}
                      ).check_stop("jane@example.com", "2026-11-19") == "replied"


def test_search_query_includes_spam_and_date():
    service = FakeService()
    GmailInbox(service).check_stop("jane@example.com", "2026-11-19")
    assert service.queries == ["from:jane@example.com after:2026/11/19 in:anywhere"]


def test_token_env_var_name():
    assert token_env_var("example_builder") == "GMAIL_TOKEN_EXAMPLE_BUILDER"
    assert token_env_var("smith-roofing") == "GMAIL_TOKEN_SMITH_ROOFING"


def test_missing_token_gives_clear_message(monkeypatch, tmp_path):
    monkeypatch.setattr(gmail_client, "SECRETS_DIR", tmp_path)
    monkeypatch.delenv("GMAIL_TOKEN_NOBODY", raising=False)
    with pytest.raises(GmailNotConnected, match="connect_gmail.py"):
        gmail_client.load_credentials("nobody")


def test_token_read_from_env_var(monkeypatch, tmp_path):
    """In GitHub Actions the token comes from an environment variable."""
    monkeypatch.setattr(gmail_client, "SECRETS_DIR", tmp_path)
    fake_token = {"token": "abc", "refresh_token": "r", "client_id": "c", "client_secret": "s",
                  "token_uri": "https://oauth2.googleapis.com/token", "scopes": gmail_client.SCOPES,
                  "expiry": "2999-01-01T00:00:00Z"}  # not expired, so no network call is made
    monkeypatch.setenv("GMAIL_TOKEN_TESTCO", json.dumps(fake_token))
    creds = gmail_client.load_credentials("testco")
    assert creds.token == "abc" and creds.refresh_token == "r"
