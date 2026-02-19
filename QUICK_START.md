# ⚡ Quick Start Guide - 5 Minutes

Get your IB Trading Bot running in 5 minutes!

---

## Step 1: Configure (2 min)

```bash
# Copy template
cp .env.example .env

# Edit with your values (open in your editor)
nano .env
```

**Required values:**
```
IB_HOST=127.0.0.1          # or your VPS IP
IB_PORT=4002               # Paper trading
WEBHOOK_SECRET=MySecret123 # Any strong value
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=123456789
DATABASE_URL=...           # Or keep default for docker
REDIS_URL=...              # Or keep default for docker
```

---

## Step 2: Initialize (1 min)

```bash
python scripts/init_all.py
```

Expected output:
```
✅ PostgreSQL OK
✅ Redis OK
✅ IB Gateway OK
✅ Telegram configured
✅ Defaults OK

6/6 checks passed
```

If something fails, see **TROUBLESHOOTING.md**

---

## Step 3: Start Services (1 min)

```bash
# Terminal 1 - Start everything
docker-compose up -d

# Check services are running
docker-compose ps
```

Should see:
```
postgres   ✓ running
redis      ✓ running
api        ✓ running
worker     ✓ running
telegram   ✓ running
```

---

## Step 4: Test It (1 min)

### Option A: Telegram Test
```
In Telegram app:
/start    # Should show welcome message
/status   # Should show bot status
/queue    # Should be empty
```

### Option B: Webhook Test
```bash
python scripts/test_webhook.py

# Should execute all scenarios successfully
```

---

## 🎉 You're Done!

Your bot is now ready. Here's what to do next:

### 1. **Setup TradingView Alerts**

In TradingView, create alert with this message:
```json
{
  "secret": "MySecret123",
  "action": "BUY",
  "ticker": "{{SYMBOL}}",
  "price": "{{CLOSE}}",
  "time": "{{timenow}}"
}
```

Replace `MySecret123` with your WEBHOOK_SECRET from .env

Alert URL: `http://your.ip:8000/webhook` (or `https://your.domain.com/webhook` for production)

### 2. **Send Test Alert**

Create a test alert or run:
```bash
python scripts/test_webhook.py
```

### 3. **Monitor in Telegram**

```
/status      # Check bot status
/queue       # See pending orders
/positions   # See open positions
/pnl         # Check today's P&L
```

---

## 🎮 Common Commands

### Status
```
/status          Bot status & limits
/positions       All open positions
/pnl             Today's P&L
/pnl_week        This week's P&L
/market          Market hours
/queue           Pending orders
/settings        Current settings
```

### Control
```
/kill            🔴 Stop ALL trading
/pause           🟡 Stop buys (sells ok)
/resume          🟢 Resume trading
/sell_all        Sell everything
/clear_queue     Clear pending
```

### Configure
```
/set_amount 500              Buy amount
/set_max_positions 300       Max open
/set_max_daily 100           Max daily buys
/set_max_invest 100000       Max investment
/set_max_per_ticker 10       Max per ticker
/set_max_loss 10000          Max daily loss
/set_reserve 2000            Min cash reserve
```

---

## 📊 What's Happening

1. **TradingView Alert** → Webhook receives it
2. **Webhook** → Validates & queues in Redis
3. **Worker** → Dequeues & checks risks
4. **IB Gateway** → Places market order
5. **Database** → Records position & trade
6. **Telegram** → Sends notification

All in **< 5 seconds per order**

---

## ✅ Verify Everything Works

Run this checklist:

- [ ] `python scripts/init_all.py` passes
- [ ] `docker-compose ps` shows all running
- [ ] `/status` returns bot status
- [ ] `python scripts/test_webhook.py` passes
- [ ] Send manual alert via webhook or test script
- [ ] Check Telegram `/queue` shows pending
- [ ] Check Telegram `/positions` shows open positions

---

## 🆘 Issues?

### API won't start
```bash
# Make sure you have .env file
ls -la .env

# Install dependencies
pip install -r requirements.txt

# Check Python version
python --version  # Must be 3.9+
```

### Can't connect to IB
```bash
# Make sure IB Gateway is running
# Port should be 4002 (paper) or 4001 (live)
# Check in .env: IB_HOST and IB_PORT
```

### Telegram bot silent
```bash
# Check token is correct
grep TELEGRAM_BOT_TOKEN .env

# Restart bot
docker-compose restart telegram
```

### More help?
→ See **TROUBLESHOOTING.md** (600+ lines of solutions)

---

## 📚 Documentation

- `SETUP_GUIDE.md` - Detailed setup
- `DEPLOYMENT_GUIDE.md` - Production deployment
- `TROUBLESHOOTING.md` - Problem solving
- `IMPLEMENTATION_CHECKLIST.md` - Verify everything
- `COMPLETION_REPORT.md` - Project summary

---

## 🚀 Production Deployment

When ready for live trading:

1. Change `IB_PORT=4001` in .env (for live account)
2. Follow **DEPLOYMENT_GUIDE.md** for VPS setup
3. Configure HTTPS with Let's Encrypt
4. Setup automated backups
5. Monitor via `/status` command daily

---

## 💡 Pro Tips

1. **Start with small amounts:**
   ```
   /set_amount 100    # Start with $100 orders
   ```

2. **Start with few positions:**
   ```
   /set_max_positions 10   # Max 10 open
   /set_max_daily_buys 5   # Max 5 per day
   ```

3. **Keep reserves:**
   ```
   /set_reserve 5000   # Always keep $5k cash
   ```

4. **Monitor daily:**
   ```
   Telegram: /pnl     # Check P&L every day
   Telegram: /status  # Check limits used
   ```

5. **Use kill switch if needed:**
   ```
   /kill              # Stops everything immediately
   /resume            # Resume when ready
   ```

---

## ⚡ TL;DR

```bash
# 1. Configure
cp .env.example .env && nano .env

# 2. Initialize
python scripts/init_all.py

# 3. Run
docker-compose up -d

# 4. Test
python scripts/test_webhook.py

# 5. Monitor
# In Telegram: /status
```

Done! ✅

---

**Questions?** Check TROUBLESHOOTING.md or review DEPLOYMENT_GUIDE.md

**Ready?** Start trading! 🚀💰
