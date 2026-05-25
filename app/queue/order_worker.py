"""
Order queue worker.
Continuously processes orders from Redis queues with rate limiting.
Handles market hours, risk checks, and order execution.
"""

import asyncio
import re
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Optional
import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database.connection import init_db, get_bot_settings, get_session
from app.queue.order_queue import (
    dequeue_order,
    enqueue_pending,
    enqueue_order,
    flush_pending_to_active,
    purge_expired_pending_orders,
    requeue_processing_order,
    ack_processed_order,
    requeue_inflight_orders,
)
from app.broker.ib_client import get_ib_client
from app.broker.market_hours import (
    ASIA_MARKET_SESSIONS,
    is_asia_market_open,
    is_krx_market_open,
    is_market_open,
    is_market_open_for_ticker,
    get_market_status,
    get_market_status_for_ticker,
)
from app.broker.order_executor import execute_buy, execute_sell
from app.risk.risk_manager import check_all_buy_risks, check_sell_risks
from app.notifications.telegram_bot import send_notification
from app.models.alert_log import AlertLog
from app.models.position import Position, PositionStatus

logger = structlog.get_logger()


def _sanitize_error_for_telegram(error_text: str) -> str:
    """
    In KIS-only mode, strip IB-related fragments from aggregated failover errors
    so Telegram only shows relevant KIS errors.
    """
    mode = (settings.broker_mode or "kis_only").strip().lower()
    text = str(error_text or "")
    if mode != "kis_only" or not text:
        return text

    # Remove common aggregate prefixes first.
    text = text.replace("모든 브로커 매수 실패:", "").replace("모든 브로커 매도 실패:", "")
    # Keep only non-IB segments when errors are joined by '|'.
    parts = [p.strip() for p in text.split("|") if p.strip()]
    parts = [p for p in parts if not p.startswith("IB:")]
    if parts:
        text = " | ".join(parts)

    if text.startswith("KIS:"):
        text = text[4:].strip()
    return text.strip() or "알 수 없는 오류"


def _friendly_order_issue_text(action: str, ticker: str, error_text: str, *, blocked: bool = False) -> str:
    """
    Convert low-level broker/runtime errors into plain Korean explanations
    that are easier to understand in Telegram.
    """
    text = _sanitize_error_for_telegram(error_text)
    action_ko = "매수" if action == "BUY" else "매도"
    prefix = "⚠️" if blocked else "❌"

    def _build(reason: str, current_state: Optional[str] = None, raw: Optional[str] = None) -> str:
        lines = [f"{prefix} {action_ko} {ticker} 주문 {'차단' if blocked else '실패'}", f"이유: {reason}"]
        if current_state:
            lines.append(f"현재 상태: {current_state}")
        if raw:
            lines.append(f"원문: {raw}")
        return "\n".join(lines)

    raw_for_debug = None if blocked else text

    if "오늘 매수는 1회만 허용됩니다" in text:
        return _build("오늘 이 종목은 이미 1번 매수되어 추가 매수를 막았습니다.")

    if "허용 종목" in text or "allowlist" in text or "not allowed" in text.lower():
        return _build(
            "자동매매 대상 목록에 없는 종목이라 주문하지 않았습니다.",
            "트레이딩뷰 와치리스트와 프로그램 허용목록이 같은지 확인해야 합니다.",
        )

    if "1주 미만 주문을 지원하지 않습니다" in text:
        return _build(
            "설정된 매수 금액으로는 1주도 살 수 없어 주문하지 않았습니다.",
            "KIS는 해외 ETF 소수점 주문을 지원하지 않아서 최소 1주 금액이 필요합니다.",
        )

    if "보유 포지션이 없습니다" in text or "보유 포지션이 없어" in text:
        return _build("현재 이 종목을 보유하고 있지 않아 매도할 수 없습니다.")

    if "거래정지종목" in text:
        return _build("이 종목은 현재 거래정지 상태라 주문할 수 없습니다.")

    if "KIS 시세 응답에서 유효 가격을 찾지 못했습니다" in text or "유효 가격" in text:
        return _build(
            "한국투자에서 현재가를 제대로 주지 않아 주문 가격을 만들 수 없었습니다.",
            "시세가 정상으로 돌아오면 다음 신호에서 다시 주문할 수 있습니다.",
        )

    if "KIS 가용금 조회 실패" in text or "매수가능금액 조회 실패" in text or "intgr-margin" in text:
        return _build(
            "한국투자에서 예수금 조회가 일시적으로 실패해 안전하게 주문을 막았습니다.",
            "잔고나 예수금이 부족하다는 뜻이 아니라, 증권사 서버 응답이 불안정했다는 뜻입니다.",
        )

    if "매수가능조회 실패" in text or "주문가능" in text:
        return _build(
            "한국투자에서 이 종목의 주문가능금액을 확인하지 못했습니다.",
            "증권사 서버 응답 문제이거나 해당 시장/종목 주문정보가 잠시 비어 있었을 수 있습니다.",
        )

    if "해외주식" in text and ("서비스" in text or "신청" in text):
        return _build(
            "한국투자 계좌의 해외주식/해외 ETF 거래 신청 상태를 확인해야 합니다.",
            "앱에서 해외주식 거래 신청, 통합증거금, 환전/외화주문 가능 상태를 확인하세요.",
        )

    if "통합증거금" in text:
        return _build(
            "통합증거금 조회 또는 사용 조건에서 막혔습니다.",
            "원화로 해외 ETF를 사려면 통합증거금 신청/상태가 정상이어야 합니다.",
        )

    if "휴장" in text or "장 휴장" in text or "시장 미개장" in text or "거래소 미접수" in text:
        return _build(
            "해당 시장이 닫혀 있거나 거래소가 주문을 받지 않는 시간입니다.",
            "필요하면 다음 장 개장 시점에 대기 주문으로 실행됩니다.",
        )

    if "주문수량" in text or "수량" in text and "부족" in text:
        return _build(
            "주문 수량 계산이 맞지 않아 주문하지 않았습니다.",
            "대개 1주 가격이 매수금보다 비싸거나 보유수량보다 많이 팔려고 할 때 발생합니다.",
        )

    if "주문단가" in text or "가격" in text and "잘못" in text:
        return _build(
            "주문 가격 형식이 증권사 규칙에 맞지 않았습니다.",
            "시장별 호가 단위나 가격 데이터가 비정상일 가능성이 있습니다.",
        )

    if "Not connected to IB Gateway" in text:
        return _build(
            "IB 게이트웨이 연결이 끊겨 IB 주문을 보낼 수 없었습니다.",
            "현재 KIS 전용 모드가 아니면 IB 연결 상태를 다시 확인해야 합니다.",
        )

    if "500 Internal Server Error" in text or "Server error '500" in text:
        if "order-rvsecncl" in text:
            return _build(
                "주문 취소 확인 단계에서 한국투자 서버가 오류를 냈습니다.",
                "미체결 주문이 남아 있을 수 있으니 한국투자 앱에서 한 번 확인하는 것이 안전합니다.",
            )
        return _build(
            "한국투자 주문 서버가 일시적으로 오류를 내서 주문을 끝까지 처리하지 못했습니다.",
            "대개 증권사 서버 쪽 일시 장애입니다. 다음 신호나 재시도에서 정상 처리될 수 있습니다.",
        )

    if "미체결" in text and "취소도 실패" in text:
        return _build(
            "주문은 들어갔지만 바로 체결되지 않았고, 취소 확인도 끝나지 않았습니다.",
            "한국투자 앱에서 이 종목의 미체결 주문이 남아 있는지 확인이 필요합니다.",
        )

    if "미체결" in text and "취소했습니다" in text:
        return _build(
            "주문이 체결되지 않아 자동으로 취소되었습니다.",
            "실제로 매수/매도가 이뤄진 것은 아닙니다.",
        )

    if "부분체결" in text:
        return _build(
            "주문 수량 일부만 체결되었습니다.",
            "잔량 처리 상태를 한국투자 앱에서 한 번 확인하는 것이 좋습니다.",
        )

    if "매매가능한 수량이 없습니다" in text:
        return _build(
            "매도 가능한 수량이 없어 주문이 거절되었습니다.",
            "이미 전량 매도됐거나, 실제 보유수량과 주문수량이 맞지 않았을 가능성이 있습니다.",
        )

    if "현금이 부족합니다" in text:
        return _build(
            "이 주문을 넣기엔 예수금이 부족해 안전하게 막았습니다.",
            "설정된 매수금액을 낮추거나 예수금을 더 넣어야 합니다.",
        )

    return _build("주문 처리 중 예상하지 못한 오류가 발생했습니다.", raw=raw_for_debug)

# Rate limiting
_last_order_time = 0.0
_min_order_interval = 1.0 / settings.max_orders_per_second  # seconds between orders
_usdkrw_cache_rate = 0.0
_usdkrw_cache_ts = 0.0
_outside_hours_notify_lock = asyncio.Lock()
_outside_hours_notify_buckets: dict[str, list[str]] = {"BUY": [], "SELL": []}
_outside_hours_notify_task: Optional[asyncio.Task] = None


def _format_usd_with_krw(usd_amount: float, usdkrw_rate: float) -> str:
    amount = float(usd_amount or 0.0)
    if usdkrw_rate > 0:
        return f"${amount:,.2f} ({amount * usdkrw_rate:,.0f}원)"
    return f"${amount:,.2f}"


def _format_signed_usd_with_krw(usd_amount: float, usdkrw_rate: float) -> str:
    sign = "+" if float(usd_amount or 0.0) >= 0 else "-"
    amount = abs(float(usd_amount or 0.0))
    if usdkrw_rate > 0:
        return f"{sign}${amount:,.2f} ({sign}{amount * usdkrw_rate:,.0f}원)"
    return f"{sign}${amount:,.2f}"


def _format_money(amount: float, currency: str, usdkrw_rate: float) -> str:
    currency_upper = str(currency or "USD").upper()
    value = float(amount or 0.0)
    if currency_upper == "KRW":
        return f"{value:,.0f}원"
    return _format_usd_with_krw(value, usdkrw_rate)


def _format_signed_money(amount: float, currency: str, usdkrw_rate: float) -> str:
    currency_upper = str(currency or "USD").upper()
    value = float(amount or 0.0)
    if currency_upper == "KRW":
        sign = "+" if value >= 0 else "-"
        return f"{sign}{abs(value):,.0f}원"
    return _format_signed_usd_with_krw(value, usdkrw_rate)


async def _get_display_usdkrw_rate() -> float:
    """Fetch USD/KRW for display with short TTL cache."""
    global _usdkrw_cache_rate, _usdkrw_cache_ts

    now = time.monotonic()
    ttl_seconds = 300.0
    if _usdkrw_cache_ts > 0 and (now - _usdkrw_cache_ts) < ttl_seconds:
        return _usdkrw_cache_rate

    try:
        from app.broker.kis_client import get_kis_client

        kis = await get_kis_client()
        if kis.is_configured:
            funds = await kis.get_effective_usd_orderable(symbol="AAPL", order_price=1.0)
            rate = float(funds.get("usd_exrt", 0.0) or 0.0)
            if rate > 0:
                _usdkrw_cache_rate = rate
                _usdkrw_cache_ts = now
                return rate
    except Exception as e:
        logger.debug("USD/KRW fetch failed for display", error=str(e))

    return _usdkrw_cache_rate


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


async def _flush_outside_hours_notifications_after_delay(delay_seconds: float = 8.0) -> None:
    """Batch outside-hours reservation alerts into a short summary."""
    global _outside_hours_notify_task

    try:
        await asyncio.sleep(max(1.0, delay_seconds))

        async with _outside_hours_notify_lock:
            snapshot = {
                action: tickers[:]
                for action, tickers in _outside_hours_notify_buckets.items()
                if tickers
            }
            for action in _outside_hours_notify_buckets:
                _outside_hours_notify_buckets[action].clear()

        if not snapshot:
            return

        first_ticker = next((tickers[0] for tickers in snapshot.values() if tickers), "")
        market = get_market_status_for_ticker(first_ticker) if first_ticker else get_market_status()
        lines = ["⏳ 장외 주문 예약 요약"]
        for action in ("SELL", "BUY"):
            tickers = snapshot.get(action) or []
            if not tickers:
                continue
            preview = ", ".join(tickers[:12])
            remainder = len(tickers) - min(len(tickers), 12)
            if remainder > 0:
                preview = f"{preview} 외 {remainder}종목"
            lines.append(f"{action}: {len(tickers)}건")
            lines.append(f"종목: {preview}")

        lines.append(f"장 상태: {market['emoji']} {_ko_market_status(market['status'])}")
        lines.append(f"다음 개장까지: {_ko_next_open(market['next_open_in'])}")
        await send_notification("\n".join(lines))
    finally:
        _outside_hours_notify_task = None


async def queue_outside_hours_notification(action: str, ticker: str) -> None:
    """Collect outside-hours queued orders and send one summary message."""
    global _outside_hours_notify_task

    normalized_action = str(action or "").upper().strip()
    if normalized_action not in ("BUY", "SELL"):
        normalized_action = "BUY"
    normalized_ticker = str(ticker or "").upper().strip()
    if not normalized_ticker:
        return

    async with _outside_hours_notify_lock:
        bucket = _outside_hours_notify_buckets.setdefault(normalized_action, [])
        if normalized_ticker not in bucket:
            bucket.append(normalized_ticker)
        if _outside_hours_notify_task is None or _outside_hours_notify_task.done():
            _outside_hours_notify_task = asyncio.create_task(
                _flush_outside_hours_notifications_after_delay()
            )


async def rate_limit():
    """Enforce rate limiting between orders."""
    global _last_order_time
    now = asyncio.get_event_loop().time()
    elapsed = now - _last_order_time

    if elapsed < _min_order_interval:
        await asyncio.sleep(_min_order_interval - elapsed)

    _last_order_time = asyncio.get_event_loop().time()


async def mark_alert_status(
    order_data: dict,
    *,
    processed: bool,
    skipped: bool,
    skip_reason: Optional[str],
    queued: Optional[bool] = None,
):
    """Update alert processing status for auditability and replay safety."""
    alert_log_id = order_data.get("alert_log_id")
    idempotency_key = order_data.get("idempotency_key")
    if not alert_log_id and not idempotency_key:
        return

    try:
        await _mark_alert_status_once(
            order_data,
            processed=processed,
            skipped=skipped,
            skip_reason=skip_reason,
            queued=queued,
            create_missing=True,
        )
    except IntegrityError:
        # The webhook background audit insert can race with a fast worker. If it
        # wins, retry as an update so processing status is still recorded.
        await _mark_alert_status_once(
            order_data,
            processed=processed,
            skipped=skipped,
            skip_reason=skip_reason,
            queued=queued,
            create_missing=False,
        )


def _strip_runtime_fields(order_data: dict) -> dict:
    """Prepare order payload for retry queue insertion."""
    payload = dict(order_data)
    payload.pop("_queue_source", None)
    payload.pop("_raw_queue_payload", None)
    return payload


async def _has_open_position_for_ticker(ticker: str) -> bool:
    """Fast DB check to avoid noisy SELL alerts for symbols we do not hold."""
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        return False

    async with get_session() as session:
        count = (
            await session.execute(
                select(Position.id)
                .where(
                    Position.ticker == symbol,
                    Position.status == PositionStatus.OPEN,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
    return count is not None


def _parse_alert_received_at(value) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _alert_log_from_order(order_data: dict) -> AlertLog:
    price = order_data.get("price")
    try:
        price_float = float(price) if price is not None else None
    except (TypeError, ValueError):
        price_float = None

    return AlertLog(
        ticker=str(order_data.get("ticker") or "").upper(),
        action=str(order_data.get("action") or "").upper(),
        price=price_float,
        alert_id=str(order_data.get("alert_id") or "")[:100] or None,
        raw_payload=None,
        source_ip=str(order_data.get("source_ip") or "")[:50] or None,
        idempotency_key=str(order_data.get("idempotency_key") or "") or None,
        received_at=_parse_alert_received_at(order_data.get("received_at")),
        queued=True,
        processed=False,
        skipped=False,
    )


async def _mark_alert_status_once(
    order_data: dict,
    *,
    processed: bool,
    skipped: bool,
    skip_reason: Optional[str],
    queued: Optional[bool],
    create_missing: bool,
) -> None:
    alert_log_id = order_data.get("alert_log_id")
    idempotency_key = order_data.get("idempotency_key")

    async with get_session() as session:
        row = None
        if alert_log_id:
            row = (
                await session.execute(
                    select(AlertLog).where(AlertLog.id == alert_log_id).limit(1)
                )
            ).scalar_one_or_none()

        if row is None and idempotency_key:
            row = (
                await session.execute(
                    select(AlertLog)
                    .where(AlertLog.idempotency_key == idempotency_key)
                    .limit(1)
                )
            ).scalar_one_or_none()

        if row is None:
            if not create_missing or not idempotency_key:
                return
            row = _alert_log_from_order(order_data)
            session.add(row)

        row.processed = processed
        row.skipped = skipped
        row.skip_reason = skip_reason
        row.processed_at = datetime.now(timezone.utc) if processed else None
        if queued is not None:
            row.queued = queued


async def process_order(order_data: dict) -> dict:
    """
    Process a single order from the queue.

    Flow:
    1. Check market hours → queue for later if closed
    2. Check risk limits → skip if exceeded
    3. Execute order via IB
    4. Send Telegram notification
    """
    action = order_data.get("action", "").upper()
    ticker = order_data.get("ticker", "")
    alert_id = order_data.get("alert_id", "")

    logger.info("Processing order", action=action, ticker=ticker)

    # 1. Check market hours
    bot_settings = await get_bot_settings()

    if bot_settings.regular_hours_only and not is_market_open_for_ticker(ticker):
        if action == "SELL" and not await _has_open_position_for_ticker(ticker):
            logger.info("SELL alert ignored silently because no open position exists", ticker=ticker)
            return {"status": "skipped", "reason": "no_open_position"}

        if bot_settings.queue_outside_hours:
            await enqueue_pending(order_data)
            await queue_outside_hours_notification(action, ticker)
            return {"status": "pending", "reason": "outside_market_hours"}
        else:
            msg = f"⏭️ {action} {ticker} 주문을 건너뛰었습니다 (장 휴장)"
            await send_notification(msg)
            return {"status": "skipped", "reason": "market_closed"}

    # 2. Risk checks
    if action == "BUY":
        risk_result = await check_all_buy_risks(ticker)
        if not risk_result:  # Risk check failed
            reason = getattr(risk_result, "reason", "리스크 체크 실패")
            msg = _friendly_order_issue_text(action, ticker, reason, blocked=True)
            await send_notification(msg)
            return {"status": "blocked", "reason": reason}
    elif action == "SELL":
        risk_result = await check_sell_risks()
        if not risk_result:  # Risk check failed
            reason = getattr(risk_result, "reason", "리스크 체크 실패")
            msg = _friendly_order_issue_text(action, ticker, reason, blocked=True)
            await send_notification(msg)
            return {"status": "blocked", "reason": reason}

    # 3. Rate limit
    await rate_limit()

    # 4. Execute order
    try:
        if action == "BUY":
            result = await execute_buy(ticker, alert_id)
        elif action == "SELL":
            result = await execute_sell(ticker, alert_id)
        else:
            return {"status": "error", "reason": f"알 수 없는 주문 유형: {action}"}
    except Exception as e:
        error_msg = _friendly_order_issue_text(action, ticker, str(e))
        logger.error("Order execution failed", action=action, ticker=ticker, error=str(e))
        await send_notification(error_msg)
        return {"status": "error", "reason": str(e)}

    # 5. Send notification
    if result.get("success"):
        usdkrw_rate = await _get_display_usdkrw_rate()
        currency = str(result.get("currency") or "USD").upper()
        if action == "BUY":
            msg = (
                f"📈 매수 {result['ticker']}\n"
                f"수량: {result['qty']} × {_format_money(result['price'], currency, usdkrw_rate)}\n"
                f"체결금액: {_format_money(result['amount'], currency, usdkrw_rate)}\n"
                f"수수료: {_format_money(result.get('commission', 0), currency, usdkrw_rate)}"
            )
        else:  # SELL
            pnl = result['pnl']
            pnl_emoji = "🟢" if pnl >= 0 else "🔴"
            partial_fill = bool(result.get('partial_fill'))
            header = "📉 매도 일부체결" if partial_fill else "📉 매도"
            detail_suffix = " 반영" if partial_fill else " 정리"
            remaining_line = ""
            partial_note = str(result.get('partial_fill_note', '') or '').strip()
            if partial_fill:
                remaining_qty = result.get('remaining_qty', 0)
                remaining_line = f"\n남은 수량: {remaining_qty}주"
                if partial_note:
                    remaining_line += f"\n참고: {partial_note}"
            msg = (
                f"{header} {result['ticker']} (총 {result['positions_closed']}개 포지션{detail_suffix})\n"
                f"수량: {result['qty']} × {_format_money(result['price'], currency, usdkrw_rate)}\n"
                f"매수 총액: {_format_money(result['entry_total'], currency, usdkrw_rate)}\n"
                f"매도 총액: {_format_money(result['exit_total'], currency, usdkrw_rate)}\n"
                f"{pnl_emoji} 손익: {_format_signed_money(pnl, currency, usdkrw_rate)} "
                f"({result['pnl_pct']:+.1f}%)"
                f"{remaining_line}"
            )
    else:
        error_text = _sanitize_error_for_telegram(result.get("error", "알 수 없는 오류"))

        if action == "SELL" and result.get("skipped"):
            reason = str(result.get("reason") or "sell_skipped")
            await send_notification(f"⏸️ {error_text}")
            return {"status": "skipped", "reason": reason}

        if action == "SELL" and "보유 포지션이 없습니다" in error_text:
            logger.info("SELL alert ignored silently because no open position exists", ticker=ticker)
            return {"status": "skipped", "reason": "no_open_position"}

        if action == "BUY" and "1주 미만 주문을 지원하지 않습니다" in error_text:
            msg = f"⏭️ BUY {ticker}: 매수금이 1주 가격보다 낮아 건너뛰었습니다"
            await send_notification(msg)
            return {"status": "skipped", "reason": "amount_below_one_share"}

        if action == "BUY" and "오늘 매수는 1회만 허용됩니다" in error_text:
            msg = f"⏭️ BUY {ticker}: 오늘 이미 매수되어 건너뛰었습니다"
            await send_notification(msg)
            return {"status": "skipped", "reason": "daily_one_buy_limit"}

        msg = _friendly_order_issue_text(action, ticker, error_text)

    await send_notification(msg)
    if result.get("success"):
        return {"status": "success", "reason": ""}
    return {"status": "failed", "reason": result.get("error", "unknown_error")}


async def worker_loop():
    """
    Main worker loop.
    Continuously polls Redis queues and processes orders.
    """
    logger.info("Order worker starting...")

    # Initialize DB
    await init_db()

    recovered = await requeue_inflight_orders()
    if recovered > 0:
        await send_notification(
            f"♻️ 워커 재시작으로 처리 중이던 주문 {recovered}건을 큐에 복구했습니다"
        )

    mode = (settings.broker_mode or "kis_only").strip().lower()
    if mode == "kis_only":
        logger.info("Worker started in KIS-only mode; skipping initial IB connection")
        await send_notification("🟢 주문 워커가 시작되었습니다 (KIS 전용 모드)")
    else:
        # Connect to IB Gateway (required for ib_only / dual_failover)
        try:
            ib = await get_ib_client()
            if ib.is_connected:
                logger.info("Worker connected to IB Gateway")
                await send_notification("🟢 주문 워커가 시작되었고 IB Gateway 연결이 완료되었습니다")
            else:
                logger.warning("Worker could not connect to IB Gateway, will retry...")
                await send_notification("🟡 주문 워커가 시작되었지만 IB Gateway에 아직 연결되지 않았습니다")
        except Exception as e:
            logger.warning(f"IB Gateway connection failed: {e}, will retry...")
            await send_notification(f"🟡 주문 워커가 시작되었습니다. IB 연결 대기 중: {str(e)}")

    # Main processing loop
    empty_count = 0
    last_pending_flush_ts = 0.0
    last_pending_purge_ts = 0.0
    while True:
        try:
            order = await dequeue_order()

            if order is None:
                now_ts = asyncio.get_event_loop().time()
                if now_ts - last_pending_purge_ts >= 300.0:
                    last_pending_purge_ts = now_ts
                    expired_orders = await purge_expired_pending_orders()
                    if expired_orders:
                        for expired_order in expired_orders:
                            await mark_alert_status(
                                expired_order,
                                processed=True,
                                skipped=True,
                                skip_reason="pending_order_expired_4h_strategy",
                                queued=False,
                            )
                        preview = ", ".join(
                            f"{str(item.get('action', '')).upper()} {str(item.get('ticker', '')).upper()}"
                            for item in expired_orders[:10]
                        )
                        remainder = len(expired_orders) - min(len(expired_orders), 10)
                        if remainder > 0:
                            preview = f"{preview} 외 {remainder}건"
                        await send_notification(
                            "⏳ 오래된 대기 주문을 폐기했습니다\n"
                            f"기준: {settings.pending_order_ttl_hours:g}시간 초과 (4시간봉/4시간봉 전략)\n"
                            f"대상: {preview}"
                        )

                open_markets = []
                if is_krx_market_open():
                    open_markets.append("KRX")
                if is_market_open():
                    open_markets.append("US")
                for market in ASIA_MARKET_SESSIONS:
                    if is_asia_market_open(market):
                        open_markets.append(market)

                if open_markets and now_ts - last_pending_flush_ts >= 60.0:
                    last_pending_flush_ts = now_ts
                    flushed = 0
                    for market in open_markets:
                        flushed += await flush_pending_to_active(market=market)
                    if flushed > 0:
                        await send_notification(
                            f"🔁 워커 안전장치가 대기 주문 {flushed}건을 실행 큐로 이동했습니다"
                        )
                        continue

                # No orders in queue, wait and check again
                empty_count += 1
                # Progressive backoff: 0.1s → 0.5s → 1s → 2s max
                wait_time = min(0.1 * (2 ** min(empty_count, 4)), 2.0)
                await asyncio.sleep(wait_time)
                continue

            empty_count = 0
            ack_now = True
            try:
                try:
                    result = await process_order(order)
                    status = result.get("status", "error")
                    reason = result.get("reason", "")

                    if status == "success":
                        await mark_alert_status(
                            order,
                            processed=True,
                            skipped=False,
                            skip_reason=None,
                            queued=False,
                        )
                    elif status == "pending":
                        await mark_alert_status(
                            order,
                            processed=False,
                            skipped=False,
                            skip_reason=None,
                            queued=True,
                        )
                    elif status in ("blocked", "skipped", "failed", "error"):
                        await mark_alert_status(
                            order,
                            processed=True,
                            skipped=True,
                            skip_reason=(reason or status)[:180],
                            queued=False,
                        )
                    else:
                        await mark_alert_status(
                            order,
                            processed=True,
                            skipped=False,
                            skip_reason=None,
                            queued=False,
                        )
                except Exception as proc_exc:
                    retries = int(order.get("retry_count", 0) or 0)
                    if retries < settings.max_order_retries:
                        retry_order = _strip_runtime_fields(order)
                        retry_order["retry_count"] = retries + 1
                        try:
                            await enqueue_order(retry_order)
                            await mark_alert_status(
                                order,
                                processed=False,
                                skipped=False,
                                skip_reason=None,
                                queued=True,
                            )
                            await send_notification(
                                f"⚠️ 주문 처리 중 예외가 발생해 재시도 큐에 넣었습니다 "
                                f"({retries + 1}/{settings.max_order_retries})\n"
                                f"{order.get('action', '')} {order.get('ticker', '')}\n"
                                f"사유: {str(proc_exc)}"
                            )
                        except Exception as retry_enqueue_exc:
                            requeued = await requeue_processing_order(order)
                            ack_now = False
                            logger.error(
                                "Retry enqueue failed",
                                error=str(retry_enqueue_exc),
                                action=order.get("action"),
                                ticker=order.get("ticker"),
                                requeued_to_source=requeued,
                            )
                            if requeued:
                                await send_notification(
                                    "⚠️ 재시도 큐 적재 실패로 원본 큐로 되돌렸습니다.\n"
                                    f"{order.get('action', '')} {order.get('ticker', '')}\n"
                                    f"사유: {str(retry_enqueue_exc)}"
                                )
                            else:
                                await send_notification(
                                    "❌ 재시도 큐 적재도 실패했습니다. "
                                    "주문을 processing 큐에 보존했습니다.\n"
                                    f"{order.get('action', '')} {order.get('ticker', '')}\n"
                                    f"사유: {str(retry_enqueue_exc)}"
                                )
                    else:
                        await mark_alert_status(
                            order,
                            processed=True,
                            skipped=True,
                            skip_reason=f"max_retries_exceeded: {str(proc_exc)[:140]}",
                            queued=False,
                        )
                        await send_notification(
                            f"❌ 주문 처리 예외가 반복되어 폐기했습니다 "
                            f"({settings.max_order_retries}회 초과)\n"
                            f"{order.get('action', '')} {order.get('ticker', '')}\n"
                            f"사유: {str(proc_exc)}"
                        )
            finally:
                if ack_now:
                    await ack_processed_order(order)

        except Exception as e:
            logger.error("Worker loop error", error=str(e))
            await asyncio.sleep(5)  # Wait before retrying


def handle_shutdown(signum, frame):
    """Handle graceful shutdown."""
    logger.info("Shutdown signal received, stopping worker...")
    sys.exit(0)


if __name__ == "__main__":
    # Handle signals for graceful shutdown
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ]
    )

    asyncio.run(worker_loop())
