#!/usr/bin/env bash
set -euo pipefail

action="${1:?Usage: invoke-project-action.sh ACTION}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/../.." && pwd)"
cd "$project_root"

python_command=""
for candidate in .venv/bin/python venv/bin/python; do
    if [[ -x "$candidate" ]] && "$candidate" -c 'import sys' >/dev/null 2>&1; then
        python_command="$candidate"
        break
    fi
done

if [[ -z "$python_command" ]]; then
    if [[ -n "${SWANE_PYTHON:-}" ]]; then
        base_python="$SWANE_PYTHON"
    elif command -v python3 >/dev/null 2>&1; then
        base_python="$(command -v python3)"
    elif command -v python >/dev/null 2>&1; then
        base_python="$(command -v python)"
    else
        echo "A supported Python 3 interpreter was not found. Set SWANE_PYTHON or install Python." >&2
        exit 1
    fi

    "$base_python" -m venv .venv
    python_command=".venv/bin/python"
fi

exec "$python_command" .codex/scripts/project_actions.py "$action"
