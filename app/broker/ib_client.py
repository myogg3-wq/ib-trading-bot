"""
IB Gateway connection manager using ib_async.
Handles connection, auto-reconnection, and connection state monitoring.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional
import structlog

from app.config import settings

logger = structlog.get_logger()

# Global IB connection instance
_ib_instance = None
_connection_lock = asyncio.Lock()


class IBClient:
    """
    Manages connection to IB Gateway via ib_async.
    Features:
    - Auto-reconnect on disconnect
    - Connection state monitoring
    - Thread-safe singleton pattern
    """

    def __init__(self):
        self.ib = None
        self._connected = False
        self._last_connected_at: Optional[datetime] = None
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 50
        self._reconnect_delay = 5  # seconds

    async def connect(self) -> bool:
        """
        Establish connection to IB Gateway.
        Returns True if connected successfully.
        """
        try:
            from ib_async import IB

            if self.ib is None:
                self.ib = IB()

            if self.ib.isConnected():
                self._connected = True
                return True

            logger.info(
                "Connecting to IB Gateway",
                host=settings.ib_host,
                port=settings.ib_port,
                client_id=settings.ib_client_id,
            )

            await self.ib.connectAsync(
                host=settings.ib_host,
                port=settings.ib_port,
                clientId=settings.ib_client_id,
                timeout=20,
            )

            # Set up disconnect handler
            self.ib.disconnectedEvent += self._on_disconnect

            self._connected = True
            self._last_connected_at = datetime.now(timezone.utc)
            self._reconnect_attempts = 0

            logger.info("Connected to IB Gateway successfully")
            return True

        except Exception as e:
            self._connected = False
            logger.error("Failed to connect to IB Gateway", error=str(e))
            return False

    async def _on_disconnect(self):
        """Handle IB Gateway disconnection."""
        self._connected = False
        logger.warning("Disconnected from IB Gateway, starting auto-reconnect...")
        await self._auto_reconnect()

    async def _auto_reconnect(self):
        """Auto-reconnect loop with exponential backoff."""
        while self._reconnect_attempts < self._max_reconnect_attempts:
            self._reconnect_attempts += 1
            delay = min(self._reconnect_delay * self._reconnect_attempts, 300)  # max 5 min

            logger.info(
                "Reconnection attempt",
                attempt=self._reconnect_attempts,
                delay=delay,
            )

            await asyncio.sleep(delay)

            try:
                success = await self.connect()
                if success:
                    logger.info("Reconnected to IB Gateway")
                    return
            except Exception as e:
                logger.error("Reconnection failed", error=str(e))

        logger.critical(
            "Max reconnection attempts reached. Manual intervention required!"
        )

    @property
    def is_connected(self) -> bool:
        """Check if connected to IB Gateway."""
        if self.ib is None:
            return False
        return self.ib.isConnected()

    async def get_account_summary(self) -> dict:
        """Get account summary (cash, equity, etc.)."""
        if not self.is_connected:
            raise ConnectionError("Not connected to IB Gateway")

        summary = {}
        account_values = self.ib.accountSummary()

        for av in account_values:
            if av.tag in ("TotalCashValue", "NetLiquidation", "BuyingPower", "AvailableFunds"):
                summary[av.tag] = float(av.value)

        return summary

    async def get_available_cash(self) -> float:
        """Get available cash for trading."""
        summary = await self.get_account_summary()
        return summary.get("AvailableFunds", 0.0)

    async def get_positions(self) -> list:
        """Get all current positions from IB."""
        if not self.is_connected:
            raise ConnectionError("Not connected to IB Gateway")

        positions = self.ib.positions()
        result = []

        for pos in positions:
            result.append({
                "symbol": pos.contract.symbol,
                "qty": float(pos.position),
                "avg_cost": float(pos.avgCost),
                "market_value": float(pos.position) * float(pos.avgCost),
            })

        return result

    async def place_market_order(self, contract, action: str, quantity: float) -> dict:
        """
        Place a market order.

        Args:
            contract: IB Contract object
            action: "BUY" or "SELL"
            quantity: Number of shares

        Returns:
            dict with order details and fill info
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to IB Gateway")

        from ib_async import MarketOrder

        order = MarketOrder(action, quantity)
        order.tif = "DAY"  # Day order

        # For fractional shares
        if quantity != int(quantity):
            order.cashQty = 0  # Let IB handle fractional

        trade = self.ib.placeOrder(contract, order)

        logger.info(
            "Order placed",
            action=action,
            symbol=contract.symbol,
            qty=quantity,
            order_id=trade.order.orderId,
        )

        # Wait for fill (with timeout)
        timeout = settings.order_timeout_seconds
        filled = False

        for _ in range(timeout * 2):  # Check every 0.5 seconds
            await asyncio.sleep(0.5)
            if trade.isDone():
                filled = True
                break

        result = {
            "order_id": trade.order.orderId,
            "perm_id": trade.order.permId,
            "status": trade.orderStatus.status,
            "filled_qty": float(trade.orderStatus.filled),
            "avg_fill_price": float(trade.orderStatus.avgFillPrice),
            "commission": sum(f.commission for f in trade.fills) if trade.fills else 0.0,
            "filled": filled and trade.orderStatus.status == "Filled",
        }

        if not result["filled"]:
            logger.warning(
                "Order not fully filled",
                order_id=result["order_id"],
                status=result["status"],
                filled_qty=result["filled_qty"],
            )
            # Cancel unfilled order
            if not trade.isDone():
                self.ib.cancelOrder(trade.order)
                logger.info("Unfilled order cancelled", order_id=result["order_id"])

        return result

    async def get_snapshot_price(self, contract) -> Optional[float]:
        """
        Get current price via snapshot (costs $0.01 per request).
        Returns last price or close price.
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to IB Gateway")

        ticker = await self.ib.reqMktDataAsync(contract, snapshot=True)

        # Wait briefly for data
        await asyncio.sleep(1)

        price = None
        if ticker.last and ticker.last > 0:
            price = float(ticker.last)
        elif ticker.close and ticker.close > 0:
            price = float(ticker.close)

        return price

    async def disconnect(self):
        """Disconnect from IB Gateway."""
        if self.ib and self.ib.isConnected():
            self.ib.disconnect()
            logger.info("Disconnected from IB Gateway")
        self._connected = False

    def get_status(self) -> dict:
        """Get connection status info."""
        return {
            "connected": self.is_connected,
            "last_connected_at": self._last_connected_at.isoformat() if self._last_connected_at else None,
            "reconnect_attempts": self._reconnect_attempts,
        }


async def get_ib_client() -> IBClient:
    """Get or create the singleton IB client."""
    global _ib_instance
    async with _connection_lock:
        if _ib_instance is None:
            _ib_instance = IBClient()
        if not _ib_instance.is_connected:
            await _ib_instance.connect()
        return _ib_instance
