#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${TRADING_BOT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RUNNER="$ROOT/scripts/run_trading_runtime_watch.sh"
BEGIN_MARK="# BEGIN AUTO_CASH_RUNTIME_WATCH"
END_MARK="# END AUTO_CASH_RUNTIME_WATCH"

chmod +x "$RUNNER"
mkdir -p "$ROOT/runtime"

existing="$(crontab -l 2>/dev/null || true)"
cleaned="$(
  printf '%s\n' "$existing" \
    | awk -v begin="$BEGIN_MARK" -v end="$END_MARK" '
        $0 == begin {skip=1; next}
        $0 == end {skip=0; next}
        !skip {print}
      ' \
    | grep -vE 'scripts/(trading_runtime_watch\.py|run_trading_runtime_watch\.sh)' \
    || true
)"

{
  if [ -n "$(printf '%s' "$cleaned" | tr -d '[:space:]')" ]; then
    printf '%s\n' "$cleaned"
  fi
  cat <<CRON
$BEGIN_MARK
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Quiet daily pre-check before the Korean morning.
CRON_TZ=Asia/Seoul
0 7 * * * "$RUNNER" daily_kst

# KRX checks: open +10m, 4h-strategy midpoint, close +20m.
CRON_TZ=Asia/Seoul
10 9 * * 1-5 "$RUNNER" krx_open_plus_10
10 13 * * 1-5 "$RUNNER" krx_midday
50 15 * * 1-5 "$RUNNER" krx_close_plus_20

# US checks: open +10m, 4h-strategy midpoint, close +20m.
CRON_TZ=America/New_York
40 9 * * 1-5 "$RUNNER" us_open_plus_10
40 13 * * 1-5 "$RUNNER" us_midday
20 16 * * 1-5 "$RUNNER" us_close_plus_20

CRON_TZ=Asia/Seoul
$END_MARK
CRON
} | crontab -

echo "Installed trading runtime watch cron entries."
crontab -l
