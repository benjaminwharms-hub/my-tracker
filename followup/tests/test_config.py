"""Tests for followup/config.py. Run all tests with:  python -m pytest"""

import shutil
from pathlib import Path

import pytest

from followup.config import CLIENTS_DIR, ConfigError, list_clients, load_config


def test_example_client_loads():
    cfg = load_config("example_builder")
    assert cfg.business_name == "Example Builders"
    assert [s.name for s in cfg.stages] == ["thank_you", "check_in", "review_request", "referral"]
    assert [s.day for s in cfg.stages] == [1, 7, 14, 90]
    assert cfg.jobs_path.name == "jobs.csv"
    assert "example_builder" in list_clients()


def make_client(tmp_path: Path, config_text: str) -> Path:
    """Copy the example client into a temp folder, then replace its config."""
    folder = tmp_path / "testco"
    shutil.copytree(CLIENTS_DIR / "example_builder" / "templates", folder / "templates")
    (folder / "config.yaml").write_text(config_text, encoding="utf-8")
    return tmp_path


GOOD = """
business_name: TestCo
from_name: Test
from_email: a@example.com
review_link: https://x
timezone: America/Chicago
stages:
  - {name: late, day: 14, template: day14_review.txt}
  - {name: early, day: 1, template: day1_thanks.txt}
"""


def test_stages_sorted_by_day(tmp_path):
    cfg = load_config("testco", make_client(tmp_path, GOOD))
    assert [s.name for s in cfg.stages] == ["early", "late"]


def test_missing_client():
    with pytest.raises(ConfigError, match="No config"):
        load_config("does_not_exist")


def test_missing_required_setting(tmp_path):
    with pytest.raises(ConfigError, match="review_link"):
        load_config("testco", make_client(tmp_path, GOOD.replace("review_link: https://x", "")))


def test_bad_timezone(tmp_path):
    with pytest.raises(ConfigError, match="timezone"):
        load_config("testco", make_client(tmp_path, GOOD.replace("America/Chicago", "Mars/Base")))


def test_missing_template_file(tmp_path):
    with pytest.raises(ConfigError, match="doesn't exist"):
        load_config("testco", make_client(tmp_path, GOOD.replace("day1_thanks.txt", "nope.txt")))


def test_duplicate_stage_names(tmp_path):
    with pytest.raises(ConfigError, match="unique"):
        load_config("testco", make_client(tmp_path, GOOD.replace("name: late", "name: early")))
