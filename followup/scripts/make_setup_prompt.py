"""Make the prompt you paste into Claude on a client's computer.

    python scripts/make_setup_prompt.py --alert-email you@yourbusiness.com

Creates dist/claude_setup_prompt.txt. On the client's computer, open the
Claude desktop app's Code tab (Claude Code), choose any folder (e.g. the
home folder), paste the prompt, and follow along. Claude asks for the
business details, installs everything, connects Gmail (the business owner
signs in), and then asks for the customer list file.

The prompt contains your Google OAuth client (client_secret.json). For
"Desktop app" clients Google doesn't treat this as truly secret: it
identifies your app and gives no access to any mailbox. Still, keep the
prompt to yourself, and NEVER commit it to this public repo. dist/ is
git-ignored.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
TEMPLATE = APP_DIR / "prompts" / "claude_setup_prompt.md"
CLIENT_SECRET = APP_DIR / "secrets" / "client_secret.json"
REPO = "benjaminwharms-hub/my-tracker"


def default_source_url() -> str:
    """A zip of this repo's current branch on GitHub (it must be pushed). Falls back to main."""
    try:
        branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=APP_DIR,
                                capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        branch = "main"
    if branch in ("", "HEAD"):
        branch = "main"
    return f"https://github.com/{REPO}/archive/refs/heads/{branch}.zip"


def build_prompt(client_secret: dict, alert_email: str, source_url: str) -> str:
    if "installed" not in client_secret:
        raise ValueError("client_secret.json isn't a 'Desktop app' OAuth client. Create one of type "
                         "Desktop app in Google Cloud (README section 4).")
    text = TEMPLATE.read_text(encoding="utf-8")
    return (text.replace("{{CLIENT_SECRET_JSON}}", json.dumps(client_secret, separators=(",", ":")))
                .replace("{{ALERT_EMAIL}}", alert_email)
                .replace("{{SOURCE_URL}}", source_url))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Make the Claude setup prompt for client computers.")
    parser.add_argument("--alert-email", required=True, help="your email: gets the test email and problem alerts")
    parser.add_argument("--source-url", default=None, help="zip to download the program from (default: this branch on GitHub)")
    parser.add_argument("--out", default=str(APP_DIR / "dist" / "claude_setup_prompt.txt"))
    args = parser.parse_args(argv)

    if not CLIENT_SECRET.exists():
        print(f"Missing {CLIENT_SECRET}. Download your OAuth client JSON from Google Cloud first (README section 4).")
        return 1
    try:
        prompt = build_prompt(json.loads(CLIENT_SECRET.read_text(encoding="utf-8")), args.alert_email,
                              args.source_url or default_source_url())
    except ValueError as e:
        print(e)
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(prompt, encoding="utf-8")
    print(f"Wrote {out}")
    print("Paste its whole contents into the Claude desktop app's Code tab on the client's computer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
