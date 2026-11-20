"""Read and write the jobs list.

For now the jobs list is a CSV file (it opens in Excel or Google Sheets).
Later a Google Sheets version can offer the same two functions,
load_jobs() and save_jobs(), and nothing else needs to change.

Columns (the order doesn't matter, and you can add your own columns):
    job_id           any unique ID. Left blank, one is filled in automatically.
    customer_name    e.g. "Jane Smith"
    customer_email   e.g. "jane@example.com"
    job_type         e.g. "kitchen remodel"
    job_address      e.g. "12 Oak St"
    completion_date  YYYY-MM-DD (or M/D/YYYY). Left blank, it is set to the
                     day the job is first seen as complete.
    status           the business sets this. "complete" starts the emails.
    followup_stage   the SYSTEM fills this in. Don't edit it by hand, except
                     to clear it to restart a sequence.
"""

import csv
import os
import re
import tempfile
import uuid
from datetime import date, datetime
from pathlib import Path

REQUIRED_COLUMNS = [
    "job_id", "customer_name", "customer_email", "job_type",
    "job_address", "completion_date", "status", "followup_stage",
]

# Status values (any capitalisation) that mean "the job is finished".
COMPLETE_STATUSES = {"complete", "completed", "done", "finished"}

# A simple email check. It catches typos, not every invalid address.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class JobsFileError(Exception):
    """Raised when the jobs file can't be used at all (e.g. a missing column)."""


def load_jobs(path: Path) -> tuple:
    """Read the CSV. Returns (rows, column_names). Each row is a dict: column name -> text."""
    if not path.exists():
        raise JobsFileError(f"Jobs file not found: {path}")

    # "utf-8-sig" also copes with the hidden marker Excel adds to CSV files.
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        columns = [c.strip() for c in (reader.fieldnames or [])]
        reader.fieldnames = columns
        rows = [{k: (v or "").strip() for k, v in row.items() if k} for row in reader]

    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        raise JobsFileError(f"{path}: missing column(s): {', '.join(missing)}")

    # Skip completely empty lines (common at the end of spreadsheets).
    rows = [r for r in rows if any(r.values())]

    # Give any job without an ID a short random one, so it can be tracked.
    for row in rows:
        if not row["job_id"]:
            row["job_id"] = uuid.uuid4().hex[:8]
    return rows, columns


def save_jobs(path: Path, rows: list, columns: list) -> None:
    """Write the rows back, keeping the original column order.

    It writes to a temporary file first, then swaps it in. A crash halfway
    through therefore can't leave a half-written jobs file.
    """
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp, path)
    except PermissionError:
        os.unlink(tmp)
        raise PermissionError(f"Couldn't save {path.name}: is it open in Excel? Close it. Emails already "
                              f"sent are recorded in the send log and won't be sent again.")
    except BaseException:
        os.unlink(tmp)
        raise


def is_complete(row: dict) -> bool:
    return row["status"].strip().lower() in COMPLETE_STATUSES


def parse_date(text: str) -> date:
    """Accept 2026-11-20 or 11/20/2026. Raises ValueError for anything else."""
    text = text.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):  # Excel often saves 11/20/26
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"can't read date '{text}' (use YYYY-MM-DD)")


def row_problem(row: dict) -> str:
    """Return a description of what's wrong with a row, or "" if it's usable."""
    if not row["customer_name"]:
        return "customer_name is blank"
    if not EMAIL_RE.match(row["customer_email"]):
        return f"customer_email '{row['customer_email']}' doesn't look valid"
    if row["completion_date"]:
        try:
            parse_date(row["completion_date"])
        except ValueError as e:
            return str(e)
    return ""
