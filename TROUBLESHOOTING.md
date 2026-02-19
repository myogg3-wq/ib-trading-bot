# 🔧 IB Trading Bot - Troubleshooting Guide

Comprehensive troubleshooting guide for common issues.

---

## 🚨 Critical Issues

### API Server Won't Start

**Symptom:** `uvicorn app.main:app` fails immediately

**Solutions:**

1. **Check Python version:**
   ```bash
   python --version  # Should be 3.9+
   ```

2. **Check virtual environment:**
   ```bash
   source venv/bin/activate  # Ensure venv is activated
   pip list | grep fastapi   # Should show FastAPI
   ```

3. **Install missing dependencies:**
   ```bash
   pip install --upgrade -r requirements.txt
   ```

4. **Check .env file exists:**
   ```bash
   ls -la .env
   # If missing: cp .env.example .env && nano .env
   ```

5. **Check database connection:**
   ```bash
   python scripts/init_all.py
   ```

---

### Worker Process Crashes

**Symptom:** Order worker keeps exiting

**Solutions:**

1. **Check PostgreSQL is running:**
   ```bash
   # Docker
   docker-compose ps

   # Or native
   psql -U tradingbot -d tradingbot -c "SELECT 1"
   ```

2. **Check Redis is running:**
   ```bash
   redis-cli ping
   # Should return: PONG
   ```

3. **Check IB Gateway connection:**
   - Is IB Gateway running? (should see it on screen)
   - Is host/port correct in .env?
   - `IB_HOST=127.0.0.1` (or your VPS IP)
   - `IB_PORT=4002` (paper) or `4001` (live)

4. **Check worker logs:**
   ```bash
   docker-compose logs worker -f
   # Or native:
   python app/queue/order_worker.py
   ```

---

### Telegram Bot Not Responding

**Symptom:** Bot doesn't reply to /status, /help, etc.

**Solutions:**

1. **Verify bot token:**
   ```bash
   # Check in .env
   grep TELEGRAM_BOT_TOKEN .env

   # Token should look like: 123456789:ABCDefGHIJKLmnoPQRStuvwxyz-1234567890
   ```

2. **Verify chat ID:**
   ```bash
   grep TELEGRAM_CHAT_ID .env

   # Chat ID should be a number like: 123456789
   ```

3. **Check if Telegram service is running:**
   ```bash
   docker-compose ps | grep telegram
   # or
   sudo systemctl status ib-bot-telegram
   ```

4. **Restart Telegram bot:**
   ```bash
   docker-compose restart telegram
   # or
   sudo systemctl restart ib-bot-telegram
   ```

5. **Check logs for errors:**
   ```bash
   docker-compose logs telegram -f
   ```

6. **Test token manually:**
   ```bash
   curl "https://api.telegram.org/bot<YOUR_TOKEN>/getMe"
   # Should return your bot info
   ```

---

## ⚠️ Order Processing Issues

### Orders Not Executing

**Symptom:** Alerts are received but no orders are placed

**Diagnosis:**

1. **Check order queue has alerts:**
   ```
   In Telegram: /queue
   Should show pending orders in queue
   ```

2. **Check worker is processing:**
   ```bash
   docker-compose logs worker -f
   # Should show processing logs
   ```

3. **Common blocks (in order of checking):**

   **a) Bot is killed:**
   ```
   In Telegram: /status
   If "🔴 KILLED" - run: /resume
   ```

   **b) Bot is paused:**
   ```
   In Telegram: /status
   If "🟡 PAUSED" - run: /resume
   ```

   **c) Insufficient cash:**
   ```
   In Telegram: /status
   Check "Total Invested" vs "Max Investment"
   ```

   **d) Daily buy limit exceeded:**
   ```
   In Telegram: /status
   Check "Today's Buys" vs limit
   ```

   **e) Daily loss limit exceeded:**
   ```
   In Telegram: /status
   Check "Daily Loss Limit"
   ```

   **f) Max positions per ticker:**
   ```
   In Telegram: /positions
   Check if ticker already has max entries
   ```

4. **Check IB connection:**
   ```
   In Telegram: /status
   Should say "Market: <emoji> OPEN" (during market hours)
   If disconnected, worker will auto-reconnect
   ```

---

### Partial Order Fills

**Symptom:** Order shows 100 shares but only 50 filled

**Causes:**

1. **Market liquidity** - Not enough buyers/sellers
2. **Slippage** - Price moved during order
3. **Fractional shares** - Using fractional trading

**Solutions:**

1. **Increase timeout in .env:**
   ```
   ORDER_TIMEOUT_SECONDS=60  # Default is 30
   ```

2. **Reduce order amount:**
   ```
   In Telegram: /set_amount 200
   # Smaller orders fill more reliably
   ```

3. **Check market hours:**
   ```
   In Telegram: /market
   # Place orders during peak hours 10am-3pm ET
   ```

---

## 🔌 Connection Issues

### IB Gateway Disconnects Frequently

**Symptom:** Frequent "Disconnected from IB Gateway" messages

**Solutions:**

1. **Check IB Gateway stability:**
   - Restart IB Gateway client
   - Update to latest version
   - Check system resources (CPU, RAM, network)

2. **Increase reconnect timeout:**
   ```python
   # In app/broker/ib_client.py
   self._reconnect_delay = 10  # Increase from 5
   self._max_reconnect_attempts = 100  # Increase from 50
   ```

3. **Network latency:**
   - If on VPS, check network stability
   - `ping 8.8.8.8` should be < 50ms

4. **Firewall rules:**
   - Ensure port 4002 (or 4001) is not blocked
   - Check router/VPS firewall settings

---

### PostgreSQL Connection Errors

**Symptom:** `could not connect to server: Connection refused`

**Solutions:**

1. **Check PostgreSQL is running:**
   ```bash
   # Docker
   docker-compose ps | grep postgres

   # Native
   sudo systemctl status postgresql
   ```

2. **Verify connection string:**
   ```bash
   # .env should have
   DATABASE_URL=postgresql+asyncpg://tradingbot:password@localhost:5432/tradingbot

   # Test connection
   psql -h localhost -U tradingbot -d tradingbot -c "SELECT 1"
   ```

3. **Reset PostgreSQL:**
   ```bash
   # Docker
   docker-compose down
   docker volume rm ib-trading-bot_postgres_data  # WARNING: Deletes database!
   docker-compose up -d postgres

   # Native
   sudo systemctl restart postgresql
   ```

---

### Redis Connection Errors

**Symptom:** `Redis connection refused` or `Cannot connect to Redis`

**Solutions:**

1. **Check Redis is running:**
   ```bash
   redis-cli ping
   # Should return: PONG

   # Or check service
   sudo systemctl status redis-server
   ```

2. **Verify connection string:**
   ```bash
   # .env should have
   REDIS_URL=redis://localhost:6379/0

   # Test connection
   redis-cli -u redis://localhost:6379/0 ping
   ```

3. **Restart Redis:**
   ```bash
   # Docker
   docker-compose restart redis

   # Native
   sudo systemctl restart redis-server
   ```

---

## 💾 Database Issues

### Database Locked / Transaction Conflicts

**Symptom:** Multiple order errors, "deadlock" in logs

**Solutions:**

1. **Check for stuck transactions:**
   ```bash
   psql -U tradingbot -d tradingbot -c "\l+"
   ```

2. **Kill stuck connections:**
   ```bash
   psql -U tradingbot -d tradingbot -c "
   SELECT pg_terminate_backend(pid)
   FROM pg_stat_activity
   WHERE datname = 'tradingbot' AND pid != pg_backend_pid();
   "
   ```

3. **Restart PostgreSQL:**
   ```bash
   docker-compose restart postgres
   # or
   sudo systemctl restart postgresql
   ```

---

### High Database Usage / Slow Queries

**Symptom:** Database consuming lots of CPU, orders slow to process

**Solutions:**

1. **Check table sizes:**
   ```bash
   psql -U tradingbot -d tradingbot -c "
   SELECT
     schemaname,
     tablename,
     pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename))
   FROM pg_tables
   ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
   "
   ```

2. **Archive old trades:**
   ```bash
   psql -U tradingbot -d tradingbot -c "
   DELETE FROM trade
   WHERE created_at < NOW() - INTERVAL '6 months';
   "
   ```

3. **Rebuild indexes:**
   ```bash
   psql -U tradingbot -d tradingbot -c "REINDEX DATABASE tradingbot;"
   ```

4. **Analyze query performance:**
   ```bash
   # Enable query logging
   # ALTER SYSTEM SET log_statement = 'all';
   # SELECT pg_reload_conf();
   ```

---

## 🌐 Webhook Issues

### Alerts Not Being Received

**Symptom:** TradingView says alert triggered but bot doesn't see it

**Solutions:**

1. **Verify webhook URL is correct:**
   ```
   TradingView Alert → Notification → Webhook URL
   Should be: https://your.domain.com/webhook (with HTTPS)
   ```

2. **Check webhook secret matches:**
   ```
   TradingView Alert Message:
   {"secret": "YOUR_SECRET", ...}

   Bot .env:
   WEBHOOK_SECRET=YOUR_SECRET

   Must be EXACTLY the same!
   ```

3. **Test webhook manually:**
   ```bash
   python scripts/test_webhook.py
   ```

4. **Check firewall allows webhook traffic:**
   ```bash
   # Test if port is accessible
   curl https://your.domain.com/health
   # Should return: {"status": "healthy", ...}
   ```

5. **Check API server is running:**
   ```bash
   curl http://localhost:8000/health
   # Should return status 200
   ```

6. **Review API logs:**
   ```bash
   docker-compose logs api -f
   ```

---

### Invalid Secret / Unauthorized (401)

**Symptom:** TradingView returns 401 Unauthorized

**Causes:**

1. Webhook secret in TradingView != .env
2. Typo in secret
3. Special characters not escaped

**Solutions:**

1. **Verify secret in both places:**
   ```bash
   # Check .env
   grep WEBHOOK_SECRET .env

   # Check TradingView alert webhook message for "secret" field
   ```

2. **Use simple secret (alphanumeric):**
   ```
   WEBHOOK_SECRET=MySecureKey123456
   # Avoid special chars like @, $, !, etc.
   ```

3. **Restart API to apply changes:**
   ```bash
   docker-compose restart api
   ```

---

## 📊 Monitoring & Performance

### Check Bot Health

```bash
# 1. API health
curl http://localhost:8000/health

# 2. Database health
psql -U tradingbot -d tradingbot -c "SELECT COUNT(*) FROM trade;"

# 3. Redis health
redis-cli ping

# 4. Queue status
# In Telegram: /queue

# 5. All services running
docker-compose ps
```

### Monitor Resource Usage

```bash
# Docker stats
docker stats

# System resources
top
# or
htop

# Disk usage
df -h
du -sh ib-trading-bot/
```

---

## 🔍 Debugging Commands

### Enable Verbose Logging

```bash
# Edit app/main.py to enable echo
# engine = create_async_engine(..., echo=True)

# Or set environment variable
export SQLALCHEMY_ECHO=1
python app/queue/order_worker.py
```

### Database Query Logs

```bash
psql -U tradingbot -d tradingbot
# Then in psql:
SET log_statement = 'all';
-- Run your queries to debug
```

### Check Configuration

```bash
python -c "from app.config import settings; print(settings)"
```

### Test Individual Components

```bash
# Test database
python scripts/init_all.py

# Test webhook
python scripts/test_webhook.py

# Test health check
curl http://localhost:8000/health
```

---

## 📋 Checklist for Troubleshooting

When something goes wrong, follow this checklist:

1. ✅ **Check all services running:**
   ```bash
   docker-compose ps
   ```

2. ✅ **Check logs:**
   ```bash
   docker-compose logs -f
   ```

3. ✅ **Check database connection:**
   ```bash
   python scripts/init_all.py
   ```

4. ✅ **Check bot status:**
   ```
   Telegram: /status
   ```

5. ✅ **Check queue:**
   ```
   Telegram: /queue
   ```

6. ✅ **Test webhook:**
   ```bash
   python scripts/test_webhook.py
   ```

7. ✅ **Check IB connection:**
   ```
   Telegram: /status → Market status
   ```

8. ✅ **Review order history:**
   ```
   Telegram: /pnl → See recent trades
   ```

---

## 📞 Getting Help

1. **Check documentation:**
   - `SETUP_GUIDE.md` - Initial setup
   - `DEPLOYMENT_GUIDE.md` - Deployment instructions
   - This file - Troubleshooting

2. **Collect debug info:**
   ```bash
   # Save everything to debug.txt
   {
     echo "=== Versions ===";
     python --version;
     echo "=== Services ===";
     docker-compose ps;
     echo "=== Configuration ===";
     cat .env | grep -v PASSWORD;
     echo "=== Logs (last 50 lines) ===";
     docker-compose logs --tail=50;
   } > debug.txt
   ```

3. **Enable debug mode:**
   - Edit `app/main.py` and add logging
   - Or set `PYTHONVERBOSE=1` environment variable

4. **Contact support:**
   - Provide output from debug.txt
   - Describe what you were doing
   - Include error messages from logs

---

## Common Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| `Connection refused` | Service not running | Check `docker-compose ps` |
| `Authentication failed` | Wrong credentials | Verify .env file |
| `Deadlock detected` | Database conflict | Restart PostgreSQL |
| `Order not filled` | Insufficient liquidity | Reduce order size |
| `Market closed` | Outside trading hours | Place order during market hours |
| `Max positions exceeded` | Too many positions | Close some positions |
| `Insufficient cash` | Not enough balance | Deposit more capital |
| `IB disconnected` | Connection lost | IB auto-reconnects (check logs) |
| `Invalid secret` | Webhook secret mismatch | Verify in TradingView & .env |
| `Duplicate alert` | Same alert sent twice | This is normal, filtered by idempotency |

---

## Final Notes

- **Always check logs first** - Most issues are visible in logs
- **Don't ignore warnings** - They often indicate future failures
- **Keep backups** - Database backups before making changes
- **Monitor resource usage** - Prevent out-of-memory issues
- **Update regularly** - Keep dependencies current

Good luck! 🚀
