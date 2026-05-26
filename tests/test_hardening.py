import json
import time
import unittest
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.gateway.webhook import _build_webhook_idempotency, _clean_tradingview_optional_field
from app.queue import order_queue
from app.broker.market_hours import get_et_day_bounds_utc, get_et_week_bounds_utc
from app.gateway.security import check_timestamp_freshness
from app.queue.order_queue import (
    BUY_QUEUE,
    PENDING_QUEUE,
    _idempotency_redis_key,
    _queue_name_for_action,
    _sanitize_order_for_queue,
    enqueue_order_once,
    flush_pending_to_active,
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

    def test_unresolved_tradingview_placeholders_are_treated_as_missing_optional_fields(self):
        self.assertEqual(_clean_tradingview_optional_field("{{timenow}}"), "")
        self.assertEqual(_clean_tradingview_optional_field("{{strategy.order.id}}"), "")
        self.assertEqual(_clean_tradingview_optional_field("real-alert-id"), "real-alert-id")

    def test_payload_only_idempotency_is_stable_within_short_ttl_bucket(self):
        payload = {"secret": "x", "action": "BUY", "ticker": "FCA", "price": "10.0"}
        now = datetime(2026, 5, 26, 1, 2, 3, tzinfo=timezone.utc)

        _, key1, dedupe1, ttl1 = _build_webhook_idempotency(
            payload=payload,
            action="BUY",
            trade_symbol="FCA",
            price_float=10.0,
            alert_id="",
            alert_time="",
            now_utc=now,
        )
        _, key2, dedupe2, ttl2 = _build_webhook_idempotency(
            payload=payload,
            action="BUY",
            trade_symbol="FCA",
            price_float=10.0,
            alert_id="",
            alert_time="",
            now_utc=now + timedelta(seconds=30),
        )

        self.assertEqual(key1, key2)
        self.assertEqual(dedupe1, dedupe2)
        self.assertEqual(ttl1, settings.webhook_fallback_idempotency_ttl_seconds)
        self.assertEqual(ttl2, settings.webhook_fallback_idempotency_ttl_seconds)

    def test_webhook_audit_fingerprint_masks_secret(self):
        payload = {"secret": "real-secret", "action": "BUY", "ticker": "FCA", "price": "10.0"}

        fingerprint, _, _, _ = _build_webhook_idempotency(
            payload=payload,
            action="BUY",
            trade_symbol="FCA",
            price_float=10.0,
            alert_id="",
            alert_time="",
            now_utc=datetime(2026, 5, 26, 1, 2, 3, tzinfo=timezone.utc),
        )

        self.assertNotIn("real-secret", fingerprint)
        self.assertIn('"secret":"***"', fingerprint)

    def test_payload_only_idempotency_rotates_after_short_ttl_bucket(self):
        payload = {"secret": "x", "action": "BUY", "ticker": "FCA", "price": "10.0"}
        now = datetime(2026, 5, 26, 1, 0, 0, tzinfo=timezone.utc)

        _, key1, dedupe1, _ = _build_webhook_idempotency(
            payload=payload,
            action="BUY",
            trade_symbol="FCA",
            price_float=10.0,
            alert_id="",
            alert_time="",
            now_utc=now,
        )
        _, key2, dedupe2, _ = _build_webhook_idempotency(
            payload=payload,
            action="BUY",
            trade_symbol="FCA",
            price_float=10.0,
            alert_id="",
            alert_time="",
            now_utc=now + timedelta(seconds=settings.webhook_fallback_idempotency_ttl_seconds),
        )

        self.assertNotEqual(key1, key2)
        self.assertEqual(dedupe1, dedupe2)

    def test_payload_only_dedupe_survives_short_ttl_bucket_boundary(self):
        payload = {"secret": "x", "action": "BUY", "ticker": "FCA", "price": "10.0"}
        ttl = settings.webhook_fallback_idempotency_ttl_seconds
        bucket_end = datetime.fromtimestamp((1_800_000 // ttl + 1) * ttl - 1, tz=timezone.utc)

        _, key1, dedupe1, _ = _build_webhook_idempotency(
            payload=payload,
            action="BUY",
            trade_symbol="FCA",
            price_float=10.0,
            alert_id="",
            alert_time="",
            now_utc=bucket_end,
        )
        _, key2, dedupe2, _ = _build_webhook_idempotency(
            payload=payload,
            action="BUY",
            trade_symbol="FCA",
            price_float=10.0,
            alert_id="",
            alert_time="",
            now_utc=bucket_end + timedelta(seconds=2),
        )

        self.assertNotEqual(key1, key2)
        self.assertEqual(dedupe1, dedupe2)


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

    async def test_flush_pending_reports_expired_payloads_for_audit(self):
        stale = {
            "action": "BUY",
            "ticker": "FCA",
            "idempotency_key": "stale-1",
            "received_at": "2000-01-01T00:00:00+00:00",
        }
        fresh = {
            "action": "BUY",
            "ticker": "QQQ",
            "idempotency_key": "fresh-1",
            "received_at": "2999-01-01T00:00:00+00:00",
        }
        fake = _PendingFakeRedis([json.dumps(fresh), json.dumps(stale)])
        order_queue._redis_client = fake

        result = await flush_pending_to_active(market="US", return_expired=True)

        self.assertEqual(result["moved"], 1)
        self.assertEqual(result["expired"], 1)
        self.assertEqual(result["expired_orders"][0]["idempotency_key"], "stale-1")
        self.assertEqual(len(fake.queues[BUY_QUEUE]), 1)
        self.assertEqual(len(fake.queues[PENDING_QUEUE]), 0)


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


class _PendingFakeRedis:
    def __init__(self, pending_rows):
        self.queues = {
            PENDING_QUEUE: list(pending_rows),
            BUY_QUEUE: [],
            "orders:sell": [],
        }

    async def llen(self, key):
        return len(self.queues.get(key, []))

    async def rpop(self, key):
        rows = self.queues.setdefault(key, [])
        if not rows:
            return None
        return rows.pop()

    async def lpush(self, key, value):
        self.queues.setdefault(key, []).insert(0, value)


if __name__ == "__main__":
    unittest.main()
