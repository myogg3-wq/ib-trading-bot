# IB Trading Bot — Setup Guide

## Prerequisites (Before Starting)

- [ ] Interactive Brokers account ($25,000+ for PDT)
- [ ] TradingView Premium+ account (100+ alerts)
- [ ] Credit card for AWS ($12-20/month)
- [ ] Smartphone with Telegram app

---

## Step 1: Create Telegram Bot (5 min)

1. Open Telegram, search `@BotFather`, send `/newbot`
2. Name it: `IB Trading Bot`
3. Save the **token** (looks like `7123456789:AAH1234...`)
4. Search `@userinfobot`, send `/start`, save your **Chat ID**

---

## Step 2: Create AWS Lightsail Instance (10 min)

1. Go to [AWS Lightsail](https://lightsail.aws.amazon.com)
2. Create instance:
   - Region: **Virginia (us-east-1)**
   - OS: **Ubuntu 22.04 LTS**
   - Plan: **$12/month (2GB RAM)** or $20/month (4GB)
3. Create a **Static IP** and attach to instance
4. Under Networking, open ports: **80, 443**
5. Download SSH key

---

## Step 3: (Optional) Domain Setup (10 min)

If you want a custom domain (recommended for SSL):

1. Buy a cheap domain ($1-10/year) from Namecheap, Cloudflare, etc.
2. Add an **A record** pointing to your Lightsail Static IP
3. Wait 5-30 min for DNS propagation

If no domain: you can use the Lightsail IP directly (SSL will be self-signed).

---

## Step 4: Deploy to Server (15 min)

### SSH into your server:
```bash
ssh -i your-key.pem ubuntu@YOUR_SERVER_IP
```

### Clone and deploy:
```bash
# Get the code onto the server (choose one):
# Option A: Git clone
git clone YOUR_REPO_URL ib-trading-bot

# Option B: SCP from your computer
# (from your local machine):
# scp -i your-key.pem -r ib-trading-bot/ ubuntu@YOUR_IP:~/

# Deploy
cd ib-trading-bot
bash scripts/deploy.sh
```

The deploy script will:
- Ask you for Telegram token, Chat ID, and trading settings
- Auto-generate passwords and secrets
- Install Docker, set up firewall, create swap
- Install IB Gateway + IBC
- Build and start all Docker containers

---

## Step 5: Configure IB Gateway (10 min)

```bash
# Edit IB Controller config
nano ~/ibc/config.ini
```

Change these lines:
```
IbLoginId=YOUR_IB_USERNAME
IbPassword=YOUR_IB_PASSWORD
TradingMode=paper          # Start with paper! Change to 'live' later
```

Start IB Gateway:
```bash
sudo systemctl start ib-gateway
sudo systemctl status ib-gateway   # Check it's running
```

---

## Step 6: Setup SSL (5 min, if you have a domain)

```bash
bash scripts/setup_ssl.sh your_domain.com
```

Your webhook URL will be: `https://your_domain.com/webhook`

---

## Step 7: Test Everything

```bash
# Test all connections
python3 scripts/test_connection.py

# Test webhook
bash scripts/test_webhook.sh http://localhost:8000 YOUR_WEBHOOK_SECRET

# Send /help to your Telegram bot — you should see all commands
```

---

## Step 8: Setup TradingView Alerts

For each ticker you want to trade:

1. Open chart with your indicator/strategy
2. Create Alert (Alt+A)
3. Enable **Webhook URL**: `https://your_domain.com/webhook`
4. Set **Message**:
```json
{"secret":"YOUR_WEBHOOK_SECRET","action":"{{strategy.order.action}}","ticker":"{{ticker}}","price":"{{close}}","alert_id":"{{alert_id}}","time":"{{timenow}}"}
```

See `scripts/tradingview_alert_template.md` for detailed instructions.

---

## Step 9: Paper Trading (2+ weeks)

Start with Paper Trading mode to verify:
- [ ] Alerts arrive correctly (check `/queue` in Telegram)
- [ ] Buy orders execute (check `/positions`)
- [ ] Sell orders close all positions (check `/pnl`)
- [ ] Daily reports arrive at 4:05 PM ET
- [ ] Settings change works (`/set_amount 500`)
- [ ] Kill switch works (`/kill`, then `/resume`)
- [ ] Sunday IB re-login works

---

## Step 10: Go Live

When Paper Trading is verified:

1. Change IBC config:
```bash
nano ~/ibc/config.ini
# Change: TradingMode=live
```

2. Change .env:
```bash
nano .env
# Change: IB_PORT=4001
```

3. Restart:
```bash
sudo systemctl restart ib-gateway
docker compose restart worker
```

4. Start small:
```
/set_amount 100        # Start with $100 per trade
/set_max_daily 10      # Max 10 buys per day
```

5. Gradually increase as you gain confidence.

---

## Daily Operations

| What | When | How |
|------|------|-----|
| Check status | Whenever | Telegram: `/status` |
| View P&L | End of day | Telegram: `/pnl` (or auto daily report) |
| IB Re-login | Every Sunday | SSH/VNC into VPS, authenticate IB Gateway |
| Adjust settings | As needed | Telegram: `/set_amount`, etc. |
| Emergency stop | If needed | Telegram: `/kill` |

---

## Troubleshooting

### Bot not responding to Telegram commands
```bash
docker compose logs telegram   # Check Telegram container logs
```

### Orders not executing
```bash
docker compose logs worker     # Check worker logs
```
Telegram: `/queue` to see pending orders

### IB Gateway disconnected
```bash
sudo systemctl status ib-gateway
sudo systemctl restart ib-gateway
```
Telegram will alert: "IB Gateway DISCONNECTED!"

### View all logs
```bash
docker compose logs -f           # All services
docker compose logs -f worker    # Just worker
docker compose logs -f api       # Just API
```

### Restart everything
```bash
docker compose restart           # Restart containers
sudo systemctl restart ib-gateway  # Restart IB Gateway
```

### Complete reset
```bash
docker compose down -v           # Stop + delete data
docker compose up -d             # Fresh start
```

---

## Cost Summary

| Item | Monthly Cost |
|------|-------------|
| AWS Lightsail (2GB) | $12 |
| TradingView Premium | $50 |
| IB Market Data | $0-5 |
| Domain (optional) | $1 |
| **Total** | **~$63-68** |
| + Trading commissions | ~$500-2000 depending on volume |
