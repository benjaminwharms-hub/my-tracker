"""Fill in email templates and build the final email.

A template is a plain text file. The first line is the subject, then a blank
line, then the body:

    Subject: Thank you, {first_name}

    Hi {first_name},
    Thanks for choosing us for your {job_type}...

Placeholders in {curly braces} are replaced with the job's details. To show a
real curly brace in an email, write it twice: {{ or }}.

The signature and the unsubscribe line are added automatically to every
email, so editing a template can never remove them.
"""

import string
from dataclasses import dataclass
from pathlib import Path

# Every placeholder a template may use.
PLACEHOLDERS = {
    "customer_name": "full name from the jobs list",
    "first_name": "first word of customer_name",
    "job_type": "e.g. kitchen remodel",
    "job_address": "e.g. 12 Oak St",
    "completion_date": "e.g. November 19, 2026",
    "business_name": "from config.yaml",
    "from_name": "from config.yaml",
    "review_link": "from config.yaml",
    "phone": "from config.yaml",
    "website": "from config.yaml",
}

UNSUBSCRIBE_LINE = "Prefer not to get these emails? Just reply STOP and we won't email you again."


class TemplateError(Exception):
    """Raised for a badly formatted template or an unknown placeholder."""


@dataclass
class Email:
    to: str
    subject: str
    body: str


def load_template(path: Path) -> tuple:
    """Read a template file. Returns (subject, body), still containing {placeholders}."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    first_line, _, rest = text.partition("\n")
    if not first_line.lower().startswith("subject:"):
        raise TemplateError(f"{path.name}: the first line must start with 'Subject:'")
    subject = first_line[len("subject:"):].strip()
    body = rest.strip("\n")
    for part in (subject, body):
        check_placeholders(part, path.name)
    return subject, body


def check_placeholders(text: str, where: str) -> None:
    """Raise TemplateError if the text uses a placeholder we don't know (usually a typo)."""
    try:
        fields = [f for _, f, _, _ in string.Formatter().parse(text) if f is not None]
    except ValueError as e:  # e.g. a single unmatched "{"
        raise TemplateError(f"{where}: {e}. To show a curly brace, write {{{{ or }}}}")
    for f in fields:
        if f not in PLACEHOLDERS:
            raise TemplateError(f"{where}: unknown placeholder {{{f}}}. "
                                f"Allowed: {', '.join('{' + p + '}' for p in PLACEHOLDERS)}")


def placeholder_values(cfg, row: dict, completion_date) -> dict:
    """Collect the values for every placeholder, from the client config and one job row."""
    name = row["customer_name"].strip()
    return {
        "customer_name": name,
        "first_name": name.split()[0] if name else "there",
        "job_type": row.get("job_type", "") or "project",
        "job_address": row.get("job_address", ""),
        "completion_date": f"{completion_date:%B} {completion_date.day}, {completion_date.year}",
        "business_name": cfg.business_name,
        "from_name": cfg.from_name,
        "review_link": cfg.review_link,
        "phone": cfg.phone,
        "website": cfg.website,
    }


def build_email(cfg, stage, row: dict, completion_date) -> Email:
    """Make the finished email for one job and one stage."""
    subject, body = load_template(cfg.templates_dir / stage.template)
    values = placeholder_values(cfg, row, completion_date)
    body = body.format(**values)
    if cfg.signature:
        body += "\n\n" + cfg.signature
    body += "\n\n--\n" + UNSUBSCRIBE_LINE
    return Email(to=row["customer_email"], subject=subject.format(**values), body=body)


def check_all_templates(cfg) -> None:
    """Check every template for a client. Run at start-up, so a typo stops the run before anything is sent."""
    for stage in cfg.stages:
        load_template(cfg.templates_dir / stage.template)
