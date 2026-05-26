"""Cash coverage checks for queued KIS BUY orders."""

from __future__ import annotations

from app.config import settings
from app.database.connection import get_bot_settings
from app.gateway.symbol_mapper import (
    canonical_trade_symbol,
    is_kis_domestic_symbol,
    kis_overseas_currency,
)
from app.queue.order_queue import get_waiting_buy_orders


async def estimate_pending_buy_cash_coverage(max_quote_checks: int = 80) -> dict:
    """
    Estimate whether current KIS buying power can cover waiting BUY orders.

    KIS 해외주문은 10만원 목표 주문이어도 고가 종목은 최소 1주를 사야 하므로,
    종목별 현재가를 확인해 `max(목표금액, 1주 예상금액)`으로 보수적으로 계산한다.
    """
    orders = await get_waiting_buy_orders(include_processing=False)
    tickers = [
        str(order.get("ticker") or "").strip().upper()
        for order in orders
        if str(order.get("ticker") or "").strip()
    ]

    result = {
        "ok": True,
        "error": None,
        "order_count": len(orders),
        "ticker_count": len(set(tickers)),
        "shortage": False,
        "target_buy_usd": 0.0,
        "target_buy_krw": 0.0,
        "min_reserve_usd": 0.0,
        "usdkrw_rate": 0.0,
        "effective_usd": 0.0,
        "available_after_reserve_usd": 0.0,
        "required_usd": 0.0,
        "shortage_usd": 0.0,
        "coverable_order_count": 0,
        "quote_checked_count": 0,
        "quote_unknown_count": 0,
        "sample_tickers": tickers[:12],
    }
    if not orders:
        return result

    try:
        from app.broker.kis_client import get_kis_client

        kis = await get_kis_client()
        if not kis.is_configured:
            raise RuntimeError("KIS 설정 누락")

        bot_settings = await get_bot_settings()
        domestic_symbols = [
            canonical_trade_symbol(ticker)
            for ticker in tickers
            if is_kis_domestic_symbol(ticker)
        ]
        overseas_symbols = [
            canonical_trade_symbol(ticker)
            for ticker in tickers
            if not is_kis_domestic_symbol(ticker)
        ]

        seed_symbol = overseas_symbols[0] if overseas_symbols else "AAPL"
        funds = await kis.get_effective_usd_orderable(symbol=seed_symbol, order_price=1.0)
        usdkrw_rate = float(funds.get("usd_exrt", 0.0) or 0.0)
        target_buy_krw = float(getattr(settings, "kis_target_buy_krw", 0.0) or 0.0)
        target_buy_usd = float(bot_settings.buy_amount_usd or 0.0)
        if target_buy_krw > 0 and usdkrw_rate > 0:
            target_buy_usd = target_buy_krw / usdkrw_rate
        target_buy_usd = max(target_buy_usd, 1.0)

        min_reserve_usd = max(float(bot_settings.min_cash_reserve or 0.0), 0.0)
        effective_usd = max(float(funds.get("effective_usd", 0.0) or 0.0), 0.0)
        overseas_available_after_reserve_krw = (
            max(effective_usd - min_reserve_usd, 0.0) * usdkrw_rate
            if usdkrw_rate > 0
            else 0.0
        )

        domestic_available_after_reserve_krw = 0.0
        domestic_target_krw = float(
            getattr(settings, "kis_domestic_target_buy_krw", 0.0)
            or target_buy_krw
            or 100000.0
        )
        if domestic_symbols:
            try:
                domestic_seed = domestic_symbols[0]
                domestic_seed_price = float(await kis.get_domestic_quote_price(domestic_seed) or 1.0)
                domestic_funds = await kis.get_domestic_orderable_cash(
                    symbol=domestic_seed,
                    order_price=max(domestic_seed_price, 1.0),
                    ord_dvsn="01",
                )
                domestic_cash_krw = float(
                    domestic_funds.get("nrcvb_buy_amt", 0.0)
                    or domestic_funds.get("ord_psbl_cash", 0.0)
                    or 0.0
                )
                domestic_reserve_krw = float(
                    getattr(settings, "kis_domestic_min_cash_reserve_krw", 0.0)
                    or 0.0
                )
                domestic_available_after_reserve_krw = max(
                    domestic_cash_krw - domestic_reserve_krw,
                    0.0,
                )
            except Exception:
                domestic_available_after_reserve_krw = 0.0

        available_after_reserve_krw = max(
            overseas_available_after_reserve_krw,
            domestic_available_after_reserve_krw,
        )
        available_after_reserve_usd = (
            available_after_reserve_krw / usdkrw_rate
            if usdkrw_rate > 0
            else max(effective_usd - min_reserve_usd, 0.0)
        )

        price_cache: dict[str, float] = {}
        quote_checked_count = 0
        quote_unknown_count = 0
        required_by_order_krw: list[float] = []

        for order in orders:
            ticker = str(order.get("ticker") or "").strip().upper()
            symbol = canonical_trade_symbol(ticker) if ticker else ""
            required_krw = target_buy_usd * usdkrw_rate if usdkrw_rate > 0 else 0.0

            if symbol:
                if symbol in price_cache:
                    required_krw = price_cache[symbol]
                elif quote_checked_count < max_quote_checks:
                    quote_checked_count += 1
                    try:
                        if is_kis_domestic_symbol(symbol):
                            price_krw = float(await kis.get_domestic_quote_price(symbol) or 0.0)
                            required_krw = max(domestic_target_krw, price_krw)
                        else:
                            quote = await kis.get_quote_snapshot(symbol)
                            price = float(quote.get("price", 0.0) or 0.0)
                            currency = str(quote.get("currency") or kis_overseas_currency(symbol))
                            one_share_need = round(max(price * 1.01, 0.01), 8)
                            if currency == "USD":
                                required_krw = max(target_buy_usd, one_share_need) * usdkrw_rate
                            else:
                                local_funds = await kis.get_effective_overseas_orderable(
                                    symbol=symbol,
                                    order_price=max(one_share_need, 1.0),
                                )
                                exrt = float(local_funds.get("exchange_rate_krw", 0.0) or 0.0)
                                target_local = target_buy_krw / exrt if target_buy_krw > 0 and exrt > 0 else one_share_need
                                required_krw = max(target_local, one_share_need) * exrt if exrt > 0 else 0.0
                    except Exception:
                        quote_unknown_count += 1
                        required_krw = domestic_target_krw if is_kis_domestic_symbol(symbol) else target_buy_usd * usdkrw_rate
                    price_cache[symbol] = required_krw
                else:
                    quote_unknown_count += 1

            required_by_order_krw.append(max(required_krw, 0.0))

        used_krw = 0.0
        coverable_order_count = 0
        for required_krw in required_by_order_krw:
            if used_krw + required_krw <= available_after_reserve_krw + 1e-9:
                used_krw += required_krw
                coverable_order_count += 1
            else:
                break

        required_krw_total = sum(required_by_order_krw)
        shortage_krw = max(required_krw_total - available_after_reserve_krw, 0.0)
        required_usd_total = required_krw_total / usdkrw_rate if usdkrw_rate > 0 else 0.0
        shortage_usd = shortage_krw / usdkrw_rate if usdkrw_rate > 0 else 0.0
        result.update(
            {
                "display_currency": "KRW",
                "target_buy_usd": round(target_buy_usd, 2),
                "target_buy_krw": round(target_buy_krw if target_buy_krw > 0 else target_buy_usd * usdkrw_rate, 0),
                "min_reserve_usd": round(min_reserve_usd, 2),
                "usdkrw_rate": round(usdkrw_rate, 6),
                "effective_usd": round(effective_usd, 2),
                "available_after_reserve_usd": round(available_after_reserve_usd, 2),
                "available_after_reserve_krw": round(available_after_reserve_krw, 0),
                "required_usd": round(required_usd_total, 2),
                "required_krw": round(required_krw_total, 0),
                "shortage_usd": round(shortage_usd, 2),
                "shortage_krw": round(shortage_krw, 0),
                "shortage": shortage_krw > 1.0,
                "coverable_order_count": coverable_order_count,
                "quote_checked_count": quote_checked_count,
                "quote_unknown_count": quote_unknown_count,
            }
        )
    except Exception as exc:
        result.update({"ok": False, "error": str(exc)})

    return result
