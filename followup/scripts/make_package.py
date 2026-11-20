"""Build the zip you put on a client's computer.

    python scripts/make_package.py

Creates dist/FollowupEmails-installer.zip containing:
    Install (Windows).bat, Install (Mac).command, READ ME FIRST.txt
    the program (run.py, setup_wizard.py, followup/, scripts/)
    starter_templates/       the default construction-company emails
    secrets/client_secret.json   YOUR Google OAuth client, so the business can sign in

Left out on purpose: tests, every client folder (other businesses' customer
data), and every Gmail token.

About client_secret.json: for "Desktop app" OAuth clients, Google treats this
file as not truly secret. It identifies your app; it gives no access to any
mailbox. Still, don't post it publicly.
"""

import argparse
import sys
import zipfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
DIST = APP_DIR / "dist"

PROGRAM_FILES = ["run.py", "setup_wizard.py", "requirements.txt", "README.md"]
PROGRAM_DIRS = ["followup", "scripts"]
STARTER = APP_DIR / "clients" / "example_builder" / "templates"
CLIENT_SECRET = APP_DIR / "secrets" / "client_secret.json"
INSTALLERS = APP_DIR / "installers"


def collect(allow_missing_secret: bool = False) -> list:
    """Return a list of (path inside the zip, source file) pairs."""
    items = [(name, APP_DIR / name) for name in PROGRAM_FILES]
    for d in PROGRAM_DIRS:
        for f in sorted((APP_DIR / d).rglob("*.py")):
            items.append((f.relative_to(APP_DIR).as_posix(), f))
    for f in sorted(STARTER.glob("*.txt")):
        items.append((f"starter_templates/{f.name}", f))
    for f in sorted(INSTALLERS.iterdir()):
        items.append((f.name, f))

    if CLIENT_SECRET.exists():
        items.append(("secrets/client_secret.json", CLIENT_SECRET))
    elif not allow_missing_secret:
        sys.exit(f"Missing {CLIENT_SECRET}. Download your OAuth client JSON from Google Cloud first "
                 f"(README section 4). Use --allow-missing-secret to build a test package anyway.")
    return items


def build(out: Path, allow_missing_secret: bool = False) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for arcname, src in collect(allow_missing_secret):
            data = src.read_bytes()
            if arcname.endswith(".bat"):
                # Windows batch files need Windows line endings (CRLF).
                data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            info = zipfile.ZipInfo(f"FollowupEmails/{arcname}")
            info.compress_type = zipfile.ZIP_DEFLATED
            # Mark the Mac installer as runnable (rwxr-xr-x), everything else rw-r--r--.
            mode = 0o755 if arcname.endswith(".command") else 0o644
            info.external_attr = (0o100000 | mode) << 16
            z.writestr(info, data)
    return out


def main():
    parser = argparse.ArgumentParser(description="Build the client installer zip.")
    parser.add_argument("--out", default=str(DIST / "FollowupEmails-installer.zip"))
    parser.add_argument("--allow-missing-secret", action="store_true",
                        help="build without secrets/client_secret.json (for testing only)")
    args = parser.parse_args()
    path = build(Path(args.out), args.allow_missing_secret)
    print(f"Built {path}")
    print("Copy it to the client's computer (USB stick, email or cloud drive), unzip it, "
          "and double-click the installer.")


if __name__ == "__main__":
    main()
