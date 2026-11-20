"""Tests for the installer pieces: client setup, scheduler files, packaging, alerts."""

import plistlib
import zipfile
from pathlib import Path

import pytest

import run as run_module
from followup import scheduler
from followup.client_setup import check_answers, create_client, make_client_id
from followup.config import load_config
from followup.jobs import REQUIRED_COLUMNS, parse_date
from scripts import make_package

ANSWERS = {
    "business_name": "Smith & Sons Roofing, LLC", "from_name": "Dave at Smith Roofing",
    "from_email": "dave@example.com", "review_link": "https://g.page/r/abc/review",
    "phone": "555-0100", "website": "", "timezone": "America/Denver",
    "signature": 'Dave Smith\nSmith & Sons "Roofing"', "alert_email": "me@example.com",
}


def test_make_client_id():
    assert make_client_id("Smith & Sons Roofing, LLC") == "smith_sons_roofing_llc"
    assert make_client_id("!!!") == "my_business"


def test_check_answers():
    assert check_answers(ANSWERS) == []
    bad = {**ANSWERS, "from_email": "dave@", "review_link": "g.page/x", "timezone": ""}
    problems = " ".join(check_answers(bad))
    assert "from_email" in problems and "https" in problems and "timezone" in problems


def test_create_client_makes_a_loadable_config(tmp_path):
    folder = create_client(ANSWERS, clients_dir=tmp_path)
    assert folder.name == "smith_sons_roofing_llc"
    cfg = load_config(folder.name, tmp_path)
    assert cfg.business_name == "Smith & Sons Roofing, LLC"
    assert cfg.signature == 'Dave Smith\nSmith & Sons "Roofing"'  # quotes and new lines survive
    assert cfg.alert_email == "me@example.com"
    assert len(cfg.stages) == 4
    assert (folder / "jobs.csv").read_text().strip() == ",".join(REQUIRED_COLUMNS)


def test_rerunning_setup_never_wipes_jobs_or_templates(tmp_path):
    folder = create_client(ANSWERS, clients_dir=tmp_path)
    (folder / "jobs.csv").write_text("precious data")
    (folder / "templates" / "day1_thanks.txt").write_text("Subject: custom\n\nedited")
    create_client({**ANSWERS, "phone": "555-9999"}, clients_dir=tmp_path, overwrite_config=True)
    assert (folder / "jobs.csv").read_text() == "precious data"
    assert "edited" in (folder / "templates" / "day1_thanks.txt").read_text()
    assert load_config(folder.name, tmp_path).phone == "555-9999"


def test_create_client_rejects_bad_answers(tmp_path):
    with pytest.raises(ValueError, match="from_email"):
        create_client({**ANSWERS, "from_email": "nope"}, clients_dir=tmp_path)


def test_windows_task_script():
    script = scheduler.build_windows_script(Path(r"C:\Users\O'Neil\FollowupEmails\.venv\Scripts\pythonw.exe"),
                                            9, 5, app_dir=Path(r"C:\Users\O'Neil\FollowupEmails"))
    assert "-StartWhenAvailable" in script  # catches up after the computer was off
    assert "-At 09:05" in script
    assert "O''Neil" in script  # an apostrophe in the path is escaped for PowerShell
    assert "--all" in script and "daily.log" in script


def test_mac_plist():
    plist = plistlib.loads(scheduler.build_mac_plist(Path("/Users/x/FollowupEmails/.venv/bin/python"), 8, 30,
                                                     app_dir=Path("/Users/x/FollowupEmails")))
    assert plist["StartCalendarInterval"] == {"Hour": 8, "Minute": 30}
    assert plist["ProgramArguments"][1] == "/Users/x/FollowupEmails/run.py"
    assert "--all" in plist["ProgramArguments"]


def test_mac_folder_warning():
    home = Path.home()
    assert "Desktop" in scheduler.mac_folder_warning(home / "Desktop" / "FollowupEmails")
    assert scheduler.mac_folder_warning(home / "FollowupEmails") == ""


def test_package_contents(tmp_path):
    out = make_package.build(tmp_path / "pkg.zip", allow_missing_secret=True)
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
        bat = z.read("FollowupEmails/Install (Windows).bat")
        mac_mode = (z.getinfo("FollowupEmails/Install (Mac).command").external_attr >> 16) & 0o777
    assert "FollowupEmails/setup_wizard.py" in names
    assert "FollowupEmails/followup/gmail_client.py" in names
    assert "FollowupEmails/starter_templates/day14_review.txt" in names
    # Never shipped: tests, any client's data, any token.
    assert not any("/tests/" in n or "/clients/" in n or "token" in n for n in names)
    assert b"\r\n" in bat and b"\n" not in bat.replace(b"\r\n", b"")  # Windows line endings
    assert mac_mode == 0o755  # runnable on a Mac


def test_excel_short_dates():
    assert parse_date("11/20/26").isoformat() == "2026-11-20"


class RecordingSender:
    def __init__(self):
        self.sent = []

    def send(self, cfg, email):
        self.sent.append(email)
        return "id"


def test_alert_email_lists_problems():
    cfg = load_config("example_builder")
    cfg.alert_email = "me@example.com"
    sender = RecordingSender()
    run_module.send_alert(cfg, sender, ["job J1: can't use this row: customer_email 'x' doesn't look valid"])
    assert sender.sent[0].to == "me@example.com"
    assert "J1" in sender.sent[0].body and "Example Builders" in sender.sent[0].subject


def test_no_alert_without_alert_email():
    cfg = load_config("example_builder")
    sender = RecordingSender()
    run_module.send_alert(cfg, sender, ["problem"])
    assert sender.sent == []


def test_log_file_option(tmp_path, monkeypatch, capsys):
    import sys
    log = tmp_path / "logs" / "daily.log"
    real_stdout, real_stderr = sys.stdout, sys.stderr
    try:
        code = run_module.main(["--client", "example_builder", "--dry-run", "--today", "2026-11-20",
                                "--log-file", str(log)])
    finally:
        sys.stdout.close()
        sys.stdout, sys.stderr = real_stdout, real_stderr
    assert code == 0
    text = log.read_text()
    assert "run started" in text and "sent 4" in text


def test_wizard_end_to_end(tmp_path, monkeypatch):
    """Walk through all 6 wizard steps with typed answers, a fake Gmail and a fake scheduler."""
    import setup_wizard
    from followup import client_setup, config, gmail_client

    monkeypatch.setattr(config, "CLIENTS_DIR", tmp_path)
    monkeypatch.setattr(client_setup, "CLIENTS_DIR", tmp_path)
    monkeypatch.setattr(setup_wizard, "CLIENTS_DIR", tmp_path)
    monkeypatch.setattr(setup_wizard, "list_clients", lambda: config.list_clients(tmp_path))
    monkeypatch.setattr(setup_wizard, "load_config", lambda cid: config.load_config(cid, tmp_path))
    secret = tmp_path / "client_secret.json"
    secret.write_text("{}")
    monkeypatch.setattr(gmail_client, "CLIENT_SECRET_FILE", secret)

    sender = RecordingSender()
    state = {"signed_in": False}

    def fake_connect(cfg):
        if not state["signed_in"]:
            raise gmail_client.GmailNotConnected("no token")
        return sender, None

    def fake_sign_in(cfg, open_browser=True):
        state["signed_in"] = True
        return cfg.from_email

    monkeypatch.setattr(gmail_client, "connect", fake_connect)
    monkeypatch.setattr(gmail_client, "sign_in", fake_sign_in)
    scheduled = {}
    monkeypatch.setattr(scheduler, "install", lambda h, m: scheduled.update(h=h, m=m) or "fake schedule")
    monkeypatch.setattr(scheduler, "run_now", lambda: None)
    monkeypatch.setattr(setup_wizard, "make_desktop_shortcut", lambda target: "Desktop/Follow-up Jobs")
    monkeypatch.setattr("sys.argv", ["setup_wizard.py"])

    typed = iter([
        "Smith Roofing", "dave@example.com", "", "https://g.page/r/abc/review", "555-0100", "",
        "America/Denver", "Dave Smith", "", "me@example.com",  # step 1 (signature: 1 line, then blank)
        "",                  # step 3: press Enter to open the browser
        "y", "",             # step 4: send test email? yes, to the default (alert email)
        "07:45",             # step 5: time
    ])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(typed))

    assert setup_wizard.main() == 0
    cfg = config.load_config("smith_roofing", tmp_path)
    assert cfg.from_name == "Smith Roofing" and cfg.signature == "Dave Smith"
    assert sender.sent[0].to == "me@example.com" and sender.sent[0].subject.startswith("[TEST]")
    assert scheduled == {"h": 7, "m": 45}
