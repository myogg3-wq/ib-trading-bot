# 🚀 IB Trading Bot - Deployment Guide

Complete step-by-step guide for deploying the IB Trading Bot.

## Prerequisites

- Python 3.9+
- PostgreSQL 12+
- Redis 6+
- IB Gateway running (paper or live)
- Telegram Bot token (from @BotFather)
- TradingView account with alerts configured

---

## 1. Local Development Setup

### 1.1 Clone & Install

```bash
cd ib-trading-bot
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 1.2 Configure Environment

```bash
cp .env.example .env
# Edit .env with your values:
nano .env
```

**Required values:**
- `IB_HOST`, `IB_PORT`, `IB_CLIENT_ID` - IB Gateway connection
- `WEBHOOK_SECRET` - Strong random secret
- `TELEGRAM_BOT_TOKEN` - Get from @BotFather
- `TELEGRAM_CHAT_ID` - Your Telegram chat ID
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string

### 1.3 Start Services

**Terminal 1 - Database & Cache:**
```bash
# Option A: Docker (recommended)
docker-compose up -d postgres redis

# Option B: Manual
postgres -D /usr/local/var/postgres
redis-server
```

**Terminal 2 - Initialize & Test:**
```bash
python scripts/init_all.py
```

This will:
- ✅ Create database tables
- ✅ Seed default settings
- ✅ Test PostgreSQL connection
- ✅ Test Redis connection
- ✅ Test IB Gateway connection
- ✅ Verify Telegram configuration

**Terminal 3 - Start API Server:**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Expected output:
```
INFO:     Application startup complete
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Terminal 4 - Start Order Worker:**
```bash
python app/queue/order_worker.py
```

Expected output:
```
2024-01-15 09:30:00 Order worker starting...
2024-01-15 09:30:01 Worker connected to IB Gateway
```

**Terminal 5 - Start Telegram Bot:**
```bash
python app/notifications/telegram_bot.py
```

Expected output:
```
2024-01-15 09:30:00 Telegram bot started
2024-01-15 09:30:00 🤖 Telegram bot started. Type /help for commands.
```

### 1.4 Test the Bot

In Telegram:
```
/start        # Show welcome & all commands
/status       # Show bot status
/settings     # View current settings
/market       # Check market hours
```

---

## 2. Production Deployment (Docker)

### 2.1 Prepare for Docker

```bash
# Create .env file (copy from .env.example)
cp .env.example .env
nano .env

# Make sure DATABASE_URL points to docker postgres service:
# DATABASE_URL=postgresql+asyncpg://tradingbot:password@postgres:5432/tradingbot
# REDIS_URL=redis://redis:6379/0
```

### 2.2 Build & Run with Docker Compose

```bash
# Start all services (postgres, redis, bot)
docker-compose up -d

# Check logs
docker-compose logs -f

# Stop all services
docker-compose down
```

Services will start:
- **postgres** - Port 5432
- **redis** - Port 6379
- **api** - Port 8000 (FastAPI webhook server)
- **worker** - Order processing
- **telegram** - Telegram bot

### 2.3 Verify Deployment

```bash
# Check if API is responding
curl http://localhost:8000/health

# Expected response:
# {
#   "status": "healthy",
#   "service": "ib-trading-bot",
#   "timestamp": "2024-01-15T09:30:00"
# }

# Check Docker logs
docker-compose logs api
docker-compose logs worker
docker-compose logs telegram
```

---

## 3. VPS Deployment (Ubuntu/Debian)

### 3.1 Server Setup

```bash
# SSH into VPS
ssh root@your.vps.ip

# Update system
apt update && apt upgrade -y

# Install dependencies
apt install -y python3.11 python3.11-venv postgresql postgresql-contrib redis-server nginx

# Create bot user
useradd -m -s /bin/bash tradingbot
su - tradingbot
```

### 3.2 Deploy Bot

```bash
# Clone repository
git clone https://github.com/yourusername/ib-trading-bot.git
cd ib-trading-bot

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Configure environment
cp .env.example .env
nano .env
```

### 3.3 Create Systemd Services

Create `/etc/systemd/system/ib-bot-api.service`:
```ini
[Unit]
Description=IB Trading Bot API Server
After=network.target postgresql.service redis-server.service

[Service]
Type=simple
User=tradingbot
WorkingDirectory=/home/tradingbot/ib-trading-bot
Environment="PATH=/home/tradingbot/ib-trading-bot/venv/bin"
ExecStart=/home/tradingbot/ib-trading-bot/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/ib-bot-worker.service`:
```ini
[Unit]
Description=IB Trading Bot Order Worker
After=network.target postgresql.service redis-server.service

[Service]
Type=simple
User=tradingbot
WorkingDirectory=/home/tradingbot/ib-trading-bot
Environment="PATH=/home/tradingbot/ib-trading-bot/venv/bin"
ExecStart=/home/tradingbot/ib-trading-bot/venv/bin/python app/queue/order_worker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/ib-bot-telegram.service`:
```ini
[Unit]
Description=IB Trading Bot Telegram Bot
After=network.target postgresql.service redis-server.service

[Service]
Type=simple
User=tradingbot
WorkingDirectory=/home/tradingbot/ib-trading-bot
Environment="PATH=/home/tradingbot/ib-trading-bot/venv/bin"
ExecStart=/home/tradingbot/ib-trading-bot/venv/bin/python app/notifications/telegram_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 3.4 Start Services

```bash
sudo systemctl daemon-reload
sudo systemctl enable ib-bot-api ib-bot-worker ib-bot-telegram
sudo systemctl start ib-bot-api ib-bot-worker ib-bot-telegram

# Check status
sudo systemctl status ib-bot-api
sudo systemctl status ib-bot-worker
sudo systemctl status ib-bot-telegram

# View logs
sudo journalctl -u ib-bot-api -f
sudo journalctl -u ib-bot-worker -f
sudo journalctl -u ib-bot-telegram -f
```

### 3.5 Configure Nginx Reverse Proxy

Create `/etc/nginx/sites-available/ib-trading-bot`:
```nginx
server {
    listen 80;
    server_name your.domain.com;

    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your.domain.com;

    # SSL certificates (get from Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/your.domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your.domain.com/privkey.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /health {
        access_log off;
        proxy_pass http://localhost:8000/health;
    }
}
```

Enable and restart Nginx:
```bash
sudo ln -s /etc/nginx/sites-available/ib-trading-bot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 3.6 Setup SSL Certificate

```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Get certificate
sudo certbot certonly --nginx -d your.domain.com

# Auto-renewal
sudo systemctl enable certbot.timer
```

---

## 4. TradingView Integration

### 4.1 Setup Alert Webhook

In TradingView Alert Template:
```json
{
    "secret": "{{YOUR_WEBHOOK_SECRET}}",
    "action": "{{ACTION}}",
    "ticker": "{{SYMBOL}}",
    "price": "{{CLOSE}}",
    "time": "{{timenow}}"
}
```

### 4.2 Configure Alert

1. Go to TradingView indicator
2. Click "Create Alert"
3. Set conditions (e.g., "close crosses above moving average")
4. Webhook URL: `https://your.domain.com/webhook` (or `http://localhost:8000/webhook` for testing)
5. Message: (paste the JSON template above with `ACTION` replaced by `BUY` or `SELL`)
6. Enable "Repeat alerts every 5 minutes" (optional, depends on strategy)
7. Create

---

## 5. Monitoring & Maintenance

### 5.1 Check Bot Status

In Telegram:
```
/status    # Current bot status
/positions # All open positions
/pnl       # Today's P&L
/queue     # Order queue status
```

### 5.2 View Logs

```bash
# API logs
docker-compose logs api -f

# Worker logs
docker-compose logs worker -f

# Telegram logs
docker-compose logs telegram -f

# Or on VPS:
sudo journalctl -u ib-bot-api -f
sudo journalctl -u ib-bot-worker -f
sudo journalctl -u ib-bot-telegram -f
```

### 5.3 Database Backup

```bash
# Backup PostgreSQL
pg_dump tradingbot > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore
psql tradingbot < backup_2024-01-15_093000.sql
```

### 5.4 Emergency Commands

In Telegram:
```
/kill        # Emergency stop ALL trading
/pause       # Pause buying (sells still work)
/resume      # Resume trading
/sell_all    # Sell ALL positions immediately
/clear_queue # Clear pending orders
```

---

## 6. Troubleshooting

### API not responding
```bash
# Check if service is running
curl http://localhost:8000/health

# Restart service
docker-compose restart api
# or on VPS:
sudo systemctl restart ib-bot-api

# Check logs
docker-compose logs api
```

### IB Gateway disconnected
```bash
# Check IB connection status in Telegram
/status

# IB will auto-reconnect with exponential backoff
# Check logs for reconnect attempts
docker-compose logs worker | grep "Reconnection"
```

### Orders not processing
```bash
# Check order queue
/queue

# Verify worker is running
docker-compose ps
# or
sudo systemctl status ib-bot-worker

# Check for risk blocks
/status
```

### Database errors
```bash
# Check PostgreSQL is running
docker-compose ps

# Verify connection string in .env
# DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db

# Check logs
docker-compose logs postgres
```

### Telegram bot not responding
```bash
# Verify token in .env
TELEGRAM_BOT_TOKEN=

# Verify chat ID in .env
TELEGRAM_CHAT_ID=

# Restart bot
docker-compose restart telegram
# or
sudo systemctl restart ib-bot-telegram

# Check logs
docker-compose logs telegram
```

---

## 7. Security Checklist

- [ ] Change `WEBHOOK_SECRET` to a strong random value
- [ ] Use HTTPS in production (SSL certificate from Let's Encrypt)
- [ ] Restrict PostgreSQL to localhost only
- [ ] Use strong PostgreSQL password
- [ ] Enable firewall (ufw on Ubuntu)
- [ ] Configure VPS security group / network rules
- [ ] Keep dependencies updated (`pip install --upgrade -r requirements.txt`)
- [ ] Rotate Telegram bot token if exposed
- [ ] Monitor IB account for unauthorized access
- [ ] Enable 2FA on all accounts
- [ ] Regular database backups (daily)
- [ ] Monitor VPS disk space and CPU usage

---

## 8. Performance Tuning

### PostgreSQL
```sql
-- Increase max connections
ALTER SYSTEM SET max_connections = 100;

-- Increase shared_buffers (25% of RAM)
ALTER SYSTEM SET shared_buffers = '2GB';

-- Increase effective_cache_size (50-75% of RAM)
ALTER SYSTEM SET effective_cache_size = '6GB';

-- Checkpoint
SELECT pg_reload_conf();
```

### Redis
```bash
# Increase maxmemory
redis-cli CONFIG SET maxmemory 2gb
redis-cli CONFIG SET maxmemory-policy allkeys-lru
redis-cli CONFIG REWRITE
```

---

## 9. Support & Debugging

### Collect Debug Info

```bash
# Save full logs
docker-compose logs > debug_logs.txt

# Database schema
pg_dump --schema-only tradingbot > schema.sql

# Current settings
# In Telegram: /settings

# Save to file for analysis
curl http://localhost:8000/health > status.json
```

### Get Help

- Review `SETUP_GUIDE.md` for additional details
- Check TradingView alert template: `scripts/tradingview_alert_template.md`
- Run initialization script: `python scripts/init_all.py`

---

## 10. Rollback / Downgrade

```bash
# Stop all services
docker-compose down

# Or on VPS
sudo systemctl stop ib-bot-api ib-bot-worker ib-bot-telegram

# Restore database backup
psql tradingbot < backup_2024-01-15_093000.sql

# Checkout previous version
git checkout v1.0.0

# Restart
docker-compose up -d
# or
sudo systemctl start ib-bot-api ib-bot-worker ib-bot-telegram
```

---

## Summary

Your bot is now deployed! 🚀

**Key services:**
- ✅ FastAPI webhook server (port 8000)
- ✅ Order worker (async queue processor)
- ✅ Telegram bot (real-time controls & monitoring)
- ✅ PostgreSQL (position & trade history)
- ✅ Redis (order queue)

**Monitor via Telegram:**
```
/status     # Bot status & risk summary
/positions  # All open positions
/pnl        # Today's profit/loss
/market     # Market hours
/queue      # Pending orders
```

Good luck! 💰
