"""Create a new client folder from the setup wizard's answers.

This is kept apart from the wizard's questions so it can be tested
without anyone typing anything.
"""

import json
import re
import shutil
from pathlib import Path

from .config import CLIENTS_DIR
from .jobs import EMAIL_RE, REQUIRED_COLUMNS

APP_DIR = Path(__file__).resolve().parent.parent
# The default email templates. In the client package they are in starter_templates/;
# in this repo they are the example client's templates.
STARTER_DIRS = [APP_DIR / "starter_templates", CLIENTS_DIR / "example_builder" / "templates"]


def starter_templates_dir() -> Path:
    for d in STARTER_DIRS:
        if d.is_dir():
            return d
    raise FileNotFoundError("Can't find the starter email templates.")


def make_client_id(business_name: str) -> str:
    """'Smith & Sons Roofing, LLC' -> 'smith_sons_roofing_llc'."""
    slug = re.sub(r"[^a-z0-9]+", "_", business_name.lower()).strip("_")
    return slug or "my_business"


def check_answers(a: dict) -> list:
    """Return a list of problems with the wizard's answers (empty if all fine)."""
    problems = []
    for key in ("business_name", "from_name", "from_email", "review_link", "timezone"):
        if not a.get(key, "").strip():
            problems.append(f"{key} is required")
    for key in ("from_email", "alert_email"):
        if a.get(key) and not EMAIL_RE.match(a[key]):
            problems.append(f"{key} '{a[key]}' doesn't look like an email address")
    if a.get("review_link") and not a["review_link"].startswith(("http://", "https://")):
        problems.append("review_link should start with https://")
    return problems


CONFIG_TEMPLATE = """\
# Settings for {business_name}. Created by the setup wizard; safe to edit.
# Lines starting with # are comments.

business_name: {q_business_name}
from_name: {q_from_name}            # the name customers see in their inbox
from_email: {q_from_email}          # the Gmail account that sends the emails
review_link: {q_review_link}
phone: {q_phone}
website: {q_website}
timezone: {q_timezone}
signature: {q_signature}

# Who gets a warning email if a daily run has problems.
alert_email: {q_alert_email}

# How many days late an email may still go out (e.g. computer was off, job entered late).
grace_days: 7

# "email" = never send the same stage twice to the same address.
# "job"   = never send the same stage twice for the same job (repeat customers get a new sequence).
dedupe_by: email

# The email sequence. "day" counts from the job's completion date.
stages:
  - name: thank_you
    day: 1
    template: day1_thanks.txt
  - name: check_in
    day: 7
    template: day7_checkin.txt
  - name: review_request
    day: 14
    template: day14_review.txt
  - name: referral
    day: 90
    template: day90_referral.txt
"""


def create_client(answers: dict, clients_dir: Path = None, overwrite_config: bool = False) -> Path:
    """Create clients/<id>/ with config.yaml, templates/ and an empty jobs.csv.

    Never overwrites an existing jobs.csv, templates or logs: re-running the
    wizard can't wipe a client's data. config.yaml is replaced only if
    overwrite_config is True.
    """
    problems = check_answers(answers)
    if problems:
        raise ValueError("; ".join(problems))

    from . import config
    clients_dir = clients_dir or config.CLIENTS_DIR  # looked up now, not when Python loaded this file
    client_id = answers.get("client_id") or make_client_id(answers["business_name"])
    folder = clients_dir / client_id
    config_path = folder / "config.yaml"

    # Never let a NEW business take over another business's folder (same name, different Gmail).
    if not answers.get("client_id") and config_path.exists():
        import yaml
        current = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if str(current.get("from_email", "")).lower() != answers["from_email"].strip().lower():
            raise ValueError(f"A different business ({current.get('business_name')}) already uses the folder "
                             f"'{client_id}'. Use a slightly different business name (e.g. add the town).")
    folder.mkdir(parents=True, exist_ok=True)

    if overwrite_config or not config_path.exists():
        values = {k: answers.get(k, "") for k in
                  ("business_name", "from_name", "from_email", "review_link", "phone",
                   "website", "timezone", "signature", "alert_email")}
        # json.dumps gives a safely quoted string, which is also valid YAML.
        quoted = {f"q_{k}": json.dumps(v.strip()) for k, v in values.items()}
        config_path.write_text(CONFIG_TEMPLATE.format(business_name=values["business_name"], **quoted),
                               encoding="utf-8")

    templates = folder / "templates"
    if not templates.exists():
        shutil.copytree(starter_templates_dir(), templates)

    jobs = folder / "jobs.csv"
    if not jobs.exists():
        jobs.write_text(",".join(REQUIRED_COLUMNS) + "\n", encoding="utf-8")

    return folder
