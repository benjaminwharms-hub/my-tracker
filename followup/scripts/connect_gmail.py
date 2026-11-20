"""Connect (or reconnect) a business's Gmail account.

    python scripts/connect_gmail.py --client example_builder

The setup wizard does this for you. Use this script on its own to reconnect,
for example if the business changed its password or revoked access.

What happens:
  1. A browser window opens on Google's sign-in page.
  2. The BUSINESS signs in with the Gmail in from_email (config.yaml) and clicks Allow.
  3. The token is saved to secrets/<client>/token.json (git ignores it).

Needs secrets/client_secret.json first (see README, section 4).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so "import followup" works

from followup.config import load_config  # noqa: E402
from followup.gmail_client import GmailNotConnected, sign_in, token_env_var, token_path  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Connect a client's Gmail account.")
    parser.add_argument("--client", required=True, help="client folder name, e.g. example_builder")
    parser.add_argument("--no-browser", action="store_true",
                        help="print the sign-in link instead of opening a browser")
    args = parser.parse_args()

    cfg = load_config(args.client)
    print(f"Connecting Gmail for {cfg.business_name}. Sign in as: {cfg.from_email}")
    try:
        actual = sign_in(cfg, open_browser=not args.no_browser)
    except GmailNotConnected as e:
        sys.exit(str(e))

    print(f"\nConnected {actual}. Token saved to {token_path(args.client)}")
    print(f"(If you run this client from GitHub Actions instead, put that file's contents in a "
          f"repository secret named {token_env_var(args.client)}.)")
    print(f"Next, send yourself a test: python scripts/send_test_email.py --client {args.client} --to YOU@example.com")


if __name__ == "__main__":
    main()
