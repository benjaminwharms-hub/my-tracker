"""Record every email sent, plus errors and stops, in send_log.csv.

The log is also the system's memory: before sending, it checks the log so the
same person never gets the same stage twice (requirement: "never email the
same person twice for the same stage").

Each row is written to disk the moment it happens. If the program crashes
halfway through a run, every email already sent is still recorded, so the
next run won't send it again.

Also here: the unsubscribe list (unsubscribed.csv). Anyone on it never gets
another email from this client, even for a new job.
"""

import csv
from datetime import datetime, timezone
from pathlib import Path

LOG_COLUMNS = ["timestamp", "client", "job_id", "customer_email", "stage", "result", "message_id", "detail"]

# Values of the "result" column.
SENT = "sent"
ERROR = "error"
STOPPED = "stopped"
SKIPPED = "skipped"


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SendLog:
    """The client's send_log.csv, loaded into memory.

    write_to_disk=False (dry-run mode) keeps new rows in memory only. A dry
    run then behaves exactly like a real run, without changing any files.
    """

    def __init__(self, path: Path, client_id: str, write_to_disk: bool = True):
        self.path = path
        self.client_id = client_id
        self.write_to_disk = write_to_disk
        self.rows = []
        if path.exists():
            with open(path, newline="", encoding="utf-8") as f:
                self.rows = list(csv.DictReader(f))

    def record(self, job_id, email, stage, result, message_id="", detail=""):
        row = {
            "timestamp": now_utc(), "client": self.client_id, "job_id": job_id,
            "customer_email": email.lower(), "stage": stage, "result": result,
            "message_id": message_id, "detail": detail,
        }
        self.rows.append(row)
        if self.write_to_disk:
            new_file = not self.path.exists()
            with open(self.path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=LOG_COLUMNS)
                if new_file:
                    writer.writeheader()
                writer.writerow(row)

    def _sent_rows(self, email=None, job_id=None):
        for r in self.rows:
            if r["result"] != SENT:
                continue
            if email is not None and r["customer_email"] != email.lower():
                continue
            if job_id is not None and r["job_id"] != job_id:
                continue
            yield r

    def sent_stages(self, email=None, job_id=None) -> set:
        """Names of stages already sent, to this email address and/or for this job."""
        return {r["stage"] for r in self._sent_rows(email, job_id)}

    def first_sent_date(self, email=None, job_id=None):
        """Date (YYYY-MM-DD) of the first email sent, or None. Replies are looked for from this date on."""
        dates = sorted(r["timestamp"][:10] for r in self._sent_rows(email, job_id))
        return dates[0] if dates else None


class UnsubscribeList:
    """unsubscribed.csv: one email address per row, never to be emailed again."""

    COLUMNS = ["customer_email", "timestamp", "reason"]

    def __init__(self, path: Path, write_to_disk: bool = True):
        self.path = path
        self.write_to_disk = write_to_disk
        self.emails = set()
        if path.exists():
            with open(path, newline="", encoding="utf-8") as f:
                self.emails = {r["customer_email"].strip().lower() for r in csv.DictReader(f)}

    def __contains__(self, email: str) -> bool:
        return email.strip().lower() in self.emails

    def add(self, email: str, reason: str) -> None:
        email = email.strip().lower()
        if email in self.emails:
            return
        self.emails.add(email)
        if self.write_to_disk:
            new_file = not self.path.exists()
            with open(self.path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.COLUMNS)
                if new_file:
                    writer.writeheader()
                writer.writerow({"customer_email": email, "timestamp": now_utc(), "reason": reason})
