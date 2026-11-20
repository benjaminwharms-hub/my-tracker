"""Tests for importing a business's own customer list (followup/importer.py)."""

from datetime import datetime

import pytest
from openpyxl import Workbook

from followup.importer import import_file, match_columns
from followup.jobs import REQUIRED_COLUMNS, load_jobs


@pytest.fixture
def jobs_path(tmp_path):
    p = tmp_path / "jobs.csv"
    p.write_text(",".join(REQUIRED_COLUMNS) + "\n")
    return p


def make_xlsx(tmp_path, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(["Smith Roofing customer list"])  # a title row above the headers, like real files
    for r in rows:
        ws.append(r)
    p = tmp_path / "Customers.xlsx"
    wb.save(p)
    return p


def test_messy_excel_columns_are_matched(tmp_path, jobs_path):
    p = make_xlsx(tmp_path, [
        ["Invoice #", "First Name", "Last Name", "E-mail Address", "Service", "Property Address", "Date Completed", "Notes"],
        [1001, "Jane", "Smith", "Jane@Example.com", "Roof repair", "1 Oak St", datetime(2026, 11, 1), "dog"],
        [1002, "Tom", "Lee", "tom@example.com", "Gutters", "2 Elm St", None, ""],
    ])
    report = import_file(p, jobs_path)
    assert report["columns_matched"]["customer_email"] == "E-mail Address"
    assert report["columns_ignored"] == ["Notes"]
    rows, _ = load_jobs(jobs_path)
    jane, tom = rows
    assert jane["job_id"] == "1001"  # not "1001.0"
    assert jane["customer_name"] == "Jane Smith" and jane["customer_email"] == "jane@example.com"
    assert jane["completion_date"] == "2026-11-01" and jane["status"] == "complete"
    assert jane["followup_stage"] == "done"  # past customer: no emails by default
    assert tom["status"] == "in progress" and tom["followup_stage"] == ""


def test_email_recent_past_option(tmp_path, jobs_path):
    p = make_xlsx(tmp_path, [["Name", "Email", "Completed"], ["Jane", "jane@example.com", "2026-11-15"]])
    report = import_file(p, jobs_path, existing_done=False)
    assert report["added_will_get_emails"] == 1
    assert load_jobs(jobs_path)[0][0]["followup_stage"] == ""


def test_csv_with_status_and_bad_rows(tmp_path, jobs_path):
    p = tmp_path / "list.csv"
    p.write_text("Client,Email,Job,Status,Finish Date\n"
                 "Jane,jane@example.com,Deck,In Progress,\n"
                 "No Email,,Deck,complete,2026-11-01\n"
                 "Bad Email,bad@,Deck,complete,2026-11-01\n"
                 "Bad Date,bd@example.com,Deck,complete,someday\n")
    report = import_file(p, jobs_path)
    assert report["added"] == 1
    reasons = " ".join(why for _, _, why in report["skipped"])
    assert "no email" in reasons and "doesn't look valid" in reasons and "completion date" in reasons
    assert load_jobs(jobs_path)[0][0]["job_type"] == "Deck"


def test_importing_twice_adds_no_duplicates(tmp_path, jobs_path):
    p = make_xlsx(tmp_path, [["Name", "Email", "Completed"], ["Jane", "jane@example.com", "2026-11-15"]])
    import_file(p, jobs_path)
    report = import_file(p, jobs_path)
    assert report["added"] == 0 and "already" in report["skipped"][0][2]


def test_preview_changes_nothing(tmp_path, jobs_path):
    before = jobs_path.read_text()
    p = make_xlsx(tmp_path, [["Name", "Email"], ["Jane", "jane@example.com"]])
    assert import_file(p, jobs_path, write=False)["added"] == 1
    assert jobs_path.read_text() == before


def test_explicit_mapping():
    cols = match_columns(["Who", "Addr", "E"], {"customer_name": "Who", "customer_email": "E"})
    assert cols["customer_name"] == 0 and cols["customer_email"] == 2


def test_missing_email_column_explains(tmp_path, jobs_path):
    p = make_xlsx(tmp_path, [["Name", "Phone"], ["Jane", "555"]])
    with pytest.raises(ValueError, match="--map"):
        import_file(p, jobs_path)


def test_unsupported_file_type(tmp_path, jobs_path):
    p = tmp_path / "list.numbers"
    p.write_text("x")
    with pytest.raises(ValueError, match="xlsx or .csv"):
        import_file(p, jobs_path)
