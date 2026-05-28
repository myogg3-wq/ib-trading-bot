"""
KIS Open API client (overseas stocks/ETF).
Designed for optional dual-broker operation alongside IBKR.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional

import httpx
import structlog

from app.config import settings
from app.gateway.symbol_mapper import (
    canonical_trade_symbol,
    kis_overseas_exchange_meta,
    trade_symbol_code,
)

logger = structlog.get_logger()

_kis_instance = None
_kis_lock = asyncio.Lock()

# Exchange code mapping (KIS overseas quote <-> order API)
_QUOTE_TO_ORDER_EXCHANGE = {
    "NAS": "NASD",   # Nasdaq
    "NYS": "NYSE",   # New York Stock Exchange
    "AMS": "AMEX",   # NYSE Arca / AMEX
    "HKS": "SEHK",   # Hong Kong
    "SHS": "SHAA",   # Shanghai
    "SZS": "SZAA",   # Shenzhen
    "TSE": "TKSE",   # Tokyo
}
_ORDER_TO_QUOTE_EXCHANGE = {v: k for k, v in _QUOTE_TO_ORDER_EXCHANGE.items()}
_ORDER_TO_CURRENCY = {
    "NASD": "USD",
    "NYSE": "USD",
    "AMEX": "USD",
    "SEHK": "HKD",
    "SHAA": "CNY",
    "SZAA": "CNY",
    "TKSE": "JPY",
}
_QUOTE_TO_CURRENCY = {
    quote: _ORDER_TO_CURRENCY.get(order, "USD")
    for quote, order in _QUOTE_TO_ORDER_EXCHANGE.items()
}
_ALL_ORDER_EXCHANGES = ["NASD", "NYSE", "AMEX", "SEHK", "SHAA", "SZAA", "TKSE"]
_US_ORDER_EXCHANGES = ["NASD", "NYSE", "AMEX"]
_BUY_TR_ID_BY_ORDER_EXCHANGE = {
    "NASD": "TTTT1002U",
    "NYSE": "TTTT1002U",
    "AMEX": "TTTT1002U",
    "SEHK": "TTTS1002U",
    "SHAA": "TTTS0202U",
    "SZAA": "TTTS0305U",
    "TKSE": "TTTS0308U",
}
_SELL_TR_ID_BY_ORDER_EXCHANGE = {
    "NASD": "TTTT1006U",
    "NYSE": "TTTT1006U",
    "AMEX": "TTTT1006U",
    "SEHK": "TTTS1001U",
    "SHAA": "TTTS1005U",
    "SZAA": "TTTS0304U",
    "TKSE": "TTTS0307U",
}
_INTEGRATED_MARGIN_FIELDS = {
    "USD": ("usd_itgr_ord_psbl_amt", "usd_frst_bltn_exrt"),
    "HKD": ("hkd_itgr_ord_psbl_amt", "hkd_frst_bltn_exrt"),
    "CNY": ("cny_itgr_ord_psbl_amt", "cny_frst_bltn_exrt"),
    "JPY": ("jpy_itgr_ord_psbl_amt", "jpy_frst_bltn_exrt"),
}
_OVERSEAS_BALANCE_PATH = "/uapi/overseas-stock/v1/trading/inquire-balance"


def _is_retryable_http_error(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError, httpx.RemoteProtocolError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = int(getattr(exc.response, "status_code", 0) or 0)
        return status in (429, 500, 502, 503, 504)
    return False


def _kis_get_retry_log_method(path: str, attempt: int, max_retries: int) -> str:
    if path == _OVERSEAS_BALANCE_PATH and attempt < max_retries:
        return ""
    return "warning"


def _to_float(value) -> Optional[float]:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if num > 0 else None


def _to_float_or_zero(value) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return 0.0
    return num if num > 0 else 0.0


def _to_float_signed_or_zero(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int_or_zero(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _quantize_us_order_price(value) -> Decimal:
    try:
        price = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise RuntimeError(f"잘못된 주문 단가입니다: {value}")
    if price < Decimal("0.01"):
        price = Decimal("0.01")
    return price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _format_us_order_price(value) -> str:
    """KIS overseas order price fields accept a compact two-decimal USD price."""
    return f"{_quantize_us_order_price(value):.2f}"


def _format_overseas_order_price(value, currency: str = "USD") -> str:
    """
    KIS overseas order price accepts up to 8 decimals.
    Keep USD at two decimals to preserve existing behavior.
    """
    currency_upper = str(currency or "USD").upper()
    if currency_upper == "USD":
        return _format_us_order_price(value)
    try:
        price = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise RuntimeError(f"잘못된 주문 단가입니다: {value}")
    if price <= Decimal("0"):
        price = Decimal("0.00000001")
    if currency_upper == "JPY":
        return str(int(price.quantize(Decimal("1"), rounding=ROUND_HALF_UP)))
    text = f"{price.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP):f}"
    return text.rstrip("0").rstrip(".") or "0.00000001"


def _format_krw_order_price(value) -> str:
    """KIS domestic cash-order price fields use integer KRW text."""
    try:
        price = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise RuntimeError(f"잘못된 국내 주문 단가입니다: {value}")
    if price < Decimal("0"):
        price = Decimal("0")
    return str(int(price.quantize(Decimal("1"), rounding=ROUND_HALF_UP)))


def _bounded_percent(value, *, default: float, lower: float = 0.0, upper: float = 20.0) -> float:
    try:
        pct = float(value)
    except (TypeError, ValueError):
        pct = default
    return max(lower, min(upper, pct))


def _buffered_buy_limit_price(price: float, currency: str) -> float:
    markup = _bounded_percent(settings.kis_buy_limit_markup_pct, default=3.0)
    buffered = float(price) * (1.0 + markup / 100.0)
    currency_upper = str(currency or "USD").upper()
    if currency_upper == "USD":
        return float(_quantize_us_order_price(buffered))
    if currency_upper == "JPY":
        return float(Decimal(str(buffered)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return float(Decimal(str(buffered)).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP))


def _buffered_sell_limit_price(price: float, currency: str, min_limit_price: Optional[float] = None) -> float:
    markdown = _bounded_percent(settings.kis_sell_limit_markdown_pct, default=1.0, upper=10.0)
    buffered = float(price) * (1.0 - markdown / 100.0)
    if min_limit_price and min_limit_price > 0:
        buffered = max(buffered, float(min_limit_price))
    currency_upper = str(currency or "USD").upper()
    if currency_upper == "USD":
        return float(_quantize_us_order_price(buffered))
    if currency_upper == "JPY":
        return float(Decimal(str(buffered)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return float(Decimal(str(buffered)).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP))


def _is_retryable_order_submit_error(exc: Exception) -> bool:
    if _is_retryable_http_error(exc):
        return True
    text = str(exc)
    markers = (
        "500 Internal Server Error",
        "502 Bad Gateway",
        "503 Service Unavailable",
        "504 Gateway Timeout",
        "429",
        "Server disconnected",
        "RemoteProtocolError",
        "timed out",
        "Timeout",
        "connection",
    )
    return any(marker.lower() in text.lower() for marker in markers)


def _normalize_domestic_symbol(symbol: str) -> str:
    symbol_upper = str(symbol or "").strip().upper()
    if ":" in symbol_upper:
        symbol_upper = symbol_upper.split(":", 1)[1].strip()
    is_numeric_code = symbol_upper.isdigit() and 5 <= len(symbol_upper) <= 7
    is_alphanumeric_product_code = bool(re.fullmatch(r"\d{4}[A-Z]\d", symbol_upper))
    if not (is_numeric_code or is_alphanumeric_product_code):
        raise RuntimeError(f"국내 종목코드는 5~7자리 숫자 또는 KRX 상품코드여야 합니다: {symbol}")
    return symbol_upper


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for value in values:
        item = str(value or "").strip().upper()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


class KISClient:
    """Minimal async client for KIS overseas quote/order APIs."""

    def __init__(self):
        self._access_token: Optional[str] = None
        self._access_token_expires_at: Optional[datetime] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._token_lock = asyncio.Lock()
        # symbol -> (quote_exchange, order_exchange)
        self._symbol_exchange_cache: dict[str, tuple[str, str]] = {}

    @property
    def is_configured(self) -> bool:
        required = [
            settings.kis_base_url,
            settings.kis_app_key,
            settings.kis_app_secret,
            settings.kis_account_no,
            settings.kis_account_product_code,
        ]
        return all(str(v).strip() for v in required)

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=20.0)
        return self._client

    def _symbol_key(self, symbol: Optional[str]) -> str:
        return canonical_trade_symbol(str(symbol or "").strip().upper())

    def _symbol_code(self, symbol: Optional[str]) -> str:
        return trade_symbol_code(self._symbol_key(symbol))

    def _explicit_overseas_meta(self, symbol: Optional[str]) -> dict:
        return kis_overseas_exchange_meta(self._symbol_key(symbol))

    def _quote_exchange_candidates(self, symbol: Optional[str] = None) -> list[str]:
        symbol_key = self._symbol_key(symbol)
        meta = self._explicit_overseas_meta(symbol_key)
        configured = str(settings.kis_quote_exchange_code or "").strip().upper()
        cached_quote = self._symbol_exchange_cache.get(symbol_key, ("", ""))[0]
        if meta.get("quote"):
            return _dedupe_preserve_order([cached_quote, str(meta["quote"])])
        return _dedupe_preserve_order([cached_quote, configured, "NAS", "NYS", "AMS"])

    def _order_exchange_candidates(self, symbol: Optional[str] = None) -> list[str]:
        symbol_key = self._symbol_key(symbol)
        meta = self._explicit_overseas_meta(symbol_key)
        configured = str(settings.kis_order_exchange_code or "").strip().upper()
        cached_order = self._symbol_exchange_cache.get(symbol_key, ("", ""))[1]
        if meta.get("order"):
            return _dedupe_preserve_order([cached_order, str(meta["order"])])
        if symbol is None:
            return _dedupe_preserve_order([configured, *_ALL_ORDER_EXCHANGES])
        return _dedupe_preserve_order([cached_order, configured, *_US_ORDER_EXCHANGES])

    def _remember_symbol_exchange(self, symbol: str, quote_exchange: str):
        symbol_key = self._symbol_key(symbol)
        quote_code = str(quote_exchange or "").strip().upper()
        if not symbol_key or not quote_code:
            return
        order_code = _QUOTE_TO_ORDER_EXCHANGE.get(
            quote_code,
            str(settings.kis_order_exchange_code or "NASD").strip().upper(),
        )
        self._symbol_exchange_cache[symbol_key] = (quote_code, order_code)

    def _currency_for_order_exchange(self, order_exchange: str) -> str:
        return _ORDER_TO_CURRENCY.get(str(order_exchange or "").strip().upper(), "USD")

    def _currency_for_quote_exchange(self, quote_exchange: str) -> str:
        return _QUOTE_TO_CURRENCY.get(str(quote_exchange or "").strip().upper(), "USD")

    def _order_tr_id(self, order_exchange: str, side: str) -> str:
        order_code = str(order_exchange or "").strip().upper()
        side_upper = str(side or "").strip().upper()
        tr_map = _BUY_TR_ID_BY_ORDER_EXCHANGE if side_upper == "BUY" else _SELL_TR_ID_BY_ORDER_EXCHANGE
        tr_id = tr_map.get(order_code)
        if not tr_id:
            fallback = settings.kis_buy_tr_id if side_upper == "BUY" else settings.kis_sell_tr_id
            tr_id = str(fallback or "").strip().upper()
        return tr_id

    async def _get(
        self,
        path: str,
        *,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
        include_response_headers: bool = False,
        retries: Optional[int] = None,
        retry_delay: Optional[float] = None,
    ):
        """
        GET wrapper with lightweight retry for transient transport failures.
        Order POST endpoints are intentionally excluded from retries.
        """
        max_retries = max(0, int(settings.kis_get_retry_count if retries is None else retries))
        base_delay = max(0.1, float(settings.kis_get_retry_delay_seconds if retry_delay is None else retry_delay))
        max_delay = max(base_delay, float(settings.kis_get_retry_max_delay_seconds or base_delay))
        attempt = 0
        while True:
            attempt += 1
            try:
                return await self._request_json(
                    "GET",
                    path,
                    headers=headers,
                    params=params,
                    include_response_headers=include_response_headers,
                )
            except Exception as e:
                if not _is_retryable_http_error(e):
                    raise
                if attempt > max_retries:
                    raise
                sleep_for = min(max_delay, base_delay * (2 ** max(0, attempt - 1)))
                sleep_for += random.uniform(0.0, min(0.25, base_delay))
                log_method = _kis_get_retry_log_method(path, attempt, max_retries)
                if log_method:
                    log_retry = getattr(logger, log_method)
                    log_retry(
                        "KIS GET transient error, retrying",
                        path=path,
                        attempt=attempt,
                        max_retries=max_retries,
                        sleep_seconds=round(sleep_for, 3),
                        error=str(e),
                    )
                await asyncio.sleep(sleep_for)

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        include_response_headers: bool = False,
        **kwargs,
    ):
        base = settings.kis_base_url.rstrip("/")
        url = f"{base}{path}"
        client = await self._http()
        response = await client.request(method, url, **kwargs)
        if (
            response.status_code == 401
            and path != "/oauth2/tokenP"
            and kwargs.get("headers", {}).get("authorization")
        ):
            logger.warning("KIS access token unauthorized, forcing refresh", path=path)
            self._access_token = None
            self._access_token_expires_at = None
            refreshed_headers = dict(kwargs.get("headers") or {})
            refreshed_headers["authorization"] = f"Bearer {await self.get_access_token(force_refresh=True)}"
            retry_kwargs = dict(kwargs)
            retry_kwargs["headers"] = refreshed_headers
            response = await client.request(method, url, **retry_kwargs)
        response.raise_for_status()
        data = response.json()
        if include_response_headers:
            return data, dict(response.headers)
        return data

    def _token_cache_path(self) -> str:
        return os.getenv("KIS_TOKEN_CACHE_PATH") or settings.kis_token_cache_path or "/app/app/.runtime/kis_access_token.json"

    def _load_cached_token_from_disk(self) -> tuple[Optional[str], Optional[datetime]]:
        path = self._token_cache_path()
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except FileNotFoundError:
            return None, None
        except Exception as e:
            logger.warning("Failed to read KIS token cache", path=path, error=str(e))
            return None, None

        token = str(payload.get("access_token") or "").strip()
        expires_at_raw = str(payload.get("expires_at") or "").strip()
        if not token or not expires_at_raw:
            return None, None
        try:
            expires_at = datetime.fromisoformat(expires_at_raw)
        except ValueError:
            logger.warning("Invalid KIS token cache timestamp", path=path, expires_at=expires_at_raw)
            return None, None
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return token, expires_at.astimezone(timezone.utc)

    def _save_cached_token_to_disk(self, token: str, expires_at: datetime):
        path = self._token_cache_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp_path = f"{path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "access_token": token,
                        "expires_at": expires_at.astimezone(timezone.utc).isoformat(),
                        "cached_at": datetime.now(timezone.utc).isoformat(),
                    },
                    f,
                )
            os.replace(tmp_path, path)
        except Exception as e:
            logger.warning("Failed to persist KIS token cache", path=path, error=str(e))

    async def get_access_token(self, force_refresh: bool = False) -> str:
        if not self.is_configured:
            raise RuntimeError("KIS 설정이 누락되었습니다 (.env의 KIS_* 값 확인)")

        async with self._token_lock:
            now = datetime.now(timezone.utc)
            if (
                not force_refresh
                and self._access_token
                and self._access_token_expires_at
                and now < self._access_token_expires_at - timedelta(seconds=60)
            ):
                return self._access_token

            if not force_refresh:
                cached_token, cached_expires_at = self._load_cached_token_from_disk()
                if (
                    cached_token
                    and cached_expires_at
                    and now < cached_expires_at - timedelta(seconds=60)
                ):
                    self._access_token = cached_token
                    self._access_token_expires_at = cached_expires_at
                    return cached_token

            payload = {
                "grant_type": "client_credentials",
                "appkey": settings.kis_app_key,
                "appsecret": settings.kis_app_secret,
            }
            headers = {"content-type": "application/json; charset=utf-8"}

            last_error: Optional[Exception] = None
            for attempt in range(1, 4):
                try:
                    data = await self._request_json(
                        "POST",
                        "/oauth2/tokenP",
                        json=payload,
                        headers=headers,
                    )
                    token = data.get("access_token")
                    if not token:
                        raise RuntimeError(f"KIS 토큰 발급 실패: {data}")

                    expires_in = int(data.get("expires_in", 86400))
                    expires_at = now + timedelta(seconds=expires_in)
                    self._access_token = token
                    self._access_token_expires_at = expires_at
                    self._save_cached_token_to_disk(token, expires_at)
                    return token
                except Exception as e:
                    last_error = e
                    logger.warning(
                        "KIS token issuance failed",
                        attempt=attempt,
                        error=str(e),
                    )
                    await asyncio.sleep(0.5 * attempt)

            cached_token, cached_expires_at = self._load_cached_token_from_disk()
            if (
                cached_token
                and cached_expires_at
                and now < cached_expires_at - timedelta(seconds=60)
            ):
                logger.warning(
                    "Using cached KIS token after issuance failure",
                    expires_at=cached_expires_at.isoformat(),
                    error=str(last_error) if last_error else "",
                )
                self._access_token = cached_token
                self._access_token_expires_at = cached_expires_at
                return cached_token

            raise RuntimeError(f"KIS 토큰 발급 실패: {str(last_error) if last_error else 'unknown'}")

    async def _authorized_headers(self, tr_id: str) -> dict:
        token = await self.get_access_token()
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": settings.kis_app_key,
            "appsecret": settings.kis_app_secret,
            "tr_id": tr_id,
            "custtype": settings.kis_custtype,
        }

    async def get_quote_snapshot(self, symbol: str) -> dict:
        """
        Get overseas quote snapshot.
        Returns:
        - price: current/last trade price (>0)
        - prev_close: previous close price (0 if unavailable)
        - quote_exchange: resolved quote exchange code
        - raw: raw KIS response payload
        """
        headers = await self._authorized_headers(settings.kis_quote_tr_id)
        symbol_key = self._symbol_key(symbol)
        symbol_code = self._symbol_code(symbol)
        tried_codes = []
        errors = []

        for quote_code in self._quote_exchange_candidates(symbol_key):
            tried_codes.append(quote_code)
            params = {
                "AUTH": "",
                "EXCD": quote_code,
                "SYMB": symbol_code,
            }

            try:
                data = await self._get(
                    settings.kis_quote_path,
                    headers=headers,
                    params=params,
                )
            except Exception as e:
                errors.append(f"{quote_code}:{str(e)}")
                continue

            if str(data.get("rt_cd", "1")) != "0":
                msg = data.get("msg1") or data.get("msg_cd") or "unknown"
                errors.append(f"{quote_code}:{msg}")
                continue

            output = data.get("output") or data.get("output1") or {}
            if not isinstance(output, dict):
                output = {}

            price_candidates = [
                output.get("last"),
                output.get("now_pric2"),
                output.get("ovrs_nmix_prpr"),
                output.get("stck_prpr"),
                output.get("ovrs_prpr"),
                output.get("clos"),
                data.get("last"),
            ]
            prev_close_candidates = [
                output.get("clos"),
                output.get("prdy_clpr"),
                output.get("ovrs_prdy_clpr"),
                output.get("stck_prdy_clpr"),
                output.get("base"),
            ]

            resolved_price = None
            for value in price_candidates:
                price = _to_float(value)
                if price is not None:
                    resolved_price = price
                    break

            if resolved_price is not None:
                prev_close = 0.0
                for value in prev_close_candidates:
                    candidate = _to_float(value)
                    if candidate is not None:
                        prev_close = float(candidate)
                        break

                self._remember_symbol_exchange(symbol_key, quote_code)
                return {
                    "symbol": symbol_key,
                    "symbol_code": symbol_code,
                    "price": float(resolved_price),
                    "prev_close": float(prev_close),
                    "quote_exchange": quote_code,
                    "currency": self._currency_for_quote_exchange(quote_code),
                    "raw": data,
                }

            errors.append(f"{quote_code}:no-price")

        reason = " / ".join(errors[:3]) if errors else "unknown"
        tried = ",".join(tried_codes) if tried_codes else "-"
        raise RuntimeError(
            f"KIS 시세 응답에서 유효 가격을 찾지 못했습니다 "
            f"(종목:{symbol_key}, 시도:{tried}, 원인:{reason})"
        )

    async def get_quote_price(self, symbol: str) -> float:
        """
        Get overseas quote price.
        Returns a positive price or raises RuntimeError.
        """
        snapshot = await self.get_quote_snapshot(symbol)
        price = float(snapshot.get("price", 0.0) or 0.0)
        if price <= 0:
            raise RuntimeError(f"KIS 시세 응답에서 유효 가격을 찾지 못했습니다 (종목:{symbol})")
        return price

    async def get_domestic_quote_snapshot(self, symbol: str) -> dict:
        """
        Get KRX/domestic quote snapshot.
        Returns price fields in KRW.
        """
        symbol_code = _normalize_domestic_symbol(symbol)
        headers = await self._authorized_headers("FHPST01010000")
        params = {
            "FID_COND_MRKT_DIV_CODE": str(settings.kis_domestic_market_div_code or "J").strip().upper(),
            "FID_INPUT_ISCD": symbol_code,
        }

        data = await self._get(
            settings.kis_domestic_quote_path,
            headers=headers,
            params=params,
        )
        if str(data.get("rt_cd", "1")) != "0":
            msg = data.get("msg1") or data.get("msg_cd") or "unknown"
            raise RuntimeError(f"KIS 국내 시세 조회 실패: {symbol_code} ({msg})")

        output = data.get("output") or {}
        if not isinstance(output, dict):
            output = {}

        price = None
        for value in (
            output.get("stck_prpr"),
            output.get("prpr"),
            output.get("stck_oprc"),
            output.get("stck_sdpr"),
        ):
            candidate = _to_float(value)
            if candidate is not None:
                price = candidate
                break

        if price is None:
            raise RuntimeError(f"KIS 국내 시세 응답에서 유효 가격을 찾지 못했습니다 (종목:{symbol_code})")

        prev_close = 0.0
        for value in (output.get("stck_prdy_clpr"), output.get("prdy_clpr"), output.get("stck_sdpr")):
            candidate = _to_float(value)
            if candidate is not None:
                prev_close = float(candidate)
                break

        return {
            "symbol": symbol_code,
            "price": float(price),
            "prev_close": float(prev_close),
            "currency": "KRW",
            "raw": data,
        }

    async def get_domestic_quote_price(self, symbol: str) -> float:
        """Get KRX/domestic quote price in KRW."""
        snapshot = await self.get_domestic_quote_snapshot(symbol)
        price = float(snapshot.get("price", 0.0) or 0.0)
        if price <= 0:
            raise RuntimeError(f"KIS 국내 시세 응답에서 유효 가격을 찾지 못했습니다 (종목:{symbol})")
        return price

    async def get_unfilled_orders(self, exchange_code: Optional[str] = None) -> list[dict]:
        """
        Query overseas unfilled orders.
        """
        headers = await self._authorized_headers("TTTS3018R")
        target_codes = (
            [str(exchange_code).strip().upper()]
            if exchange_code
            else self._order_exchange_candidates()
        )
        rows: list[dict] = []
        seen = set()
        errors = []
        success_calls = 0

        for code in target_codes:
            params = {
                "CANO": settings.kis_account_no,
                "ACNT_PRDT_CD": settings.kis_account_product_code,
                "OVRS_EXCG_CD": code,
                "SORT_SQN": "DS",
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": "",
            }
            try:
                data = await self._get(
                    "/uapi/overseas-stock/v1/trading/inquire-nccs",
                    headers=headers,
                    params=params,
                )
            except Exception as e:
                errors.append(f"{code}:{str(e)}")
                continue

            if str(data.get("rt_cd", "1")) != "0":
                msg = data.get("msg1") or data.get("msg_cd") or "unknown"
                errors.append(f"{code}:{msg}")
                continue

            success_calls += 1
            output = data.get("output") or []
            if not isinstance(output, list):
                continue
            for row in output:
                if not isinstance(row, dict):
                    continue
                key = (
                    str(row.get("odno") or "").strip(),
                    str(row.get("pdno") or row.get("ovrs_pdno") or "").strip().upper(),
                )
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row)

        if success_calls == 0 and errors:
            raise RuntimeError("KIS 미체결 조회 실패: " + " / ".join(errors[:3]))
        return rows

    async def find_unfilled_order(self, order_id: str, symbol: str) -> Optional[dict]:
        """
        Find unfilled order row by order id and symbol.
        """
        target_order = str(order_id or "").strip()
        target_key = self._symbol_key(symbol)
        target_symbol = self._symbol_code(target_key)
        if not target_order:
            return None
        rows = await self.get_unfilled_orders(exchange_code=self._order_exchange_candidates(target_key)[0])
        for row in rows:
            if not isinstance(row, dict):
                continue
            odno = str(row.get("odno") or "").strip()
            pdno = str(row.get("pdno") or "").strip().upper()
            if odno == target_order and pdno == target_symbol:
                return row
        return None

    async def has_unfilled_symbol_order(self, symbol: str) -> bool:
        """Return True when an open overseas order exists for this symbol."""
        symbol_key = self._symbol_key(symbol)
        target_symbol = self._symbol_code(symbol_key)
        rows = await self.get_unfilled_orders(exchange_code=self._order_exchange_candidates(symbol_key)[0])
        for row in rows:
            if not isinstance(row, dict):
                continue
            pdno = str(row.get("pdno") or row.get("ovrs_pdno") or "").strip().upper()
            unfilled_qty = _to_int_or_zero(row.get("nccs_qty") or row.get("ord_psbl_qty") or row.get("qty"))
            if pdno == target_symbol and unfilled_qty > 0:
                return True
        return False

    async def get_overseas_balance(
        self,
        exchange_code: Optional[str] = None,
        currency_code: Optional[str] = None,
    ) -> list[dict]:
        """
        Query overseas balance rows (output1).
        """
        headers = await self._authorized_headers("TTTS3012R")
        target_codes = (
            [str(exchange_code).strip().upper()]
            if exchange_code
            else self._order_exchange_candidates()
        )
        rows: list[dict] = []
        seen_symbols = set()
        errors = []
        success_calls = 0

        for code in target_codes:
            params = {
                "CANO": settings.kis_account_no,
                "ACNT_PRDT_CD": settings.kis_account_product_code,
                "OVRS_EXCG_CD": code,
                "TR_CRCY_CD": str(currency_code or self._currency_for_order_exchange(code)).upper(),
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": "",
            }
            try:
                data = await self._get(
                    _OVERSEAS_BALANCE_PATH,
                    headers=headers,
                    params=params,
                )
            except Exception as e:
                errors.append(f"{code}:{str(e)}")
                continue

            if str(data.get("rt_cd", "1")) != "0":
                msg = data.get("msg1") or data.get("msg_cd") or "unknown"
                errors.append(f"{code}:{msg}")
                continue

            success_calls += 1
            output = data.get("output1") or []
            if not isinstance(output, list):
                continue
            for row in output:
                if not isinstance(row, dict):
                    continue
                symbol_key = str(
                    row.get("ovrs_pdno")
                    or row.get("pdno")
                    or row.get("item_cd")
                    or ""
                ).strip().upper()
                if symbol_key and symbol_key in seen_symbols:
                    continue
                if symbol_key:
                    seen_symbols.add(symbol_key)
                rows.append(row)

        if success_calls == 0 and errors:
            raise RuntimeError("KIS 잔고 조회 실패: " + " / ".join(errors[:3]))
        return rows

    async def get_overseas_balance_summary(
        self,
        exchange_code: Optional[str] = None,
        currency_code: str = "USD",
    ) -> dict:
        """
        Query overseas balance summary (output2).
        Returns purchase/evaluation/pnl aggregate fields in USD.
        """
        headers = await self._authorized_headers("TTTS3012R")
        order_code = (
            str(exchange_code).strip().upper()
            if exchange_code
            else self._order_exchange_candidates()[0]
        )
        params = {
            "CANO": settings.kis_account_no,
            "ACNT_PRDT_CD": settings.kis_account_product_code,
            "OVRS_EXCG_CD": order_code,
            "TR_CRCY_CD": currency_code,
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": "",
        }
        data = await self._get(
            _OVERSEAS_BALANCE_PATH,
            headers=headers,
            params=params,
        )
        if str(data.get("rt_cd", "1")) != "0":
            msg = data.get("msg1") or data.get("msg_cd") or "unknown"
            raise RuntimeError(f"KIS 잔고 요약 조회 실패: {msg}")

        output2 = data.get("output2") or {}
        if isinstance(output2, list):
            output2 = output2[0] if output2 else {}
        if not isinstance(output2, dict):
            output2 = {}

        purchase_usd = _to_float_or_zero(output2.get("frcr_pchs_amt1"))
        eval_amount_usd = _to_float_or_zero(output2.get("tot_evlu_pfls_amt"))
        eval_pnl_usd = _to_float_signed_or_zero(output2.get("ovrs_tot_pfls"))
        eval_pnl_pct = 0.0
        try:
            eval_pnl_pct = float(output2.get("tot_pftrt") or 0.0)
        except (TypeError, ValueError):
            eval_pnl_pct = 0.0

        return {
            "purchase_usd": round(purchase_usd, 8),
            "eval_amount_usd": round(eval_amount_usd, 8),
            "eval_pnl_usd": round(eval_pnl_usd, 8),
            "eval_pnl_pct": float(eval_pnl_pct),
            "raw": output2,
        }

    async def get_symbol_balance(self, symbol: str) -> dict:
        """
        Return simplified per-symbol balance snapshot.
        """
        target_key = self._symbol_key(symbol)
        target = self._symbol_code(target_key)
        order_candidates = self._order_exchange_candidates(target_key)
        currency = self._currency_for_order_exchange(order_candidates[0])

        for order_code in order_candidates:
            currency = self._currency_for_order_exchange(order_code)
            rows = await self.get_overseas_balance(exchange_code=order_code, currency_code=currency)

            for row in rows:
                if not isinstance(row, dict):
                    continue
                pdno = str(
                    row.get("ovrs_pdno")
                    or row.get("pdno")
                    or row.get("item_cd")
                    or ""
                ).strip().upper()
                if pdno != target:
                    continue

                qty = _to_int_or_zero(
                    row.get("ovrs_cblc_qty")
                    or row.get("cblc_qty")
                    or row.get("hold_qty")
                    or row.get("blce_qty")
                )
                orderable_qty = _to_int_or_zero(
                    row.get("ord_psbl_qty")
                    or row.get("sell_psbl_qty")
                    or row.get("ovrs_ord_psbl_qty")
                )
                avg_price = _to_float_or_zero(
                    row.get("pchs_avg_pric")
                    or row.get("avg_unpr")
                    or row.get("avg_price")
                )
                self._symbol_exchange_cache[target_key] = (
                    _ORDER_TO_QUOTE_EXCHANGE.get(order_code, ""),
                    order_code,
                )
                return {
                    "symbol": target_key,
                    "symbol_code": target,
                    "currency": currency,
                    "qty": qty,
                    "orderable_qty": orderable_qty,
                    "avg_price": round(avg_price, 6),
                    "raw": row,
                }

        return {
            "symbol": target_key,
            "symbol_code": target,
            "currency": currency,
            "qty": 0,
            "orderable_qty": 0,
            "avg_price": 0.0,
            "raw": None,
        }

    async def get_order_history(
        self,
        start_ymd: str,
        end_ymd: str,
        symbol: str = "%",
        side_code: str = "00",
        ccld_nccs_code: str = "00",
        exchange_code: Optional[str] = None,
    ) -> list[dict]:
        """
        Query overseas order/execution history rows.
        """
        headers = await self._authorized_headers("TTTS3035R")
        symbol_key = self._symbol_key(symbol)
        symbol_code = self._symbol_code(symbol_key)
        is_all_symbols = symbol_code in ("", "%")
        target_codes = (
            [str(exchange_code).strip().upper()]
            if exchange_code
            else self._order_exchange_candidates(None if is_all_symbols else symbol_key)
        )
        rows: list[dict] = []
        seen = set()
        errors = []
        success_calls = 0

        for code in target_codes:
            params = {
                "CANO": settings.kis_account_no,
                "ACNT_PRDT_CD": settings.kis_account_product_code,
                "PDNO": symbol_code or "%",
                "ORD_STRT_DT": start_ymd,
                "ORD_END_DT": end_ymd,
                "SLL_BUY_DVSN": side_code,  # 00 all, 01 sell, 02 buy
                "CCLD_NCCS_DVSN": ccld_nccs_code,  # 00 all, 01 filled, 02 unfilled
                "OVRS_EXCG_CD": code,
                "SORT_SQN": "DS",
                "ORD_DT": "",
                "ORD_GNO_BRNO": "",
                "ODNO": "",
                "CTX_AREA_NK200": "",
                "CTX_AREA_FK200": "",
            }
            try:
                data = await self._get(
                    "/uapi/overseas-stock/v1/trading/inquire-ccnl",
                    headers=headers,
                    params=params,
                )
            except Exception as e:
                errors.append(f"{code}:{str(e)}")
                continue

            if str(data.get("rt_cd", "1")) != "0":
                msg = data.get("msg1") or data.get("msg_cd") or "unknown"
                errors.append(f"{code}:{msg}")
                continue

            success_calls += 1
            output = data.get("output") or []
            if isinstance(output, dict):
                output = [output]
            if not isinstance(output, list):
                continue
            for row in output:
                if not isinstance(row, dict):
                    continue
                key = (
                    str(row.get("odno") or "").strip(),
                    str(row.get("pdno") or "").strip().upper(),
                    str(row.get("ord_dt") or "").strip(),
                )
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row)

        if success_calls == 0 and errors:
            raise RuntimeError("KIS 주문체결내역 조회 실패: " + " / ".join(errors[:3]))
        return rows

    async def find_order_history_row(self, order_id: str, symbol: str, days_back: int = 2) -> Optional[dict]:
        """
        Find a history row by order id + symbol in recent date window.
        """
        target_order = str(order_id or "").strip()
        target_key = self._symbol_key(symbol)
        target_symbol = self._symbol_code(target_key)
        if not target_order:
            return None

        now_utc = datetime.now(timezone.utc)
        start_ymd = (now_utc - timedelta(days=max(1, days_back))).strftime("%Y%m%d")
        end_ymd = now_utc.strftime("%Y%m%d")
        rows = await self.get_order_history(
            start_ymd=start_ymd,
            end_ymd=end_ymd,
            symbol=target_key or "%",
            side_code="00",
            ccld_nccs_code="00",
        )
        for row in rows:
            if not isinstance(row, dict):
                continue
            odno = str(row.get("odno") or "").strip()
            pdno = str(row.get("pdno") or "").strip().upper()
            if odno == target_order and pdno == target_symbol:
                return row
        return None

    def _parse_execution_row(self, row: dict) -> dict:
        filled_qty = _to_int_or_zero(row.get("ft_ccld_qty") or row.get("ccld_qty"))
        unfilled_qty = _to_int_or_zero(row.get("nccs_qty"))
        fill_price = _to_float_or_zero(
            row.get("ft_ccld_unpr3")
            or row.get("ft_ccld_unpr")
            or row.get("ft_ccld_unpr2")
        )
        fill_amount = _to_float_or_zero(
            row.get("ft_ccld_amt3")
            or row.get("ft_ccld_amt")
            or row.get("tot_ccld_amt")
        )
        if fill_amount <= 0 and fill_price > 0 and filled_qty > 0:
            fill_amount = fill_price * filled_qty
        status_name = str(row.get("prcs_stat_name") or "").strip()
        return {
            "filled_qty": filled_qty,
            "unfilled_qty": unfilled_qty,
            "fill_price": round(fill_price, 6),
            "fill_amount": round(fill_amount, 2),
            "status_name": status_name,
        }

    async def wait_for_order_outcome(
        self,
        order_id: str,
        symbol: str,
        side: str,
        expected_qty: int,
        pre_qty: Optional[int] = None,
        poll_count: int = 6,
        poll_delay_seconds: float = 2.0,
        ) -> dict:
        """
        Poll order history and unfilled queues to determine fill outcome safely.
        """
        side_upper = str(side or "").strip().upper()
        symbol_key = self._symbol_key(symbol)

        for idx in range(max(1, poll_count)):
            row = await self.find_order_history_row(order_id=order_id, symbol=symbol_key)
            if row:
                parsed = self._parse_execution_row(row)
                if parsed["filled_qty"] > 0 and parsed["unfilled_qty"] == 0:
                    return {"state": "filled", "raw": row, **parsed}
                if parsed["unfilled_qty"] > 0:
                    return {"state": "open", "raw": row, **parsed}
                if parsed["status_name"] in ("완료", "거부", "접수거부"):
                    return {"state": "closed_unfilled", "raw": row, **parsed}

            unfilled = await self.find_unfilled_order(order_id=order_id, symbol=symbol_key)
            if unfilled:
                parsed = self._parse_execution_row(unfilled)
                return {"state": "open", "raw": unfilled, **parsed}

            if idx < poll_count - 1:
                await asyncio.sleep(max(0.2, poll_delay_seconds))

        # Fallback: infer from post-order balance delta when history query is delayed.
        inferred = await self._infer_fill_from_balance_delta(
            symbol=symbol_key,
            side=side_upper,
            expected_qty=expected_qty,
            pre_qty=pre_qty,
        )
        if inferred.get("filled_qty", 0) > 0:
            return inferred

        return {
            "state": "unknown",
            "filled_qty": 0,
            "unfilled_qty": expected_qty,
            "fill_price": 0.0,
            "fill_amount": 0.0,
            "status_name": "",
            "raw": None,
        }

    async def _infer_fill_from_balance_delta(
        self,
        symbol: str,
        side: str,
        expected_qty: int,
        pre_qty: Optional[int] = None,
        poll_count: int = 4,
        poll_delay_seconds: float = 1.5,
    ) -> dict:
        """Infer fill result from balance change when KIS order APIs respond ambiguously."""
        symbol_key = self._symbol_key(symbol)
        side_upper = str(side or "").strip().upper()

        try:
            if pre_qty is None:
                pre_qty = 0

            for idx in range(max(1, poll_count)):
                balance = await self.get_symbol_balance(symbol_key)
                now_qty = int(balance.get("qty", 0))
                avg_price = float(balance.get("avg_price", 0.0) or 0.0)

                if side_upper == "BUY":
                    delta = max(0, now_qty - pre_qty)
                else:
                    delta = max(0, pre_qty - now_qty)

                if delta > 0:
                    qty = min(expected_qty, delta)
                    amount = round(avg_price * qty, 2) if avg_price > 0 else 0.0
                    return {
                        "state": "filled_via_balance",
                        "filled_qty": qty,
                        "unfilled_qty": max(0, expected_qty - qty),
                        "fill_price": round(avg_price, 6),
                        "fill_amount": amount,
                        "status_name": "BALANCE_CONFIRMED",
                        "raw": balance.get("raw"),
                    }

                if idx < poll_count - 1:
                    await asyncio.sleep(max(0.2, poll_delay_seconds))
        except Exception:
            pass

        return {
            "state": "unknown",
            "filled_qty": 0,
            "unfilled_qty": expected_qty,
            "fill_price": 0.0,
            "fill_amount": 0.0,
            "status_name": "",
            "raw": None,
        }

    async def cancel_order(self, symbol: str, order_id: str, qty: int) -> dict:
        """
        Cancel overseas order by original order number.
        """
        if qty <= 0:
            raise RuntimeError("취소 수량은 1주 이상이어야 합니다")
        symbol_key = self._symbol_key(symbol)
        symbol_code = self._symbol_code(symbol_key)
        order_exchange = self._order_exchange_candidates(symbol_key)[0]
        headers = await self._authorized_headers("TTTT1004U")
        body = {
            "CANO": settings.kis_account_no,
            "ACNT_PRDT_CD": settings.kis_account_product_code,
            "OVRS_EXCG_CD": order_exchange,
            "PDNO": symbol_code,
            "ORGN_ODNO": str(order_id),
            "RVSE_CNCL_DVSN_CD": "02",  # cancel
            "ORD_QTY": str(int(qty)),
            "OVRS_ORD_UNPR": "0",
            "MGCO_APTM_ODNO": "",
            "ORD_SVR_DVSN_CD": "0",
        }
        data = await self._request_json(
            "POST",
            "/uapi/overseas-stock/v1/trading/order-rvsecncl",
            headers=headers,
            json=body,
        )
        if str(data.get("rt_cd", "1")) != "0":
            msg = data.get("msg1") or data.get("msg_cd") or "unknown"
            raise RuntimeError(f"KIS 주문 취소 실패: {msg}")
        return {"success": True, "raw": data}

    async def get_integrated_margin_usd_orderable(self) -> dict:
        """
        Query integrated-margin dashboard and return USD orderable amount.
        This reflects 통합증거금(원화 기반 해외 주문가능) when enabled.
        """
        headers = await self._authorized_headers("TTTC0869R")
        params = {
            "CANO": settings.kis_account_no,
            "ACNT_PRDT_CD": settings.kis_account_product_code,
            "CMA_EVLU_AMT_ICLD_YN": "N",
            # 02: KRW basis for both fields (matches HTS integrated-margin screen)
            "WCRC_FRCR_DVSN_CD": "02",
            "FWEX_CTRT_FRCR_DVSN_CD": "02",
        }
        data = await self._get(
            "/uapi/domestic-stock/v1/trading/intgr-margin",
            headers=headers,
            params=params,
        )

        if str(data.get("rt_cd", "1")) != "0":
            msg = data.get("msg1") or data.get("msg_cd") or "unknown"
            raise RuntimeError(f"KIS 통합증거금 조회 실패: {msg}")

        output = data.get("output") or {}
        if not isinstance(output, dict):
            output = {}

        usd_itgr_ord_psbl_amt_krw = _to_float_or_zero(output.get("usd_itgr_ord_psbl_amt"))
        usd_exrt = _to_float_or_zero(output.get("usd_frst_bltn_exrt"))
        usd_itgr_ord_psbl_amt_usd = (
            usd_itgr_ord_psbl_amt_krw / usd_exrt if usd_exrt > 0 else 0.0
        )
        stock_cash_objt_krw = _to_float_or_zero(output.get("stck_cash_objt_amt"))
        stock_eval_objt_krw = _to_float_or_zero(output.get("stck_evlu_objt_amt"))
        stock_cash_use_krw = _to_float_or_zero(output.get("stck_cash_use_amt"))
        stock_eval_use_krw = _to_float_or_zero(output.get("stck_evlu_use_amt"))
        total_asset_objt_krw = stock_cash_objt_krw + stock_eval_objt_krw
        total_asset_use_krw = stock_cash_use_krw + stock_eval_use_krw

        return {
            "mode_name": str(output.get("ovrs_stck_itgr_mgna_dvsn_name") or "").strip(),
            "usd_itgr_orderable_krw": round(usd_itgr_ord_psbl_amt_krw, 2),
            "usd_exrt": round(usd_exrt, 8),
            "usd_itgr_orderable_usd": round(usd_itgr_ord_psbl_amt_usd, 2),
            "stock_cash_objt_krw": round(stock_cash_objt_krw, 2),
            "stock_eval_objt_krw": round(stock_eval_objt_krw, 2),
            "stock_cash_use_krw": round(stock_cash_use_krw, 2),
            "stock_eval_use_krw": round(stock_eval_use_krw, 2),
            "total_asset_objt_krw": round(total_asset_objt_krw, 2),
            "total_asset_use_krw": round(total_asset_use_krw, 2),
        }

    async def get_integrated_margin_currency_orderable(self, currency: str = "USD") -> dict:
        """
        Query integrated margin for a target overseas currency.
        KIS returns these orderable fields in KRW basis when WCRC_FRCR_DVSN_CD=02.
        """
        currency_upper = str(currency or "USD").strip().upper()
        field_name, exchange_rate_field = _INTEGRATED_MARGIN_FIELDS.get(
            currency_upper,
            _INTEGRATED_MARGIN_FIELDS["USD"],
        )
        headers = await self._authorized_headers("TTTC0869R")
        params = {
            "CANO": settings.kis_account_no,
            "ACNT_PRDT_CD": settings.kis_account_product_code,
            "CMA_EVLU_AMT_ICLD_YN": "N",
            "WCRC_FRCR_DVSN_CD": "02",
            "FWEX_CTRT_FRCR_DVSN_CD": "02",
        }
        data = await self._get(
            "/uapi/domestic-stock/v1/trading/intgr-margin",
            headers=headers,
            params=params,
        )
        if str(data.get("rt_cd", "1")) != "0":
            msg = data.get("msg1") or data.get("msg_cd") or "unknown"
            raise RuntimeError(f"KIS 통합증거금 조회 실패: {msg}")

        output = data.get("output") or {}
        if not isinstance(output, dict):
            output = {}

        orderable_krw = _to_float_or_zero(output.get(field_name))
        exchange_rate_krw = _to_float_or_zero(output.get(exchange_rate_field))
        orderable_local = orderable_krw / exchange_rate_krw if exchange_rate_krw > 0 else 0.0

        return {
            "currency": currency_upper,
            "mode_name": str(output.get("ovrs_stck_itgr_mgna_dvsn_name") or "").strip(),
            "integrated_krw": round(orderable_krw, 2),
            "exchange_rate_krw": round(exchange_rate_krw, 8),
            "integrated_local": round(orderable_local, 8),
            "raw": output,
        }

    async def get_effective_overseas_orderable(self, symbol: str = "AAPL", order_price: float = 1.0) -> dict:
        """
        Return effective buying power for the symbol's KIS overseas market.
        Amounts are reported in the market currency plus KRW conversion.
        """
        symbol_key = self._symbol_key(symbol)
        symbol_code = self._symbol_code(symbol_key)
        order_code = self._order_exchange_candidates(symbol_key)[0]
        currency = self._currency_for_order_exchange(order_code)
        headers = await self._authorized_headers("TTTS3007R")
        order_price_text = _format_overseas_order_price(order_price, currency)
        direct_ovrs = 0.0
        direct_frcr = 0.0
        psamount_errors = []
        success_calls = 0

        for candidate_order_code in self._order_exchange_candidates(symbol_key):
            params = {
                "CANO": settings.kis_account_no,
                "ACNT_PRDT_CD": settings.kis_account_product_code,
                "OVRS_EXCG_CD": candidate_order_code,
                "OVRS_ORD_UNPR": order_price_text,
                "ITEM_CD": symbol_code,
            }
            try:
                data = await self._get(
                    "/uapi/overseas-stock/v1/trading/inquire-psamount",
                    headers=headers,
                    params=params,
                )
            except Exception as e:
                psamount_errors.append(f"{candidate_order_code}:{str(e)}")
                continue

            if str(data.get("rt_cd", "1")) != "0":
                msg = data.get("msg1") or data.get("msg_cd") or "unknown"
                psamount_errors.append(f"{candidate_order_code}:{msg}")
                continue

            success_calls += 1
            output = data.get("output") or {}
            if not isinstance(output, dict):
                output = {}
            direct_ovrs = max(direct_ovrs, _to_float_or_zero(output.get("ovrs_ord_psbl_amt")))
            direct_frcr = max(direct_frcr, _to_float_or_zero(output.get("ord_psbl_frcr_amt")))

        if success_calls == 0 and psamount_errors:
            raise RuntimeError(f"KIS 매수가능금액 조회 실패: {' / '.join(psamount_errors[:3])}")

        try:
            integrated = await self.get_integrated_margin_currency_orderable(currency)
        except Exception as e:
            logger.warning(
                "KIS integrated margin lookup failed, falling back to direct buying power",
                symbol=symbol_key,
                currency=currency,
                error=str(e),
            )
            integrated = {
                "currency": currency,
                "mode_name": "",
                "integrated_krw": 0.0,
                "exchange_rate_krw": 0.0,
                "integrated_local": 0.0,
            }

        exchange_rate_krw = float(integrated.get("exchange_rate_krw", 0.0) or 0.0)
        integrated_local = float(integrated.get("integrated_local", 0.0) or 0.0)
        effective_local = max(direct_ovrs, direct_frcr, integrated_local)
        effective_krw = effective_local * exchange_rate_krw if exchange_rate_krw > 0 else 0.0

        return {
            "symbol": symbol_key,
            "symbol_code": symbol_code,
            "order_exchange": order_code,
            "currency": currency,
            "effective_local": round(effective_local, 8),
            "effective_krw": round(effective_krw, 2),
            "direct_ovrs_local": round(direct_ovrs, 8),
            "direct_frcr_local": round(direct_frcr, 8),
            "integrated_local": round(integrated_local, 8),
            "integrated_krw": integrated.get("integrated_krw", 0.0),
            "integrated_mode": integrated.get("mode_name", ""),
            "exchange_rate_krw": round(exchange_rate_krw, 8),
            "usd_exrt": round(exchange_rate_krw, 8) if currency == "USD" else 0.0,
            "effective_usd": round(effective_local, 2) if currency == "USD" else 0.0,
            "direct_ovrs_usd": round(direct_ovrs, 2) if currency == "USD" else 0.0,
            "direct_frcr_usd": round(direct_frcr, 2) if currency == "USD" else 0.0,
            "integrated_usd": round(integrated_local, 2) if currency == "USD" else 0.0,
        }

    async def get_effective_usd_orderable(self, symbol: str = "AAPL", order_price: float = 1.0) -> dict:
        """
        Return effective USD buying power for overseas orders.
        Combines direct 해외주문가능금액 and 통합증거금 USD 가능금액.
        """
        headers = await self._authorized_headers("TTTS3007R")
        symbol_upper = str(symbol or "").strip().upper()
        order_price_text = _format_us_order_price(order_price)
        direct_ovrs_usd = 0.0
        direct_frcr_usd = 0.0
        psamount_errors = []
        success_calls = 0

        for order_code in self._order_exchange_candidates(symbol_upper):
            params = {
                "CANO": settings.kis_account_no,
                "ACNT_PRDT_CD": settings.kis_account_product_code,
                "OVRS_EXCG_CD": order_code,
                "OVRS_ORD_UNPR": order_price_text,
                "ITEM_CD": symbol_upper,
            }
            try:
                data = await self._get(
                    "/uapi/overseas-stock/v1/trading/inquire-psamount",
                    headers=headers,
                    params=params,
                )
            except Exception as e:
                psamount_errors.append(f"{order_code}:{str(e)}")
                continue

            if str(data.get("rt_cd", "1")) != "0":
                msg = data.get("msg1") or data.get("msg_cd") or "unknown"
                psamount_errors.append(f"{order_code}:{msg}")
                continue

            success_calls += 1
            output = data.get("output") or {}
            if not isinstance(output, dict):
                output = {}

            direct_ovrs_usd = max(direct_ovrs_usd, _to_float_or_zero(output.get("ovrs_ord_psbl_amt")))
            direct_frcr_usd = max(direct_frcr_usd, _to_float_or_zero(output.get("ord_psbl_frcr_amt")))

        if success_calls == 0 and psamount_errors:
            raise RuntimeError(f"KIS 매수가능금액 조회 실패: {' / '.join(psamount_errors[:3])}")

        try:
            integrated = await self.get_integrated_margin_usd_orderable()
            integrated_usd = float(integrated.get("usd_itgr_orderable_usd", 0.0))
        except Exception as e:
            logger.warning(
                "KIS integrated margin lookup failed, falling back to direct buying power",
                symbol=symbol_upper,
                error=str(e),
            )
            integrated = {
                "mode_name": "",
                "usd_itgr_orderable_krw": 0.0,
                "usd_exrt": 0.0,
                "usd_itgr_orderable_usd": 0.0,
                "stock_cash_objt_krw": 0.0,
                "stock_eval_objt_krw": 0.0,
                "stock_cash_use_krw": 0.0,
                "stock_eval_use_krw": 0.0,
                "total_asset_objt_krw": 0.0,
                "total_asset_use_krw": 0.0,
            }
            integrated_usd = 0.0

        effective_usd = max(direct_ovrs_usd, direct_frcr_usd, integrated_usd)

        return {
            "effective_usd": round(effective_usd, 2),
            "direct_ovrs_usd": round(direct_ovrs_usd, 2),
            "direct_frcr_usd": round(direct_frcr_usd, 2),
            "integrated_usd": round(integrated_usd, 2),
            "integrated_mode": integrated.get("mode_name", ""),
            "usd_exrt": integrated.get("usd_exrt", 0.0),
            "integrated_krw": integrated.get("usd_itgr_orderable_krw", 0.0),
            "stock_cash_objt_krw": integrated.get("stock_cash_objt_krw", 0.0),
            "stock_eval_objt_krw": integrated.get("stock_eval_objt_krw", 0.0),
            "stock_cash_use_krw": integrated.get("stock_cash_use_krw", 0.0),
            "stock_eval_use_krw": integrated.get("stock_eval_use_krw", 0.0),
            "total_asset_objt_krw": integrated.get("total_asset_objt_krw", 0.0),
            "total_asset_use_krw": integrated.get("total_asset_use_krw", 0.0),
        }

    async def place_market_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        limit_price: Optional[float] = None,
    ) -> dict:
        """
        Place overseas order.
        side: BUY or SELL
        qty: integer shares

        Note:
        KIS US endpoint uses ORD_DVSN=00(limit) for regular sessions.
        We therefore send a quote-based limit price (>= $0.01).
        """
        if qty <= 0:
            raise RuntimeError("주문 수량은 1주 이상이어야 합니다")

        side_upper = side.upper().strip()
        if side_upper not in ("BUY", "SELL"):
            raise RuntimeError(f"잘못된 주문 방향: {side}")

        symbol_key = self._symbol_key(symbol)
        symbol_code = self._symbol_code(symbol_key)

        # Resolve quote exchange before choosing the order exchange. Many ETFs
        # are not NASDAQ-listed, and KIS requires the matching order venue.
        if limit_price is None:
            quote = await self.get_quote_snapshot(symbol_key)
            px = float(quote.get("price", 0.0) or 0.0)
        else:
            px = float(limit_price)
            if symbol_key not in self._symbol_exchange_cache:
                try:
                    await self.get_quote_snapshot(symbol_key)
                except Exception as exc:
                    logger.warning(
                        "KIS quote exchange resolution failed before order; using fallback exchange",
                        symbol=symbol_key,
                        error=str(exc),
                    )

        order_exchange = self._order_exchange_candidates(symbol_key)[0]
        currency = self._currency_for_order_exchange(order_exchange)
        tr_id = self._order_tr_id(order_exchange, side_upper)
        headers = await self._authorized_headers(tr_id)
        if px < 0.01:
            raise RuntimeError(f"주문 단가가 너무 낮습니다: {px:.8f} {currency}")
        price_text = _format_overseas_order_price(px, currency)

        body = {
            "CANO": settings.kis_account_no,
            "ACNT_PRDT_CD": settings.kis_account_product_code,
            "OVRS_EXCG_CD": order_exchange,
            "PDNO": symbol_code,
            "ORD_DVSN": "00",  # limit
            "ORD_QTY": str(qty),
            "OVRS_ORD_UNPR": price_text,
            "CTAC_TLNO": "",
            "MGCO_APTM_ODNO": "",
            "SLL_TYPE": "00" if side_upper == "SELL" else "",
            "ORD_SVR_DVSN_CD": "0",
        }

        data = await self._request_json(
            "POST",
            settings.kis_order_path,
            headers=headers,
            json=body,
        )

        if str(data.get("rt_cd", "1")) != "0":
            msg = data.get("msg1") or data.get("msg_cd") or "unknown"
            raise RuntimeError(f"KIS 주문 실패: {msg}")

        output = data.get("output") or {}
        order_no = ""
        if isinstance(output, dict):
            order_no = (
                str(output.get("ODNO") or output.get("ord_no") or output.get("KRX_FWDG_ORD_ORGNO") or "")
            )

        return {"order_id": order_no, "raw": data}

    async def place_buy_by_amount(self, symbol: str, amount_usd: float) -> dict:
        symbol_key = self._symbol_key(symbol)
        pre_balance = await self.get_symbol_balance(symbol_key)
        pre_qty = int(pre_balance.get("qty", 0))
        max_attempts = 1 + max(0, int(settings.kis_order_post_retry_count or 0))
        retry_delay = max(0.2, float(settings.kis_order_post_retry_delay_seconds or 2.0))
        last_error = ""

        for attempt in range(max_attempts):
            quote = await self.get_quote_snapshot(symbol_key)
            currency = str(
                quote.get("currency")
                or self._currency_for_order_exchange(self._order_exchange_candidates(symbol_key)[0])
            )
            price = float(quote.get("price", 0.0) or 0.0)
            if price <= 0:
                raise RuntimeError(f"KIS 시세 응답에서 유효 가격을 찾지 못했습니다 (종목:{symbol_key})")

            order_price = _buffered_buy_limit_price(price, currency)
            qty = max(1, int(float(amount_usd or 0.0) // max(order_price, 0.00000001)))

            try:
                order = await self.place_market_order(
                    symbol=symbol_key,
                    side="BUY",
                    qty=qty,
                    limit_price=order_price,
                )
            except Exception as exc:
                inferred = await self._infer_fill_from_balance_delta(
                    symbol=symbol_key,
                    side="BUY",
                    expected_qty=qty,
                    pre_qty=pre_qty,
                    poll_count=6,
                    poll_delay_seconds=2.0,
                )
                if inferred.get("filled_qty", 0) > 0:
                    return {
                        "success": True,
                        "ticker": symbol_key,
                        "qty": float(inferred["filled_qty"]),
                        "price": round(float(inferred.get("fill_price", order_price) or order_price), 6),
                        "amount": round(float(inferred.get("fill_amount", 0.0) or 0.0), 2),
                        "commission": 0.0,
                        "order_id": "",
                        "currency": currency,
                    }

                last_error = f"KIS 매수 요청 실패: {str(exc)}"
                if attempt < max_attempts - 1 and _is_retryable_order_submit_error(exc):
                    try:
                        has_open_order = await self.has_unfilled_symbol_order(symbol_key)
                    except Exception as check_exc:
                        logger.warning(
                            "KIS BUY retry suppressed because unfilled-order check failed",
                            ticker=symbol_key,
                            error=str(check_exc),
                        )
                        return {
                            "success": False,
                            "error": f"{last_error}. 미체결 확인 실패로 중복 방지를 위해 자동 재시도를 중단했습니다: {str(check_exc)}",
                        }
                    if has_open_order:
                        return {
                            "success": False,
                            "error": f"{last_error}. KIS 미체결 주문이 남아 있어 중복 방지를 위해 자동 재시도를 중단했습니다.",
                        }
                    logger.warning(
                        "KIS BUY submit transient failure; retrying after balance/open-order check",
                        ticker=symbol_key,
                        attempt=attempt + 1,
                        max_attempts=max_attempts,
                        error=str(exc),
                    )
                    await asyncio.sleep(retry_delay)
                    continue
                raise

            order_id = str(order.get("order_id", "")).strip()
            if not order_id:
                inferred = await self._infer_fill_from_balance_delta(
                    symbol=symbol_key,
                    side="BUY",
                    expected_qty=qty,
                    pre_qty=pre_qty,
                    poll_count=6,
                    poll_delay_seconds=2.0,
                )
                if inferred.get("filled_qty", 0) > 0:
                    return {
                        "success": True,
                        "ticker": symbol_key,
                        "qty": float(inferred["filled_qty"]),
                        "price": round(float(inferred.get("fill_price", order_price) or order_price), 6),
                        "amount": round(float(inferred.get("fill_amount", 0.0) or 0.0), 2),
                        "commission": 0.0,
                        "order_id": "",
                        "currency": currency,
                    }
                last_error = "KIS 주문번호를 받지 못했습니다"
                if attempt < max_attempts - 1:
                    if await self.has_unfilled_symbol_order(symbol_key):
                        return {
                            "success": False,
                            "error": f"{last_error}. KIS 미체결 주문이 남아 있어 중복 방지를 위해 자동 재시도를 중단했습니다.",
                        }
                    await asyncio.sleep(retry_delay)
                    continue
                return {"success": False, "error": last_error}

            outcome = await self.wait_for_order_outcome(
                order_id=order_id,
                symbol=symbol_key,
                side="BUY",
                expected_qty=qty,
                pre_qty=pre_qty,
            )
            filled_qty = int(outcome.get("filled_qty", 0))
            unfilled_qty = int(outcome.get("unfilled_qty", 0))
            fill_price = float(outcome.get("fill_price", 0.0) or 0.0)
            fill_amount = float(outcome.get("fill_amount", 0.0) or 0.0)

            if unfilled_qty > 0:
                try:
                    await self.cancel_order(symbol=symbol_key, order_id=order_id, qty=unfilled_qty)
                    unfilled_qty = 0
                except Exception as cancel_err:
                    err_text = str(cancel_err)
                    # KIS may return transient cancel errors right after accept/fill.
                    # Keep polling before deciding failure.
                    follow = await self.wait_for_order_outcome(
                        order_id=order_id,
                        symbol=symbol_key,
                        side="BUY",
                        expected_qty=qty,
                        pre_qty=pre_qty,
                        poll_count=8,
                        poll_delay_seconds=2.0,
                    )
                    filled_qty = int(follow.get("filled_qty", filled_qty))
                    unfilled_qty = int(follow.get("unfilled_qty", unfilled_qty))
                    fill_price = float(follow.get("fill_price", fill_price) or fill_price)
                    fill_amount = float(follow.get("fill_amount", fill_amount) or fill_amount)
                    if filled_qty >= qty:
                        unfilled_qty = 0
                    elif filled_qty <= 0 and follow.get("state") == "closed_unfilled":
                        unfilled_qty = 0
                    elif not (
                        ("거래소 미접수" in err_text)
                        or ("매매가능한 수량이 없습니다" in err_text)
                        or ("500 Internal Server Error" in err_text)
                        or ("Server disconnected without sending a response" in err_text)
                    ):
                        last_error = (
                            f"KIS 매수 주문 미체결({unfilled_qty}주)이며 취소도 실패했습니다: "
                            f"{err_text}"
                        )
                        return {"success": False, "error": last_error}

                if filled_qty >= qty:
                    unfilled_qty = 0

                if unfilled_qty > 0:
                    try:
                        await self.cancel_order(symbol=symbol_key, order_id=order_id, qty=unfilled_qty)
                        unfilled_qty = 0
                    except Exception as cancel_err_2:
                        follow2 = await self.wait_for_order_outcome(
                            order_id=order_id,
                            symbol=symbol_key,
                            side="BUY",
                            expected_qty=qty,
                            pre_qty=pre_qty,
                            poll_count=8,
                            poll_delay_seconds=2.0,
                        )
                        filled_qty = int(follow2.get("filled_qty", filled_qty))
                        unfilled_qty = int(follow2.get("unfilled_qty", unfilled_qty))
                        fill_price = float(follow2.get("fill_price", fill_price) or fill_price)
                        fill_amount = float(follow2.get("fill_amount", fill_amount) or fill_amount)
                        if filled_qty >= qty:
                            unfilled_qty = 0
                        if unfilled_qty > 0:
                            if filled_qty <= 0:
                                last_error = (
                                    f"KIS 매수 주문 미체결({unfilled_qty}주)이며 취소도 실패했습니다: "
                                    f"{str(cancel_err_2)}"
                                )
                                return {"success": False, "error": last_error}
                            return {
                                "success": False,
                                "error": (
                                    f"KIS 매수 주문이 부분체결되었습니다 "
                                    f"({filled_qty}/{qty}주). 잔량 취소 확인이 필요합니다."
                                ),
                            }

            if filled_qty <= 0:
                last_error = f"KIS 매수 주문이 미체결 또는 체결확인 실패로 취소되었습니다 ({qty}주)"
                if attempt < max_attempts - 1:
                    logger.warning(
                        "KIS BUY was not filled; retrying once with refreshed quote",
                        ticker=symbol_key,
                        order_id=order_id,
                        attempt=attempt + 1,
                        max_attempts=max_attempts,
                        limit_price=order_price,
                    )
                    await asyncio.sleep(retry_delay)
                    continue
                return {"success": False, "error": last_error}

            if fill_price <= 0:
                fill_price = order_price
            if fill_amount <= 0:
                fill_amount = round(filled_qty * fill_price, 2)

            return {
                "success": True,
                "ticker": symbol_key,
                "qty": float(filled_qty),
                "price": round(fill_price, 6),
                "amount": round(fill_amount, 2),
                "commission": 0.0,
                "order_id": order_id,
                "currency": currency,
            }

        return {"success": False, "error": last_error or "KIS 매수 재시도 후에도 체결되지 않았습니다"}

    async def place_sell_qty(
        self,
        symbol: str,
        qty: float,
        min_limit_price: Optional[float] = None,
    ) -> dict:
        qty_int = int(qty)
        if qty_int < 1:
            return {"success": False, "error": "KIS 매도 수량이 1주 미만입니다"}

        symbol_key = self._symbol_key(symbol)
        pre_balance = await self.get_symbol_balance(symbol_key)
        pre_qty = int(pre_balance.get("qty", 0))

        quote = await self.get_quote_snapshot(symbol_key)
        currency = str(quote.get("currency") or self._currency_for_order_exchange(self._order_exchange_candidates(symbol_key)[0]))
        price = float(quote.get("price", 0.0) or 0.0)
        order_price = _buffered_sell_limit_price(price, currency, min_limit_price=min_limit_price)
        order = await self.place_market_order(
            symbol=symbol_key,
            side="SELL",
            qty=qty_int,
            limit_price=order_price,
        )
        order_id = str(order.get("order_id", "")).strip()
        if not order_id:
            return {"success": False, "error": "KIS 주문번호를 받지 못했습니다"}

        outcome = await self.wait_for_order_outcome(
            order_id=order_id,
            symbol=symbol_key,
            side="SELL",
            expected_qty=qty_int,
            pre_qty=pre_qty,
        )
        filled_qty = int(outcome.get("filled_qty", 0))
        unfilled_qty = int(outcome.get("unfilled_qty", 0))
        fill_price = float(outcome.get("fill_price", 0.0) or 0.0)
        fill_amount = float(outcome.get("fill_amount", 0.0) or 0.0)

        async def _refresh_sell_confirmation(
            poll_count: int = 4,
            poll_delay_seconds: float = 1.0,
        ) -> None:
            nonlocal filled_qty, unfilled_qty, fill_price, fill_amount
            inferred = await self._infer_fill_from_balance_delta(
                symbol=symbol_key,
                side="SELL",
                expected_qty=qty_int,
                pre_qty=pre_qty,
                poll_count=poll_count,
                poll_delay_seconds=poll_delay_seconds,
            )
            inferred_filled = int(inferred.get("filled_qty", 0) or 0)
            if inferred_filled > filled_qty:
                filled_qty = inferred_filled
            if filled_qty >= qty_int:
                unfilled_qty = 0
            elif filled_qty > 0:
                unfilled_qty = max(0, qty_int - filled_qty)

            inferred_price = float(inferred.get("fill_price", 0.0) or 0.0)
            if fill_price <= 0 and inferred_price > 0:
                fill_price = inferred_price

            inferred_amount = float(inferred.get("fill_amount", 0.0) or 0.0)
            if fill_amount <= 0 and inferred_amount > 0:
                fill_amount = inferred_amount

        if filled_qty >= qty_int:
            unfilled_qty = 0

        if unfilled_qty > 0:
            cancel_error_text = ""
            try:
                await self.cancel_order(symbol=symbol_key, order_id=order_id, qty=unfilled_qty)
                unfilled_qty = 0
            except Exception as cancel_err:
                cancel_error_text = str(cancel_err)
                if "거래소 미접수" in cancel_error_text:
                    follow = await self.wait_for_order_outcome(
                        order_id=order_id,
                        symbol=symbol_key,
                        side="SELL",
                        expected_qty=qty_int,
                        pre_qty=pre_qty,
                        poll_count=8,
                        poll_delay_seconds=2.0,
                    )
                    filled_qty = int(follow.get("filled_qty", filled_qty))
                    unfilled_qty = int(follow.get("unfilled_qty", unfilled_qty))
                    fill_price = float(follow.get("fill_price", fill_price) or fill_price)
                    fill_amount = float(follow.get("fill_amount", fill_amount) or fill_amount)

            await _refresh_sell_confirmation()

            if unfilled_qty > 0:
                try:
                    await self.cancel_order(symbol=symbol_key, order_id=order_id, qty=unfilled_qty)
                    unfilled_qty = 0
                except Exception as cancel_err_2:
                    cancel_error_text = str(cancel_err_2)
                    await _refresh_sell_confirmation(poll_count=5, poll_delay_seconds=1.2)
                    if filled_qty <= 0:
                        return {
                            "success": False,
                            "error": (
                                f"KIS 매도 주문 미체결({unfilled_qty}주)이며 취소도 실패했습니다: "
                                f"{cancel_error_text}"
                            ),
                        }

            await _refresh_sell_confirmation()

            if filled_qty > 0:
                if fill_price <= 0:
                    fill_price = order_price
                if fill_amount <= 0:
                    fill_amount = round(filled_qty * fill_price, 2)
                remaining_qty = max(0, qty_int - filled_qty)
                if remaining_qty <= 0:
                    return {
                        "success": True,
                        "ticker": symbol_key,
                        "qty": float(filled_qty),
                        "price": round(fill_price, 6),
                        "amount": round(fill_amount, 2),
                        "commission": 0.0,
                        "order_id": order_id,
                        "currency": currency,
                    }
                return {
                    "success": True,
                    "partial_fill": True,
                    "ticker": symbol_key,
                    "qty": float(filled_qty),
                    "price": round(fill_price, 6),
                    "amount": round(fill_amount, 2),
                    "commission": 0.0,
                    "order_id": order_id,
                    "remaining_qty": remaining_qty,
                    "currency": currency,
                    "error": (
                        f"KIS 매도 주문이 부분체결되었습니다 "
                        f"({filled_qty}/{qty_int}주). "
                        + (
                            "잔량 취소 확인이 필요합니다."
                            if cancel_error_text
                            else "잔량은 취소되었습니다."
                        )
                    ),
                }

            return {
                "success": False,
                "error": f"KIS 매도 주문이 미체결되어 취소했습니다 ({qty_int}주)",
            }

        if filled_qty <= 0:
            await _refresh_sell_confirmation(poll_count=4, poll_delay_seconds=1.0)
        if filled_qty <= 0:
            return {"success": False, "error": "KIS 매도 체결 확인 실패"}

        if fill_price <= 0:
            fill_price = order_price
        if fill_amount <= 0:
            fill_amount = round(filled_qty * fill_price, 2)

        return {
            "success": True,
            "ticker": symbol_key,
            "qty": float(filled_qty),
            "price": round(fill_price, 6),
            "amount": round(fill_amount, 2),
            "commission": 0.0,
            "order_id": order_id,
            "currency": currency,
        }

    async def get_domestic_orderable_cash(self, symbol: str, order_price: float, ord_dvsn: str = "01") -> dict:
        """
        Query KIS domestic buyable cash/quantity.

        For no-margin buying, use nrcvb_buy_amt/nrcvb_buy_qty as the safe fields.
        """
        symbol_code = _normalize_domestic_symbol(symbol)
        headers = await self._authorized_headers("TTTC8908R")
        params = {
            "CANO": settings.kis_account_no,
            "ACNT_PRDT_CD": settings.kis_account_product_code,
            "PDNO": symbol_code,
            "ORD_UNPR": _format_krw_order_price(order_price),
            "ORD_DVSN": str(ord_dvsn or "01"),
            "CMA_EVLU_AMT_ICLD_YN": "N",
            "OVRS_ICLD_YN": "N",
        }
        data = await self._get(
            "/uapi/domestic-stock/v1/trading/inquire-psbl-order",
            headers=headers,
            params=params,
        )
        if str(data.get("rt_cd", "1")) != "0":
            msg = data.get("msg1") or data.get("msg_cd") or "unknown"
            raise RuntimeError(f"KIS 국내 매수가능조회 실패: {msg}")

        output = data.get("output") or {}
        if not isinstance(output, dict):
            output = {}

        return {
            "ord_psbl_cash": round(_to_float_or_zero(output.get("ord_psbl_cash")), 2),
            "nrcvb_buy_amt": round(_to_float_or_zero(output.get("nrcvb_buy_amt")), 2),
            "max_buy_amt": round(_to_float_or_zero(output.get("max_buy_amt")), 2),
            "nrcvb_buy_qty": _to_int_or_zero(output.get("nrcvb_buy_qty")),
            "max_buy_qty": _to_int_or_zero(output.get("max_buy_qty")),
            "raw": output,
        }

    async def get_domestic_balance(self) -> list[dict]:
        """
        Query KIS domestic balance rows.
        """
        base_headers = await self._authorized_headers("TTTC8434R")
        rows_out: list[dict] = []
        fk100 = ""
        nk100 = ""
        tr_cont = ""

        for _ in range(10):
            headers = dict(base_headers)
            if tr_cont:
                headers["tr_cont"] = "N"
            params = {
                "CANO": settings.kis_account_no,
                "ACNT_PRDT_CD": settings.kis_account_product_code,
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "",
                "INQR_DVSN": "01",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "00",
                "CTX_AREA_FK100": fk100,
                "CTX_AREA_NK100": nk100,
            }
            data, response_headers = await self._get(
                "/uapi/domestic-stock/v1/trading/inquire-balance",
                headers=headers,
                params=params,
                include_response_headers=True,
            )
            if str(data.get("rt_cd", "1")) != "0":
                msg = data.get("msg1") or data.get("msg_cd") or "unknown"
                raise RuntimeError(f"KIS 국내 잔고 조회 실패: {msg}")

            rows = data.get("output1") or []
            if isinstance(rows, dict):
                rows = [rows]
            rows_out.extend(row for row in rows if isinstance(row, dict))

            tr_cont = str(response_headers.get("tr_cont") or response_headers.get("Tr-Cont") or "").strip().upper()
            fk100 = str(data.get("ctx_area_fk100") or "").strip()
            nk100 = str(data.get("ctx_area_nk100") or "").strip()
            if tr_cont not in ("M", "F") or not (fk100 or nk100):
                break

        return rows_out

    async def get_domestic_symbol_balance(self, symbol: str) -> dict:
        """Return simplified KRX/domestic per-symbol balance snapshot."""
        symbol_code = _normalize_domestic_symbol(symbol)
        rows = await self.get_domestic_balance()
        for row in rows:
            pdno = str(row.get("pdno") or row.get("PDNO") or "").strip()
            if pdno != symbol_code:
                continue
            return {
                "symbol": symbol_code,
                "qty": _to_int_or_zero(row.get("hldg_qty")),
                "orderable_qty": _to_int_or_zero(row.get("ord_psbl_qty")),
                "avg_price": round(_to_float_or_zero(row.get("pchs_avg_pric")), 6),
                "price": round(_to_float_or_zero(row.get("prpr")), 6),
                "purchase_amount": round(_to_float_or_zero(row.get("pchs_amt")), 2),
                "eval_amount": round(_to_float_or_zero(row.get("evlu_amt")), 2),
                "eval_pnl": round(_to_float_signed_or_zero(row.get("evlu_pfls_amt")), 2),
                "eval_pnl_pct": round(_to_float_signed_or_zero(row.get("evlu_pfls_rt")), 4),
                "raw": row,
            }
        return {
            "symbol": symbol_code,
            "qty": 0,
            "orderable_qty": 0,
            "avg_price": 0.0,
            "price": 0.0,
            "purchase_amount": 0.0,
            "eval_amount": 0.0,
            "eval_pnl": 0.0,
            "eval_pnl_pct": 0.0,
            "raw": None,
        }

    async def place_domestic_cash_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        *,
        ord_dvsn: str = "01",
        order_price: float = 0.0,
    ) -> dict:
        """
        Place KIS domestic/KRX cash order.
        side: BUY or SELL
        """
        if qty <= 0:
            raise RuntimeError("국내 주문 수량은 1주 이상이어야 합니다")

        symbol_code = _normalize_domestic_symbol(symbol)
        side_upper = str(side or "").strip().upper()
        if side_upper not in ("BUY", "SELL"):
            raise RuntimeError(f"잘못된 국내 주문 방향: {side}")

        order_type = str(ord_dvsn or "01").strip()
        order_price_text = "0" if order_type == "01" else _format_krw_order_price(order_price)
        if order_type != "01" and int(order_price_text) <= 0:
            raise RuntimeError(f"국내 지정가 주문 단가가 올바르지 않습니다: {order_price}")

        tr_id = "TTTC0012U" if side_upper == "BUY" else "TTTC0011U"
        headers = await self._authorized_headers(tr_id)
        body = {
            "CANO": settings.kis_account_no,
            "ACNT_PRDT_CD": settings.kis_account_product_code,
            "PDNO": symbol_code,
            "ORD_DVSN": order_type,
            "ORD_QTY": str(int(qty)),
            "ORD_UNPR": order_price_text,
            "EXCG_ID_DVSN_CD": str(settings.kis_domestic_exchange_code or "KRX").strip().upper(),
            "SLL_TYPE": "01" if side_upper == "SELL" else "",
            "CNDT_PRIC": "",
        }
        data = await self._request_json(
            "POST",
            settings.kis_domestic_order_path,
            headers=headers,
            json=body,
        )
        if str(data.get("rt_cd", "1")) != "0":
            msg = data.get("msg1") or data.get("msg_cd") or "unknown"
            raise RuntimeError(f"KIS 국내 주문 실패: {msg}")

        output = data.get("output") or {}
        order_no = ""
        if isinstance(output, dict):
            order_no = str(output.get("ODNO") or output.get("odno") or output.get("ord_no") or "").strip()
        return {"order_id": order_no, "raw": data}

    async def place_domestic_market_order(self, symbol: str, side: str, qty: int) -> dict:
        """Place KIS domestic/KRX market cash order."""
        return await self.place_domestic_cash_order(symbol=symbol, side=side, qty=qty)

    async def place_domestic_ioc_limit_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        limit_price: float,
    ) -> dict:
        """Place a KRX IOC limit order so unfilled remainder is not left open."""
        return await self.place_domestic_cash_order(
            symbol=symbol,
            side=side,
            qty=qty,
            ord_dvsn="11",
            order_price=limit_price,
        )

    async def get_domestic_order_history(
        self,
        *,
        start_ymd: str,
        end_ymd: str,
        symbol: str = "",
        order_id: str = "",
        side_code: str = "00",
        filled_code: str = "00",
    ) -> list[dict]:
        """
        Query KIS domestic daily order/execution history.
        """
        base_headers = await self._authorized_headers("TTTC0081R")
        rows_out: list[dict] = []
        fk100 = ""
        nk100 = ""
        tr_cont = ""

        for _ in range(10):
            headers = dict(base_headers)
            if tr_cont:
                headers["tr_cont"] = "N"
            params = {
                "CANO": settings.kis_account_no,
                "ACNT_PRDT_CD": settings.kis_account_product_code,
                "INQR_STRT_DT": start_ymd,
                "INQR_END_DT": end_ymd,
                "SLL_BUY_DVSN_CD": side_code,
                "PDNO": _normalize_domestic_symbol(symbol) if symbol else "",
                "CCLD_DVSN": filled_code,
                "INQR_DVSN": "00",
                "INQR_DVSN_3": "00",
                "ORD_GNO_BRNO": "",
                "ODNO": str(order_id or "").strip(),
                "INQR_DVSN_1": "",
                "CTX_AREA_FK100": fk100,
                "CTX_AREA_NK100": nk100,
                "EXCG_ID_DVSN_CD": str(settings.kis_domestic_exchange_code or "KRX").strip().upper(),
            }
            data, response_headers = await self._get(
                "/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
                headers=headers,
                params=params,
                include_response_headers=True,
            )
            if str(data.get("rt_cd", "1")) != "0":
                msg = data.get("msg1") or data.get("msg_cd") or "unknown"
                raise RuntimeError(f"KIS 국내 체결내역 조회 실패: {msg}")

            rows = data.get("output1") or []
            if isinstance(rows, dict):
                rows = [rows]
            rows_out.extend(row for row in rows if isinstance(row, dict))

            tr_cont = str(response_headers.get("tr_cont") or response_headers.get("Tr-Cont") or "").strip().upper()
            fk100 = str(data.get("ctx_area_fk100") or "").strip()
            nk100 = str(data.get("ctx_area_nk100") or "").strip()
            if tr_cont not in ("M", "F") or not (fk100 or nk100):
                break

        return rows_out

    async def wait_for_domestic_order_outcome(
        self,
        order_id: str,
        symbol: str,
        side: str,
        expected_qty: int,
        pre_qty: Optional[int] = None,
        poll_count: int = 6,
        poll_delay_seconds: float = 1.5,
    ) -> dict:
        """
        Poll domestic order history and balance delta to confirm KRX order fill.
        """
        symbol_code = _normalize_domestic_symbol(symbol)
        side_upper = str(side or "").strip().upper()
        now_kst = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=9)))
        ymd = now_kst.strftime("%Y%m%d")

        for idx in range(max(1, poll_count)):
            try:
                rows = await self.get_domestic_order_history(
                    start_ymd=ymd,
                    end_ymd=ymd,
                    symbol=symbol_code,
                    order_id=order_id,
                    side_code="02" if side_upper == "BUY" else "01",
                    filled_code="00",
                )
                for row in rows:
                    if str(row.get("odno") or "").strip() != str(order_id or "").strip():
                        continue
                    filled_qty = _to_int_or_zero(row.get("tot_ccld_qty"))
                    total_qty = _to_int_or_zero(row.get("tot_ord_qty") or row.get("ord_qty") or expected_qty)
                    remaining_qty = _to_int_or_zero(row.get("rmn_qty"))
                    fill_price = _to_float_or_zero(row.get("avg_prvs") or row.get("pchs_avg_pric"))
                    fill_amount = _to_float_or_zero(row.get("tot_ccld_amt") or row.get("prsm_tlex_smtl"))
                    if fill_amount <= 0 and fill_price > 0 and filled_qty > 0:
                        fill_amount = fill_price * filled_qty
                    if filled_qty > 0:
                        return {
                            "state": "filled" if remaining_qty == 0 else "partial",
                            "filled_qty": filled_qty,
                            "unfilled_qty": max(0, total_qty - filled_qty, remaining_qty),
                            "fill_price": round(fill_price, 6),
                            "fill_amount": round(fill_amount, 2),
                            "raw": row,
                        }
            except Exception as e:
                logger.debug("KIS domestic history polling failed", symbol=symbol_code, error=str(e))

            try:
                if pre_qty is not None:
                    balance = await self.get_domestic_symbol_balance(symbol_code)
                    now_qty = int(balance.get("qty", 0) or 0)
                    avg_price = float(balance.get("avg_price", 0.0) or 0.0)
                    if side_upper == "BUY":
                        delta = max(0, now_qty - pre_qty)
                    else:
                        delta = max(0, pre_qty - now_qty)
                    if delta > 0:
                        qty = min(int(expected_qty), int(delta))
                        price = avg_price if avg_price > 0 else float(balance.get("price", 0.0) or 0.0)
                        return {
                            "state": "filled_via_balance",
                            "filled_qty": qty,
                            "unfilled_qty": max(0, int(expected_qty) - qty),
                            "fill_price": round(price, 6),
                            "fill_amount": round(price * qty, 2) if price > 0 else 0.0,
                            "raw": balance.get("raw"),
                        }
            except Exception:
                pass

            if idx < poll_count - 1:
                await asyncio.sleep(max(0.2, poll_delay_seconds))

        return {
            "state": "unknown",
            "filled_qty": 0,
            "unfilled_qty": expected_qty,
            "fill_price": 0.0,
            "fill_amount": 0.0,
            "raw": None,
        }

    async def place_domestic_buy_by_amount(self, symbol: str, amount_krw: float) -> dict:
        """Buy a domestic/KRX symbol using an approximate KRW target amount."""
        symbol_code = _normalize_domestic_symbol(symbol)
        price = await self.get_domestic_quote_price(symbol_code)
        qty = max(1, int(float(amount_krw or 0.0) // float(price)))

        pre_balance = await self.get_domestic_symbol_balance(symbol_code)
        pre_qty = int(pre_balance.get("qty", 0) or 0)

        order = await self.place_domestic_market_order(symbol=symbol_code, side="BUY", qty=qty)
        order_id = str(order.get("order_id", "")).strip()
        if not order_id:
            return {"success": False, "error": "KIS 국내 주문번호를 받지 못했습니다"}

        outcome = await self.wait_for_domestic_order_outcome(
            order_id=order_id,
            symbol=symbol_code,
            side="BUY",
            expected_qty=qty,
            pre_qty=pre_qty,
        )
        filled_qty = int(outcome.get("filled_qty", 0) or 0)
        fill_price = float(outcome.get("fill_price", 0.0) or 0.0)
        fill_amount = float(outcome.get("fill_amount", 0.0) or 0.0)
        if filled_qty <= 0:
            return {"success": False, "error": f"KIS 국내 매수 체결을 확인하지 못했습니다 ({qty}주)"}
        if fill_price <= 0:
            fill_price = price
        if fill_amount <= 0:
            fill_amount = round(fill_price * filled_qty, 2)

        return {
            "success": True,
            "ticker": symbol_code,
            "qty": float(filled_qty),
            "price": round(fill_price, 6),
            "amount": round(fill_amount, 2),
            "commission": 0.0,
            "order_id": order_id,
            "currency": "KRW",
        }

    async def place_domestic_sell_qty(
        self,
        symbol: str,
        qty: float,
        min_limit_price: Optional[float] = None,
    ) -> dict:
        """Sell a domestic/KRX symbol by quantity, optionally with profit protection."""
        symbol_code = _normalize_domestic_symbol(symbol)
        qty_int = int(qty)
        if qty_int < 1:
            return {"success": False, "error": "KIS 국내 매도 수량이 1주 미만입니다"}

        pre_balance = await self.get_domestic_symbol_balance(symbol_code)
        pre_qty = int(pre_balance.get("qty", 0) or 0)
        orderable_qty = int(pre_balance.get("orderable_qty", 0) or 0)
        if orderable_qty > 0:
            qty_int = min(qty_int, orderable_qty)
        if qty_int < 1:
            return {"success": False, "error": f"{symbol_code} 국내 매도 가능 수량이 없습니다"}

        protected_limit_price = float(min_limit_price or 0.0)
        if protected_limit_price > 0:
            order = await self.place_domestic_ioc_limit_order(
                symbol=symbol_code,
                side="SELL",
                qty=qty_int,
                limit_price=protected_limit_price,
            )
        else:
            order = await self.place_domestic_market_order(symbol=symbol_code, side="SELL", qty=qty_int)
        order_id = str(order.get("order_id", "")).strip()
        if not order_id:
            return {"success": False, "error": "KIS 국내 주문번호를 받지 못했습니다"}

        outcome = await self.wait_for_domestic_order_outcome(
            order_id=order_id,
            symbol=symbol_code,
            side="SELL",
            expected_qty=qty_int,
            pre_qty=pre_qty,
        )
        filled_qty = int(outcome.get("filled_qty", 0) or 0)
        fill_price = float(outcome.get("fill_price", 0.0) or 0.0)
        fill_amount = float(outcome.get("fill_amount", 0.0) or 0.0)
        if filled_qty <= 0:
            if protected_limit_price > 0:
                return {
                    "success": False,
                    "skipped": True,
                    "reason": "sell_profit_only_hold",
                    "error": (
                        f"{symbol_code} 수익 보호 지정가 "
                        f"{_format_krw_order_price(protected_limit_price)}원에 즉시 체결되지 않아 매도를 보류했습니다"
                    ),
                    "order_id": order_id,
                    "ticker": symbol_code,
                    "currency": "KRW",
                }
            return {"success": False, "error": f"KIS 국내 매도 체결을 확인하지 못했습니다 ({qty_int}주)"}
        if fill_price <= 0:
            fill_price = float(await self.get_domestic_quote_price(symbol_code))
        if fill_amount <= 0:
            fill_amount = round(fill_price * filled_qty, 2)

        return {
            "success": True,
            "ticker": symbol_code,
            "qty": float(filled_qty),
            "price": round(fill_price, 6),
            "amount": round(fill_amount, 2),
            "commission": 0.0,
            "order_id": order_id,
            "currency": "KRW",
        }

    async def close(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None


async def get_kis_client() -> KISClient:
    global _kis_instance
    async with _kis_lock:
        if _kis_instance is None:
            _kis_instance = KISClient()
        return _kis_instance
