# Telegram Bot Setup (5 minutes)

## Step 1: Create Bot
1. Open Telegram, search for `@BotFather`
2. Send `/newbot`
3. Enter bot name: `IB Trading Bot` (or any name)
4. Enter username: `your_ib_trading_bot` (must end with `bot`)
5. BotFather gives you a **token** like: `7123456789:AAH1234abcd5678efgh`
6. **Save this token** → goes into `.env` as `TELEGRAM_BOT_TOKEN`

## Step 2: Get Your Chat ID
1. Search for `@userinfobot` in Telegram
2. Send `/start`
3. It replies with your **Chat ID** (a number like `123456789`)
4. **Save this ID** → goes into `.env` as `TELEGRAM_CHAT_ID`

## Step 3: Start Your Bot
1. Go to your new bot in Telegram (link from BotFather)
2. Press **Start**
3. Now the bot can send you messages

## Step 4: Test
After deployment, send `/help` to your bot.
You should see all 21 commands listed.
