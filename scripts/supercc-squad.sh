#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCRIPT_PATH="$SCRIPT_DIR/supercc_squad.py"

if command -v python3 >/dev/null 2>&1; then
  exec python3 "$SCRIPT_PATH" "$@"
fi

if command -v python >/dev/null 2>&1; then
  exec python "$SCRIPT_PATH" "$@"
fi

if command -v python.exe >/dev/null 2>&1; then
  WIN_SCRIPT="$SCRIPT_PATH"
  if command -v wslpath >/dev/null 2>&1; then
    WIN_SCRIPT=$(wslpath -w "$SCRIPT_PATH")
  elif command -v cygpath >/dev/null 2>&1; then
    WIN_SCRIPT=$(cygpath -w "$SCRIPT_PATH")
  fi
  exec python.exe "$WIN_SCRIPT" "$@"
fi

if command -v py.exe >/dev/null 2>&1; then
  WIN_SCRIPT="$SCRIPT_PATH"
  if command -v wslpath >/dev/null 2>&1; then
    WIN_SCRIPT=$(wslpath -w "$SCRIPT_PATH")
  elif command -v cygpath >/dev/null 2>&1; then
    WIN_SCRIPT=$(cygpath -w "$SCRIPT_PATH")
  fi
  exec py.exe -3 "$WIN_SCRIPT" "$@"
fi

printf '%s\n' "supercc-squad.sh: python3/python is required to run supercc_squad.py" >&2
exit 127
