# Your Indicator Patch Guide

## What to Change

Your Pine Script code needs ONE small change at the bottom.
Replace the `alertcondition` lines with `alert()` calls that send JSON to webhook.

## Find This Section (near bottom of your code):

```pine
// Alert Logic for Indicator 1
alertcondition(pos_reg_div_detected, title='[Indi 1] Positive Regular Div Detected', message='Positive Regular Divergence Detected')
alertcondition(neg_reg_div_detected, title='[Indi 1] Negative Regular Div Detected', message='Negative Regular Divergence Detected')
alertcondition(sell_100_condition, title='[Indi 1] SELL 100% Signal', message='SELL 100% Signal Detected')
alertcondition(buy_300_condition, title='[Indi 1] BUY 300$ Signal', message='BUY 300$ Signal Detected')
```

## Replace With:

```pine
// Webhook Alerts for Auto-Trading
webhookSecret = input.string("YOUR_WEBHOOK_SECRET_HERE", "Webhook Secret", group="Webhook")

if buy_300_condition
    alert('{"secret":"' + webhookSecret + '","action":"BUY","ticker":"' + syminfo.ticker + '","price":"' + str.tostring(close) + '"}', alert.freq_once_per_bar)

if sell_100_condition
    alert('{"secret":"' + webhookSecret + '","action":"SELL","ticker":"' + syminfo.ticker + '","price":"' + str.tostring(close) + '"}', alert.freq_once_per_bar)
```

## Also Find This Section (Indicator 2 alerts):

```pine
// Alerts for Indicator 2
alertcondition(s2_buySignal, title='[Indi 2] Buy Alert', message='Buy signal generated!')
alertcondition(s2_sellSignal, title='[Indi 2] Sell Alert', message='Sell signal generated!')
```

## Optionally Add (if you want Indicator 2 signals too):

```pine
// Uncomment these if you also want Indicator 2 signals to trigger trades:
// if s2_buySignal
//     alert('{"secret":"' + webhookSecret + '","action":"BUY","ticker":"' + syminfo.ticker + '","price":"' + str.tostring(close) + '"}', alert.freq_once_per_bar)
// if s2_sellSignal
//     alert('{"secret":"' + webhookSecret + '","action":"SELL","ticker":"' + syminfo.ticker + '","price":"' + str.tostring(close) + '"}', alert.freq_once_per_bar)
```

## Key Difference

- `alertcondition()` → static message, can't include ticker dynamically
- `alert()` → dynamic message with `syminfo.ticker` automatically included!

## Alert Setup

When creating alerts for each ticker:
- Condition: "Any alert() function call"
- Webhook URL: https://your_domain.com/webhook
- Message: `{{message}}`    ← just this! The JSON is built in the script
