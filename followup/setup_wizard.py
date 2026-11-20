"""Setup wizard: sets everything up on a client's computer.

You don't normally run this by hand. "Install (Windows).bat" and
"Install (Mac).command" run it after installing the Python packages.

    python setup_wizard.py              # set up (or update) the business
    python setup_wizard.py --uninstall  # remove the daily schedule

No-questions mode (used when Claude does the setup for you):
    python setup_wizard.py --answers business.json --test-to you@example.com --time 09:00
business.json holds the step 1 answers: business_name, from_email, from_name,
review_link, phone, website, timezone, signature, alert_email.

Steps:
  1. Ask for the business details
  2. Create the business's folder (config, email templates, empty jobs list)
  3. Connect their Gmail (browser sign-in)
  4. Send a test email
  5. Schedule the daily run
  6. Put a "Follow-up Jobs" shortcut on the desktop
"""

import argparse
import json
import platform
import subprocess
import sys
from datetime import date

from followup import scheduler
from followup.client_setup import check_answers, create_client, make_client_id
from followup.config import CLIENTS_DIR, list_clients, load_config

LINE = "-" * 60


def ask(question: str, default: str = "", required: bool = True) -> str:
    """Ask a question. Pressing Enter accepts the [default]."""
    hint = f" [{default}]" if default else ""
    while True:
        answer = input(f"{question}{hint}: ").strip() or default
        if answer or not required:
            return answer
        print("  (this one is required)")


def yes(question: str, default: bool = True) -> bool:
    answer = input(f"{question} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
    return default if not answer else answer.startswith("y")


def detect_timezone() -> str:
    try:
        from tzlocal import get_localzone_name
        return get_localzone_name() or "America/Chicago"
    except Exception:
        return "America/Chicago"


def step(n: int, title: str) -> None:
    print(f"\n{LINE}\nStep {n} of 6: {title}\n{LINE}")


def ask_business_details(existing=None) -> dict:
    """Step 1. If the business is already set up, its current values are the defaults."""
    e = existing
    print("Press Enter to accept the value in [brackets].\n")
    while True:
        a = {}
        a["business_name"] = ask("Business name (e.g. Smith Roofing)", e.business_name if e else "")
        a["from_email"] = ask("Gmail address the emails are sent from", e.from_email if e else "")
        a["from_name"] = ask("Sender name customers will see", e.from_name if e else f"{a['business_name']}")
        a["review_link"] = ask("Google review link (Google Business Profile > 'Ask for reviews')",
                               e.review_link if e else "")
        a["phone"] = ask("Business phone", e.phone if e else "", required=False)
        a["website"] = ask("Website", e.website if e else "", required=False)
        a["timezone"] = ask("Timezone", e.timezone if e else detect_timezone())
        print("Email signature (the lines at the bottom of each email). Type each line and press Enter;")
        print("press Enter on an empty line to finish." + (" Leave it empty to keep the current one." if e else ""))
        lines = []
        while True:
            line = input("  > ").rstrip()
            if not line:
                break
            lines.append(line)
        a["signature"] = "\n".join(lines) if lines else (e.signature if e else f"{a['from_name']}\n{a['business_name']}")
        a["alert_email"] = ask("Email for problem alerts (usually your own, the installer)",
                               e.alert_email if e else "", required=False)
        if existing:
            a["client_id"] = existing.client_id

        problems = check_answers(a)
        if not problems:
            return a
        print("\nPlease fix these and try again:\n  - " + "\n  - ".join(problems) + "\n")


def make_desktop_shortcut(target) -> str:
    """Put a "Follow-up Jobs" shortcut to jobs.csv on the desktop. Returns where, or "" if it failed."""
    system = platform.system()
    try:
        if system == "Windows":
            ps = ("$d=[Environment]::GetFolderPath('Desktop'); "
                  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut(\"$d\\Follow-up Jobs.lnk\"); "
                  f"$s.TargetPath={scheduler._ps_quote(target)}; $s.Save(); Write-Output $d")
            out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True,
                                 capture_output=True, text=True).stdout.strip()
            return f"{out}\\Follow-up Jobs"
        if system == "Darwin":
            script = (f'tell application "Finder" to make alias file to POSIX file "{target}" '
                      f'at (path to desktop folder) with properties {{name:"Follow-up Jobs.csv"}}')
            subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
            return "Desktop/Follow-up Jobs.csv"
    except Exception:
        pass
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Set up automated follow-up emails on this computer.")
    parser.add_argument("--uninstall", action="store_true", help="remove the daily schedule")
    parser.add_argument("--answers", help="JSON file with the business details: asks no questions at all")
    parser.add_argument("--test-to", help="with --answers: send the test email here (default: no test email)")
    parser.add_argument("--time", default="09:00", help="with --answers: daily run time, HH:MM (default 09:00)")
    args = parser.parse_args()
    quiet = bool(args.answers)  # no-questions mode

    if args.uninstall:
        print(scheduler.uninstall())
        return 0

    print(f"\n{'=' * 60}\n  Automated customer follow-up emails: setup\n{'=' * 60}")

    from followup.gmail_client import CLIENT_SECRET_FILE
    if not CLIENT_SECRET_FILE.exists():
        print(f"\nThis install package is missing {CLIENT_SECRET_FILE.name}, so Gmail can't be connected.\n"
              f"Ask your installer for a new package (built with secrets/client_secret.json in place).")
        return 1

    # ---- Step 1: details
    step(1, "Business details")
    existing_ids = list_clients()  # sample "example..." folders are left out
    existing = load_config(existing_ids[0]) if existing_ids else None
    if quiet:
        answers = json.loads(open(args.answers, encoding="utf-8").read())
        answers = {k: str(v) for k, v in answers.items() if v is not None}
        answers.setdefault("from_name", answers.get("business_name", ""))
        answers.setdefault("timezone", detect_timezone())
        answers.setdefault("signature", f"{answers['from_name']}\n{answers.get('business_name', '')}")
        if existing:
            answers["client_id"] = existing.client_id  # update the same business, keep its data
        problems = check_answers(answers)
        if problems:
            print("Problems with the answers file:\n  - " + "\n  - ".join(problems))
            return 1
        print(f"Using answers from {args.answers}")
    elif existing:
        print(f"Already set up for: {existing.business_name}.")
        if not yes("Change the business details?", default=False):
            answers = None
        else:
            answers = ask_business_details(existing)
    else:
        answers = ask_business_details()

    # ---- Step 2: folder
    step(2, "Creating the business's folder")
    if answers:
        folder = create_client(answers, overwrite_config=True)
        client_id = folder.name
    else:
        client_id = existing.client_id
        folder = CLIENTS_DIR / client_id
    cfg = load_config(client_id)
    print(f"Folder: {folder}")
    print("  config.yaml   settings (you can edit it later)")
    print("  templates/    the 4 emails (edit the wording any time)")
    print("  jobs.csv      the jobs list. Set status to 'complete' to start the emails.")

    # ---- Step 3: Gmail
    step(3, "Connect Gmail")
    from followup.gmail_client import GmailNotConnected, connect, sign_in
    already_ok = False
    try:
        connect(cfg)
        already_ok = True
        print(f"Gmail is already connected ({cfg.from_email}).")
    except Exception:
        pass
    if not already_ok or (not quiet and yes("Reconnect Gmail anyway?", default=False)):
        print(f"A browser window will open. Sign in as {cfg.from_email} and click Allow.")
        print("If Google says 'Google hasn't verified this app', click Advanced, then 'Go to ...'.")
        if not quiet:
            input("Press Enter to open the browser...")
        while True:
            try:
                print(f"Connected: {sign_in(cfg)}", flush=True)
                break
            except GmailNotConnected as e:
                print(f"\n  ! {e}")
                if quiet or not yes("Try again?"):
                    print("Setup stopped. Run the installer again when ready.")
                    return 1

    # ---- Step 4: test email
    step(4, "Test email")
    if (args.test_to if quiet else yes("Send a test email to check how it looks?")):
        to = args.test_to if quiet else ask("Send it to", cfg.alert_email or cfg.from_email)
        from followup.templates import build_email
        sender, _ = connect(cfg)
        test_row = {"customer_name": "Test Customer", "customer_email": to,
                    "job_type": "kitchen remodel", "job_address": "12 Example St"}
        email = build_email(cfg, cfg.stages[0], test_row, date.today())
        email.subject = "[TEST] " + email.subject
        sender.send(cfg, email)
        print(f"Sent to {to}. Check that inbox (and the spam folder).")

    # ---- Step 5: schedule
    step(5, "Schedule the daily run")
    time_text = args.time if quiet else ask("What time should it run each day? (24-hour, HH:MM)", "09:00")
    try:
        hour, minute = (int(x) for x in time_text.split(":"))
        print(f"Scheduled: {scheduler.install(hour, minute)}")
        scheduler.run_now()  # one run right away, to prove the schedule works
        print(f"Ran it once now as a check. Output goes to {scheduler.LOG_FILE}")
    except Exception as e:
        print(f"  ! Couldn't schedule it automatically: {e}")

    # ---- Step 6: shortcut
    step(6, "Desktop shortcut")
    where = make_desktop_shortcut(cfg.jobs_path)
    print(f"Shortcut created: {where}" if where else f"Open the jobs list here: {cfg.jobs_path}")

    print(f"""
{'=' * 60}
  All set!
{'=' * 60}
How to use it:
  1. Open "Follow-up Jobs" on the desktop (opens in Excel / Numbers).
  2. Add a row for each job: name, email, job type, address.
  3. When a job is finished, set status to: complete
     (and the completion date, or leave it blank for today).
  4. SAVE IT AS CSV. If Excel asks, choose "Keep current format".
The emails then go out automatically, once a day. Customers who
reply or say STOP get no more emails.
""")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nSetup cancelled.")
        sys.exit(1)
