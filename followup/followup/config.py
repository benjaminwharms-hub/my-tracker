"""Load and check one client's settings.

Every client business gets its own folder under clients/, for example:

    clients/example_builder/
        config.yaml      <- business name, review link, timings...
        templates/       <- one .txt file per email in the sequence
        jobs.csv         <- the jobs list
        send_log.csv     <- created automatically: every email sent

The folder name ("example_builder") is the client's ID. You pass it on the
command line: python run.py --client example_builder
"""

from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

# The clients/ folder sits next to this package (followup/clients/).
CLIENTS_DIR = Path(__file__).resolve().parent.parent / "clients"

# Settings every config.yaml must have.
REQUIRED_KEYS = ["business_name", "from_name", "from_email", "review_link", "timezone", "stages"]


class ConfigError(Exception):
    """Raised when a client's config is missing or wrong. The message says what to fix."""


@dataclass
class Stage:
    """One email in the sequence, e.g. the Day 7 check-in."""

    name: str  # short ID used in logs, e.g. "check_in"
    day: int  # days after the job's completion date
    template: str  # file name inside the client's templates/ folder


@dataclass
class ClientConfig:
    """Everything the system needs to know about one client business."""

    client_id: str
    folder: Path
    business_name: str
    from_name: str
    from_email: str
    review_link: str
    timezone: str
    stages: list  # list of Stage, sorted by day
    phone: str = ""
    website: str = ""
    signature: str = ""
    # How many days late an email may still go out (e.g. if a job is entered
    # late or a run was missed). Older than that, the stage is skipped.
    grace_days: int = 7
    # "email": never send the same stage twice to the same email address (default).
    # "job":   never send the same stage twice for the same job. Repeat
    #          customers then get a fresh sequence for each new job.
    dedupe_by: str = "email"
    # Where to email a warning if a daily run has errors (usually you, the operator).
    alert_email: str = ""
    jobs_file: str = "jobs.csv"
    log_file: str = "send_log.csv"
    unsubscribe_file: str = "unsubscribed.csv"
    extra: dict = field(default_factory=dict)  # any other keys, for your own use

    # Handy full paths to this client's files.
    @property
    def jobs_path(self) -> Path:
        return self.folder / self.jobs_file

    @property
    def log_path(self) -> Path:
        return self.folder / self.log_file

    @property
    def unsubscribe_path(self) -> Path:
        return self.folder / self.unsubscribe_file

    @property
    def templates_dir(self) -> Path:
        return self.folder / "templates"

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


def list_clients(clients_dir: Path = None, include_examples: bool = False) -> list:
    """Return the IDs of all client folders that contain a config.yaml.

    Folders whose name starts with "example" (sample data) are left out unless
    include_examples=True. That way "run.py --all" never tries to email from them.
    """
    clients_dir = clients_dir or CLIENTS_DIR
    ids = sorted(p.parent.name for p in clients_dir.glob("*/config.yaml"))
    return ids if include_examples else [c for c in ids if not c.startswith("example")]


def load_config(client_id: str, clients_dir: Path = CLIENTS_DIR) -> ClientConfig:
    """Read clients/<client_id>/config.yaml and check it. Raises ConfigError if anything is wrong."""
    folder = clients_dir / client_id
    path = folder / "config.yaml"
    if not path.exists():
        raise ConfigError(f"No config found at {path}. Known clients: {list_clients(clients_dir, include_examples=True)}")

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    missing = [k for k in REQUIRED_KEYS if not raw.get(k)]
    if missing:
        raise ConfigError(f"{path}: missing required setting(s): {', '.join(missing)}")

    # Check the timezone name is real, e.g. "America/Chicago".
    try:
        ZoneInfo(raw["timezone"])
    except (ZoneInfoNotFoundError, ValueError):
        raise ConfigError(f"{path}: unknown timezone '{raw['timezone']}' (use a name like America/Chicago)")

    stages = _parse_stages(raw["stages"], folder, path)

    dedupe_by = raw.get("dedupe_by", "email")
    if dedupe_by not in ("email", "job"):
        raise ConfigError(f"{path}: dedupe_by must be 'email' or 'job', not '{dedupe_by}'")

    # Pull out the known settings; anything else goes into `extra`.
    known = {
        "business_name", "from_name", "from_email", "review_link", "timezone", "stages",
        "phone", "website", "signature", "grace_days", "dedupe_by", "alert_email",
        "jobs_file", "log_file", "unsubscribe_file",
    }
    extra = {k: v for k, v in raw.items() if k not in known}

    return ClientConfig(
        client_id=client_id,
        folder=folder,
        business_name=str(raw["business_name"]),
        from_name=str(raw["from_name"]),
        from_email=str(raw["from_email"]),
        review_link=str(raw["review_link"]),
        timezone=str(raw["timezone"]),
        stages=stages,
        phone=str(raw.get("phone", "")),
        website=str(raw.get("website", "")),
        signature=str(raw.get("signature", "")).strip(),
        grace_days=int(raw.get("grace_days", 7)),
        dedupe_by=dedupe_by,
        alert_email=str(raw.get("alert_email", "") or ""),
        jobs_file=raw.get("jobs_file", "jobs.csv"),
        log_file=raw.get("log_file", "send_log.csv"),
        unsubscribe_file=raw.get("unsubscribe_file", "unsubscribed.csv"),
        extra=extra,
    )


def _parse_stages(raw_stages, folder: Path, path: Path) -> list:
    """Turn the `stages:` list from YAML into Stage objects and check them."""
    if not isinstance(raw_stages, list) or not raw_stages:
        raise ConfigError(f"{path}: 'stages' must be a list of emails")

    stages = []
    for i, s in enumerate(raw_stages, start=1):
        try:
            stage = Stage(name=str(s["name"]), day=int(s["day"]), template=str(s["template"]))
        except (KeyError, TypeError, ValueError):
            raise ConfigError(f"{path}: stage #{i} needs a name, a whole-number day, and a template")
        if not (folder / "templates" / stage.template).exists():
            raise ConfigError(f"{path}: stage '{stage.name}' uses template '{stage.template}', "
                              f"but templates/{stage.template} doesn't exist")
        stages.append(stage)

    names = [s.name for s in stages]
    if len(set(names)) != len(names):
        raise ConfigError(f"{path}: stage names must be unique (got {names})")

    # Names that the system itself writes into the follow-up stage column.
    reserved = {"started", "done", "stopped_replied", "stopped_unsubscribed"}
    if reserved & set(names):
        raise ConfigError(f"{path}: these stage names are reserved: {sorted(reserved)}")

    return sorted(stages, key=lambda s: s.day)
