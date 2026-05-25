#!/bin/zsh
set -euo pipefail

ROOT="/Users/sehee/Desktop/SUB_Factory/Auto_Cash/ib-trading-bot"
HELPER="file://${ROOT}/output/oauth-setup-helper.html"
URLS=(
  "$HELPER"
  "https://console.cloud.google.com/apis/credentials"
)

for url in "${URLS[@]}"; do
  open -a Safari "$url"
  sleep 1
done

echo "Opened Signal Loom Google OAuth setup in Safari."
