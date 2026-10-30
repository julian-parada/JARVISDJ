#!/usr/bin/env bash
# Instalador para Linux / macOS (en Windows usa instalar.bat)
set -euo pipefail
cd "$(dirname "$0")"

PY=""
for cand in python3.13 python3.12 python3.11 python3; do
  if command -v "$cand" >/dev/null && "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    PY="$cand"; break
  fi
done
[ -z "$PY" ] && { echo "[XX] Necesitas Python 3.11 o superior"; exit 1; }

[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -e . -q
.venv/bin/jarvis setup

echo
echo "Para hablar con JARVIS:  .venv/bin/jarvis chat"
