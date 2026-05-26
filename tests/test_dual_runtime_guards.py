import unittest

from app.config import settings
from app.risk import risk_manager


class AllowedTickerParseTests(unittest.TestCase):
    def setUp(self):
        self._orig_allowed = settings.allowed_tickers

    def tearDown(self):
        settings.allowed_tickers = self._orig_allowed

    def test_empty_allowlist_means_allow_all(self):
        settings.allowed_tickers = ""
        self.assertEqual(settings.allowed_ticker_list, [])

    def test_allowlist_normalizes_case_and_spaces(self):
        settings.allowed_tickers = " ibb, Bndx ,  hero "
        self.assertEqual(settings.allowed_ticker_list, ["IBB", "BNDX", "HERO"])


class CashCheckRoutingTests(unittest.TestCase):
    def setUp(self):
        self._orig_mode = settings.broker_mode
        self._orig_primary = settings.primary_broker
        self._orig_secondary = settings.secondary_broker

    def tearDown(self):
        settings.broker_mode = self._orig_mode
        settings.primary_broker = self._orig_primary
        settings.secondary_broker = self._orig_secondary

    def test_cash_chain_ib_only(self):
        settings.broker_mode = "ib_only"
        self.assertEqual(risk_manager._cash_check_broker_chain(), ["ib"])

    def test_cash_chain_kis_only(self):
        settings.broker_mode = "kis_only"
        self.assertEqual(risk_manager._cash_check_broker_chain(), ["kis"])

    def test_cash_chain_dual_failover_respects_order(self):
        settings.broker_mode = "dual_failover"
        settings.primary_broker = "kis"
        settings.secondary_broker = "ib"
        self.assertEqual(risk_manager._cash_check_broker_chain(), ["kis", "ib"])


if __name__ == "__main__":
    unittest.main()
