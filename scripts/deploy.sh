#!/bin/bash
# ============================================
# ONE-CLICK FULL DEPLOYMENT SCRIPT
# This is the ONLY script you need to run on VPS.
# It does everything: setup, install, configure, start.
#
# Usage:
#   1. SSH into your VPS
#   2. git clone your-repo (or scp files)
#   3. cd ib-trading-bot
#   4. bash scripts/deploy.sh
# ============================================

set -e

echo "╔══════════════════════════════════════════════╗"
echo "║   IB Trading Bot — Full Deployment           ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# --- Check if .env exists ---
if [ ! -f ".env" ]; then
    echo ">>> No .env file found. Running setup wizard..."
    bash scripts/generate_env.sh
    echo ""
fi

# --- 1. System setup ---
echo "━━━ Step 1/6: System Setup ━━━"
sudo apt-get update -qq
sudo apt-get install -y -qq docker.io docker-compose-plugin curl wget unzip default-jre xvfb

# Ensure Docker is running
sudo systemctl enable docker
sudo systemctl start docker

# Add current user to docker group
sudo usermod -aG docker $USER 2>/dev/null || true

echo "✓ System packages installed"

# --- 2. Firewall ---
echo ""
echo "━━━ Step 2/6: Firewall ━━━"
sudo ufw allow 22/tcp 2>/dev/null || true
sudo ufw allow 80/tcp 2>/dev/null || true
sudo ufw allow 443/tcp 2>/dev/null || true
sudo ufw --force enable 2>/dev/null || true
echo "✓ Firewall configured"

# --- 3. Swap (if not exists) ---
echo ""
echo "━━━ Step 3/6: Swap ━━━"
if [ ! -f /swapfile ]; then
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo "✓ 2GB swap created"
else
    echo "✓ Swap already exists"
fi

# --- 4. IB Gateway + IBC ---
echo ""
echo "━━━ Step 4/6: IB Gateway ━━━"
if [ ! -d "$HOME/ibc" ]; then
    echo "Installing IB Gateway + IBC..."
    bash scripts/setup_ib_gateway.sh
else
    echo "✓ IB Gateway already installed"
fi

# --- 5. Docker services ---
echo ""
echo "━━━ Step 5/6: Docker Services ━━━"
echo "Building and starting containers..."

# Use sudo if user isn't in docker group yet
if groups | grep -q docker; then
    docker compose build
    docker compose up -d
else
    sudo docker compose build
    sudo docker compose up -d
fi

echo "✓ Docker services started"

# --- 6. Status check ---
echo ""
echo "━━━ Step 6/6: Status Check ━━━"
sleep 5  # Wait for services to start

echo ""
echo "Docker containers:"
if groups | grep -q docker; then
    docker compose ps
else
    sudo docker compose ps
fi

echo ""

# Health check
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo "✓ API server is healthy"
else
    echo "⚠ API server not responding yet (may still be starting)"
fi

# --- Done ---
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║          DEPLOYMENT COMPLETE!                 ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "Remaining manual steps:"
echo ""
echo "  1. IB Gateway login:"
echo "     - Edit ~/ibc/config.ini (set username/password)"
echo "     - sudo systemctl start ib-gateway"
echo ""
echo "  2. SSL setup (if you have a domain):"
echo "     bash scripts/setup_ssl.sh your_domain.com"
echo ""
echo "  3. TradingView:"
echo "     - Set webhook URL: https://your_domain.com/webhook"
echo "     - Set alert message (see SETUP_GUIDE.md)"
echo ""
echo "  4. Test:"
echo "     curl -X POST http://localhost:8000/webhook \\"
echo "       -H 'Content-Type: application/json' \\"
echo "       -d '{\"secret\":\"YOUR_SECRET\",\"action\":\"BUY\",\"ticker\":\"AAPL\"}'"
echo ""
echo "  5. Check Telegram bot: send /help to your bot"
echo ""
echo "  Logs: docker compose logs -f"
echo "  Stop: docker compose down"
echo ""
