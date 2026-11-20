"""Run the daily follow-up emails.

Examples:
    python run.py --client example_builder --dry-run       # print emails, change nothing
    python run.py --all --dry-run --today 2026-12-04       # pretend it's another day
    python run.py --all                                    # the real daily run (sends email)

Exit code: 0 if everything worked, 1 if any job had an error. The scheduler
uses this to flag a failed run.
"""

import argparse
import sys
import traceback
from datetime import date, datetime
from pathlib import Path

from followup.config import ConfigError, list_clients, load_config
from followup.runner import run_client
from followup.sender import DryRunSender, NoInbox
from followup.templates import Email


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Send follow-up emails for completed jobs.")
    who = parser.add_mutually_exclusive_group(required=True)
    who.add_argument("--client", action="append", help="client folder name (repeat for several)")
    who.add_argument("--all", action="store_true", help="run every client in clients/")
    parser.add_argument("--dry-run", action="store_true", help="print emails instead of sending; change no files")
    parser.add_argument("--today", help="pretend today is this date (YYYY-MM-DD); for testing")
    parser.add_argument("--live-inbox", action="store_true",
                        help="with --dry-run: still check the real Gmail inbox for replies/STOP (read-only)")
    parser.add_argument("--log-file", help="add all output to this file (used by the daily scheduler)")
    args = parser.parse_args(argv)

    if args.log_file:
        # Scheduled runs have no screen, so send everything printed to a log file instead.
        Path(args.log_file).parent.mkdir(parents=True, exist_ok=True)
        sys.stdout = sys.stderr = open(args.log_file, "a", encoding="utf-8", buffering=1)
        print(f"\n===== run started {datetime.now():%Y-%m-%d %H:%M} =====")

    client_ids = list_clients() if args.all else args.client
    if not client_ids:
        print("No clients set up yet. Run the setup wizard first.")
    had_errors = False

    for client_id in client_ids:
        print(f"\n### {client_id}{' (DRY RUN: nothing will be sent or saved)' if args.dry_run else ''}")
        cfg = sender = None
        try:
            cfg = load_config(client_id)
            # "Today" is in the business's own timezone, not the server's.
            today = date.fromisoformat(args.today) if args.today else datetime.now(cfg.tz).date()
            if args.dry_run and not args.live_inbox:
                sender, inbox = DryRunSender(), NoInbox()
            else:
                from followup.gmail_client import connect  # only needed when Gmail is used
                sender, inbox = connect(cfg)
                if args.dry_run:  # --live-inbox: read replies from Gmail, but only PRINT emails
                    sender = DryRunSender()
            summary = run_client(cfg, today, sender, inbox, dry_run=args.dry_run)
            problems = summary.errors
            print(f"  -> {today}: sent {summary.sent}, stopped {summary.stopped}, "
                  f"finished {summary.finished}, errors {len(problems)}")
        except Exception as e:  # e.g. bad config or Gmail not connected: skip this client, carry on
            kind = "Config problem" if isinstance(e, ConfigError) else type(e).__name__
            print(f"  !! {kind}: {e}")
            if args.log_file:
                traceback.print_exc()
            problems = [f"{kind}: {e}"]

        if problems:
            had_errors = True
            if not args.dry_run:
                send_alert(cfg, sender, problems)

    return 1 if had_errors else 0


def send_alert(cfg, sender, problems) -> None:
    """Email the operator (alert_email in config.yaml) a list of what went wrong.

    It uses the business's own Gmail. If Gmail itself is what's broken (e.g.
    the token expired), the alert can't be sent, and the problem is only in
    the log file.
    """
    if not cfg or not cfg.alert_email or sender is None:
        return
    body = (f"The daily follow-up run for {cfg.business_name} had {len(problems)} problem(s):\n\n"
            + "\n".join(f"- {p}" for p in problems)
            + "\n\nEmails without problems were still sent. Fix these and the next daily run will retry.")
    try:
        sender.send(cfg, Email(to=cfg.alert_email, subject=f"[Follow-up emails] problem for {cfg.business_name}",
                               body=body))
        print(f"  (alert emailed to {cfg.alert_email})")
    except Exception as e:
        print(f"  (couldn't send alert email: {e})")


if __name__ == "__main__":
    sys.exit(main())
