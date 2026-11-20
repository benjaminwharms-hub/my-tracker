"""Gmail: OAuth login, sending, and checking for replies or STOP.

HOW THE LOGIN WORKS (OAuth)
  - You (the operator) create ONE Google Cloud "OAuth client" and save its
    file as secrets/client_secret.json. The README shows how.
  - Each business connects its own Gmail once, with
    scripts/connect_gmail.py. That saves a token for that business only.
  - The token is the key to their mailbox, so treat it like a password. It is
    never put in the code or committed to git. It lives in:
        locally:          secrets/<client_id>/token.json
        GitHub Actions:   a secret named GMAIL_TOKEN_<CLIENT_ID>, e.g.
                          GMAIL_TOKEN_EXAMPLE_BUILDER, holding the same JSON

PERMISSIONS ASKED FOR ("scopes")
  gmail.send      send email as the business
  gmail.readonly  search the inbox for customer replies and STOP messages
"""

import base64
import json
import os
import re
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

SECRETS_DIR = Path(__file__).resolve().parent.parent / "secrets"
CLIENT_SECRET_FILE = SECRETS_DIR / "client_secret.json"

# Words that mean "stop emailing me", as opposed to an ordinary reply.
UNSUBSCRIBE_RE = re.compile(r"\b(unsubscribe|opt[ -]?out|remove me|take me off|no more emails)\b", re.I)
STOP_FIRST_WORD_RE = re.compile(r"^\W*stop\b", re.I)  # a reply that starts with "STOP"

# Out-of-office and other automatic replies should NOT stop the sequence.
AUTO_REPLY_SUBJECT_RE = re.compile(r"^(automatic reply|auto[- ]?reply|out of (the )?office|ooo\b)", re.I)


class GmailNotConnected(Exception):
    """No token, or the token stopped working. The fix is to run scripts/connect_gmail.py."""


def token_env_var(client_id: str) -> str:
    """The name of the GitHub secret / environment variable that holds a client's token."""
    return "GMAIL_TOKEN_" + re.sub(r"[^A-Za-z0-9]", "_", client_id).upper()


def token_path(client_id: str) -> Path:
    return SECRETS_DIR / client_id / "token.json"


# ---------------------------------------------------------------- connecting

def load_credentials(client_id: str):
    """Find this client's saved token (environment variable first, then the local file)."""
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    env_name = token_env_var(client_id)
    path = token_path(client_id)
    if os.environ.get(env_name):
        info, source = json.loads(os.environ[env_name]), f"${env_name}"
    elif path.exists():
        info, source = json.loads(path.read_text(encoding="utf-8")), str(path)
    else:
        raise GmailNotConnected(f"No Gmail token for '{client_id}'. Run: "
                                f"python scripts/connect_gmail.py --client {client_id}")

    creds = Credentials.from_authorized_user_info(info, SCOPES)
    if not creds.valid:
        try:
            creds.refresh(Request())  # get a fresh short-lived access token
        except RefreshError as e:
            raise GmailNotConnected(
                f"The Gmail token for '{client_id}' (from {source}) no longer works ({e}). "
                f"The business may have revoked access, or the app is in Testing mode (tokens "
                f"expire after 7 days). Reconnect: python scripts/connect_gmail.py --client {client_id}")
        if source == str(path):  # keep the local file up to date
            path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def build_service(creds):
    from googleapiclient.discovery import build
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def connected_address(service) -> str:
    """The email address of the Gmail account we're logged into."""
    return service.users().getProfile(userId="me").execute(num_retries=3)["emailAddress"].lower()


def sign_in(cfg, open_browser: bool = True) -> str:
    """Open Google's sign-in page, and save the token if the right account signed in.

    Used by scripts/connect_gmail.py and the setup wizard. Returns the connected address.
    """
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CLIENT_SECRET_FILE.exists():
        raise GmailNotConnected(f"Missing {CLIENT_SECRET_FILE}. Create an OAuth client in "
                                f"Google Cloud first (see README, section 4).")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
    # access_type=offline + prompt=consent make Google return a long-lived "refresh token",
    # so the daily run keeps working without anyone signing in again.
    creds = flow.run_local_server(port=0, open_browser=open_browser, access_type="offline",
                                  prompt="consent", login_hint=cfg.from_email)

    actual = connected_address(build_service(creds))
    if actual != cfg.from_email.lower():
        raise GmailNotConnected(f"You signed in as {actual}, but the business's email is set to "
                                f"{cfg.from_email}. Nothing was saved. Sign in with the right account.")

    path = token_path(cfg.client_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(creds.to_json(), encoding="utf-8")
    try:
        path.chmod(0o600)  # only this user account can read it (no effect on Windows)
    except OSError:
        pass
    return actual


def connect(cfg, service=None):
    """Return (sender, inbox) for a client's Gmail. Called by run.py for real runs.

    Safety check: the connected account must match from_email in config.yaml,
    so one business's emails can never go out from another business's Gmail.
    """
    if service is None:
        service = build_service(load_credentials(cfg.client_id))
    actual = connected_address(service)
    if actual != cfg.from_email.lower():
        raise GmailNotConnected(f"Connected Gmail is {actual}, but config.yaml says from_email: "
                                f"{cfg.from_email}. Fix the config or reconnect the right account.")
    return GmailSender(service), GmailInbox(service, own_address=actual)


# ---------------------------------------------------------------- sending

def make_mime(cfg, email) -> EmailMessage:
    """Turn our Email (to/subject/body) into a real email message."""
    msg = EmailMessage()
    msg["From"] = formataddr((cfg.from_name, cfg.from_email))
    msg["To"] = email.to
    msg["Subject"] = email.subject
    # Gmail and other mail apps show their own "Unsubscribe" button for this
    # header. Clicking it sends us an email with subject "unsubscribe", which
    # GmailInbox spots on the next run.
    msg["List-Unsubscribe"] = f"<mailto:{cfg.from_email}?subject=unsubscribe>"
    msg.set_content(email.body)
    return msg


class GmailSender:
    def __init__(self, service):
        self.service = service

    def send(self, cfg, email) -> str:
        raw = base64.urlsafe_b64encode(make_mime(cfg, email).as_bytes()).decode()
        result = self.service.users().messages().send(userId="me", body={"raw": raw}).execute(num_retries=3)
        return result["id"]


# ---------------------------------------------------------------- replies / STOP

class GmailInbox:
    def __init__(self, service, own_address=""):
        self.service = service
        self.own_address = own_address

    def check_stop(self, customer_email: str, since_date: str):
        """Look for any email FROM the customer on or after since_date (YYYY-MM-DD).

        Returns "unsubscribed", "replied", or None (no reply found).
        Automatic replies (out-of-office) are ignored. Spam and trash are
        searched too, so a STOP can't be missed because it was filed away.
        """
        query = f"from:{customer_email} after:{since_date.replace('-', '/')} in:anywhere"
        messages = self.service.users().messages()
        found = messages.list(userId="me", q=query, maxResults=20).execute(num_retries=3).get("messages", [])

        result = None
        for m in found:
            msg = messages.get(userId="me", id=m["id"], format="metadata",
                               metadataHeaders=["Subject", "Auto-Submitted", "X-Autoreply", "Precedence"]
                               ).execute(num_retries=3)
            headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
            if _is_auto_reply(headers):
                continue
            text = headers.get("subject", "") + "\n" + msg.get("snippet", "")
            if UNSUBSCRIBE_RE.search(text) or STOP_FIRST_WORD_RE.search(msg.get("snippet", "")) \
                    or STOP_FIRST_WORD_RE.search(headers.get("subject", "")):
                return "unsubscribed"  # strongest answer, so stop looking
            result = "replied"
        return result


def _is_auto_reply(headers: dict) -> bool:
    auto = headers.get("auto-submitted", "no").lower()
    if auto and auto != "no":
        return True
    if "x-autoreply" in headers or headers.get("precedence", "").lower() in ("auto_reply", "bulk", "junk"):
        return True
    return bool(AUTO_REPLY_SUBJECT_RE.search(headers.get("subject", "")))
