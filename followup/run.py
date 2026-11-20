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
from datetime import date, datetime

from followup.config import ConfigError, list_clients, load_config
from followup.runner import run_client
from followup.sender import DryRunSender, NoInbox


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Send follow-up emails for completed jobs.")
    who = parser.add_mutually_exclusive_group(required=True)
    who.add_argument("--client", action="append", help="client folder name (repeat for several)")
    who.add_argument("--all", action="store_true", help="run every client in clients/")
    parser.add_argument("--dry-run", action="store_true", help="print emails instead of sending; change no files")
    parser.add_argument("--today", help="pretend today is this date (YYYY-MM-DD); for testing")
    args = parser.parse_args(argv)

    client_ids = list_clients() if args.all else args.client
    had_errors = False

    for client_id in client_ids:
        print(f"\n### {client_id}{' (DRY RUN: nothing will be sent or saved)' if args.dry_run else ''}")
        try:
            cfg = load_config(client_id)
            # "Today" is in the business's own timezone, not the server's.
            today = date.fromisoformat(args.today) if args.today else datetime.now(cfg.tz).date()
            if args.dry_run:
                sender, inbox = DryRunSender(), NoInbox()
            else:
                from followup.gmail_client import connect  # only needed for real sending
                sender, inbox = connect(cfg)
            summary = run_client(cfg, today, sender, inbox, dry_run=args.dry_run)
        except Exception as e:  # e.g. bad config or Gmail not connected: skip this client, carry on
            had_errors = True
            kind = "Config problem" if isinstance(e, ConfigError) else type(e).__name__
            print(f"  !! {kind}: {e}")
            continue

        print(f"  -> {today}: sent {summary.sent}, stopped {summary.stopped}, "
              f"finished {summary.finished}, errors {len(summary.errors)}")
        had_errors |= bool(summary.errors)

    return 1 if had_errors else 0


if __name__ == "__main__":
    sys.exit(main())
