#!/bin/bash
# ==================================================================
#  Automated follow-up emails: Mac installer
#  Double-click this file. If macOS says it "can't be opened", right-click
#  it, choose Open, then click Open again.
#  It will:
#    1. check that Python 3.10+ is installed
#    2. copy the program to ~/FollowupEmails (macOS blocks background jobs
#       from reading Desktop/Documents/Downloads, so it can't stay there)
#    3. install the Python packages it needs
#    4. start the setup wizard
#  Running it again later is safe: it updates the program and keeps the
#  business's jobs list, settings and Gmail connection.
# ==================================================================
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/FollowupEmails"

echo "Checking for Python..."
PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 \
                 /Library/Frameworks/Python.framework/Versions/3.*/bin/python3 \
                 /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && \
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done

if [ -z "$PY" ]; then
  echo
  echo "Python 3.10 or newer is needed."
  echo "Your browser will open the download page: download the macOS installer, run it,"
  echo "then double-click this installer again."
  open "https://www.python.org/downloads/macos/"
  read -r -p "Press Enter to close..."
  exit 1
fi
echo "Using $("$PY" --version)"

echo "Copying program files to $DEST ..."
mkdir -p "$DEST"
if [ "$SRC" != "$DEST" ]; then
  # Copy everything except the Python environment and logs (keeps existing data in DEST).
  (cd "$SRC" && tar cf - --exclude ".venv" --exclude "logs" .) | (cd "$DEST" && tar xf -)
fi
cd "$DEST"

if [ ! -x ".venv/bin/python" ]; then
  echo "Creating a private Python environment..."
  "$PY" -m venv .venv
fi

echo "Installing packages (first time takes a minute)..."
.venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt

.venv/bin/python setup_wizard.py || true
read -r -p "Press Enter to close..."
