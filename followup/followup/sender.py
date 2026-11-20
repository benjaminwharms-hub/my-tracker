"""The "send" and "check inbox" parts, kept separate from the rest of the logic.

The runner talks to two small objects:
    sender.send(cfg, email)               -> returns a message ID
    inbox.check_stop(email, since_date)   -> None, "replied" or "unsubscribed"

In dry-run mode, DryRunSender prints the email and NoInbox reports no
replies. In real mode, the Gmail versions in gmail_client.py do the work.
Tests use fake versions. Because the rest of the code never knows which one
it has, a dry run exercises exactly the same logic as a real run.
"""

import itertools


class DryRunSender:
    """Prints emails instead of sending them."""

    def __init__(self, out=print):
        self.out = out
        self._counter = itertools.count(1)

    def send(self, cfg, email) -> str:
        line = "=" * 70
        self.out(f"\n{line}\n[DRY RUN] would send from: {cfg.from_name} <{cfg.from_email}>\n"
                 f"To:      {email.to}\nSubject: {email.subject}\n{'-' * 70}\n{email.body}\n{line}")
        return f"dry-run-{next(self._counter)}"


class NoInbox:
    """Used in dry runs: there's no Gmail to check, so it never reports replies."""

    def check_stop(self, customer_email, since_date):
        return None
