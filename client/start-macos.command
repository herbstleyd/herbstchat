#!/usr/bin/env bash
# Herbstchat starten (Linux) - legt beim ersten Start eine virtuelle Umgebung an
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Erster Start: richte Python-Umgebung ein ..."
  python3 -m venv .venv || { echo "Bitte python3-venv installieren (z.B. sudo apt install python3-venv)"; exit 1; }
  .venv/bin/pip install --upgrade pip >/dev/null
  .venv/bin/pip install -r requirements.txt
fi
exec .venv/bin/python herbstchat.py "$@"
