"""Tests for followup/templates.py."""

from datetime import date

import pytest

from followup.config import load_config
from followup.templates import (UNSUBSCRIBE_LINE, TemplateError, build_email, check_all_templates,
                                load_template)

ROW = {
    "customer_name": "Jane Smith", "customer_email": "jane@example.com",
    "job_type": "kitchen remodel", "job_address": "12 Oak St",
}


def test_example_templates_are_valid():
    check_all_templates(load_config("example_builder"))


def test_build_email_fills_placeholders_and_adds_footer():
    cfg = load_config("example_builder")
    review = next(s for s in cfg.stages if s.name == "review_request")
    email = build_email(cfg, review, ROW, date(2026, 11, 6))
    assert email.to == "jane@example.com"
    assert email.subject == "A quick favour, Jane?"
    assert cfg.review_link in email.body
    assert "{" not in email.body
    assert email.body.endswith(UNSUBSCRIBE_LINE)
    assert "Sam Rivera" in email.body  # the signature


def write(tmp_path, text):
    p = tmp_path / "t.txt"
    p.write_text(text, encoding="utf-8")
    return p


def test_subject_line_required(tmp_path):
    with pytest.raises(TemplateError, match="Subject"):
        load_template(write(tmp_path, "Hi {first_name}"))


def test_unknown_placeholder_is_caught(tmp_path):
    with pytest.raises(TemplateError, match="customer_nme"):
        load_template(write(tmp_path, "Subject: hi\n\nHi {customer_nme}"))


def test_unmatched_brace_is_caught(tmp_path):
    with pytest.raises(TemplateError, match="curly brace"):
        load_template(write(tmp_path, "Subject: hi\n\nHi {first_name"))


def test_double_braces_show_literally(tmp_path):
    subject, body = load_template(write(tmp_path, "Subject: hi\n\nUse {{braces}}"))
    assert body.format() == "Use {braces}"
