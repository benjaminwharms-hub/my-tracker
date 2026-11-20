"""Send every email in a client's sequence to YOUR OWN address, so you can see them in a real inbox.

    python scripts/send_test_email.py --client example_builder --to you@example.com

It uses made-up job details and doesn't touch jobs.csv or the send log.
Use --stage to send just one, e.g. --stage review_request.
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from followup.config import load_config  # noqa: E402
from followup.gmail_client import connect  # noqa: E402
from followup.templates import build_email  # noqa: E402

SAMPLE_JOB = {"customer_name": "Test Customer", "job_type": "kitchen remodel", "job_address": "12 Example St"}


def main():
    parser = argparse.ArgumentParser(description="Send test emails to yourself.")
    parser.add_argument("--client", required=True)
    parser.add_argument("--to", required=True, help="your own email address")
    parser.add_argument("--stage", help="send only this stage (default: all)")
    args = parser.parse_args()

    cfg = load_config(args.client)
    stages = [s for s in cfg.stages if args.stage in (None, s.name)]
    if not stages:
        sys.exit(f"No stage named '{args.stage}'. Stages: {[s.name for s in cfg.stages]}")

    sender, _ = connect(cfg)
    for stage in stages:
        email = build_email(cfg, stage, {**SAMPLE_JOB, "customer_email": args.to}, date.today())
        email.subject = f"[TEST {stage.name}] {email.subject}"
        print(f"Sent {stage.name} -> {args.to} (Gmail id {sender.send(cfg, email)})")


if __name__ == "__main__":
    main()
