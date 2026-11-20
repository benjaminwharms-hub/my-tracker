"""Connect a business's Gmail account (do this once per client).

    python scripts/connect_gmail.py --client example_builder

What happens:
  1. A browser window opens on Google's sign-in page.
  2. The BUSINESS signs in with the Gmail account that will send the emails
     (the one in from_email in their config.yaml) and clicks Allow.
     (Done-for-you tip: do this together on a screen share, or have them sign
     in on your computer. You never need to see their password.)
  3. The token is saved to secrets/<client>/token.json (git ignores it).
  4. For GitHub Actions, copy that file's contents into a repository secret.
     This script prints the secret's name.

Needs secrets/client_secret.json first. The README explains how to get it.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so "import followup" works

from followup.config import load_config  # noqa: E402
from followup.gmail_client import (CLIENT_SECRET_FILE, SCOPES, build_service, connected_address,  # noqa: E402
                                   token_env_var, token_path)


def main():
    parser = argparse.ArgumentParser(description="Connect a client's Gmail account.")
    parser.add_argument("--client", required=True, help="client folder name, e.g. example_builder")
    parser.add_argument("--no-browser", action="store_true",
                        help="print the sign-in link instead of opening a browser")
    args = parser.parse_args()

    cfg = load_config(args.client)
    if not CLIENT_SECRET_FILE.exists():
        sys.exit(f"Missing {CLIENT_SECRET_FILE}. Create an OAuth client in Google Cloud first (see README).")

    from google_auth_oauthlib.flow import InstalledAppFlow

    print(f"Connecting Gmail for {cfg.business_name}. Sign in as: {cfg.from_email}")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
    # access_type=offline + prompt=consent make Google return a long-lived "refresh token",
    # so the daily run can keep working without anyone signing in again.
    creds = flow.run_local_server(port=0, open_browser=not args.no_browser,
                                  access_type="offline", prompt="consent",
                                  login_hint=cfg.from_email)

    actual = connected_address(build_service(creds))
    if actual != cfg.from_email.lower():
        sys.exit(f"You signed in as {actual}, but config.yaml says from_email: {cfg.from_email}. "
                 f"Nothing saved. Sign in with the right account, or fix the config.")

    path = token_path(args.client)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(creds.to_json(), encoding="utf-8")
    try:
        path.chmod(0o600)  # only your user account can read it (no effect on Windows)
    except OSError:
        pass

    print(f"\nConnected {actual}. Token saved to {path}")
    print(f"For GitHub Actions: add a repository secret named {token_env_var(args.client)} "
          f"and paste the whole contents of that file as its value.")
    print(f"Next, send yourself a test: python scripts/send_test_email.py --client {args.client} --to YOU@example.com")


if __name__ == "__main__":
    main()
