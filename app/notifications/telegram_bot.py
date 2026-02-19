"""
Telegram Bot for notifications and commands.
All settings adjustable via Telegram commands.
"""

import asyncio
import signal
import sys
from datetime import datetime, timezone
from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
import structlog

from app.config import settings
from app.database.connection import init_db, get_bot_settings, update_bot_setting
from app.risk.risk_manager import get_risk_summary
from app.queue.order_queue import get_queue_stats, clear_all_queues
from app.broker.market_hours import get_market_status

logger = structlog.get_logger()

# Global reference for sending notifications from other modules
_bot_app = None


def is_authorized(update: Update) -> bool:
    """Check if the message is from the authorized chat."""
    chat_id = str(update.effective_chat.id)
    return chat_id == settings.telegram_chat_id


# ============================================
# COMMAND HANDLERS
# ============================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message with all available commands."""
    if not is_authorized(update):
        return

    msg = """🤖 *IB Trading Bot*

Welcome\\! Here are all available commands:

📊 *Status & Info*
/status \\- Current bot status overview
/positions \\- All open positions
/pnl \\- Today's profit/loss
/pnl\\_week \\- This week's P&L
/market \\- Market hours status
/queue \\- Order queue status

⚙️ *Settings \\(Adjustable\\)*
/settings \\- View all current settings
/set\\_amount \\<$\\> \\- Set buy amount
/set\\_max\\_positions \\<N\\> \\- Max open positions
/set\\_max\\_daily \\<N\\> \\- Max daily buys
/set\\_max\\_invest \\<$\\> \\- Max total investment
/set\\_max\\_per\\_ticker \\<N\\> \\- Max buys per ticker
/set\\_max\\_loss \\<$\\> \\- Max daily loss limit
/set\\_reserve \\<$\\> \\- Min cash reserve

🔧 *Control*
/pause \\- Pause buying \\(sells still work\\)
/resume \\- Resume buying
/kill \\- Emergency stop ALL trading
/sell\\_all \\- Sell ALL positions
/clear\\_queue \\- Clear order queue

/help \\- Show this message"""

    await update.message.reply_text(msg, parse_mode="MarkdownV2")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Same as /start."""
    await cmd_start(update, context)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current bot status overview."""
    if not is_authorized(update):
        return

    try:
        risk = await get_risk_summary()
        market = get_market_status()
        queue = await get_queue_stats()

        # Status emoji
        if risk["is_killed"]:
            bot_status = "🔴 KILLED"
        elif risk["is_paused"]:
            bot_status = "🟡 PAUSED"
        else:
            bot_status = "🟢 RUNNING"

        pnl_emoji = "🟢" if risk["today_pnl"] >= 0 else "🔴"

        msg = (
            f"📊 Bot Status: {bot_status}\n"
            f"{'─' * 30}\n"
            f"\n"
            f"💰 Buy Amount: ${risk['buy_amount']:.0f}\n"
            f"\n"
            f"📈 Open Positions: {risk['open_positions']}/{risk['max_investment']/risk['buy_amount']:.0f}\n"
            f"🏷️ Unique Tickers: {risk['unique_tickers']}\n"
            f"💵 Total Invested: ${risk['total_invested']:,.0f} / ${risk['max_investment']:,.0f}\n"
            f"\n"
            f"📅 Today's Buys: {risk['today_buys']}/{risk['max_daily_buys']}\n"
            f"{pnl_emoji} Today's P&L: ${risk['today_pnl']:+,.2f}\n"
            f"🛑 Daily Loss Limit: -${risk['max_daily_loss']:,.0f}\n"
            f"\n"
            f"{market['emoji']} Market: {market['status']} ({market['current_time_et']})\n"
            f"⏰ Next Open: {market['next_open_in']}\n"
            f"\n"
            f"📬 Queue: {queue['sell_queue']} sells, {queue['buy_queue']} buys, {queue['pending_queue']} pending"
        )

        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ Error getting status: {str(e)}")


async def cmd_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all open positions."""
    if not is_authorized(update):
        return

    try:
        from sqlalchemy import select, func
        from app.database.connection import get_session
        from app.models.position import Position, PositionStatus

        async with get_session() as session:
            # Get positions grouped by ticker
            result = await session.execute(
                select(
                    Position.ticker,
                    func.count(Position.id).label("count"),
                    func.sum(Position.qty).label("total_qty"),
                    func.sum(Position.entry_amount_usd).label("total_amount"),
                    func.avg(Position.entry_price).label("avg_price"),
                ).where(
                    Position.status == PositionStatus.OPEN
                ).group_by(Position.ticker).order_by(
                    func.sum(Position.entry_amount_usd).desc()
                )
            )
            positions = result.all()

        if not positions:
            await update.message.reply_text("📭 No open positions")
            return

        msg_lines = [f"📈 Open Positions ({len(positions)} tickers)\n{'─' * 30}"]

        for pos in positions[:50]:  # Limit display to 50
            ticker, count, total_qty, total_amount, avg_price = pos
            buys_label = f"({count}x)" if count > 1 else ""
            msg_lines.append(
                f"\n{ticker} {buys_label}\n"
                f"  Qty: {total_qty:.4f} × avg ${avg_price:.2f}\n"
                f"  Invested: ${total_amount:.0f}"
            )

        if len(positions) > 50:
            msg_lines.append(f"\n... and {len(positions) - 50} more tickers")

        total_invested = sum(p[3] for p in positions)
        msg_lines.append(f"\n{'─' * 30}")
        msg_lines.append(f"Total Invested: ${total_invested:,.0f}")

        msg = "\n".join(msg_lines)

        # Telegram message limit is 4096 chars
        if len(msg) > 4000:
            # Split into chunks
            for i in range(0, len(msg), 4000):
                await update.message.reply_text(msg[i:i + 4000])
        else:
            await update.message.reply_text(msg)

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def cmd_pnl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show today's P&L."""
    if not is_authorized(update):
        return

    try:
        from sqlalchemy import select, func
        from app.database.connection import get_session
        from app.models.trade import Trade, TradeSide, TradeStatus

        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        async with get_session() as session:
            # Today's sells with P&L
            result = await session.execute(
                select(Trade).where(
                    Trade.side == TradeSide.SELL,
                    Trade.status == TradeStatus.FILLED,
                    Trade.created_at >= today_start,
                ).order_by(Trade.created_at.desc())
            )
            sells = result.scalars().all()

            # Today's buy count
            buy_count = (await session.execute(
                select(func.count(Trade.id)).where(
                    Trade.side == TradeSide.BUY,
                    Trade.status == TradeStatus.FILLED,
                    Trade.created_at >= today_start,
                )
            )).scalar() or 0

        if not sells and buy_count == 0:
            await update.message.reply_text("📊 No trades today")
            return

        total_pnl = sum(t.total_pnl_usd or 0 for t in sells)
        total_commission = sum(t.commission or 0 for t in sells)
        winners = sum(1 for t in sells if (t.total_pnl_usd or 0) >= 0)
        losers = len(sells) - winners

        pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"

        msg = (
            f"📊 Today's Performance\n"
            f"{'─' * 30}\n"
            f"\n"
            f"Buys: {buy_count}\n"
            f"Sells: {len(sells)} (✅{winners} / ❌{losers})\n"
            f"\n"
            f"{pnl_emoji} Total P&L: ${total_pnl:+,.2f}\n"
            f"💸 Commission: ${total_commission:,.2f}\n"
            f"📊 Net P&L: ${total_pnl - total_commission:+,.2f}\n"
        )

        # Show individual trades (last 10)
        if sells:
            msg += f"\n{'─' * 30}\nRecent sells:\n"
            for t in sells[:10]:
                pnl = t.total_pnl_usd or 0
                emoji = "🟢" if pnl >= 0 else "🔴"
                msg += f"{emoji} {t.ticker}: ${pnl:+.2f}\n"

        await update.message.reply_text(msg)

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def cmd_pnl_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show this week's P&L."""
    if not is_authorized(update):
        return

    try:
        from sqlalchemy import select, func
        from app.database.connection import get_session
        from app.models.trade import Trade, TradeSide, TradeStatus
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        week_start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        async with get_session() as session:
            result = await session.execute(
                select(
                    func.count(Trade.id),
                    func.sum(Trade.total_pnl_usd),
                    func.sum(Trade.commission),
                ).where(
                    Trade.side == TradeSide.SELL,
                    Trade.status == TradeStatus.FILLED,
                    Trade.created_at >= week_start,
                )
            )
            row = result.one()
            sell_count = row[0] or 0
            total_pnl = row[1] or 0.0
            total_comm = row[2] or 0.0

        pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"

        msg = (
            f"📊 This Week's Performance\n"
            f"{'─' * 30}\n"
            f"Sells: {sell_count}\n"
            f"{pnl_emoji} Total P&L: ${total_pnl:+,.2f}\n"
            f"💸 Commission: ${total_comm:,.2f}\n"
            f"📊 Net P&L: ${total_pnl - total_comm:+,.2f}"
        )

        await update.message.reply_text(msg)

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def cmd_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show market hours status."""
    if not is_authorized(update):
        return

    market = get_market_status()
    msg = (
        f"🏛️ US Market Status\n"
        f"{'─' * 30}\n"
        f"{market['emoji']} Status: {market['status']}\n"
        f"🕐 Time: {market['current_time_et']}\n"
        f"⏰ Next Open: {market['next_open_in']}\n"
        f"📅 Weekend: {'Yes' if market['is_weekend'] else 'No'}"
    )
    await update.message.reply_text(msg)


async def cmd_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show order queue status."""
    if not is_authorized(update):
        return

    queue = await get_queue_stats()
    msg = (
        f"📬 Order Queue\n"
        f"{'─' * 30}\n"
        f"🔴 Sell queue: {queue['sell_queue']}\n"
        f"🟢 Buy queue: {queue['buy_queue']}\n"
        f"⏳ Pending (market open): {queue['pending_queue']}\n"
        f"📊 Total: {queue['total']}"
    )
    await update.message.reply_text(msg)


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all current settings."""
    if not is_authorized(update):
        return

    try:
        s = await get_bot_settings()
        d = s.to_display_dict()

        status = "🔴 KILLED" if d["is_killed"] else ("🟡 PAUSED" if d["is_paused"] else "🟢 RUNNING")

        msg = (
            f"⚙️ Current Settings\n"
            f"{'─' * 30}\n"
            f"\n"
            f"Status: {status}\n"
            f"\n"
            f"💰 Buy Amount: ${d['buy_amount_usd']:.0f}\n"
            f"📊 Max Positions: {d['max_open_positions']}\n"
            f"📅 Max Daily Buys: {d['max_daily_buys']}\n"
            f"💵 Max Total Investment: ${d['max_total_investment']:,.0f}\n"
            f"🔄 Max Per Ticker: {d['max_per_ticker']}\n"
            f"🛑 Max Daily Loss: ${d['max_daily_loss']:,.0f}\n"
            f"🏦 Min Cash Reserve: ${d['min_cash_reserve']:,.0f}\n"
            f"\n"
            f"⏰ Regular Hours Only: {'Yes' if d['regular_hours_only'] else 'No'}\n"
            f"📥 Queue Outside Hours: {'Yes' if d['queue_outside_hours'] else 'No'}\n"
            f"\n"
            f"Change with /set_amount, /set_max_positions, etc."
        )

        await update.message.reply_text(msg)

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


# ============================================
# SETTING COMMANDS
# ============================================

async def _update_setting(update: Update, context, key: str, value_type: type, label: str):
    """Generic setting updater."""
    if not is_authorized(update):
        return

    if not context.args:
        await update.message.reply_text(f"Usage: /set_{key.replace('_', '')} <value>")
        return

    try:
        new_value = value_type(context.args[0])
        if new_value <= 0:
            await update.message.reply_text("❌ Value must be positive")
            return
    except ValueError:
        await update.message.reply_text(f"❌ Invalid value. Must be a {'number' if value_type == float else 'whole number'}")
        return

    old_settings = await get_bot_settings()
    old_value = getattr(old_settings, key)

    await update_bot_setting(key, new_value)

    await update.message.reply_text(
        f"✅ {label} updated\n"
        f"{'─' * 20}\n"
        f"Before: {old_value}\n"
        f"After: {new_value}"
    )


async def cmd_set_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set buy amount per order."""
    await _update_setting(update, context, "buy_amount_usd", float, "Buy Amount ($)")


async def cmd_set_max_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set max open positions."""
    await _update_setting(update, context, "max_open_positions", int, "Max Open Positions")


async def cmd_set_max_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set max daily buys."""
    await _update_setting(update, context, "max_daily_buys", int, "Max Daily Buys")


async def cmd_set_max_invest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set max total investment."""
    await _update_setting(update, context, "max_total_investment", float, "Max Total Investment ($)")


async def cmd_set_max_per_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set max buys per ticker."""
    await _update_setting(update, context, "max_per_ticker", int, "Max Buys Per Ticker")


async def cmd_set_max_loss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set max daily loss limit."""
    await _update_setting(update, context, "max_daily_loss", float, "Max Daily Loss ($)")


async def cmd_set_reserve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set minimum cash reserve."""
    await _update_setting(update, context, "min_cash_reserve", float, "Min Cash Reserve ($)")


# ============================================
# CONTROL COMMANDS
# ============================================

async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pause buying (sells still execute)."""
    if not is_authorized(update):
        return

    await update_bot_setting("is_paused", True)
    await update_bot_setting("is_killed", False)
    await update.message.reply_text(
        "🟡 Buying PAUSED\n"
        "Sells will still execute.\n"
        "Use /resume to restart buying."
    )


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resume all trading."""
    if not is_authorized(update):
        return

    await update_bot_setting("is_paused", False)
    await update_bot_setting("is_killed", False)
    await update.message.reply_text("🟢 Trading RESUMED — all operations active")


async def cmd_kill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Emergency stop ALL trading."""
    if not is_authorized(update):
        return

    await update_bot_setting("is_killed", True)
    await update.message.reply_text(
        "🔴 EMERGENCY STOP ACTIVATED\n"
        "ALL trading halted (buys AND sells).\n"
        "Use /resume to restart."
    )


async def cmd_sell_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sell ALL open positions."""
    if not is_authorized(update):
        return

    await update.message.reply_text(
        "⚠️ SELL ALL requested.\n"
        "Reply 'YES SELL ALL' to confirm."
    )

    # Store confirmation state
    context.user_data["awaiting_sell_all"] = True


async def cmd_clear_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear all order queues."""
    if not is_authorized(update):
        return

    await clear_all_queues()
    await update.message.reply_text("🗑️ All order queues cleared")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle non-command messages (for confirmations)."""
    if not is_authorized(update):
        return

    text = update.message.text.strip().upper()

    # Handle sell_all confirmation
    if context.user_data.get("awaiting_sell_all") and text == "YES SELL ALL":
        context.user_data["awaiting_sell_all"] = False

        await update.message.reply_text("🔄 Selling ALL positions...")

        try:
            from sqlalchemy import select, func
            from app.database.connection import get_session
            from app.models.position import Position, PositionStatus
            from app.queue.order_queue import enqueue_order

            async with get_session() as session:
                result = await session.execute(
                    select(func.distinct(Position.ticker)).where(
                        Position.status == PositionStatus.OPEN
                    )
                )
                tickers = [row[0] for row in result.all()]

            if not tickers:
                await update.message.reply_text("📭 No open positions to sell")
                return

            for ticker in tickers:
                await enqueue_order({"action": "SELL", "ticker": ticker, "alert_id": "manual_sell_all"})

            await update.message.reply_text(
                f"📤 {len(tickers)} SELL orders queued for processing"
            )

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    elif context.user_data.get("awaiting_sell_all"):
        context.user_data["awaiting_sell_all"] = False
        await update.message.reply_text("❌ Sell all cancelled")


# ============================================
# NOTIFICATION SENDER
# ============================================

async def send_notification(message: str):
    """
    Send a notification message to the configured Telegram chat.
    Called from other modules (worker, etc.).
    """
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.warning("Telegram not configured, skipping notification")
        return

    try:
        from telegram import Bot
        bot = Bot(token=settings.telegram_bot_token)
        await bot.send_message(
            chat_id=settings.telegram_chat_id,
            text=message,
        )
    except Exception as e:
        logger.error("Failed to send Telegram notification", error=str(e))


async def send_daily_report():
    """Send daily performance report."""
    try:
        from sqlalchemy import select, func
        from app.database.connection import get_session
        from app.models.trade import Trade, TradeSide, TradeStatus
        from app.models.position import Position, PositionStatus

        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        async with get_session() as session:
            # Today's stats
            buy_count = (await session.execute(
                select(func.count(Trade.id)).where(
                    Trade.side == TradeSide.BUY,
                    Trade.status == TradeStatus.FILLED,
                    Trade.created_at >= today_start,
                )
            )).scalar() or 0

            sell_result = await session.execute(
                select(
                    func.count(Trade.id),
                    func.sum(Trade.total_pnl_usd),
                    func.sum(Trade.commission),
                ).where(
                    Trade.side == TradeSide.SELL,
                    Trade.status == TradeStatus.FILLED,
                    Trade.created_at >= today_start,
                )
            )
            sell_row = sell_result.one()
            sell_count = sell_row[0] or 0
            total_pnl = sell_row[1] or 0.0
            total_comm = sell_row[2] or 0.0

            # Open positions
            open_count = (await session.execute(
                select(func.count(Position.id)).where(Position.status == PositionStatus.OPEN)
            )).scalar() or 0

            total_invested = (await session.execute(
                select(func.sum(Position.entry_amount_usd)).where(
                    Position.status == PositionStatus.OPEN
                )
            )).scalar() or 0.0

        pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"

        msg = (
            f"📊 Daily Report — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
            f"{'═' * 30}\n"
            f"\n"
            f"📈 Buys: {buy_count}\n"
            f"📉 Sells: {sell_count}\n"
            f"\n"
            f"{pnl_emoji} Gross P&L: ${total_pnl:+,.2f}\n"
            f"💸 Commission: ${total_comm:,.2f}\n"
            f"📊 Net P&L: ${total_pnl - total_comm:+,.2f}\n"
            f"\n"
            f"📂 Open Positions: {open_count}\n"
            f"💵 Total Invested: ${total_invested:,.0f}\n"
            f"{'═' * 30}"
        )

        await send_notification(msg)

    except Exception as e:
        logger.error("Failed to send daily report", error=str(e))


# ============================================
# BOT SETUP
# ============================================

async def setup_commands(app):
    """Register bot commands so they show up in Telegram's command menu."""
    commands = [
        BotCommand("start", "Show welcome & all commands"),
        BotCommand("help", "Show all commands"),
        BotCommand("status", "Bot status overview"),
        BotCommand("positions", "All open positions"),
        BotCommand("pnl", "Today's P&L"),
        BotCommand("pnl_week", "This week's P&L"),
        BotCommand("market", "Market hours status"),
        BotCommand("queue", "Order queue status"),
        BotCommand("settings", "View all settings"),
        BotCommand("set_amount", "Set buy amount ($)"),
        BotCommand("set_max_positions", "Max open positions"),
        BotCommand("set_max_daily", "Max daily buys"),
        BotCommand("set_max_invest", "Max total investment ($)"),
        BotCommand("set_max_per_ticker", "Max buys per ticker"),
        BotCommand("set_max_loss", "Max daily loss ($)"),
        BotCommand("set_reserve", "Min cash reserve ($)"),
        BotCommand("pause", "Pause buying"),
        BotCommand("resume", "Resume trading"),
        BotCommand("kill", "Emergency stop ALL"),
        BotCommand("sell_all", "Sell ALL positions"),
        BotCommand("clear_queue", "Clear order queue"),
    ]
    await app.bot.set_my_commands(commands)


def create_bot_app():
    """Create and configure the Telegram bot application."""
    if not settings.telegram_bot_token:
        logger.warning("Telegram bot token not configured")
        return None

    app = ApplicationBuilder().token(settings.telegram_bot_token).build()

    # Register command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("positions", cmd_positions))
    app.add_handler(CommandHandler("pnl", cmd_pnl))
    app.add_handler(CommandHandler("pnl_week", cmd_pnl_week))
    app.add_handler(CommandHandler("market", cmd_market))
    app.add_handler(CommandHandler("queue", cmd_queue))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("set_amount", cmd_set_amount))
    app.add_handler(CommandHandler("set_max_positions", cmd_set_max_positions))
    app.add_handler(CommandHandler("set_max_daily", cmd_set_max_daily))
    app.add_handler(CommandHandler("set_max_invest", cmd_set_max_invest))
    app.add_handler(CommandHandler("set_max_per_ticker", cmd_set_max_per_ticker))
    app.add_handler(CommandHandler("set_max_loss", cmd_set_max_loss))
    app.add_handler(CommandHandler("set_reserve", cmd_set_reserve))
    app.add_handler(CommandHandler("pause", cmd_pause))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("kill", cmd_kill))
    app.add_handler(CommandHandler("sell_all", cmd_sell_all))
    app.add_handler(CommandHandler("clear_queue", cmd_clear_queue))

    # Message handler for confirmations
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app


async def run_bot():
    """Run the Telegram bot."""
    await init_db()

    app = create_bot_app()
    if not app:
        logger.error("Cannot start bot: token not configured")
        return

    # Register commands in Telegram
    async with app:
        await setup_commands(app)
        await app.start()

        logger.info("Telegram bot started")
        await send_notification("🤖 Telegram bot started. Type /help for commands.")

        # Run polling
        await app.updater.start_polling(drop_pending_updates=True)

        # Keep running
        stop_event = asyncio.Event()

        def signal_handler(sig, frame):
            stop_event.set()

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        await stop_event.wait()

        await app.updater.stop()
        await app.stop()


if __name__ == "__main__":
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ]
    )

    asyncio.run(run_bot())
