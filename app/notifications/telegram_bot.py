"""
Telegram Bot for notifications and commands.
All settings adjustable via Telegram commands.
"""

import asyncio
import os
import re
import signal
import sys
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
import httpx
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
from app.database.connection import init_db, get_bot_settings, update_bot_setting, get_session
from app.risk.risk_manager import get_risk_summary
from app.queue.order_queue import get_queue_stats, clear_all_queues, get_waiting_ticker_stats, get_redis
from app.broker.market_hours import (
    ASIA_MARKET_SESSIONS,
    get_asia_market_status,
    get_market_status,
    get_krx_market_status,
    get_et_day_bounds_utc,
    get_et_week_bounds_utc,
    get_et_now,
)

logger = structlog.get_logger()

# Global reference for sending notifications from other modules
_bot_app = None
_notify_bot = None
_telegram_poller_instance_id = None
_notify_bot_lock = asyncio.Lock()
_notify_send_semaphore = asyncio.Semaphore(1)
_CONFIRM_STATE_KEY = "pending_action_confirm"
_CONFIRM_TTL_SECONDS = 120
_TELEGRAM_POLLER_LOCK_KEY = "telegram:poller_lock"
_TELEGRAM_POLLER_LOCK_TTL_SECONDS = 90


async def _acquire_telegram_poller_lock(instance_id: str):
    """Ensure only one in-house Telegram polling process is active."""
    redis_client = await get_redis()
    while True:
        acquired = await redis_client.set(
            _TELEGRAM_POLLER_LOCK_KEY,
            instance_id,
            ex=_TELEGRAM_POLLER_LOCK_TTL_SECONDS,
            nx=True,
        )
        if acquired:
            logger.info("Telegram poller lock acquired", instance_id=instance_id)
            return redis_client

        current_owner = await redis_client.get(_TELEGRAM_POLLER_LOCK_KEY)
        logger.warning(
            "Telegram poller lock already held; waiting for release",
            instance_id=instance_id,
            current_owner=current_owner,
        )
        await asyncio.sleep(5)


async def _renew_telegram_poller_lock(redis_client, instance_id: str, stop_event: asyncio.Event):
    """Refresh the Redis lock TTL while this process owns the poller."""
    try:
        while not stop_event.is_set():
            await asyncio.sleep(max(10, _TELEGRAM_POLLER_LOCK_TTL_SECONDS // 3))
            current_owner = await redis_client.get(_TELEGRAM_POLLER_LOCK_KEY)
            if current_owner != instance_id:
                logger.warning(
                    "Telegram poller lock ownership changed unexpectedly",
                    instance_id=instance_id,
                    current_owner=current_owner,
                )
                continue
            await redis_client.expire(_TELEGRAM_POLLER_LOCK_KEY, _TELEGRAM_POLLER_LOCK_TTL_SECONDS)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("Telegram poller lock renew failed", instance_id=instance_id, error=str(exc))


async def _release_telegram_poller_lock(redis_client, instance_id: str):
    """Release the Redis lock if it is still owned by this process."""
    try:
        current_owner = await redis_client.get(_TELEGRAM_POLLER_LOCK_KEY)
        if current_owner == instance_id:
            await redis_client.delete(_TELEGRAM_POLLER_LOCK_KEY)
            logger.info("Telegram poller lock released", instance_id=instance_id)
    except Exception as exc:
        logger.warning("Telegram poller lock release failed", instance_id=instance_id, error=str(exc))


async def _get_telegram_poller_health() -> dict:
    """Summarize Telegram polling lock state for /status."""
    try:
        redis_client = await get_redis()
        owner = await redis_client.get(_TELEGRAM_POLLER_LOCK_KEY)
        ttl = await redis_client.ttl(_TELEGRAM_POLLER_LOCK_KEY)
    except Exception as exc:
        return {"ok": False, "status": "확인실패", "error": str(exc), "owner": None, "ttl": None, "is_self": False}

    owner = str(owner or "").strip() or None
    is_self = bool(owner and _telegram_poller_instance_id and owner == _telegram_poller_instance_id)

    if not owner:
        status = "미확보"
    elif is_self:
        status = "정상"
    else:
        status = "다른 인스턴스 점유"

    ttl_value = None if ttl is None or int(ttl) < 0 else int(ttl)
    return {
        "ok": owner is not None,
        "status": status,
        "owner": owner,
        "ttl": ttl_value,
        "is_self": is_self,
    }


def _ko_market_status(status: str) -> str:
    """Convert market status code to Korean."""
    return {
        "OPEN": "정규장",
        "EXTENDED": "시간외",
        "CLOSED": "휴장",
    }.get(status, status)


def _ko_next_open(next_open: str) -> str:
    """Convert next-open text to Korean format."""
    if next_open == "NOW":
        return "지금"

    match = re.fullmatch(r"(\d+)h (\d+)m", next_open)
    if match:
        hours, minutes = match.groups()
        return f"{hours}시간 {minutes}분"

    return next_open


def _ko_yes_no(value: bool) -> str:
    """Convert boolean to Korean yes/no text."""
    return "예" if value else "아니오"


def _format_usd_with_krw(usd_amount: float, usdkrw_rate: float) -> str:
    """Format USD with optional KRW conversion."""
    if usdkrw_rate > 0:
        return f"${usd_amount:,.2f} ({usd_amount * usdkrw_rate:,.0f}원)"
    return f"${usd_amount:,.2f}"


def _format_signed_usd_with_krw(usd_amount: float, usdkrw_rate: float) -> str:
    sign = "+" if usd_amount >= 0 else "-"
    abs_amount = abs(float(usd_amount or 0.0))
    if usdkrw_rate > 0:
        return f"{sign}${abs_amount:,.2f} ({sign}{abs_amount * usdkrw_rate:,.0f}원)"
    return f"{sign}${abs_amount:,.2f}"


def _format_usd_as_krw(usd_amount: float, usdkrw_rate: float) -> str:
    amount = float(usd_amount or 0.0)
    if abs(amount) < 1e-9:
        return "0원"
    if usdkrw_rate <= 0:
        return "환율 조회 실패"
    return f"{amount * usdkrw_rate:,.0f}원"


def _format_signed_usd_as_krw(usd_amount: float, usdkrw_rate: float) -> str:
    amount = float(usd_amount or 0.0)
    if abs(amount) < 1e-9:
        return "0원"
    if usdkrw_rate <= 0:
        return "환율 조회 실패"
    return _format_signed_krw(amount * usdkrw_rate)


def _format_signed_krw(krw_amount: float) -> str:
    amount = float(krw_amount or 0.0)
    sign = "+" if amount >= 0 else "-"
    return f"{sign}{abs(amount):,.0f}원"


def _format_pending_buy_cash_shortage_block(coverage: dict) -> str:
    """Format a concise cash-shortage warning for the daily report."""
    order_count = int(coverage.get("order_count") or 0)
    if order_count <= 0:
        return ""

    if not coverage.get("ok"):
        error = str(coverage.get("error") or "가용금 조회 실패")
        return (
            "\n현금 확인 경고:\n"
            f"매수 대기: {order_count}건\n"
            f"상태: 가용금 확인 실패 ({error[:120]})\n"
        )

    if not coverage.get("shortage"):
        return ""

    if str(coverage.get("display_currency") or "").upper() == "KRW" or coverage.get("required_krw") is not None:
        def _krw_text(value: float) -> str:
            return f"{float(value or 0.0):,.0f}원"

        quote_unknown_count = int(coverage.get("quote_unknown_count") or 0)
        quote_note = (
            f"참고: 시세 미확인 {quote_unknown_count}건은 목표 매수금액 기준으로 추정\n"
            if quote_unknown_count > 0
            else ""
        )

        return (
            "\n현금 부족 경고:\n"
            f"매수 대기: {order_count}건\n"
            f"예상 필요: {_krw_text(float(coverage.get('required_krw') or 0.0))}\n"
            f"예비금 제외 가용: {_krw_text(float(coverage.get('available_after_reserve_krw') or 0.0))}\n"
            f"부족 예상: {_krw_text(float(coverage.get('shortage_krw') or 0.0))}\n"
            f"예상 가능: 약 {int(coverage.get('coverable_order_count') or 0)}/{order_count}건\n"
            f"{quote_note}"
        )

    usdkrw_rate = float(coverage.get("usdkrw_rate") or 0.0)

    def _usd_to_krw_text(value: float) -> str:
        if usdkrw_rate <= 0:
            return f"${float(value or 0.0):,.2f}"
        return f"{float(value or 0.0) * usdkrw_rate:,.0f}원"

    quote_unknown_count = int(coverage.get("quote_unknown_count") or 0)
    quote_note = (
        f"참고: 시세 미확인 {quote_unknown_count}건은 목표 매수금액 기준으로 추정\n"
        if quote_unknown_count > 0
        else ""
    )

    return (
        "\n현금 부족 경고:\n"
        f"매수 대기: {order_count}건\n"
        f"예상 필요: {_usd_to_krw_text(float(coverage.get('required_usd') or 0.0))}\n"
        f"예비금 제외 가용: {_usd_to_krw_text(float(coverage.get('available_after_reserve_usd') or 0.0))}\n"
        f"부족 예상: {_usd_to_krw_text(float(coverage.get('shortage_usd') or 0.0))}\n"
        f"예상 가능: 약 {int(coverage.get('coverable_order_count') or 0)}/{order_count}건\n"
        f"{quote_note}"
    )


def _short_status_reason(reason: Optional[str]) -> str:
    """Make audit/error reasons readable in Telegram status messages."""
    text = str(reason or "-").replace("\n", " ").strip()
    if not text or text == "-":
        return "-"
    if "no_open_position" in text or "보유 포지션이 없습니다" in text:
        return "보유 없음이라 정상 무시"
    if "미체결" in text and "취소" in text:
        return "미체결 후 취소됨"
    if "500 Internal Server Error" in text:
        return "KIS 일시 오류"
    if "Server disconnected" in text:
        return "KIS 연결 일시 끊김"
    if "손실 상태" in text or "sell_profit_only_hold" in text:
        return "손실 상태라 매도 보류"
    return text[:46]


def _format_pct(value: float) -> str:
    return f"{float(value or 0.0):+.2f}%"


def _build_ascii_trend_bar(value: float, max_abs: float, width: int = 8) -> str:
    amount = float(value or 0.0)
    if max_abs <= 0:
        return "-" * width
    filled = max(1, int(round((abs(amount) / max_abs) * width))) if amount != 0 else 0
    char = "+" if amount >= 0 else "-"
    return char * filled + "." * max(0, width - filled)


def _build_sparkline(values: list[float]) -> str:
    if not values:
        return "-"

    bars = "▁▂▃▄▅▆▇█"
    min_v = min(values)
    max_v = max(values)
    if max_v == min_v:
        return bars[0] * len(values)

    out = []
    span = max_v - min_v
    for value in values:
        idx = int(round(((value - min_v) / span) * (len(bars) - 1)))
        idx = max(0, min(len(bars) - 1, idx))
        out.append(bars[idx])
    return "".join(out)


def _to_float_or_zero(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_float_signed_or_zero(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _kis_order_exchange_to_quote_code(value: str) -> str:
    code = str(value or "").strip().upper()
    return {
        "NASD": "NAS",
        "NYSE": "NYS",
        "AMEX": "AMS",
        "SEHK": "HKS",
        "SHAA": "SHS",
        "SZAA": "SZS",
        "TKSE": "TSE",
    }.get(code, "")


def _kis_exchange_to_currency(value: str) -> str:
    code = str(value or "").strip().upper()
    return {
        "NAS": "USD",
        "NYS": "USD",
        "AMS": "USD",
        "NASD": "USD",
        "NYSE": "USD",
        "AMEX": "USD",
        "HKS": "HKD",
        "SEHK": "HKD",
        "SHS": "CNY",
        "SHAA": "CNY",
        "SZS": "CNY",
        "SZAA": "CNY",
        "TSE": "JPY",
        "TKSE": "JPY",
    }.get(code, "USD")


def _filled_trade_time_window(model, start_utc, end_utc):
    from sqlalchemy import and_, or_

    return or_(
        and_(
            model.filled_at.is_not(None),
            model.filled_at >= start_utc,
            model.filled_at < end_utc,
        ),
        and_(
            model.filled_at.is_(None),
            model.created_at >= start_utc,
            model.created_at < end_utc,
        ),
    )


async def _get_display_usdkrw_rate() -> tuple[float, str]:
    kis_result = await _fetch_kis_balance_snapshot()
    return await _resolve_usdkrw_rate(kis_result)


def _format_setting_value(key: str, value, usdkrw_rate: float) -> str:
    if key in {"buy_amount_usd", "max_total_investment", "min_cash_reserve"}:
        return _format_usd_with_krw(float(value or 0.0), usdkrw_rate)
    if isinstance(value, float):
        if value.is_integer():
            return f"{int(value):,}"
        return f"{value:,.4f}"
    return str(value)


async def _require_double_confirm(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    action_key: str,
    preview_text: str,
) -> bool:
    now_ts = datetime.now(timezone.utc).timestamp()
    pending = context.user_data.get(_CONFIRM_STATE_KEY)
    if pending:
        pending_key = str(pending.get("key", ""))
        expires_ts = float(pending.get("expires_ts", 0.0) or 0.0)
        if pending_key == action_key and now_ts <= expires_ts:
            context.user_data.pop(_CONFIRM_STATE_KEY, None)
            return True
        if now_ts > expires_ts:
            context.user_data.pop(_CONFIRM_STATE_KEY, None)

    context.user_data[_CONFIRM_STATE_KEY] = {
        "key": action_key,
        "expires_ts": now_ts + _CONFIRM_TTL_SECONDS,
    }
    await update.message.reply_text(
        "⚠️ 실행 전 확인\n"
        f"{preview_text}\n\n"
        f"{_CONFIRM_TTL_SECONDS // 60}분 안에 같은 명령어를 한 번 더 보내면 실행합니다.\n"
        "취소하려면 '취소'라고 입력하세요."
    )
    return False


def is_authorized(update: Update) -> bool:
    """Check if the message is from the authorized chat."""
    chat_id = str(update.effective_chat.id)
    return chat_id == settings.telegram_chat_id


def _format_allowlist_summary() -> str:
    """Keep Telegram settings readable even with hundreds of watchlist symbols."""
    allowed_tickers = settings.allowed_ticker_list
    if not allowed_tickers:
        return "전체 허용(미제한)"

    from app.gateway.symbol_mapper import is_kis_domestic_symbol, split_tv_ticker

    krx_count = sum(1 for ticker in allowed_tickers if is_kis_domestic_symbol(ticker))
    asia_count = sum(
        1
        for ticker in allowed_tickers
        if split_tv_ticker(ticker)[0] in ("HKEX", "SSE", "SZSE", "TSE")
    )
    us_count = len(allowed_tickers) - krx_count - asia_count
    return f"총 {len(allowed_tickers)}개 (미국 {us_count}개, 아시아 {asia_count}개, 국내 KRX {krx_count}개)"


# ============================================
# COMMAND HANDLERS
# ============================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message with all available commands."""
    if not is_authorized(update):
        return

    msg = """🤖 KIS Trading Bot

환영합니다. 사용 가능한 명령어입니다:

📊 상태/정보
/status - 현재 봇 상태
/balance - KIS 잔고 조회
/positions - 전체 보유 포지션
/pnl - 오늘 손익
/pnl_week - 이번 주 손익
/daily_report_now - 일일 리포트 즉시 전송
/market - 장 상태
/queue - 주문 큐 상태

⚙️ 설정
/settings - 현재 설정 보기
/set_amount <금액> - 매수 금액 설정
/set_max_positions <N> - 최대 보유 포지션 수
/set_max_daily <N> - 일일 최대 매수 횟수
/set_max_invest <금액> - 총 최대 투자금
/set_max_per_ticker <N> - 종목당 최대 매수 횟수
/set_reserve <금액> - 최소 현금 보유액

🔧 제어
/pause - 매수 일시중지 (매도는 계속)
/resume - 매수 재개
/kill - 전체 거래 긴급 중지
/sell_all - 수익 중 보유 포지션 매도 요청 (손실 종목 보류)
/clear_queue - 주문 큐 비우기

※ 설정/제어 명령은 실수 방지를 위해 같은 명령 2회 입력 시 실행됩니다.

/help - 이 도움말 표시"""

    await update.message.reply_text(msg)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Same as /start."""
    await cmd_start(update, context)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current bot status overview."""
    if not is_authorized(update):
        return

    try:
        from sqlalchemy import select, func
        from app.models.alert_log import AlertLog
        from app.models.trade import Trade, TradeSide, TradeStatus

        risk = await get_risk_summary()
        market = get_market_status()
        krx_market = get_krx_market_status()
        queue = await get_queue_stats()
        telegram_health = await _get_telegram_poller_health()
        today_start, today_end = get_et_day_bounds_utc()
        filled_window = _filled_trade_time_window(Trade, today_start, today_end)
        kis_portfolio = await _fetch_kis_portfolio_metrics(
            include_today_eval_pnl=True,
            quote_sample_limit=200,
        )

        async with get_session() as session:
            failed_alert_buy_count = (await session.execute(
                select(func.count(AlertLog.id)).where(
                    AlertLog.action == "BUY",
                    AlertLog.skipped.is_(True),
                    AlertLog.received_at >= today_start,
                    AlertLog.received_at < today_end,
                )
            )).scalar() or 0

            failed_alert_sell_count = (await session.execute(
                select(func.count(AlertLog.id)).where(
                    AlertLog.action == "SELL",
                    AlertLog.skipped.is_(True),
                    AlertLog.received_at >= today_start,
                    AlertLog.received_at < today_end,
                )
            )).scalar() or 0

            recent_failed_alert_rows = (await session.execute(
                select(
                    AlertLog.action,
                    AlertLog.ticker,
                    AlertLog.skip_reason,
                ).where(
                    AlertLog.skipped.is_(True),
                    AlertLog.received_at >= today_start,
                    AlertLog.received_at < today_end,
                ).order_by(AlertLog.id.desc()).limit(5)
            )).all()

            failed_trade_buy_count = (await session.execute(
                select(func.count(Trade.id)).where(
                    Trade.side == TradeSide.BUY,
                    Trade.status == TradeStatus.FAILED,
                    Trade.created_at >= today_start,
                    Trade.created_at < today_end,
                )
            )).scalar() or 0

            failed_trade_sell_count = (await session.execute(
                select(func.count(Trade.id)).where(
                    Trade.side == TradeSide.SELL,
                    Trade.status == TradeStatus.FAILED,
                    Trade.created_at >= today_start,
                    Trade.created_at < today_end,
                )
            )).scalar() or 0

            recent_failed_trade_rows = (await session.execute(
                select(
                    Trade.side,
                    Trade.ticker,
                    Trade.error_message,
                ).where(
                    Trade.status == TradeStatus.FAILED,
                    Trade.created_at >= today_start,
                    Trade.created_at < today_end,
                ).order_by(Trade.id.desc()).limit(5)
            )).all()

            sell_summary = (await session.execute(
                select(
                    func.sum(Trade.total_pnl_usd),
                    func.sum(Trade.commission),
                ).where(
                    Trade.side == TradeSide.SELL,
                    Trade.status == TradeStatus.FILLED,
                    filled_window,
                )
            )).one()

        # Status emoji
        if risk["is_killed"]:
            bot_status = "🔴 긴급중지"
        elif risk["is_paused"]:
            bot_status = "🟡 일시중지"
        else:
            bot_status = "🟢 실행중"

        usdkrw_rate, _ = await _get_display_usdkrw_rate()
        if kis_portfolio.get("ok"):
            kis_usd_exrt = float(kis_portfolio.get("usd_exrt", 0.0) or 0.0)
            if kis_usd_exrt > 0:
                usdkrw_rate = kis_usd_exrt
        realized_gross = float(sell_summary[0] or 0.0)
        realized_comm = float(sell_summary[1] or 0.0)
        realized_net = realized_gross - realized_comm
        pnl_emoji = "🟢" if realized_net >= 0 else "🔴"
        account_summary_block = ""
        if kis_portfolio.get("ok"):
            total_asset_krw = float(kis_portfolio.get("total_asset_krw", 0.0) or 0.0)
            purchase_krw = float(kis_portfolio.get("invested_krw", 0.0) or 0.0)
            cash_krw = float(kis_portfolio.get("cash_krw", 0.0) or 0.0)
            eval_pnl_krw = float(kis_portfolio.get("today_eval_pnl_krw", 0.0) or 0.0)
            eval_pnl_pct = float(kis_portfolio.get("today_eval_pnl_pct", 0.0) or 0.0)
            account_day_pnl_krw = eval_pnl_krw + (realized_net * usdkrw_rate)
            account_day_emoji = "🟢" if account_day_pnl_krw >= 0 else "🔴"
            eval_emoji = "🟢" if eval_pnl_krw >= 0 else "🔴"
            account_summary_block = (
                f"\n"
                f"💎 총자산: {total_asset_krw:,.0f}원\n"
                f"💵 매입금액: {purchase_krw:,.0f}원\n"
                f"💰 예수금: {cash_krw:,.0f}원\n"
                f"{eval_emoji} 보유 평가손익: {_format_signed_krw(eval_pnl_krw)} ({eval_pnl_pct:+.2f}%)\n"
                f"{account_day_emoji} 오늘 계좌손익: {_format_signed_krw(account_day_pnl_krw)}\n"
            )

        alert_fail_total = failed_alert_buy_count + failed_alert_sell_count
        telegram_status_icon = "🟢" if telegram_health.get("is_self") else ("🟡" if telegram_health.get("owner") else "🔴")
        telegram_ttl = telegram_health.get("ttl")
        telegram_ttl_text = f"{telegram_ttl}초" if isinstance(telegram_ttl, int) else "-"
        telegram_owner = telegram_health.get("owner") or "-"
        if len(telegram_owner) > 28:
            telegram_owner = telegram_owner[:28] + "..."
        if recent_failed_alert_rows:
            recent_alert_fail_line_items = []
            for action, ticker, reason in recent_failed_alert_rows:
                cleaned_reason = _short_status_reason(reason)
                recent_alert_fail_line_items.append(f"- {action} {ticker}: {cleaned_reason}")
            recent_alert_fail_lines = "\n".join(recent_alert_fail_line_items)
        else:
            recent_alert_fail_lines = "없음"

        trade_fail_total = failed_trade_buy_count + failed_trade_sell_count
        if recent_failed_trade_rows:
            recent_trade_fail_line_items = []
            for side, ticker, reason in recent_failed_trade_rows:
                side_text = side.value if hasattr(side, "value") else str(side)
                cleaned_reason = _short_status_reason(reason)
                recent_trade_fail_line_items.append(f"- {side_text} {ticker}: {cleaned_reason}")
            recent_trade_fail_lines = "\n".join(recent_trade_fail_line_items)
        else:
            recent_trade_fail_lines = "없음"

        system_health_line = "현재 시스템 이상: 없음"
        if risk["is_killed"]:
            system_health_line = "현재 시스템 이상: 긴급중지 상태"
        elif telegram_health.get("status") != "정상":
            system_health_line = f"현재 시스템 이상: 텔레그램 폴러 {telegram_health.get('status')}"
        elif queue["processing_queue"] > 0:
            system_health_line = f"현재 시스템 상태: 주문 처리중 {queue['processing_queue']}건"

        msg = (
            f"📊 봇 상태: {bot_status}\n"
            f"{'─' * 30}\n"
            f"{system_health_line}\n"
            f"\n"
            f"💰 매수 금액: {_format_usd_with_krw(risk['buy_amount'], usdkrw_rate)}\n"
            f"\n"
            f"📈 보유 포지션: {risk['open_positions']}/{risk['max_open_positions']}\n"
            f"🏷️ 보유 종목 수: {risk['unique_tickers']}\n"
            f"💵 총 투자금: {_format_usd_with_krw(risk['total_invested'], usdkrw_rate)} / "
            f"{_format_usd_with_krw(risk['max_investment'], usdkrw_rate)}\n"
            f"\n"
            f"📅 오늘 매수: {risk['today_buys']}/{risk['max_daily_buys']}\n"
            f"{pnl_emoji} 오늘 실현 순손익: {_format_signed_usd_with_krw(realized_net, usdkrw_rate)}\n"
            f"\n"
            f"{market['emoji']} 미국장: {_ko_market_status(market['status'])} ({market['current_time_et']}) / "
            f"다음 {_ko_next_open(market['next_open_in'])}\n"
            f"{krx_market['emoji']} 한국장: {_ko_market_status(krx_market['status'])} ({krx_market['current_time_kst']}) / "
            f"다음 {_ko_next_open(krx_market['next_open_in'])}\n"
            f"{account_summary_block}"
            f"\n"
            f"📬 큐: 매도 {queue['sell_queue']}건, 매수 {queue['buy_queue']}건, "
            f"대기 {queue['pending_queue']}건(미국 {queue.get('pending_us', 0)} / 아시아 {queue.get('pending_asia', 0)} / 한국 {queue.get('pending_krx', 0)} / 만료대상 {queue.get('pending_expired', 0)}), "
            f"처리중 {queue['processing_queue']}건\n"
            f"{telegram_status_icon} 텔레그램 폴러: {telegram_health['status']} (TTL {telegram_ttl_text})\n"
            f"🪪 폴러 소유자: {telegram_owner}\n"
            f"\n"
            f"🧾 오늘 주문 실패 기록: 매수 {failed_trade_buy_count}건, 매도 {failed_trade_sell_count}건 "
            f"(총 {trade_fail_total}건)\n"
            f"최근 실패 기록 5건:\n{recent_trade_fail_lines}\n"
            f"\n"
            f"🧾 오늘 처리 제외 알림: 매수 {failed_alert_buy_count}건, 매도 {failed_alert_sell_count}건 "
            f"(총 {alert_fail_total}건)\n"
            f"최근 처리 제외 5건:\n{recent_alert_fail_lines}"
        )

        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"❌ 상태 조회 중 오류: {str(e)}")


async def _fetch_ib_balance_snapshot() -> dict:
    """Fetch IBKR cash/equity snapshot for Telegram /balance."""
    from app.broker.ib_client import get_ib_client

    try:
        ib = await asyncio.wait_for(get_ib_client(), timeout=8.0)
    except Exception as e:
        return {"ok": False, "error": f"IBKR 연결 실패: {str(e)}"}

    if not ib.is_connected:
        return {"ok": False, "error": "IBKR 미연결 상태입니다"}

    try:
        summary = await asyncio.wait_for(ib.get_account_summary(), timeout=8.0)
    except Exception as e:
        return {"ok": False, "error": f"IBKR 잔고 조회 실패: {str(e)}"}

    return {
        "ok": True,
        "available_funds": float(summary.get("AvailableFunds", 0.0) or 0.0),
        "total_cash_value": float(summary.get("TotalCashValue", 0.0) or 0.0),
        "net_liquidation": float(summary.get("NetLiquidation", 0.0) or 0.0),
        "buying_power": float(summary.get("BuyingPower", 0.0) or 0.0),
    }


async def _fetch_kis_balance_snapshot() -> dict:
    """Fetch KIS overseas buying power snapshot for Telegram /balance."""
    from app.broker.kis_client import get_kis_client

    try:
        kis = await asyncio.wait_for(get_kis_client(), timeout=5.0)
    except Exception as e:
        return {"ok": False, "error": f"KIS 클라이언트 오류: {str(e)}"}

    if not kis.is_configured:
        return {"ok": False, "error": "KIS 설정 누락 (.env의 KIS_* 값 필요)"}

    try:
        funds = await asyncio.wait_for(
            kis.get_effective_usd_orderable(symbol="AAPL", order_price=1.0),
            timeout=10.0,
        )
    except Exception as e:
        return {"ok": False, "error": f"KIS 잔고 조회 실패: {str(e)}"}

    usd_exrt = float(funds.get("usd_exrt", 0.0) or 0.0)
    effective_usd = float(funds.get("effective_usd", 0.0) or 0.0)
    effective_krw = effective_usd * usd_exrt if usd_exrt > 0 else 0.0
    stock_cash_objt_krw = float(funds.get("stock_cash_objt_krw", 0.0) or 0.0)
    stock_eval_objt_krw = float(funds.get("stock_eval_objt_krw", 0.0) or 0.0)
    total_asset_objt_krw = float(funds.get("total_asset_objt_krw", 0.0) or 0.0)

    total_eval_usd = 0.0
    balance_rows = []
    try:
        balance_rows = await asyncio.wait_for(kis.get_overseas_balance(), timeout=10.0)
        for row in balance_rows:
            if not isinstance(row, dict):
                continue
            try:
                total_eval_usd += float(row.get("ovrs_stck_evlu_amt") or 0.0)
            except (TypeError, ValueError):
                continue
    except Exception:
        # Balance detail is auxiliary for display; do not fail whole command.
        balance_rows = []

    total_eval_krw = total_eval_usd * usd_exrt if usd_exrt > 0 else 0.0
    total_asset_krw_est = total_asset_objt_krw
    if total_asset_krw_est <= 0:
        total_asset_krw_est = stock_cash_objt_krw + stock_eval_objt_krw
    # Some KIS responses return 0 for stock_eval_objt_krw even with open overseas positions.
    if stock_eval_objt_krw <= 0 and total_eval_krw > 0 and stock_cash_objt_krw > 0:
        total_asset_krw_est = max(total_asset_krw_est, stock_cash_objt_krw + total_eval_krw)

    return {
        "ok": True,
        "effective_usd": effective_usd,
        "effective_krw": float(effective_krw),
        "direct_ovrs_usd": float(funds.get("direct_ovrs_usd", 0.0) or 0.0),
        "direct_frcr_usd": float(funds.get("direct_frcr_usd", 0.0) or 0.0),
        "integrated_usd": float(funds.get("integrated_usd", 0.0) or 0.0),
        "integrated_krw": float(funds.get("integrated_krw", 0.0) or 0.0),
        "usd_exrt": usd_exrt,
        "integrated_mode": str(funds.get("integrated_mode", "") or ""),
        "stock_cash_objt_krw": stock_cash_objt_krw,
        "stock_eval_objt_krw": stock_eval_objt_krw,
        "stock_cash_use_krw": float(funds.get("stock_cash_use_krw", 0.0) or 0.0),
        "stock_eval_use_krw": float(funds.get("stock_eval_use_krw", 0.0) or 0.0),
        "total_asset_objt_krw": total_asset_objt_krw,
        "total_asset_krw_est": float(total_asset_krw_est),
        "total_asset_use_krw": float(funds.get("total_asset_use_krw", 0.0) or 0.0),
        "overseas_eval_usd": float(total_eval_usd),
        "overseas_eval_krw": float(total_eval_krw),
        "overseas_positions": int(len(balance_rows)),
    }


async def _fetch_kis_portfolio_metrics(
    *,
    include_today_eval_pnl: bool = False,
    quote_sample_limit: int = 200,
) -> dict:
    """
    Fetch KIS holdings-based portfolio metrics.
    - invested_usd: purchase principal (sum of frcr_pchs_amt1 fallback avg*qty)
    - market_value_usd: current evaluation amount (sum of ovrs_stck_evlu_amt)
    - unrealized_total_pnl_usd: total unrealized P&L from KIS rows
    - today_eval_pnl_usd: mark-to-market daily change based on (last - prev_close) * qty
    """
    from app.broker.kis_client import get_kis_client

    try:
        kis = await asyncio.wait_for(get_kis_client(), timeout=5.0)
    except Exception as e:
        return {"ok": False, "error": f"KIS 클라이언트 오류: {str(e)}"}

    if not kis.is_configured:
        return {"ok": False, "error": "KIS 설정 누락 (.env의 KIS_* 값 필요)"}

    overseas_error = None
    try:
        rows = await asyncio.wait_for(kis.get_overseas_balance(), timeout=12.0)
    except Exception as e:
        overseas_error = str(e)
        logger.debug("KIS overseas balance fetch failed for portfolio metrics", error=overseas_error)
        rows = []

    try:
        domestic_rows = await asyncio.wait_for(kis.get_domestic_balance(), timeout=12.0)
    except Exception as e:
        logger.debug("KIS domestic balance fetch failed for portfolio metrics", error=str(e))
        domestic_rows = []

    if not rows and not domestic_rows and overseas_error:
        return {"ok": False, "error": f"KIS 보유내역 조회 실패: {overseas_error}"}

    currency_rates = {"KRW": 1.0}
    for currency in ("USD", "HKD", "CNY", "JPY"):
        try:
            rate_snapshot = await asyncio.wait_for(
                kis.get_integrated_margin_currency_orderable(currency),
                timeout=10.0,
            )
            rate = max(_to_float_or_zero(rate_snapshot.get("exchange_rate_krw")), 0.0)
            if rate > 0:
                currency_rates[currency] = rate
        except Exception as e:
            logger.debug("KIS currency rate fetch failed for portfolio metrics", currency=currency, error=str(e))

    holdings = []
    invested_usd_rows = 0.0
    market_value_usd_rows = 0.0
    unrealized_total_pnl_usd_rows = 0.0
    invested_krw_rows = 0.0
    market_value_krw_rows = 0.0
    unrealized_total_pnl_krw_rows = 0.0

    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(
            row.get("ovrs_pdno")
            or row.get("pdno")
            or row.get("item_cd")
            or ""
        ).strip().upper()
        qty = max(
            _to_float_or_zero(
                row.get("ovrs_cblc_qty")
                or row.get("cblc_qty")
                or row.get("hold_qty")
                or row.get("blce_qty")
            ),
            0.0,
        )
        if not symbol or qty <= 0:
            continue

        exchange_code = str(row.get("ovrs_excg_cd") or row.get("excg_cd") or "").strip().upper()
        currency = _kis_exchange_to_currency(exchange_code)
        row_rate = max(
            _to_float_or_zero(
                row.get("frst_bltn_exrt")
                or row.get("bass_exrt")
                or row.get("aply_exrt")
                or row.get("exrt")
            ),
            0.0,
        )
        krw_rate = row_rate or float(currency_rates.get(currency, 0.0) or 0.0)

        now_price = max(_to_float_or_zero(row.get("now_pric2")), 0.0)
        purchase_usd = _to_float_or_zero(row.get("frcr_pchs_amt1"))
        if purchase_usd <= 0:
            avg_price = max(_to_float_or_zero(row.get("pchs_avg_pric")), 0.0)
            if avg_price > 0:
                purchase_usd = avg_price * qty

        eval_usd = max(_to_float_or_zero(row.get("ovrs_stck_evlu_amt")), 0.0)
        unrealized_usd = _to_float_or_zero(row.get("frcr_evlu_pfls_amt"))
        if unrealized_usd == 0.0 and eval_usd > 0 and purchase_usd > 0:
            unrealized_usd = eval_usd - purchase_usd

        invested_usd_rows += max(purchase_usd, 0.0)
        market_value_usd_rows += eval_usd
        unrealized_total_pnl_usd_rows += unrealized_usd
        if krw_rate > 0:
            invested_krw_rows += max(purchase_usd, 0.0) * krw_rate
            market_value_krw_rows += eval_usd * krw_rate
            unrealized_total_pnl_krw_rows += unrealized_usd * krw_rate
        holdings.append(
            {
                "symbol": symbol,
                "qty": qty,
                "now_price": now_price,
                "currency": currency,
                "quote_exchange_hint": _kis_order_exchange_to_quote_code(row.get("ovrs_excg_cd")),
            }
        )

    for row in domestic_rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("pdno") or row.get("PDNO") or "").strip().upper()
        qty = max(
            _to_float_or_zero(
                row.get("hldg_qty")
                or row.get("ord_psbl_qty")
                or row.get("cblc_qty")
            ),
            0.0,
        )
        if not symbol or qty <= 0:
            continue
        purchase_krw = _to_float_or_zero(row.get("pchs_amt"))
        eval_krw = _to_float_or_zero(row.get("evlu_amt"))
        pnl_krw = _to_float_signed_or_zero(row.get("evlu_pfls_amt"))
        if purchase_krw <= 0:
            avg_price = _to_float_or_zero(row.get("pchs_avg_pric"))
            if avg_price > 0:
                purchase_krw = avg_price * qty
        if eval_krw <= 0:
            now_price = _to_float_or_zero(row.get("prpr"))
            if now_price > 0:
                eval_krw = now_price * qty
        if pnl_krw == 0.0 and eval_krw > 0 and purchase_krw > 0:
            pnl_krw = eval_krw - purchase_krw

        invested_krw_rows += max(purchase_krw, 0.0)
        market_value_krw_rows += max(eval_krw, 0.0)
        unrealized_total_pnl_krw_rows += pnl_krw
        holdings.append(
            {
                "symbol": f"KRX:{symbol}",
                "qty": qty,
                "now_price": _to_float_or_zero(row.get("prpr")),
                "currency": "KRW",
                "quote_exchange_hint": "KRX",
            }
        )

    summary_ok = bool(rows or domestic_rows)
    usd_rate_for_display = float(currency_rates.get("USD", 0.0) or 0.0)
    invested_usd = invested_krw_rows / usd_rate_for_display if usd_rate_for_display > 0 else invested_usd_rows
    market_value_usd = market_value_krw_rows / usd_rate_for_display if usd_rate_for_display > 0 else market_value_usd_rows
    unrealized_total_pnl_usd = (
        unrealized_total_pnl_krw_rows / usd_rate_for_display
        if usd_rate_for_display > 0
        else unrealized_total_pnl_usd_rows
    )
    eval_pnl_pct = (
        (unrealized_total_pnl_krw_rows / invested_krw_rows) * 100.0
        if invested_krw_rows > 0
        else 0.0
    )

    usd_exrt = 0.0
    cash_krw = 0.0
    integrated_total_asset_krw = 0.0
    try:
        seed_symbol = next((h["symbol"] for h in holdings if h.get("currency") != "KRW"), "AAPL")
        funds = await asyncio.wait_for(
            kis.get_effective_usd_orderable(symbol=seed_symbol, order_price=1.0),
            timeout=10.0,
        )
        usd_exrt = max(_to_float_or_zero(funds.get("usd_exrt")), 0.0)
        cash_krw = max(_to_float_or_zero(funds.get("stock_cash_objt_krw")), 0.0)
        integrated_total_asset_krw = max(_to_float_or_zero(funds.get("total_asset_objt_krw")), 0.0)
    except Exception:
        usd_exrt = float(currency_rates.get("USD", 0.0) or 0.0)
        cash_krw = 0.0
        integrated_total_asset_krw = 0.0

    if usd_exrt <= 0 and usd_rate_for_display > 0:
        usd_exrt = usd_rate_for_display

    invested_krw = invested_krw_rows
    market_value_krw = market_value_krw_rows
    eval_pnl_krw = unrealized_total_pnl_krw_rows

    computed_total_asset_krw = max(cash_krw, 0.0) + max(market_value_krw, 0.0)
    total_asset_krw = computed_total_asset_krw if computed_total_asset_krw > 0 else integrated_total_asset_krw

    return {
        "ok": True,
        "summary_ok": summary_ok,
        "position_count": len(holdings),
        "invested_usd": round(invested_usd, 2),
        "invested_krw": round(invested_krw, 0),
        "market_value_usd": round(market_value_usd, 2),
        "market_value_krw": round(market_value_krw, 0),
        "unrealized_total_pnl_usd": round(unrealized_total_pnl_usd, 2),
        "unrealized_total_pnl_krw": round(eval_pnl_krw, 0),
        "unrealized_total_pnl_pct": round(eval_pnl_pct, 4),
        # 사용자 앱 기준의 "당일 평가손익"은 KIS 잔고 요약의 현재 평가손익 합계에 맞춘다.
        "today_eval_pnl_usd": round(unrealized_total_pnl_usd, 2),
        "today_eval_pnl_krw": round(eval_pnl_krw, 0),
        "today_eval_pnl_pct": round(eval_pnl_pct, 4),
        "cash_krw": round(cash_krw, 0),
        "total_asset_krw": round(total_asset_krw, 0),
        "usd_exrt": usd_exrt,
    }


async def _upsert_kis_portfolio_snapshot(kis_portfolio: dict) -> Optional[dict]:
    """Persist or refresh today's KIS balance snapshot for trend reporting."""
    if not kis_portfolio.get("ok"):
        return None

    from sqlalchemy import select
    from app.models.portfolio_snapshot import PortfolioSnapshot

    snapshot_date = get_et_now().date()
    payload = {
        "total_asset_krw": float(kis_portfolio.get("total_asset_krw", 0.0) or 0.0),
        "purchase_amount_krw": float(kis_portfolio.get("invested_krw", 0.0) or 0.0),
        "cash_krw": float(kis_portfolio.get("cash_krw", 0.0) or 0.0),
        "today_eval_pnl_krw": float(kis_portfolio.get("today_eval_pnl_krw", 0.0) or 0.0),
        "today_eval_pnl_pct": float(kis_portfolio.get("today_eval_pnl_pct", 0.0) or 0.0),
        "captured_at": datetime.now(timezone.utc),
    }

    async with get_session() as session:
        result = await session.execute(
            select(PortfolioSnapshot).where(
                PortfolioSnapshot.snapshot_date == snapshot_date,
                PortfolioSnapshot.broker == "KIS",
            )
        )
        snapshot = result.scalar_one_or_none()
        if snapshot is None:
            snapshot = PortfolioSnapshot(
                snapshot_date=snapshot_date,
                broker="KIS",
                **payload,
            )
            session.add(snapshot)
        else:
            for key, value in payload.items():
                setattr(snapshot, key, value)

    return {
        "snapshot_date": snapshot_date,
        "broker": "KIS",
        **payload,
    }


async def _fetch_recent_balance_snapshot_series(days: int = 7) -> list[dict]:
    """Return recent KIS balance-trend snapshots for the daily report."""
    from sqlalchemy import desc, select
    from app.models.portfolio_snapshot import PortfolioSnapshot

    count = max(1, int(days or 7))
    async with get_session() as session:
        result = await session.execute(
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.broker == "KIS")
            .order_by(desc(PortfolioSnapshot.snapshot_date))
            .limit(count)
        )
        rows = list(result.scalars().all())

    rows.reverse()
    return [
        {
            "label": row.snapshot_date.strftime("%m-%d"),
            "snapshot_date": row.snapshot_date.isoformat(),
            "today_eval_pnl_krw": float(row.today_eval_pnl_krw or 0.0),
            "today_eval_pnl_pct": float(row.today_eval_pnl_pct or 0.0),
            "total_asset_krw": float(row.total_asset_krw or 0.0),
            "purchase_amount_krw": float(row.purchase_amount_krw or 0.0),
            "cash_krw": float(row.cash_krw or 0.0),
        }
        for row in rows
    ]


async def _fetch_all_time_total_pnl_snapshot_series(usdkrw_rate: float) -> list[dict]:
    """
    Return all saved KIS total-P&L trend snapshots.

    Total P&L for a saved date is cumulative realized SELL P&L through
    that ET date + that day's saved KIS holdings evaluation P&L.
    The displayed percentage uses one latest capital basis for the whole
    series so the trend does not jump only because more cash/positions were
    added later.
    """
    from sqlalchemy import select
    from app.models.portfolio_snapshot import PortfolioSnapshot
    from app.models.trade import Trade, TradeSide, TradeStatus

    et_tz = get_et_now().tzinfo
    rate = float(usdkrw_rate or 0.0)

    async with get_session() as session:
        snapshot_result = await session.execute(
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.broker == "KIS")
            .order_by(PortfolioSnapshot.snapshot_date)
        )
        snapshots = list(snapshot_result.scalars().all())

        trade_result = await session.execute(
            select(Trade).where(
                Trade.side == TradeSide.SELL,
                Trade.status == TradeStatus.FILLED,
            )
        )
        sell_trades = list(trade_result.scalars().all())

    if not snapshots:
        return []

    realized_by_date: dict = {}
    for trade in sell_trades:
        ts = trade.filled_at or trade.created_at
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        trade_date = ts.astimezone(et_tz).date()
        realized_net_usd = float(trade.total_pnl_usd or 0.0) - float(trade.commission or 0.0)
        realized_by_date[trade_date] = realized_by_date.get(trade_date, 0.0) + realized_net_usd

    realized_items = sorted(realized_by_date.items())
    realized_idx = 0
    cumulative_realized_usd = 0.0
    series = []

    for row in snapshots:
        while realized_idx < len(realized_items) and realized_items[realized_idx][0] <= row.snapshot_date:
            cumulative_realized_usd += float(realized_items[realized_idx][1] or 0.0)
            realized_idx += 1

        realized_krw = cumulative_realized_usd * rate if rate > 0 else 0.0
        holding_eval_krw = float(row.today_eval_pnl_krw or 0.0)
        total_pnl_krw = realized_krw + holding_eval_krw
        basis_krw = max(
            float(row.purchase_amount_krw or 0.0),
            float(row.total_asset_krw or 0.0) - total_pnl_krw,
            0.0,
        )

        series.append(
            {
                "label": row.snapshot_date.strftime("%m-%d"),
                "snapshot_date": row.snapshot_date.isoformat(),
                "total_pnl_krw": round(total_pnl_krw, 0),
                "basis_krw": round(basis_krw, 0),
                "total_pnl_pct": 0.0,
                "realized_krw": round(realized_krw, 0),
                "holding_eval_krw": round(holding_eval_krw, 0),
            }
        )

    display_basis_krw = next(
        (
            float(item["basis_krw"] or 0.0)
            for item in reversed(series)
            if float(item["basis_krw"] or 0.0) > 0
        ),
        0.0,
    )
    if display_basis_krw > 0:
        for item in series:
            total_pnl_krw = float(item["total_pnl_krw"] or 0.0)
            item["basis_krw"] = round(display_basis_krw, 0)
            item["total_pnl_pct"] = round((total_pnl_krw / display_basis_krw) * 100.0, 4)

    return series


async def _fetch_investment_start_date_label() -> Optional[str]:
    """Return the ET date of the first actual buy fill, if available."""
    from sqlalchemy import select
    from app.models.trade import Trade, TradeSide, TradeStatus

    et_tz = get_et_now().tzinfo
    async with get_session() as session:
        result = await session.execute(
            select(Trade).where(
                Trade.side == TradeSide.BUY,
                Trade.status.in_([TradeStatus.FILLED, TradeStatus.PARTIAL]),
            )
        )
        buy_trades = list(result.scalars().all())

    first_ts = None
    for trade in buy_trades:
        ts = trade.filled_at or trade.created_at
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if first_ts is None or ts < first_ts:
            first_ts = ts

    if first_ts is None:
        return None
    return first_ts.astimezone(et_tz).strftime("%Y-%m-%d")


def _format_investment_elapsed_line(start_date_label: Optional[str]) -> str:
    """Return a concise investment age line for the daily report footer."""
    if not start_date_label:
        return ""

    try:
        start_date = datetime.strptime(start_date_label[:10], "%Y-%m-%d").date()
    except ValueError:
        return ""

    inclusive_end_date = get_et_now().date() + timedelta(days=1)
    if inclusive_end_date <= start_date:
        return ""

    years = inclusive_end_date.year - start_date.year
    months = inclusive_end_date.month - start_date.month
    days = inclusive_end_date.day - start_date.day

    if days < 0:
        previous_month_end = inclusive_end_date.replace(day=1) - timedelta(days=1)
        days += previous_month_end.day
        months -= 1

    if months < 0:
        years -= 1
        months += 12

    if years < 0:
        return ""

    return f"\n투자한지 {years}년, {months}개월 {days}일 째..!\n"


async def _fetch_recent_daily_pnl_series(days: int = 7) -> list[dict]:
    """
    Return recent ET-day realized net P&L series.
    Net P&L = realized sell pnl - commission.
    """
    from sqlalchemy import select, func
    from app.database.connection import get_session
    from app.models.trade import Trade, TradeSide, TradeStatus

    count = max(1, int(days or 7))
    now_utc = datetime.now(timezone.utc)
    series = []

    async with get_session() as session:
        for day_offset in range(count - 1, -1, -1):
            ref_utc = now_utc - timedelta(days=day_offset)
            day_start, day_end = get_et_day_bounds_utc(now_utc=ref_utc)
            filled_window = _filled_trade_time_window(Trade, day_start, day_end)

            result = await session.execute(
                select(
                    func.sum(Trade.total_pnl_usd),
                    func.sum(Trade.commission),
                ).where(
                    Trade.side == TradeSide.SELL,
                    Trade.status == TradeStatus.FILLED,
                    filled_window,
                )
            )
            row = result.one()
            gross_pnl = float(row[0] or 0.0)
            commission = float(row[1] or 0.0)
            net_pnl = gross_pnl - commission
            label = day_start.astimezone(get_et_now().tzinfo).strftime("%m-%d")
            series.append(
                {
                    "label": label,
                    "gross_pnl_usd": round(gross_pnl, 2),
                    "commission_usd": round(commission, 2),
                    "net_pnl_usd": round(net_pnl, 2),
                }
            )

    return series


async def _resolve_usdkrw_rate(kis_result: dict) -> tuple[float, str]:
    """
    Resolve USD/KRW rate for display.
    Priority: KIS reported rate -> public FX fallback.
    """
    if kis_result.get("ok"):
        kis_rate = float(kis_result.get("usd_exrt", 0.0) or 0.0)
        if kis_rate > 0:
            return kis_rate, "KIS"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://api.frankfurter.app/latest",
                params={"from": "USD", "to": "KRW"},
            )
            resp.raise_for_status()
            data = resp.json()
            rate = float((data.get("rates") or {}).get("KRW") or 0.0)
            if rate > 0:
                return rate, "FRANKFURTER"
    except Exception:
        pass

    return 0.0, "-"


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show KIS balance/cash snapshot."""
    if not is_authorized(update):
        return

    kis_result = await _fetch_kis_balance_snapshot()
    usdkrw_rate, usdkrw_source = await _resolve_usdkrw_rate(kis_result)
    rate_line = (
        f"{usdkrw_rate:,.4f} [{usdkrw_source}]"
        if usdkrw_rate > 0
        else f"조회실패 [{usdkrw_source}]"
    )

    if kis_result.get("ok"):
        mode_text = kis_result.get("integrated_mode") or "-"
        stock_cash_objt_krw = float(kis_result.get("stock_cash_objt_krw", 0.0) or 0.0)
        stock_eval_objt_krw = float(kis_result.get("stock_eval_objt_krw", 0.0) or 0.0)
        stock_eval_display_krw = (
            stock_eval_objt_krw
            if stock_eval_objt_krw > 0
            else float(kis_result.get("overseas_eval_krw", 0.0) or 0.0)
        )
        total_asset_objt_krw = float(kis_result.get("total_asset_krw_est", 0.0) or 0.0)

        kis_text = (
            f"💎 총자산(추정): {total_asset_objt_krw:,.0f}원\n"
            f"현금자산(추정): {stock_cash_objt_krw:,.0f}원\n"
            f"주식평가(추정): {stock_eval_display_krw:,.0f}원\n"
            f"실효 가용: {_format_usd_with_krw(kis_result['effective_usd'], kis_result['usd_exrt'])}\n"
            f"직접 해외주문가능: {_format_usd_with_krw(kis_result['direct_ovrs_usd'], kis_result['usd_exrt'])}\n"
            f"외화주문가능: {_format_usd_with_krw(kis_result['direct_frcr_usd'], kis_result['usd_exrt'])}\n"
            f"통합증거금 가용: {_format_usd_with_krw(kis_result['integrated_usd'], kis_result['usd_exrt'])}\n"
            f"통합증거금 가용(KRW): {kis_result['integrated_krw']:,.0f}원\n"
            f"해외보유 평가: {_format_usd_with_krw(kis_result['overseas_eval_usd'], kis_result['usd_exrt'])} "
            f"({kis_result['overseas_positions']}종목)\n"
            f"기준환율: {kis_result['usd_exrt']:,.4f}\n"
            f"통합모드: {mode_text}\n"
            "상태: 🟢 조회 성공"
        )
        msg = (
            "계좌 잔고 조회\n"
            f"{'─' * 30}\n"
            f"총자산: 💎 {total_asset_objt_krw:,.0f}원\n"
            f"{'─' * 30}\n"
            f"환율(USD/KRW): {rate_line}\n"
            f"{'─' * 30}\n"
            "\n"
            "한국투자\n"
            f"{kis_text}"
        )
    else:
        kis_text = (
            "상태: 🔴 조회 실패\n"
            f"오류: {kis_result.get('error', '조회 실패')}"
        )
        msg = (
            "계좌 잔고 조회\n"
            f"{'─' * 30}\n"
            "한국투자\n"
            f"{kis_text}"
        )
    await update.message.reply_text(msg)


async def cmd_daily_report_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send daily report immediately for verification/testing."""
    if not is_authorized(update):
        return

    try:
        await update.message.reply_text("⏳ 일일 리포트를 지금 생성해서 전송합니다...")
        await send_daily_report()
        await update.message.reply_text("✅ 일일 리포트 즉시 전송을 완료했습니다.")
    except Exception as e:
        await update.message.reply_text(f"❌ 일일 리포트 즉시 전송 실패: {str(e)}")


async def cmd_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all open positions."""
    if not is_authorized(update):
        return

    try:
        from sqlalchemy import select, func
        from app.database.connection import get_session
        from app.models.position import Position, PositionStatus
        usdkrw_rate, _ = await _get_display_usdkrw_rate()

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
            await update.message.reply_text("📭 보유 포지션이 없습니다")
            return

        msg_lines = [f"📈 보유 포지션 ({len(positions)}개 종목)\n{'─' * 30}"]

        for pos in positions[:50]:  # Limit display to 50
            ticker, count, total_qty, total_amount, avg_price = pos
            buys_label = f"({count}x)" if count > 1 else ""
            msg_lines.append(
                f"\n{ticker} {buys_label}\n"
                f"  수량: {total_qty:.4f} × 평균 {_format_usd_with_krw(avg_price, usdkrw_rate)}\n"
                f"  투자금: {_format_usd_with_krw(total_amount, usdkrw_rate)}"
            )

        if len(positions) > 50:
            msg_lines.append(f"\n... 외 {len(positions) - 50}개 종목")

        total_invested = sum(p[3] for p in positions)
        msg_lines.append(f"\n{'─' * 30}")
        msg_lines.append(f"총 투자금: {_format_usd_with_krw(total_invested, usdkrw_rate)}")

        msg = "\n".join(msg_lines)

        # Telegram message limit is 4096 chars
        if len(msg) > 4000:
            # Split into chunks
            for i in range(0, len(msg), 4000):
                await update.message.reply_text(msg[i:i + 4000])
        else:
            await update.message.reply_text(msg)

    except Exception as e:
        await update.message.reply_text(f"❌ 오류: {str(e)}")


async def cmd_pnl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show today's P&L."""
    if not is_authorized(update):
        return

    try:
        from sqlalchemy import select, func
        from app.database.connection import get_session
        from app.models.trade import Trade, TradeSide, TradeStatus

        today_start, today_end = get_et_day_bounds_utc()
        filled_window = _filled_trade_time_window(Trade, today_start, today_end)
        usdkrw_rate, _ = await _get_display_usdkrw_rate()
        kis_portfolio = await _fetch_kis_portfolio_metrics(
            include_today_eval_pnl=True,
            quote_sample_limit=200,
        )
        if kis_portfolio.get("ok"):
            kis_usd_exrt = float(kis_portfolio.get("usd_exrt", 0.0) or 0.0)
            if kis_usd_exrt > 0:
                usdkrw_rate = kis_usd_exrt

        async with get_session() as session:
            # Today's sells with P&L
            result = await session.execute(
                select(Trade).where(
                    Trade.side == TradeSide.SELL,
                    Trade.status == TradeStatus.FILLED,
                    filled_window,
                ).order_by(Trade.filled_at.desc(), Trade.created_at.desc())
            )
            sells = result.scalars().all()

            # Today's buy count
            buy_count = (await session.execute(
                select(func.count(Trade.id)).where(
                    Trade.side == TradeSide.BUY,
                    Trade.status == TradeStatus.FILLED,
                    filled_window,
                )
            )).scalar() or 0

            kis_sell_count = (await session.execute(
                select(func.count(Trade.id)).where(
                    Trade.side == TradeSide.SELL,
                    Trade.status == TradeStatus.FILLED,
                    Trade.ib_order_id < 0,
                    filled_window,
                )
            )).scalar() or 0

        total_pnl = sum(t.total_pnl_usd or 0 for t in sells)
        total_commission = sum(t.commission or 0 for t in sells)
        realized_net_pnl = total_pnl - total_commission
        winners = sum(1 for t in sells if (t.total_pnl_usd or 0) >= 0)
        losers = len(sells) - winners

        realized_emoji = "🟢" if realized_net_pnl >= 0 else "🔴"
        eval_line = ""
        account_line = ""
        if kis_portfolio.get("ok"):
            today_eval_pnl_krw = float(kis_portfolio.get("today_eval_pnl_krw", 0.0) or 0.0)
            today_eval_pnl_pct = float(kis_portfolio.get("today_eval_pnl_pct", 0.0) or 0.0)
            eval_emoji = "🟢" if today_eval_pnl_krw >= 0 else "🔴"
            eval_line = (
                f"{eval_emoji} 보유주식 평가손익: "
                f"{_format_signed_krw(today_eval_pnl_krw)} ({today_eval_pnl_pct:+.2f}%)\n"
            )
            account_day_pnl_krw = today_eval_pnl_krw + (realized_net_pnl * usdkrw_rate)
            account_emoji = "🟢" if account_day_pnl_krw >= 0 else "🔴"
            account_line = f"{account_emoji} 오늘 계좌손익(실현+평가): {_format_signed_krw(account_day_pnl_krw)}\n"

        commission_note_line = ""
        if len(sells) > 0 and kis_sell_count > 0 and abs(float(total_commission or 0.0)) < 1e-9:
            commission_note_line = (
                "ℹ️ KIS 체결 수수료 확정값은 현재 OpenAPI 응답에 없어 0원으로 집계될 수 있습니다.\n"
            )

        msg = (
            f"📊 오늘의 성과\n"
            f"{'─' * 30}\n"
            f"\n"
            f"매수: {buy_count}\n"
            f"매도: {len(sells)} (✅{winners} / ❌{losers})\n"
            f"\n"
            f"{realized_emoji} 오늘 실현손익: {_format_signed_usd_with_krw(total_pnl, usdkrw_rate)}\n"
            f"💸 오늘 수수료: {_format_usd_with_krw(total_commission, usdkrw_rate)}\n"
            f"📊 오늘 순손익: {_format_signed_usd_with_krw(realized_net_pnl, usdkrw_rate)}\n"
            f"{commission_note_line}"
            f"{eval_line}"
            f"{account_line}"
        )

        # Show individual trades (last 10)
        if sells:
            msg += f"\n{'─' * 30}\n최근 매도:\n"
            for t in sells[:10]:
                pnl = t.total_pnl_usd or 0
                emoji = "🟢" if pnl >= 0 else "🔴"
                msg += f"{emoji} {t.ticker}: {_format_signed_usd_with_krw(pnl, usdkrw_rate)}\n"
        elif buy_count == 0:
            msg += "\n오늘 체결된 매도는 없습니다.\n"

        await update.message.reply_text(msg)

    except Exception as e:
        await update.message.reply_text(f"❌ 오류: {str(e)}")


async def cmd_pnl_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show this week's P&L."""
    if not is_authorized(update):
        return

    try:
        from sqlalchemy import select, func
        from app.database.connection import get_session
        from app.models.trade import Trade, TradeSide, TradeStatus
        week_start, week_end = get_et_week_bounds_utc()
        filled_window = _filled_trade_time_window(Trade, week_start, week_end)
        usdkrw_rate, _ = await _get_display_usdkrw_rate()

        async with get_session() as session:
            buy_count = (await session.execute(
                select(func.count(Trade.id)).where(
                    Trade.side == TradeSide.BUY,
                    Trade.status == TradeStatus.FILLED,
                    filled_window,
                )
            )).scalar() or 0

            result = await session.execute(
                select(
                    func.count(Trade.id),
                    func.sum(Trade.total_pnl_usd),
                    func.sum(Trade.commission),
                ).where(
                    Trade.side == TradeSide.SELL,
                    Trade.status == TradeStatus.FILLED,
                    filled_window,
                )
            )
            row = result.one()
            sell_count = row[0] or 0
            total_pnl = row[1] or 0.0
            total_comm = row[2] or 0.0

            kis_sell_count = (await session.execute(
                select(func.count(Trade.id)).where(
                    Trade.side == TradeSide.SELL,
                    Trade.status == TradeStatus.FILLED,
                    Trade.ib_order_id < 0,
                    filled_window,
                )
            )).scalar() or 0

        realized_net_pnl = float(total_pnl or 0.0) - float(total_comm or 0.0)
        pnl_emoji = "🟢" if realized_net_pnl >= 0 else "🔴"
        commission_note_line = ""
        if sell_count > 0 and kis_sell_count > 0 and abs(float(total_comm or 0.0)) < 1e-9:
            commission_note_line = (
                "ℹ️ KIS 체결 수수료 확정값은 현재 OpenAPI 응답에 없어 0원으로 집계될 수 있습니다.\n"
            )

        msg = (
            f"📊 이번 주 성과\n"
            f"{'─' * 30}\n"
            f"매수: {buy_count}\n"
            f"매도: {sell_count}\n"
            f"{pnl_emoji} 이번 주 실현손익: {_format_signed_usd_with_krw(total_pnl, usdkrw_rate)}\n"
            f"💸 이번 주 수수료: {_format_usd_with_krw(total_comm, usdkrw_rate)}\n"
            f"📊 이번 주 순손익: {_format_signed_usd_with_krw(realized_net_pnl, usdkrw_rate)}\n"
            f"{commission_note_line}"
        )

        await update.message.reply_text(msg)

    except Exception as e:
        await update.message.reply_text(f"❌ 오류: {str(e)}")


async def cmd_market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show market hours status."""
    if not is_authorized(update):
        return

    market = get_market_status()
    krx_market = get_krx_market_status()
    asia_blocks = []
    asia_names = {
        "HKEX": "홍콩장",
        "SSE": "중국 상해장",
        "SZSE": "중국 심천장",
        "TSE": "일본장",
    }
    for market_key in ASIA_MARKET_SESSIONS:
        asia = get_asia_market_status(market_key)
        asia_blocks.append(
            f"{asia_names.get(market_key, market_key)}\n"
            f"{asia['emoji']} 상태: {_ko_market_status(asia['status'])}\n"
            f"현재 시각: {asia['current_time_local']}\n"
            f"다음 개장까지: {_ko_next_open(asia['next_open_in'])}\n"
            f"주말 여부: {_ko_yes_no(asia['is_weekend'])}"
        )
    msg = (
        f"🏛️ 장 상태\n"
        f"{'─' * 30}\n"
        f"미국장\n"
        f"{market['emoji']} 상태: {_ko_market_status(market['status'])}\n"
        f"현재 시각: {market['current_time_et']}\n"
        f"다음 개장까지: {_ko_next_open(market['next_open_in'])}\n"
        f"주말 여부: {_ko_yes_no(market['is_weekend'])}\n"
        f"\n"
        f"한국장(KRX)\n"
        f"{krx_market['emoji']} 상태: {_ko_market_status(krx_market['status'])}\n"
        f"현재 시각: {krx_market['current_time_kst']}\n"
        f"다음 개장까지: {_ko_next_open(krx_market['next_open_in'])}\n"
        f"주말 여부: {_ko_yes_no(krx_market['is_weekend'])}\n"
        f"\n"
        + "\n\n".join(asia_blocks)
    )
    await update.message.reply_text(msg)


async def cmd_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show order queue status."""
    if not is_authorized(update):
        return

    queue = await get_queue_stats()
    msg = (
        f"📬 주문 큐 상태\n"
        f"{'─' * 30}\n"
        f"매도 큐: {queue['sell_queue']}\n"
        f"매수 큐: {queue['buy_queue']}\n"
        f"대기 큐: {queue['pending_queue']} "
        f"(미국 {queue.get('pending_us', 0)} / 아시아 {queue.get('pending_asia', 0)} / 한국 {queue.get('pending_krx', 0)}"
        f" / 만료대상 {queue.get('pending_expired', 0)})\n"
        f"처리 중 큐: {queue['processing_queue']}\n"
        f"전체: {queue['total']}"
    )
    await update.message.reply_text(msg)


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all current settings."""
    if not is_authorized(update):
        return

    try:
        s = await get_bot_settings()
        d = s.to_display_dict()
        usdkrw_rate, _ = await _get_display_usdkrw_rate()
        allowed_text = _format_allowlist_summary()

        status = "🔴 긴급중지" if d["is_killed"] else ("🟡 일시중지" if d["is_paused"] else "🟢 실행중")

        broker_text = "브로커: KIS 전용"

        msg = (
            f"⚙️ 현재 설정\n"
            f"{'─' * 30}\n"
            f"\n"
            f"상태: {status}\n"
            f"{broker_text}\n"
            f"허용 종목: {allowed_text}\n"
            f"\n"
            f"💰 매수 금액: {_format_usd_with_krw(d['buy_amount_usd'], usdkrw_rate)}\n"
            f"📊 최대 보유 포지션: {d['max_open_positions']}\n"
            f"📅 일일 최대 매수 횟수: {d['max_daily_buys']}\n"
            f"💵 총 최대 투자금: {_format_usd_with_krw(d['max_total_investment'], usdkrw_rate)}\n"
            f"🔄 종목당 최대 매수 횟수: {d['max_per_ticker']}\n"
            f"🛑 일일 손실 한도: 비활성화\n"
            f"🏦 최소 현금 보유액: {_format_usd_with_krw(d['min_cash_reserve'], usdkrw_rate)}\n"
            f"\n"
            f"⏰ 정규장만 거래: {_ko_yes_no(d['regular_hours_only'])}\n"
            f"📥 장외 시간 주문 대기: {_ko_yes_no(d['queue_outside_hours'])}\n"
            f"\n"
            f"/set_amount, /set_max_positions 등 명령은 2회 확인 후 적용됩니다."
        )

        await update.message.reply_text(msg)

    except Exception as e:
        await update.message.reply_text(f"❌ 오류: {str(e)}")


# ============================================
# SETTING COMMANDS
# ============================================

async def _update_setting(
    update: Update,
    context,
    key: str,
    value_type: type,
    label: str,
    usage_command: str,
):
    """Generic setting updater."""
    if not is_authorized(update):
        return

    if not context.args:
        await update.message.reply_text(f"사용법: /{usage_command} <값>")
        return

    try:
        new_value = value_type(context.args[0])
        if new_value <= 0:
            await update.message.reply_text("❌ 값은 0보다 커야 합니다")
            return
    except ValueError:
        await update.message.reply_text(
            f"❌ 잘못된 값입니다. {'숫자' if value_type == float else '정수'}를 입력하세요."
        )
        return

    old_settings = await get_bot_settings()
    old_value = getattr(old_settings, key)
    usdkrw_rate, _ = await _get_display_usdkrw_rate()

    old_value_text = _format_setting_value(key, old_value, usdkrw_rate)
    new_value_text = _format_setting_value(key, new_value, usdkrw_rate)
    preview_text = (
        f"{label} 변경 예정\n"
        f"{'─' * 20}\n"
        f"이전: {old_value_text}\n"
        f"변경: {new_value_text}"
    )
    action_key = f"setting:{key}:{new_value}"
    if not await _require_double_confirm(
        update,
        context,
        action_key=action_key,
        preview_text=preview_text,
    ):
        return

    await update_bot_setting(key, new_value)

    await update.message.reply_text(
        f"✅ {label} 변경 완료\n"
        f"{'─' * 20}\n"
        f"이전: {old_value_text}\n"
        f"변경: {new_value_text}"
    )


async def cmd_set_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set buy amount per order."""
    await _update_setting(
        update,
        context,
        "buy_amount_usd",
        float,
        "매수 금액",
        "set_amount",
    )


async def cmd_set_max_positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set max open positions."""
    await _update_setting(
        update,
        context,
        "max_open_positions",
        int,
        "최대 보유 포지션",
        "set_max_positions",
    )


async def cmd_set_max_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set max daily buys."""
    await _update_setting(
        update,
        context,
        "max_daily_buys",
        int,
        "일일 최대 매수 횟수",
        "set_max_daily",
    )


async def cmd_set_max_invest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set max total investment."""
    await _update_setting(
        update,
        context,
        "max_total_investment",
        float,
        "총 최대 투자금",
        "set_max_invest",
    )


async def cmd_set_max_per_ticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set max buys per ticker."""
    await _update_setting(
        update,
        context,
        "max_per_ticker",
        int,
        "종목당 최대 매수 횟수",
        "set_max_per_ticker",
    )


async def cmd_set_reserve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set minimum cash reserve."""
    await _update_setting(
        update,
        context,
        "min_cash_reserve",
        float,
        "최소 현금 보유액",
        "set_reserve",
    )


# ============================================
# CONTROL COMMANDS
# ============================================

async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pause buying (sells still execute)."""
    if not is_authorized(update):
        return

    if not await _require_double_confirm(
        update,
        context,
        action_key="control:pause",
        preview_text="매수 일시중지를 실행합니다.\n(매도는 계속 실행)",
    ):
        return

    await update_bot_setting("is_paused", True)
    await update_bot_setting("is_killed", False)
    await update.message.reply_text(
        "🟡 매수 일시중지\n"
        "매도는 계속 실행됩니다.\n"
        "/resume 명령으로 매수를 재개할 수 있습니다."
    )


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resume all trading."""
    if not is_authorized(update):
        return

    if not await _require_double_confirm(
        update,
        context,
        action_key="control:resume",
        preview_text="거래 재개를 실행합니다.\n(매수/매도 로직 활성화)",
    ):
        return

    await update_bot_setting("is_paused", False)
    await update_bot_setting("is_killed", False)
    await update.message.reply_text("🟢 거래 재개 — 모든 동작이 활성화되었습니다")


async def cmd_kill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Emergency stop ALL trading."""
    if not is_authorized(update):
        return

    if not await _require_double_confirm(
        update,
        context,
        action_key="control:kill",
        preview_text="긴급 정지를 실행합니다.\n(매수/매도 모두 즉시 중단)",
    ):
        return

    await update_bot_setting("is_killed", True)
    await update.message.reply_text(
        "🔴 긴급 정지 활성화\n"
        "모든 거래(매수/매도)가 중단되었습니다.\n"
        "/resume 명령으로 재개할 수 있습니다."
    )


async def cmd_sell_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Queue sell requests for open positions while preserving the no-loss-sell rule."""
    if not is_authorized(update):
        return

    if not await _require_double_confirm(
        update,
        context,
        action_key="control:sell_all",
        preview_text=(
            "보유 포지션 매도 요청을 실행합니다.\n"
            "손실 중인 종목은 손실 매도 금지 정책에 따라 자동 보류됩니다."
        ),
    ):
        return

    await update.message.reply_text(
        "🔄 보유 포지션 매도 요청을 진행합니다...\n"
        "손실 중인 종목은 매도하지 않고 보류합니다."
    )

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
            await update.message.reply_text("📭 매도할 보유 포지션이 없습니다")
            return

        for ticker in tickers:
            await enqueue_order({"action": "SELL", "ticker": ticker, "alert_id": "manual_sell_all"})

        await update.message.reply_text(
            f"📤 {len(tickers)}개 종목의 매도 요청을 처리 큐에 넣었습니다\n"
            "단, 손실 중인 종목은 주문 실행 단계에서 자동 보류됩니다."
        )

    except Exception as e:
        await update.message.reply_text(f"❌ 오류: {str(e)}")


async def cmd_clear_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear all order queues."""
    if not is_authorized(update):
        return

    if not await _require_double_confirm(
        update,
        context,
        action_key="control:clear_queue",
        preview_text="모든 주문 큐 비우기를 실행합니다.\n(대기/처리중 주문 상태가 정리됨)",
    ):
        return

    await clear_all_queues()
    cleared_alerts = 0
    try:
        from sqlalchemy import select
        from app.database.connection import get_session
        from app.models.alert_log import AlertLog

        async with get_session() as session:
            rows = (
                await session.execute(
                    select(AlertLog).where(
                        AlertLog.queued.is_(True),
                        AlertLog.processed.is_(False),
                    )
                )
            ).scalars().all()

            now = datetime.now(timezone.utc)
            for row in rows:
                row.queued = False
                row.processed = True
                row.skipped = True
                row.skip_reason = "manual_clear_queue"
                row.processed_at = now

            cleared_alerts = len(rows)
    except Exception as e:
        logger.error("Failed to reconcile alert logs after queue clear", error=str(e))

    await update.message.reply_text(
        f"🗑️ 모든 주문 큐를 비웠습니다\n"
        f"정리된 알림 로그: {cleared_alerts}건"
    )


async def cmd_mobile_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Deprecated IBKR maintenance command.

    The system is KIS-only now, so this command intentionally does not
    run host-level SSH or IB Gateway control scripts.
    """
    if not is_authorized(update):
        return

    await update.message.reply_text(
        "ℹ️ /mobile_login 명령은 제거되었습니다.\n"
        "현재 시스템은 KIS(한국투자) 전용으로 운용되며 IBKR Gateway 제어를 하지 않습니다."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle non-command messages (for cancellation of pending confirmations)."""
    if not is_authorized(update):
        return

    text = update.message.text.strip()
    normalized = " ".join(text.lower().split())
    if normalized in {"취소", "cancel", "/cancel"}:
        if context.user_data.get(_CONFIRM_STATE_KEY):
            context.user_data.pop(_CONFIRM_STATE_KEY, None)
            await update.message.reply_text("❌ 확인 대기 작업을 취소했습니다")


# ============================================
# NOTIFICATION SENDER
# ============================================

async def send_notification(message: str, parse_mode: Optional[str] = None) -> bool:
    """
    Send a notification message to the configured Telegram chat.
    Called from other modules (worker, etc.).
    """
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.warning("Telegram not configured, skipping notification")
        return False

    from telegram import Bot
    from telegram.error import RetryAfter, TimedOut, NetworkError

    async with _notify_bot_lock:
        global _notify_bot
        if _notify_bot is None:
            _notify_bot = Bot(token=settings.telegram_bot_token)
        bot = _notify_bot

    # Retry policy for transient Telegram/network errors.
    max_attempts = 4
    default_backoffs = (1.0, 2.0, 5.0)

    for attempt in range(1, max_attempts + 1):
        try:
            async with _notify_send_semaphore:
                await bot.send_message(
                    chat_id=settings.telegram_chat_id,
                    text=message,
                    parse_mode=parse_mode,
                    connect_timeout=5.0,
                    read_timeout=10.0,
                    write_timeout=10.0,
                    pool_timeout=20.0,
                )
            return True
        except RetryAfter as e:
            if attempt >= max_attempts:
                logger.error(
                    "Failed to send Telegram notification (rate limited)",
                    attempt=attempt,
                    retry_after=float(getattr(e, "retry_after", 0) or 0),
                    error=str(e),
                )
                return False
            wait_seconds = max(1.0, float(getattr(e, "retry_after", 1.0) or 1.0))
            logger.warning(
                "Telegram send rate limited, retrying",
                attempt=attempt,
                wait_seconds=wait_seconds,
            )
            await asyncio.sleep(wait_seconds)
        except (TimedOut, NetworkError) as e:
            if attempt >= max_attempts:
                logger.error(
                    "Failed to send Telegram notification (network/timeout)",
                    attempt=attempt,
                    error=str(e),
                )
                return False
            wait_seconds = default_backoffs[min(attempt - 1, len(default_backoffs) - 1)]
            logger.warning(
                "Telegram send transient failure, retrying",
                attempt=attempt,
                wait_seconds=wait_seconds,
                error=str(e),
            )
            await asyncio.sleep(wait_seconds)
        except Exception as e:
            logger.error("Failed to send Telegram notification", error=str(e), attempt=attempt)
            return False

    return False


async def send_daily_report():
    """Send daily performance report."""
    try:
        from sqlalchemy import select, func
        from app.database.connection import get_session
        from app.models.trade import Trade, TradeSide, TradeStatus
        from app.models.position import Position, PositionStatus
        from app.gateway.symbol_mapper import is_kis_domestic_symbol

        today_start, today_end = get_et_day_bounds_utc()
        filled_window = _filled_trade_time_window(Trade, today_start, today_end)
        usdkrw_rate, _ = await _get_display_usdkrw_rate()
        kis_portfolio = await _fetch_kis_portfolio_metrics(
            include_today_eval_pnl=True,
            quote_sample_limit=200,
        )
        if kis_portfolio.get("ok"):
            kis_usd_exrt = float(kis_portfolio.get("usd_exrt", 0.0) or 0.0)
            if kis_usd_exrt > 0:
                usdkrw_rate = kis_usd_exrt

        async with get_session() as session:
            # Today's stats
            buy_count = (await session.execute(
                select(func.count(Trade.id)).where(
                    Trade.side == TradeSide.BUY,
                    Trade.status == TradeStatus.FILLED,
                    filled_window,
                )
            )).scalar() or 0

            buy_rows = (
                await session.execute(
                    select(Trade.ticker, Trade.total_fill_amount_usd).where(
                        Trade.side == TradeSide.BUY,
                        Trade.status == TradeStatus.FILLED,
                        filled_window,
                    )
                )
            ).all()

            buy_amount_krw = 0.0
            for ticker, amount in buy_rows:
                native_amount = float(amount or 0.0)
                if is_kis_domestic_symbol(str(ticker or "")):
                    buy_amount_krw += native_amount
                elif usdkrw_rate > 0:
                    buy_amount_krw += native_amount * usdkrw_rate

            sell_rows = (
                await session.execute(
                    select(Trade.ticker, Trade.total_fill_amount_usd, Trade.total_pnl_usd).where(
                        Trade.side == TradeSide.SELL,
                        Trade.status == TradeStatus.FILLED,
                        filled_window,
                    )
                )
            ).all()
            sell_count = len(sell_rows)
            sell_amount_krw = 0.0
            total_pnl_krw_from_trades = 0.0
            for ticker, amount, pnl in sell_rows:
                native_amount = float(amount or 0.0)
                native_pnl = float(pnl or 0.0)
                if is_kis_domestic_symbol(str(ticker or "")):
                    sell_amount_krw += native_amount
                    total_pnl_krw_from_trades += native_pnl
                elif usdkrw_rate > 0:
                    sell_amount_krw += native_amount * usdkrw_rate
                    total_pnl_krw_from_trades += native_pnl * usdkrw_rate

            # Legacy USD aggregates are intentionally no longer used for display
            # because domestic/KRX trades store native KRW in the same amount fields.
            _legacy_buy_amount_usd = float((await session.execute(
                select(func.sum(Trade.total_fill_amount_usd)).where(
                    Trade.side == TradeSide.BUY,
                    Trade.status == TradeStatus.FILLED,
                    filled_window,
                )
            )).scalar() or 0.0)

            sell_result = await session.execute(
                select(
                    func.count(Trade.id),
                    func.sum(Trade.total_fill_amount_usd),
                    func.sum(Trade.total_pnl_usd),
                ).where(
                    Trade.side == TradeSide.SELL,
                    Trade.status == TradeStatus.FILLED,
                    filled_window,
                )
            )
            sell_row = sell_result.one()
            _legacy_sell_count = sell_row[0] or 0
            _legacy_sell_amount_usd = float(sell_row[1] or 0.0)
            _legacy_total_pnl = sell_row[2] or 0.0

            # Open positions
            open_count = (await session.execute(
                select(func.count(Position.id)).where(Position.status == PositionStatus.OPEN)
            )).scalar() or 0

        waiting = await get_waiting_ticker_stats(include_processing=False)
        cash_shortage_block = ""
        if int(waiting.get("buy_order_count") or 0) > 0:
            from app.cash_monitor import estimate_pending_buy_cash_coverage

            cash_coverage = await estimate_pending_buy_cash_coverage()
            cash_shortage_block = _format_pending_buy_cash_shortage_block(cash_coverage)
        open_count_display = int(open_count)
        account_total_asset_line = ""
        account_purchase_line = ""
        account_cash_line = ""
        today_eval_line = "당일 평가손익(보유주식): 조회 실패\n"
        trend_block = ""
        investment_start_label = await _fetch_investment_start_date_label()
        investment_elapsed_line = _format_investment_elapsed_line(investment_start_label)

        if kis_portfolio.get("ok"):
            open_count_display = int(kis_portfolio.get("position_count", open_count_display) or open_count_display)
            await _upsert_kis_portfolio_snapshot(kis_portfolio)

            total_asset_krw = float(kis_portfolio.get("total_asset_krw", 0.0) or 0.0)
            purchase_krw = float(kis_portfolio.get("invested_krw", 0.0) or 0.0)
            cash_krw = float(kis_portfolio.get("cash_krw", 0.0) or 0.0)
            if total_asset_krw > 0:
                account_total_asset_line = f"총 자산: {total_asset_krw:,.0f}원\n"
            if purchase_krw > 0:
                account_purchase_line = f"매입 금액: {purchase_krw:,.0f}원\n"
            if cash_krw >= 0:
                account_cash_line = f"총 예수금: {cash_krw:,.0f}원\n"

            today_eval_pnl_krw = float(kis_portfolio.get("today_eval_pnl_krw", 0.0) or 0.0)
            today_eval_pnl_pct = float(kis_portfolio.get("today_eval_pnl_pct", 0.0) or 0.0)
            today_eval_line = (
                f"보유주식 평가손익: "
                f"{_format_signed_krw(today_eval_pnl_krw)} "
                f"({today_eval_pnl_pct:+.2f}%)\n"
            )

        total_pnl_trend_series = await _fetch_all_time_total_pnl_snapshot_series(usdkrw_rate)
        if total_pnl_trend_series:
            trend_lines = []
            basis_krw = float(total_pnl_trend_series[-1].get("basis_krw", 0.0) or 0.0)
            display_series = total_pnl_trend_series[-30:]
            if not investment_start_label:
                investment_start_label = str(total_pnl_trend_series[0].get("snapshot_date") or "")[:10]
                investment_elapsed_line = _format_investment_elapsed_line(investment_start_label)
            investment_start_line = (
                f"투자 시작일: {investment_start_label}\n" if investment_start_label else ""
            )
            ranked_items = sorted(
                enumerate(display_series),
                key=lambda pair: float(pair[1].get("total_pnl_pct") or 0.0),
                reverse=True,
            )
            rank_labels = {}
            for rank, (idx, _) in enumerate(ranked_items[:3], start=1):
                rank_labels[idx] = "<b>1등 👑</b>" if rank == 1 else f"<b>{rank}등</b>"

            for idx, item in enumerate(display_series):
                total_pnl_krw = float(item["total_pnl_krw"] or 0.0)
                total_pnl_pct = float(item["total_pnl_pct"] or 0.0)
                rank_suffix = f" {rank_labels[idx]}" if idx in rank_labels else ""
                trend_lines.append(
                    f"{item['label']} {_format_signed_krw(total_pnl_krw)} "
                    f"({total_pnl_pct:+.2f}%){rank_suffix}"
                )
            trend_block = (
                f"\n전체 기간 총손익추이(최근 {len(display_series)}일):\n"
                f"{investment_start_line}"
                f"수익률 기준원금: {basis_krw:,.0f}원\n"
                + "\n".join(trend_lines)
                + "\n"
            )

        msg = (
            f"📊 일일 리포트 — {get_et_now().strftime('%Y-%m-%d')} (ET)\n"
            f"\n"
            f"매수: {buy_count}\n"
            f"매도: {sell_count}\n"
            f"매수 대기 종목: {waiting['buy_ticker_count']} "
            f"(주문 {waiting['buy_order_count']}건)\n"
            f"매도 대기 종목: {waiting['sell_ticker_count']} "
            f"(주문 {waiting['sell_order_count']}건)\n"
            f"{cash_shortage_block}"
            f"오늘 매수금액: {buy_amount_krw:,.0f}원\n"
            f"오늘 매도금액: {sell_amount_krw:,.0f}원\n"
            f"\n"
            f"오늘 실현손익: {_format_signed_krw(total_pnl_krw_from_trades)}\n"
            f"\n"
            f"보유 포지션: {open_count_display}\n"
            f"{account_total_asset_line}"
            f"{account_purchase_line}"
            f"{account_cash_line}"
            f"{today_eval_line}"
            f"{trend_block}"
            f"{investment_elapsed_line}"
        )

        await send_notification(msg, parse_mode="HTML")

    except Exception as e:
        logger.error("Failed to send daily report", error=str(e))


# ============================================
# BOT SETUP
# ============================================

async def setup_commands(app):
    """Register bot commands so they show up in Telegram's command menu."""
    commands = [
        BotCommand("start", "도움말 및 명령어 보기"),
        BotCommand("help", "전체 명령어 보기"),
        BotCommand("status", "현재 봇 상태"),
        BotCommand("balance", "KIS 잔고 조회"),
        BotCommand("positions", "보유 포지션 보기"),
        BotCommand("pnl", "오늘 손익"),
        BotCommand("pnl_week", "이번 주 손익"),
        BotCommand("daily_report_now", "일일 리포트 즉시 전송"),
        BotCommand("market", "장 상태"),
        BotCommand("queue", "주문 큐 상태"),
        BotCommand("settings", "현재 설정"),
        BotCommand("set_amount", "매수 금액 설정"),
        BotCommand("set_max_positions", "최대 보유 포지션"),
        BotCommand("set_max_daily", "일일 최대 매수 횟수"),
        BotCommand("set_max_invest", "총 최대 투자금"),
        BotCommand("set_max_per_ticker", "종목당 최대 매수 횟수"),
        BotCommand("set_reserve", "최소 현금 보유액"),
        BotCommand("pause", "매수 일시중지"),
        BotCommand("resume", "거래 재개"),
        BotCommand("kill", "전체 거래 긴급중지"),
        BotCommand("sell_all", "수익 중 포지션 매도 요청"),
        BotCommand("clear_queue", "주문 큐 비우기"),
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
    app.add_handler(CommandHandler("balance", cmd_balance))
    app.add_handler(CommandHandler("positions", cmd_positions))
    app.add_handler(CommandHandler("pnl", cmd_pnl))
    app.add_handler(CommandHandler("pnl_week", cmd_pnl_week))
    app.add_handler(CommandHandler("daily_report_now", cmd_daily_report_now))
    app.add_handler(CommandHandler("market", cmd_market))
    app.add_handler(CommandHandler("queue", cmd_queue))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("set_amount", cmd_set_amount))
    app.add_handler(CommandHandler("set_max_positions", cmd_set_max_positions))
    app.add_handler(CommandHandler("set_max_daily", cmd_set_max_daily))
    app.add_handler(CommandHandler("set_max_invest", cmd_set_max_invest))
    app.add_handler(CommandHandler("set_max_per_ticker", cmd_set_max_per_ticker))
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

    global _telegram_poller_instance_id
    instance_id = f"{os.uname().nodename}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
    _telegram_poller_instance_id = instance_id
    redis_client = await _acquire_telegram_poller_lock(instance_id)
    lock_stop_event = asyncio.Event()
    renew_task = asyncio.create_task(_renew_telegram_poller_lock(redis_client, instance_id, lock_stop_event))

    try:
        # Register commands in Telegram
        async with app:
            await setup_commands(app)
            try:
                await app.bot.delete_webhook(drop_pending_updates=True)
            except Exception as exc:
                logger.warning("Failed to clear Telegram webhook before polling", error=str(exc))
            await app.start()

            logger.info("Telegram bot started", instance_id=instance_id)
            await send_notification("🤖 텔레그램 봇이 시작되었습니다. /help 명령으로 사용법을 확인하세요.")

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
    finally:
        lock_stop_event.set()
        renew_task.cancel()
        try:
            await renew_task
        except asyncio.CancelledError:
            pass
        await _release_telegram_poller_lock(redis_client, instance_id)
        _telegram_poller_instance_id = None


if __name__ == "__main__":
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ]
    )

    asyncio.run(run_bot())
