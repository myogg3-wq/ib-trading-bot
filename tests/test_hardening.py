import time
import unittest
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.queue import order_queue
from app.broker.market_hours import get_et_day_bounds_utc, get_et_week_bounds_utc
from app.gateway.security import check_timestamp_freshness
from app.queue.order_queue import (
    BUY_QUEUE,
    _idempotency_redis_key,
    _queue_name_for_action,
    _sanitize_order_for_queue,
    enqueue_order_once,
)


class SecurityTests(unittest.TestCase):
    def test_tradingview_allowlist_includes_current_official_ips(self):
        expected = {
            "52.89.214.238",
            "34.212.75.30",
            "54.218.53.128",
            "52.32.178.7",
        }
        self.assertTrue(expected.issubset(set(settings.tv_ip_list)))

    def test_timestamp_freshness_rejects_stale_epoch(self):
        stale_epoch = str(time.time() - 600)
        self.assertFalse(check_timestamp_freshness(stale_epoch, max_age_seconds=60))

    def test_timestamp_freshness_accepts_recent_iso(self):
        recent_iso = datetime.now(timezone.utc).isoformat()
        self.assertTrue(check_timestamp_freshness(recent_iso, max_age_seconds=300))

    def test_timestamp_freshness_rejects_malformed_timestamp(self):
        self.assertFalse(check_timestamp_freshness("{{timenow}}", max_age_seconds=300))


class MarketWindowTests(unittest.TestCase):
    def test_et_day_bounds_are_24_hours(self):
        start_utc, end_utc = get_et_day_bounds_utc(datetime(2026, 2, 25, 15, 0, tzinfo=timezone.utc))
        self.assertEqual(end_utc - start_utc, timedelta(days=1))

    def test_et_week_bounds_are_7_days(self):
        start_utc, end_utc = get_et_week_bounds_utc(datetime(2026, 2, 25, 15, 0, tzinfo=timezone.utc))
        self.assertEqual(end_utc - start_utc, timedelta(days=7))


class QueueTests(unittest.TestCase):
    def test_sanitize_order_removes_runtime_metadata(self):
        raw = {
            "action": "BUY",
            "ticker": "AAPL",
            "_queue_source": "orders:buy",
            "_raw_queue_payload": "{...}",
        }
        cleaned = _sanitize_order_for_queue(raw)
        self.assertIn("action", cleaned)
        self.assertIn("ticker", cleaned)
        self.assertNotIn("_queue_source", cleaned)
        self.assertNotIn("_raw_queue_payload", cleaned)

    def test_queue_name_for_action_routes_buy_and_sell(self):
        self.assertEqual(_queue_name_for_action("buy"), BUY_QUEUE)
        self.assertEqual(_queue_name_for_action("SELL"), "orders:sell")

    def test_idempotency_key_is_namespaced(self):
        self.assertEqual(_idempotency_redis_key("abc"), "orders:idempotency:abc")


class QueueIdempotencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._orig_redis = order_queue._redis_client

    async def asyncTearDown(self):
        order_queue._redis_client = self._orig_redis

    async def test_enqueue_order_once_uses_atomic_redis_guard(self):
        fake = _FakeRedis(eval_result=1)
        order_queue._redis_client = fake

        queued = await enqueue_order_once(
            {
                "action": "BUY",
                "ticker": "FCA",
                "idempotency_key": "idem-1",
                "_raw_queue_payload": "runtime-only",
            },
            ttl_seconds=60,
        )

        self.assertTrue(queued)
        self.assertEqual(len(fake.eval_calls), 1)
        _, numkeys, dedupe_key, queue_name, order_json, _, ttl = fake.eval_calls[0]
        self.assertEqual(numkeys, 2)
        self.assertEqual(dedupe_key, "orders:idempotency:idem-1")
        self.assertEqual(queue_name, BUY_QUEUE)
        self.assertEqual(ttl, 60)
        self.assertNotIn("_raw_queue_payload", order_json)

    async def test_enqueue_order_once_reports_duplicate_without_lpush(self):
        fake = _FakeRedis(eval_result=0)
        order_queue._redis_client = fake

        queued = await enqueue_order_once(
            {"action": "BUY", "ticker": "FCA", "idempotency_key": "idem-1"},
            ttl_seconds=60,
        )

        self.assertFalse(queued)
        self.assertEqual(fake.lpush_calls, [])


class _FakeRedis:
    def __init__(self, eval_result):
        self.eval_result = eval_result
        self.eval_calls = []
        self.lpush_calls = []

    async def eval(self, *args):
        self.eval_calls.append(args)
        return self.eval_result

    async def lpush(self, *args):
        self.lpush_calls.append(args)


if __name__ == "__main__":
    unittest.main()
