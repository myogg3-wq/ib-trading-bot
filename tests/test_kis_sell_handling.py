import unittest
import atexit
import os
from pathlib import Path
from unittest.mock import AsyncMock

TEST_KIS_TOKEN_CACHE_PATH = Path(__file__).resolve().parent / ".tmp_kis_access_token.json"
os.environ["KIS_TOKEN_CACHE_PATH"] = str(TEST_KIS_TOKEN_CACHE_PATH)
atexit.register(lambda: TEST_KIS_TOKEN_CACHE_PATH.unlink(missing_ok=True))

from app.config import settings
from app.broker import order_executor
from app.broker.kis_client import KISClient, _format_us_order_price


class KISOrderPriceFormattingTests(unittest.TestCase):
    def test_order_price_is_always_two_decimal_text(self):
        self.assertEqual(_format_us_order_price(77.08), "77.08")
        self.assertEqual(_format_us_order_price(77.081234), "77.08")
        self.assertEqual(_format_us_order_price(77.085), "77.09")

    def test_order_price_has_minimum_cent(self):
        self.assertEqual(_format_us_order_price(0), "0.01")
        self.assertEqual(_format_us_order_price(0.004), "0.01")


class KISSellHandlingTests(unittest.IsolatedAsyncioTestCase):
    async def test_confirmed_sell_fill_is_success_when_db_persist_fails(self):
        old_get_session = order_executor.get_session

        class FailingSession:
            async def __aenter__(self):
                raise RuntimeError("db down")

            async def __aexit__(self, exc_type, exc, tb):
                return False

        try:
            order_executor.get_session = lambda: FailingSession()
            result = await order_executor._apply_kis_sell_fill(
                symbol="FCA",
                requested_qty=1,
                filled_qty=1,
                fill_price=20.0,
                commission=0.0,
                raw_order_id="sell-db-fail",
                alert_id="alert-1",
                currency="USD",
            )
        finally:
            order_executor.get_session = old_get_session

        self.assertTrue(result["success"])
        self.assertTrue(result["db_persist_pending_reconcile"])
        self.assertEqual(result["qty"], 1)
        self.assertEqual(result["exit_total"], 20.0)

    async def test_full_fill_is_treated_as_success_even_if_history_looks_open(self):
        client = KISClient()
        client.get_symbol_balance = AsyncMock(return_value={"qty": 1, "avg_price": 0.0})
        client.get_quote_snapshot = AsyncMock(return_value={"symbol": "VOT", "price": 100.0, "currency": "USD"})
        client.place_market_order = AsyncMock(return_value={"order_id": "abc123"})
        client.wait_for_order_outcome = AsyncMock(
            return_value={
                "filled_qty": 1,
                "unfilled_qty": 1,
                "fill_price": 0.0,
                "fill_amount": 0.0,
            }
        )
        client.cancel_order = AsyncMock(return_value={"success": True})
        client._infer_fill_from_balance_delta = AsyncMock(
            return_value={
                "filled_qty": 1,
                "unfilled_qty": 0,
                "fill_price": 0.0,
                "fill_amount": 0.0,
            }
        )

        result = await client.place_sell_qty("VOT", 1)

        self.assertTrue(result["success"])
        self.assertEqual(result["qty"], 1.0)
        self.assertNotIn("partial_fill", result)

    async def test_partial_fill_is_returned_as_partial_success(self):
        client = KISClient()
        client.get_symbol_balance = AsyncMock(return_value={"qty": 2, "avg_price": 0.0})
        client.get_quote_snapshot = AsyncMock(return_value={"symbol": "ROM", "price": 50.0, "currency": "USD"})
        client.place_market_order = AsyncMock(return_value={"order_id": "sell-1"})
        client.wait_for_order_outcome = AsyncMock(
            return_value={
                "filled_qty": 1,
                "unfilled_qty": 1,
                "fill_price": 49.5,
                "fill_amount": 49.5,
            }
        )
        client.cancel_order = AsyncMock(return_value={"success": True})
        client._infer_fill_from_balance_delta = AsyncMock(
            return_value={
                "filled_qty": 1,
                "unfilled_qty": 1,
                "fill_price": 49.5,
                "fill_amount": 49.5,
            }
        )

        result = await client.place_sell_qty("ROM", 2)

        self.assertTrue(result["success"])
        self.assertTrue(result["partial_fill"])
        self.assertEqual(result["qty"], 1.0)
        self.assertEqual(result["remaining_qty"], 1)


class KISBuyHandlingTests(unittest.IsolatedAsyncioTestCase):
    async def test_buy_uses_configured_limit_markup(self):
        old_markup = settings.kis_buy_limit_markup_pct
        try:
            settings.kis_buy_limit_markup_pct = 3.0
            client = KISClient()
            client.get_quote_snapshot = AsyncMock(
                return_value={"symbol": "TESL", "price": 17.0, "currency": "USD"}
            )
            client.get_symbol_balance = AsyncMock(return_value={"qty": 0, "avg_price": 0.0})
            client.place_market_order = AsyncMock(return_value={"order_id": "buy-1"})
            client.wait_for_order_outcome = AsyncMock(
                return_value={
                    "filled_qty": 3,
                    "unfilled_qty": 0,
                    "fill_price": 17.51,
                    "fill_amount": 52.53,
                }
            )

            result = await client.place_buy_by_amount("TESL", 66.5)

            self.assertTrue(result["success"])
            self.assertEqual(result["qty"], 3.0)
            self.assertEqual(client.place_market_order.await_args.kwargs["limit_price"], 17.51)
        finally:
            settings.kis_buy_limit_markup_pct = old_markup

    async def test_buy_retries_transient_submit_error_after_safety_checks(self):
        old_retry_count = settings.kis_order_post_retry_count
        old_retry_delay = settings.kis_order_post_retry_delay_seconds
        try:
            settings.kis_order_post_retry_count = 1
            settings.kis_order_post_retry_delay_seconds = 0.2
            client = KISClient()
            client.get_quote_snapshot = AsyncMock(
                side_effect=[
                    {"symbol": "SATO", "price": 18.0, "currency": "USD"},
                    {"symbol": "SATO", "price": 18.1, "currency": "USD"},
                ]
            )
            client.get_symbol_balance = AsyncMock(return_value={"qty": 0, "avg_price": 0.0})
            client.place_market_order = AsyncMock(
                side_effect=[RuntimeError("500 Internal Server Error"), {"order_id": "buy-2"}]
            )
            client._infer_fill_from_balance_delta = AsyncMock(
                return_value={
                    "filled_qty": 0,
                    "unfilled_qty": 3,
                    "fill_price": 0.0,
                    "fill_amount": 0.0,
                }
            )
            client.has_unfilled_symbol_order = AsyncMock(return_value=False)
            client.wait_for_order_outcome = AsyncMock(
                return_value={
                    "filled_qty": 3,
                    "unfilled_qty": 0,
                    "fill_price": 18.64,
                    "fill_amount": 55.92,
                }
            )

            result = await client.place_buy_by_amount("SATO", 66.5)

            self.assertTrue(result["success"])
            self.assertEqual(client.place_market_order.await_count, 2)
            client.has_unfilled_symbol_order.assert_awaited_once_with("SATO")
        finally:
            settings.kis_order_post_retry_count = old_retry_count
            settings.kis_order_post_retry_delay_seconds = old_retry_delay


if __name__ == "__main__":
    unittest.main()
