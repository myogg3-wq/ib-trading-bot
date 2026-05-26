import unittest

from app.broker import order_executor
from app.config import settings


class BrokerRoutingTests(unittest.TestCase):
    def setUp(self):
        self._orig_mode = settings.broker_mode
        self._orig_primary = settings.primary_broker
        self._orig_secondary = settings.secondary_broker

    def tearDown(self):
        settings.broker_mode = self._orig_mode
        settings.primary_broker = self._orig_primary
        settings.secondary_broker = self._orig_secondary

    def test_ib_only_chain(self):
        settings.broker_mode = "ib_only"
        self.assertEqual(order_executor._broker_execution_chain(), ["ib"])

    def test_kis_only_chain(self):
        settings.broker_mode = "kis_only"
        self.assertEqual(order_executor._broker_execution_chain(), ["kis"])

    def test_dual_failover_chain_dedupes(self):
        settings.broker_mode = "dual_failover"
        settings.primary_broker = "IB"
        settings.secondary_broker = "ib"
        self.assertEqual(order_executor._broker_execution_chain(), ["ib"])

    def test_dual_failover_chain_primary_secondary(self):
        settings.broker_mode = "dual_failover"
        settings.primary_broker = "kis"
        settings.secondary_broker = "ib"
        self.assertEqual(order_executor._broker_execution_chain(), ["kis", "ib"])

    def test_invalid_mode_falls_back_to_kis(self):
        settings.broker_mode = "unknown_mode"
        self.assertEqual(order_executor._broker_execution_chain(), ["kis"])

    def test_kis_synthetic_order_id_is_negative(self):
        synthetic = order_executor._kis_synthetic_order_id("abc123", "AAPL", "BUY")
        self.assertLess(synthetic, 0)


if __name__ == "__main__":
    unittest.main()
