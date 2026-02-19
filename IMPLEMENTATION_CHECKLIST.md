# ✅ IB Trading Bot - Implementation Checklist

Complete checklist for verifying all automation features are working correctly.

---

## Phase 1: Configuration ✓

- [ ] `.env` file created with all required values
- [ ] `WEBHOOK_SECRET` set to a strong random value
- [ ] `TELEGRAM_BOT_TOKEN` obtained from @BotFather
- [ ] `TELEGRAM_CHAT_ID` set to your chat ID
- [ ] `DATABASE_URL` points to accessible PostgreSQL
- [ ] `REDIS_URL` points to accessible Redis
- [ ] `IB_HOST` and `IB_PORT` correct for your setup (4002=paper, 4001=live)

---

## Phase 2: Database Setup ✓

- [ ] PostgreSQL running (docker-compose or native)
- [ ] Database initialization: `python scripts/init_all.py`
- [ ] Default bot settings created in DB
- [ ] All tables created:
  - `bot_settings` - Bot configuration
  - `position` - Open positions
  - `trade` - Trade history
  - `alert_log` - Webhook alerts
- [ ] Database schema verified: `psql -U tradingbot -d tradingbot -dt`

---

## Phase 3: Cache & Queue ✓

- [ ] Redis running
- [ ] Redis connectivity verified: `redis-cli ping`
- [ ] Order queues created:
  - `orders:sell` - High priority
  - `orders:buy` - Normal priority
  - `orders:pending` - For market-closed alerts
- [ ] Queue stats working: Run worker and check `/queue` command

---

## Phase 4: Webhook Endpoint ✓

**API Server:**
- [ ] API starts without errors: `uvicorn app.main:app --reload`
- [ ] Health check endpoint works: `curl http://localhost:8000/health`
- [ ] Webhook endpoint accepts POST: `curl -X POST http://localhost:8000/webhook`

**Webhook Security:**
- [ ] IP whitelist working (TradingView IPs blocked if not in list)
- [ ] Secret validation working (test with wrong secret → 401)
- [ ] Idempotency working (duplicate alerts not double-queued)
- [ ] Invalid actions rejected (test with action=HOLD → 400)

**Test Webhook:**
```bash
python scripts/test_webhook.py
```
- [ ] All test scenarios pass
- [ ] Invalid secret rejected
- [ ] Invalid action rejected

---

## Phase 5: Order Worker ✓

**Worker Process:**
- [ ] Worker starts: `python app/queue/order_worker.py`
- [ ] Connects to IB Gateway
- [ ] Connects to PostgreSQL
- [ ] Connects to Redis
- [ ] Starts polling queues every 0.1-2 seconds

**Order Processing Flow:**
- [ ] Worker dequeues orders
- [ ] Checks market hours
- [ ] Runs risk checks (8 checks)
- [ ] Respects rate limiting (max_orders_per_second)
- [ ] Executes orders via IB
- [ ] Records positions in DB
- [ ] Records trades in DB
- [ ] Sends Telegram notifications

**Test Order Processing:**
1. Send BUY alert via webhook/test script
2. Check in Telegram: `/queue` → Should see order
3. Check worker logs → Should see processing
4. Check in Telegram: `/status` → Should see position opened
5. Check in Telegram: `/positions` → Should see the bought stock

---

## Phase 6: Risk Management ✓

**Risk Checks (all 8 must work):**

1. [ ] **Kill Switch** - `/kill` stops all trading, `/resume` enables
2. [ ] **Pause** - `/pause` stops buys but allows sells
3. [ ] **Cash Balance** - Blocks if insufficient cash
4. [ ] **Total Investment** - Blocks if max investment reached
5. [ ] **Open Positions** - Blocks if max positions reached
6. [ ] **Per-Ticker Limit** - Blocks if too many per ticker
7. [ ] **Daily Buy Limit** - Blocks after max daily buys
8. [ ] **Daily Loss Limit** - Blocks after max daily loss

**Test Risk Checks:**
```
In Telegram:
/status                          # Check current limits
/set_max_positions 1             # Set to 1
Send BUY alert                   # Should execute
Send another BUY alert           # Should be blocked
/set_max_positions 200           # Restore default
```

---

## Phase 7: Scheduler Jobs ✓

**Five scheduled jobs must run automatically:**

1. [ ] **Market Open (9:30 AM ET, weekdays):**
   - Flushes pending queue → active queue
   - Sends Telegram notification
   - Test: Set clock ahead or check logs

2. [ ] **Daily Report (4:05 PM ET, weekdays):**
   - Sends performance summary
   - Shows buys, sells, P&L, commission
   - Test: Manually trigger or check logs

3. [ ] **Position Sync (10:00, 14:00, 18:00 ET, weekdays):**
   - Compares IB positions vs DB
   - Reports mismatches via Telegram
   - Test: Manually buy in IB, check sync

4. [ ] **Health Check (every 5 minutes):**
   - Checks IB connection
   - Alerts if disconnected
   - Test: Check logs, should see entries every 5 min

5. [ ] **Sunday Reminder (10:00 AM ET, Sunday):**
   - Reminds to login to IB
   - Test: Set clock to Sunday or check logs

**Verify Scheduler:**
```bash
# Check scheduler started in API logs
docker-compose logs api | grep "Scheduler started"

# All jobs should be registered
docker-compose logs api | grep "Market Open\|Daily Report\|Position Sync\|Health Check\|Sunday"
```

---

## Phase 8: Telegram Bot ✓

**Bot Process:**
- [ ] Bot starts: `python app/notifications/telegram_bot.py`
- [ ] Registers commands with Telegram
- [ ] Starts polling updates
- [ ] Authorizes only from configured chat ID

**Status Commands (Read-Only):**
- [ ] `/start` - Shows welcome message
- [ ] `/help` - Shows all commands
- [ ] `/status` - Shows bot status, open positions, P&L
- [ ] `/positions` - Lists all open positions
- [ ] `/pnl` - Shows today's P&L breakdown
- [ ] `/pnl_week` - Shows this week's P&L
- [ ] `/market` - Shows market hours status
- [ ] `/queue` - Shows pending orders
- [ ] `/settings` - Shows all current settings

**Setting Commands (Adjustable):**
- [ ] `/set_amount 500` - Change buy amount
- [ ] `/set_max_positions 300` - Change max positions
- [ ] `/set_max_daily 100` - Change max daily buys
- [ ] `/set_max_invest 100000` - Change max investment
- [ ] `/set_max_per_ticker 10` - Change max per ticker
- [ ] `/set_max_loss 10000` - Change max daily loss
- [ ] `/set_reserve 2000` - Change min cash reserve

**Control Commands (Critical):**
- [ ] `/pause` - Pause buying (sells work)
- [ ] `/resume` - Resume all trading
- [ ] `/kill` - Emergency stop ALL trading
- [ ] `/sell_all` - Sell all positions (with confirmation)
- [ ] `/clear_queue` - Clear pending orders

**Notifications:**
- [ ] BUY execution notifications
- [ ] SELL execution notifications
- [ ] Risk block notifications
- [ ] Market open flush notification
- [ ] Daily report notification
- [ ] Position sync mismatch notifications
- [ ] IB disconnect notifications
- [ ] Worker startup notification

**Test Telegram Bot:**
1. Send `/start` → Should show welcome
2. Send `/status` → Should show status
3. Send `/pause` → Should pause buying
4. Send `/resume` → Should resume
5. Send `/kill` → Should stop all trading
6. Send `/resume` → Should restart
7. All command responses should be in < 2 seconds

---

## Phase 9: IB Gateway Integration ✓

**Connection:**
- [ ] IB Gateway application is running
- [ ] Client ID matches (IB_CLIENT_ID in .env)
- [ ] Port matches (IB_PORT: 4002=paper, 4001=live)
- [ ] Auto-reconnect works (test by restarting IB)

**Account Data:**
- [ ] Can read available cash
- [ ] Can read open positions
- [ ] Can read account summary

**Order Execution:**
- [ ] Can place BUY market orders
- [ ] Can place SELL market orders
- [ ] Orders fill reliably
- [ ] Commission calculated correctly
- [ ] Unfilled orders are cancelled after timeout

**Test IB Integration:**
```bash
# In Telegram:
/status                # Check cash available
/positions             # Check open positions

# Send test alert and verify:
# 1. Order placed in IB
# 2. Position recorded in DB
# 3. Trade recorded in DB
# 4. Notification sent to Telegram
```

---

## Phase 10: Data Persistence ✓

**Position Tracking:**
- [ ] All BUY orders create position records
- [ ] Position has: ticker, qty, entry_price, entry_time, status=OPEN
- [ ] All SELL orders close position records
- [ ] Closed position has: exit_price, exit_time, pnl, status=CLOSED
- [ ] Test: `/positions` shows all open positions

**Trade History:**
- [ ] All BUY orders create trade records
- [ ] All SELL orders create trade records
- [ ] Trade has: ticker, side, filled_qty, avg_fill_price, commission, status=FILLED
- [ ] Failed orders have: status=FAILED, error_message
- [ ] Test: `/pnl` shows all today's trades

**Alert Logging:**
- [ ] All webhook alerts logged to alert_log table
- [ ] Includes: ticker, action, price, idempotency_key
- [ ] Duplicate alerts filtered by idempotency_key
- [ ] Test: Send duplicate alert → should be ignored

---

## Phase 11: Monitoring & Observability ✓

**Logging:**
- [ ] Structured logs (JSON format via structlog)
- [ ] Logs include timestamps
- [ ] Logs show all significant events
- [ ] Error logging with full context
- [ ] Test: `docker-compose logs -f` shows activity

**Metrics Available:**
- [ ] Order counts (today's buys/sells via /status)
- [ ] Position counts (via /status)
- [ ] Cash available (implicit in status)
- [ ] P&L tracking (via /pnl)
- [ ] Queue depths (via /queue)

**Alerting:**
- [ ] Risk blocks notify Telegram
- [ ] IB disconnects notify Telegram
- [ ] Worker startup/shutdown notified
- [ ] Failed orders notified
- [ ] Test: Trigger errors and check Telegram

---

## Phase 12: TradingView Integration ✓

**Alert Configuration:**
- [ ] TradingView webhook URL: `https://your.domain/webhook`
- [ ] Webhook secret matches .env exactly
- [ ] Alert message JSON is valid:
  ```json
  {
    "secret": "YOUR_SECRET",
    "action": "BUY",
    "ticker": "{{SYMBOL}}",
    "price": "{{CLOSE}}",
    "time": "{{timenow}}"
  }
  ```

**Test Alert:**
- [ ] Create test alert in TradingView
- [ ] Check bot receives it: `/queue`
- [ ] Verify order processes
- [ ] Check notification in Telegram

**Production Setup:**
- [ ] Configure actual strategy in TradingView
- [ ] Set appropriate alert conditions
- [ ] Enable alert notifications
- [ ] Test multiple symbols

---

## Phase 13: Documentation ✓

- [ ] README.md - Project overview
- [ ] SETUP_GUIDE.md - Initial setup instructions
- [ ] DEPLOYMENT_GUIDE.md - Production deployment
- [ ] TROUBLESHOOTING.md - Problem solving
- [ ] This checklist - Feature verification

---

## Phase 14: Security Hardening ✓

- [ ] .env is in .gitignore (never commit secrets)
- [ ] Strong WEBHOOK_SECRET (random, 32+ chars)
- [ ] PostgreSQL password is strong
- [ ] Redis has AUTH enabled (optional but recommended)
- [ ] IB account has 2FA enabled
- [ ] Telegram bot token protected
- [ ] API behind HTTPS in production
- [ ] Firewall configured (only allow needed ports)
- [ ] Regular backups of database
- [ ] Secrets not logged (review logs for credentials)

---

## Phase 15: Performance Testing ✓

**Load Testing:**
- [ ] Send 10 rapid BUY alerts → All should queue properly
- [ ] Send BUY + SELL in quick succession → Correct priority
- [ ] API response time < 100ms
- [ ] Order processing time < 5 seconds per order

**Stability Testing:**
- [ ] Bot runs for 24 hours without crashing
- [ ] No memory leaks (check `docker stats`)
- [ ] No database connection exhaustion
- [ ] Auto-reconnection works if IB disconnects

---

## Phase 16: Deployment ✓

**Docker Deployment:**
- [ ] `docker-compose.yml` is configured
- [ ] All services start: `docker-compose up -d`
- [ ] All services healthy: `docker-compose ps`
- [ ] Volumes persist data between restarts

**VPS Deployment (if applicable):**
- [ ] Services run as systemd units
- [ ] Services auto-restart on failure
- [ ] Logs accessible via journalctl
- [ ] Nginx reverse proxy configured
- [ ] SSL certificate installed (Let's Encrypt)
- [ ] Auto-renewal configured

---

## Final Verification

Run the complete initialization and testing:

```bash
# 1. Initialize everything
python scripts/init_all.py

# 2. Start all services
docker-compose up -d

# 3. Test webhook
python scripts/test_webhook.py

# 4. Send manual test orders
# In Telegram: /status, /queue, /positions

# 5. Monitor logs
docker-compose logs -f
```

**All green? 🟢 You're ready to go!**

```
✅ Configuration complete
✅ Database ready
✅ Queue working
✅ Webhook receiving alerts
✅ Worker processing orders
✅ Risk management enforced
✅ Scheduler running jobs
✅ Telegram bot responding
✅ IB Gateway integrated
✅ Data persisting
✅ Monitoring active
✅ TradingView alerts flowing
✅ Security hardened
✅ Performance tested
✅ Deployment verified

🚀 Ready for live trading!
```

---

## Ongoing Maintenance

### Daily:
- [ ] Check `/status` in Telegram
- [ ] Review `/pnl` for any anomalies
- [ ] Monitor logs for errors

### Weekly:
- [ ] Backup database
- [ ] Review `/positions` for concentration risk
- [ ] Check system resources (disk, CPU, RAM)

### Monthly:
- [ ] Review risk settings
- [ ] Archive old trades
- [ ] Update dependencies (`pip install --upgrade -r requirements.txt`)
- [ ] Review IB account for unauthorized activity

### Quarterly:
- [ ] Full disaster recovery test
- [ ] Security audit
- [ ] Performance optimization
- [ ] Update documentation

---

## Support

If any phase fails:

1. Check **TROUBLESHOOTING.md** for that error
2. Review logs: `docker-compose logs -f`
3. Run: `python scripts/init_all.py` to verify setup
4. Check configuration in .env file

Good luck! 💰 🚀
