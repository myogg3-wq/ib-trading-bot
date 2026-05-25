#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${TRADING_BOT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
LABEL="${1:-scheduled}"
RUNTIME_DIR="$ROOT/runtime"
LOG_FILE="$RUNTIME_DIR/trading_runtime_watch.log"
LOCK_FILE="$RUNTIME_DIR/trading_runtime_watch.lock"

mkdir -p "$RUNTIME_DIR"
exec 9>"$LOCK_FILE"

if command -v flock >/dev/null 2>&1; then
  if ! flock -n 9; then
    printf '[%s] skip: previous watch still running (%s)\n' "$(date -Is)" "$LABEL" >> "$LOG_FILE"
    exit 0
  fi
fi

{
  printf '\n[%s] trading runtime watch start (%s)\n' "$(date -Is)" "$LABEL"
  cd "$ROOT"
  python3 scripts/trading_runtime_watch.py
  rc=$?
  printf '[%s] trading runtime watch end (%s) rc=%s\n' "$(date -Is)" "$LABEL" "$rc"
  exit "$rc"
} >> "$LOG_FILE" 2>&1
