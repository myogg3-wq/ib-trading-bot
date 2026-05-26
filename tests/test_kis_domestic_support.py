import unittest
import atexit
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from unittest.mock import AsyncMock

TEST_KIS_TOKEN_CACHE_PATH = Path(__file__).resolve().parent / ".tmp_kis_access_token.json"
os.environ["KIS_TOKEN_CACHE_PATH"] = str(TEST_KIS_TOKEN_CACHE_PATH)
atexit.register(lambda: TEST_KIS_TOKEN_CACHE_PATH.unlink(missing_ok=True))

from app.broker.kis_client import KISClient, _format_krw_order_price, _normalize_domestic_symbol
from app.gateway.symbol_mapper import (
    canonical_trade_symbol,
    is_kis_domestic_symbol,
    kis_overseas_currency,
)
from app.queue.order_queue import _pending_order_matches_market, is_pending_order_expired, pending_order_age_hours
from app.queue.order_worker import _format_money, _format_signed_money


class KISDomesticSymbolTests(unittest.TestCase):
    def test_detects_tradingview_krx_numeric_symbols(self):
        self.assertTrue(is_kis_domestic_symbol("KRX:069500"))
        self.assertTrue(is_kis_domestic_symbol("069500"))
        self.assertTrue(is_kis_domestic_symbol("1234567"))
        self.assertTrue(is_kis_domestic_symbol("KRX:0005G0"))
        self.assertTrue(is_kis_domestic_symbol("0005G0"))

    def test_rejects_us_symbols(self):
        self.assertFalse(is_kis_domestic_symbol("AAPL"))
        self.assertFalse(is_kis_domestic_symbol("NASDAQ:QQQ"))
        self.assertFalse(is_kis_domestic_symbol("NASDAQ:GOOX"))
        self.assertFalse(is_kis_domestic_symbol("SSE:515050"))
        self.assertFalse(is_kis_domestic_symbol("SZSE:159994"))
        self.assertFalse(is_kis_domestic_symbol("HKEX:3193"))

    def test_canonical_preserves_asia_exchange_prefix(self):
        self.assertEqual(canonical_trade_symbol("SSE:515050"), "SSE:515050")
        self.assertEqual(canonical_trade_symbol("SZSE:159994"), "SZSE:159994")
        self.assertEqual(canonical_trade_symbol("HKEX:3193"), "HKEX:03193")
        self.assertEqual(canonical_trade_symbol("KRX:069500"), "069500")
        self.assertEqual(kis_overseas_currency("TSE:213A"), "JPY")


class KISDomesticFormattingTests(unittest.TestCase):
    def test_domestic_symbol_normalization_accepts_krx_product_codes(self):
        self.assertEqual(_normalize_domestic_symbol("KRX:0005G0"), "0005G0")
        self.assertEqual(_normalize_domestic_symbol("0117V0"), "0117V0")

    def test_krw_order_price_is_integer_text(self):
        self.assertEqual(_format_krw_order_price(12345.4), "12345")
        self.assertEqual(_format_krw_order_price(12345.5), "12346")
        self.assertEqual(_format_krw_order_price(0), "0")

    def test_telegram_money_format_uses_won_for_krw(self):
        self.assertEqual(_format_money(100000, "KRW", 1450), "100,000원")
        self.assertEqual(_format_signed_money(-1234, "KRW", 1450), "-1,234원")


class KISDomesticPendingQueueTests(unittest.TestCase):
    def test_pending_flush_market_filter_separates_krx_and_us(self):
        self.assertTrue(_pending_order_matches_market({"ticker": "KRX:069500"}, "KRX"))
        self.assertFalse(_pending_order_matches_market({"ticker": "KRX:069500"}, "US"))
        self.assertFalse(_pending_order_matches_market({"ticker": "QQQ"}, "KRX"))
        self.assertTrue(_pending_order_matches_market({"ticker": "QQQ"}, "US"))
        self.assertTrue(_pending_order_matches_market({"ticker": "HKEX:3193"}, "HKEX"))
        self.assertFalse(_pending_order_matches_market({"ticker": "HKEX:3193"}, "US"))
        self.assertFalse(_pending_order_matches_market({"ticker": "SSE:515050"}, "KRX"))
        self.assertTrue(_pending_order_matches_market({"ticker": "TSE:213A"}, "TSE"))

    def test_pending_order_ttl_expires_stale_4h_strategy_orders(self):
        now = datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)
        fresh = {"ticker": "QQQ", "queued_at": (now - timedelta(hours=12)).isoformat()}
        stale = {"ticker": "QQQ", "queued_at": (now - timedelta(hours=120)).isoformat()}

        self.assertAlmostEqual(pending_order_age_hours(fresh, now_utc=now), 12.0)
        self.assertFalse(is_pending_order_expired(fresh, now_utc=now))
        self.assertTrue(is_pending_order_expired(stale, now_utc=now))

    def test_pending_order_ttl_uses_original_received_at_after_requeue(self):
        now = datetime(2026, 5, 26, 13, 30, tzinfo=timezone.utc)
        requeued_after_holiday = {
            "ticker": "FCA",
            "received_at": (now - timedelta(hours=89.5)).isoformat(),
            "queued_at": (now - timedelta(minutes=1)).isoformat(),
        }

        self.assertAlmostEqual(
            pending_order_age_hours(requeued_after_holiday, now_utc=now),
            89.5,
        )
        self.assertTrue(is_pending_order_expired(requeued_after_holiday, now_utc=now))


class KISDomesticBuySizingTests(unittest.IsolatedAsyncioTestCase):
    async def test_buy_by_amount_uses_nearest_under_target_quantity(self):
        client = KISClient()
        client.get_domestic_quote_price = AsyncMock(return_value=34000.0)
        client.get_domestic_symbol_balance = AsyncMock(return_value={"qty": 0})
        client.place_domestic_market_order = AsyncMock(return_value={"order_id": "krx-1"})
        client.wait_for_domestic_order_outcome = AsyncMock(
            return_value={
                "filled_qty": 2,
                "unfilled_qty": 0,
                "fill_price": 34010.0,
                "fill_amount": 68020.0,
            }
        )

        result = await client.place_domestic_buy_by_amount("069500", 100000)

        self.assertTrue(result["success"])
        self.assertEqual(result["qty"], 2.0)
        self.assertEqual(result["amount"], 68020.0)
        client.place_domestic_market_order.assert_awaited_once_with(
            symbol="069500",
            side="BUY",
            qty=2,
        )

    async def test_buy_by_amount_buys_one_share_when_price_exceeds_target(self):
        client = KISClient()
        client.get_domestic_quote_price = AsyncMock(return_value=120000.0)
        client.get_domestic_symbol_balance = AsyncMock(return_value={"qty": 0})
        client.place_domestic_market_order = AsyncMock(return_value={"order_id": "krx-2"})
        client.wait_for_domestic_order_outcome = AsyncMock(
            return_value={
                "filled_qty": 1,
                "unfilled_qty": 0,
                "fill_price": 120000.0,
                "fill_amount": 120000.0,
            }
        )

        result = await client.place_domestic_buy_by_amount("069500", 100000)

        self.assertTrue(result["success"])
        self.assertEqual(result["qty"], 1.0)
        client.place_domestic_market_order.assert_awaited_once_with(
            symbol="069500",
            side="BUY",
            qty=1,
        )


class KISDomesticSellProtectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_domestic_ioc_limit_order_uses_profit_protecting_order_type(self):
        client = KISClient()
        client._authorized_headers = AsyncMock(return_value={})
        client._request_json = AsyncMock(return_value={"rt_cd": "0", "output": {"ODNO": "ioc-1"}})

        result = await client.place_domestic_ioc_limit_order(
            symbol="069500",
            side="SELL",
            qty=3,
            limit_price=12345.6,
        )

        self.assertEqual(result["order_id"], "ioc-1")
        body = client._request_json.await_args.kwargs["json"]
        self.assertEqual(body["ORD_DVSN"], "11")
        self.assertEqual(body["ORD_UNPR"], "12346")
        self.assertEqual(body["SLL_TYPE"], "01")

    async def test_domestic_profit_protected_sell_skips_when_ioc_limit_does_not_fill(self):
        client = KISClient()
        client.get_domestic_symbol_balance = AsyncMock(
            return_value={"qty": 5, "orderable_qty": 5}
        )
        client.place_domestic_ioc_limit_order = AsyncMock(return_value={"order_id": "ioc-2"})
        client.place_domestic_market_order = AsyncMock()
        client.wait_for_domestic_order_outcome = AsyncMock(
            return_value={
                "filled_qty": 0,
                "unfilled_qty": 5,
                "fill_price": 0.0,
                "fill_amount": 0.0,
            }
        )

        result = await client.place_domestic_sell_qty(
            "069500",
            5,
            min_limit_price=10123.4,
        )

        self.assertFalse(result["success"])
        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "sell_profit_only_hold")
        client.place_domestic_ioc_limit_order.assert_awaited_once_with(
            symbol="069500",
            side="SELL",
            qty=5,
            limit_price=10123.4,
        )
        client.place_domestic_market_order.assert_not_awaited()


class KISOverseasOrderRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_symbol_balance_searches_exchange_candidates(self):
        client = KISClient()
        seen_exchanges = []

        async def fake_balance(exchange_code=None, currency_code=None):
            seen_exchanges.append(exchange_code)
            if exchange_code == "AMEX":
                return [
                    {
                        "ovrs_pdno": "XHE",
                        "ovrs_cblc_qty": "1",
                        "ord_psbl_qty": "1",
                        "pchs_avg_pric": "78.7499",
                    }
                ]
            return []

        client.get_overseas_balance = AsyncMock(side_effect=fake_balance)

        result = await client.get_symbol_balance("XHE")

        self.assertEqual(result["qty"], 1)
        self.assertEqual(result["orderable_qty"], 1)
        self.assertEqual(result["avg_price"], 78.7499)
        self.assertIn("AMEX", seen_exchanges)

    async def test_direct_order_resolves_exchange_before_order_payload(self):
        client = KISClient()
        client._authorized_headers = AsyncMock(return_value={})
        client._request_json = AsyncMock(return_value={"rt_cd": "0", "output": {"ODNO": "1"}})

        async def fake_quote(symbol):
            client._remember_symbol_exchange(symbol, "AMS")
            return {"symbol": symbol, "price": 100.0, "quote_exchange": "AMS", "currency": "USD"}

        client.get_quote_snapshot = AsyncMock(side_effect=fake_quote)

        result = await client.place_market_order("SPY", "BUY", 1)

        self.assertEqual(result["order_id"], "1")
        body = client._request_json.await_args.kwargs["json"]
        self.assertEqual(body["OVRS_EXCG_CD"], "AMEX")
        self.assertEqual(body["PDNO"], "SPY")

    async def test_asia_order_uses_prefixed_exchange_and_clean_symbol_code(self):
        client = KISClient()
        client._authorized_headers = AsyncMock(return_value={})
        client._request_json = AsyncMock(return_value={"rt_cd": "0", "output": {"ODNO": "2"}})
        client.get_quote_snapshot = AsyncMock(
            return_value={
                "symbol": "SSE:515050",
                "symbol_code": "515050",
                "price": 1.2345,
                "quote_exchange": "SHS",
                "currency": "CNY",
            }
        )

        result = await client.place_market_order("SSE:515050", "BUY", 1)

        self.assertEqual(result["order_id"], "2")
        headers_tr_id = client._authorized_headers.await_args.args[0]
        body = client._request_json.await_args.kwargs["json"]
        self.assertEqual(headers_tr_id, "TTTS0202U")
        self.assertEqual(body["OVRS_EXCG_CD"], "SHAA")
        self.assertEqual(body["PDNO"], "515050")


class KISDomesticPaginationTests(unittest.IsolatedAsyncioTestCase):
    async def test_domestic_balance_reads_continuation_pages(self):
        client = KISClient()
        client._authorized_headers = AsyncMock(return_value={})
        pages = [
            (
                {
                    "rt_cd": "0",
                    "output1": [{"pdno": "069500", "hldg_qty": "1"}],
                    "ctx_area_fk100": "NEXT_FK",
                    "ctx_area_nk100": "NEXT_NK",
                },
                {"tr_cont": "M"},
            ),
            (
                {
                    "rt_cd": "0",
                    "output1": [{"pdno": "102110", "hldg_qty": "2"}],
                    "ctx_area_fk100": "",
                    "ctx_area_nk100": "",
                },
                {"tr_cont": "D"},
            ),
        ]

        async def fake_get(*args, **kwargs):
            return pages.pop(0)

        client._get = AsyncMock(side_effect=fake_get)

        rows = await client.get_domestic_balance()

        self.assertEqual([row["pdno"] for row in rows], ["069500", "102110"])
        self.assertEqual(client._get.await_count, 2)


if __name__ == "__main__":
    unittest.main()
