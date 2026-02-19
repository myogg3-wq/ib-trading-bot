#!/bin/bash
# ============================================
# Interactive .env Generator
# Run: bash scripts/generate_env.sh
# ============================================

set -e

ENV_FILE=".env"

echo "============================================"
echo "  IB Trading Bot — .env Setup"
echo "============================================"
echo ""

# Generate a random secret
RANDOM_SECRET=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))")

echo "This will create your .env file with all required settings."
echo ""

# --- IB Gateway ---
echo "--- IB Gateway ---"
read -p "IB Gateway Host [127.0.0.1]: " IB_HOST
IB_HOST=${IB_HOST:-127.0.0.1}

read -p "IB Gateway Port (4002=Paper, 4001=Live) [4002]: " IB_PORT
IB_PORT=${IB_PORT:-4002}

read -p "IB Client ID [1]: " IB_CLIENT_ID
IB_CLIENT_ID=${IB_CLIENT_ID:-1}

# --- Webhook ---
echo ""
echo "--- Webhook Security ---"
echo "Auto-generated secret: $RANDOM_SECRET"
read -p "Use this secret? (Y/n): " USE_RANDOM
if [[ "$USE_RANDOM" =~ ^[Nn] ]]; then
    read -p "Enter your webhook secret: " WEBHOOK_SECRET
else
    WEBHOOK_SECRET=$RANDOM_SECRET
fi

# --- Telegram ---
echo ""
echo "--- Telegram Bot ---"
echo "(Get these from @BotFather and @userinfobot on Telegram)"
read -p "Telegram Bot Token: " TELEGRAM_BOT_TOKEN
read -p "Telegram Chat ID: " TELEGRAM_CHAT_ID

# --- Database ---
echo ""
echo "--- Database ---"
DB_PASSWORD=$(openssl rand -hex 16 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(16))")
echo "Auto-generated DB password: $DB_PASSWORD"
read -p "Use this password? (Y/n): " USE_DB_PASS
if [[ "$USE_DB_PASS" =~ ^[Nn] ]]; then
    read -p "Enter DB password: " DB_PASSWORD
fi

# --- Trading Defaults ---
echo ""
echo "--- Trading Defaults ---"
read -p "Buy amount per order USD [300]: " BUY_AMOUNT
BUY_AMOUNT=${BUY_AMOUNT:-300}

read -p "Max open positions [200]: " MAX_POSITIONS
MAX_POSITIONS=${MAX_POSITIONS:-200}

read -p "Max daily buys [80]: " MAX_DAILY
MAX_DAILY=${MAX_DAILY:-80}

read -p "Max total investment USD [90000]: " MAX_INVEST
MAX_INVEST=${MAX_INVEST:-90000}

read -p "Max buys per ticker [5]: " MAX_PER_TICKER
MAX_PER_TICKER=${MAX_PER_TICKER:-5}

read -p "Max daily loss USD [5000]: " MAX_LOSS
MAX_LOSS=${MAX_LOSS:-5000}

read -p "Min cash reserve USD [1000]: " MIN_RESERVE
MIN_RESERVE=${MIN_RESERVE:-1000}

# --- Write .env ---
cat > "$ENV_FILE" << EOF
# ===========================================
# IB Trading Bot - Environment Configuration
# Generated on $(date)
# ===========================================

# === IB Gateway ===
IB_HOST=$IB_HOST
IB_PORT=$IB_PORT
IB_CLIENT_ID=$IB_CLIENT_ID

# === Webhook Security ===
WEBHOOK_SECRET=$WEBHOOK_SECRET
WEBHOOK_PORT=8000

# === Telegram Bot ===
TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID

# === Database ===
DATABASE_URL=postgresql+asyncpg://tradingbot:${DB_PASSWORD}@db:5432/tradingbot
POSTGRES_USER=tradingbot
POSTGRES_PASSWORD=$DB_PASSWORD
POSTGRES_DB=tradingbot

# === Redis ===
REDIS_URL=redis://redis:6379/0

# === Trading Defaults ===
DEFAULT_BUY_AMOUNT_USD=$BUY_AMOUNT
DEFAULT_MAX_OPEN_POSITIONS=$MAX_POSITIONS
DEFAULT_MAX_DAILY_BUYS=$MAX_DAILY
DEFAULT_MAX_TOTAL_INVESTMENT=$MAX_INVEST
DEFAULT_MAX_PER_TICKER=$MAX_PER_TICKER
DEFAULT_MAX_DAILY_LOSS=$MAX_LOSS
DEFAULT_MIN_CASH_RESERVE=$MIN_RESERVE
EOF

echo ""
echo "============================================"
echo "  .env file created successfully!"
echo "============================================"
echo ""
echo "Your webhook secret (save this for TradingView):"
echo "  $WEBHOOK_SECRET"
echo ""
echo "Next: docker compose up -d"
