# TradingView Alert Setup

## Alert Message Template

Copy-paste this EXACTLY into your TradingView alert's "Message" field:

```json
{"secret":"YOUR_WEBHOOK_SECRET","action":"{{strategy.order.action}}","ticker":"{{ticker}}","price":"{{close}}","alert_id":"{{alert_id}}","time":"{{timenow}}"}
```

**Replace `YOUR_WEBHOOK_SECRET` with the secret from your .env file.**


## Webhook URL

```
https://your_domain.com/webhook
```


## Setting Up Alerts (Per Indicator/Strategy)

1. Open your chart with your indicator/strategy
2. Click "Alerts" (clock icon) or press Alt+A
3. Condition: Select your indicator/strategy
4. Check "Webhook URL"
5. Enter your URL: `https://your_domain.com/webhook`
6. In "Message" field, paste the template above
7. Set "Alert name" (e.g., "AAPL Auto-Trade")
8. Click "Create"


## If Your Strategy Uses strategy.entry/strategy.close

Your Pine Script should have:

```pine
//@version=5
strategy("My Strategy", overlay=true)

// Your buy/sell conditions
longCondition = ...your buy condition...
shortCondition = ...your sell condition...

if (longCondition)
    strategy.entry("BUY", strategy.long)

if (shortCondition)
    strategy.close("BUY")
```

The `{{strategy.order.action}}` placeholder will automatically become:
- `buy` when strategy.entry fires
- `sell` when strategy.close fires


## If Your Indicator Uses alertcondition()

```pine
//@version=5
indicator("My Indicator", overlay=true)

buySignal = ...your buy condition...
sellSignal = ...your sell condition...

alertcondition(buySignal, title="Buy Signal", message='{"secret":"YOUR_SECRET","action":"BUY","ticker":"{{ticker}}","price":"{{close}}","alert_id":"{{alert_id}}"}')
alertcondition(sellSignal, title="Sell Signal", message='{"secret":"YOUR_SECRET","action":"SELL","ticker":"{{ticker}}","price":"{{close}}","alert_id":"{{alert_id}}"}')
```

Then create TWO alerts per ticker:
1. Alert for "Buy Signal" condition → webhook
2. Alert for "Sell Signal" condition → webhook


## Bulk Alert Setup (For Hundreds of Tickers)

TradingView doesn't have a built-in bulk alert creator, but:

### Option A: Use a Screener-Based Alert (Recommended)
If your strategy works on a screener, you can create ONE alert for the screener
that fires for any matching ticker.

### Option B: Manual Setup
- TradingView Premium: 400 alerts
- TradingView Expert: 800 alerts
- Set alerts one by one per ticker

### Option C: Use a Pine Script watchlist approach
```pine
//@version=5
strategy("Multi-Ticker Bot", overlay=true)

// This runs on whatever chart you apply it to
// Apply to each ticker's chart and create alert
longCondition = ...
shortCondition = ...

if (longCondition)
    strategy.entry("BUY", strategy.long)
if (shortCondition)
    strategy.close("BUY")
```


## Testing Your Alert

Send a test webhook manually:

```bash
curl -X POST https://your_domain.com/webhook \
  -H "Content-Type: application/json" \
  -d '{"secret":"YOUR_SECRET","action":"BUY","ticker":"AAPL","price":"150.00"}'
```

Expected response:
```json
{"status":"accepted","action":"BUY","ticker":"AAPL"}
```
