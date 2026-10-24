#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.10+ is required. Install Python 3 and rerun this script." >&2
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[test]"

printf "\nRelqon setup completed.\n"
printf "Run: ./.venv/bin/relqon run .\n"
printf "Help: ./.venv/bin/relqon --help\n"
