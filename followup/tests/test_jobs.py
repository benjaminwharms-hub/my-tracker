"""Tests for reading and writing the jobs CSV (followup/jobs.py)."""

from datetime import date

import pytest

from followup.jobs import JobsFileError, is_complete, load_jobs, parse_date, row_problem, save_jobs

HEADER = "job_id,customer_name,customer_email,job_type,job_address,completion_date,status,followup_stage,notes\n"


def write(tmp_path, text):
    p = tmp_path / "jobs.csv"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_and_save_round_trip(tmp_path):
    p = write(tmp_path, HEADER + "J1,Jane Smith,jane@example.com,deck,1 Oak St,2026-11-19,Complete,,gate code 1234\n\n")
    rows, cols = load_jobs(p)
    assert len(rows) == 1  # the blank line is ignored
    assert rows[0]["customer_name"] == "Jane Smith"
    assert cols[-1] == "notes"  # extra columns are kept

    rows[0]["followup_stage"] = "thank_you"
    save_jobs(p, rows, cols)
    rows2, _ = load_jobs(p)
    assert rows2[0]["followup_stage"] == "thank_you"
    assert rows2[0]["notes"] == "gate code 1234"


def test_blank_job_id_gets_filled(tmp_path):
    rows, _ = load_jobs(write(tmp_path, HEADER + ",Jane,jane@example.com,deck,x,,complete,,\n"))
    assert len(rows[0]["job_id"]) == 8


def test_excel_bom_is_handled(tmp_path):
    p = tmp_path / "jobs.csv"
    p.write_text(HEADER + "J1,Jane,jane@example.com,deck,x,,complete,,\n", encoding="utf-8-sig")
    rows, cols = load_jobs(p)
    assert cols[0] == "job_id"


def test_missing_column(tmp_path):
    with pytest.raises(JobsFileError, match="customer_email"):
        load_jobs(write(tmp_path, "job_id,customer_name\nJ1,Jane\n"))


def test_is_complete():
    assert is_complete({"status": " Completed "})
    assert not is_complete({"status": "in progress"})


def test_parse_date():
    assert parse_date("2026-11-20") == date(2026, 11, 20)
    assert parse_date("11/20/2026") == date(2026, 11, 20)
    with pytest.raises(ValueError):
        parse_date("next tuesday")


def test_row_problem():
    good = {"customer_name": "Jane", "customer_email": "jane@example.com", "completion_date": "2026-11-20"}
    assert row_problem(good) == ""
    assert "email" in row_problem({**good, "customer_email": "jane@"})
    assert "date" in row_problem({**good, "completion_date": "soon"})
    assert "name" in row_problem({**good, "customer_name": ""})
