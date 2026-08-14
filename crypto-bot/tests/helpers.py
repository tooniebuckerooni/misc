"""Shared test helpers (plain module — imported as `from helpers import ...`)."""

from __future__ import annotations

from src.brokers.base import BrokerAdapter
from src.core.types import OHLCVBar, Ticker


def make_flat_then_breakout(n: int = 40, base: float = 100.0, breakout: float = 106.0):
    """n flat bars around `base`, then one bar that breaks out to `breakout`."""
    bars: list[OHLCVBar] = []
    ts = 0
    for i in range(n):
        c = base + (0.2 if i % 2 else -0.2)
        bars.append(OHLCVBar(ts, c - 0.1, c + 0.3, c - 0.3, c, 50))
        ts += 900_000
    bars.append(OHLCVBar(ts, base + 0.2, breakout + 0.5, base + 0.1, breakout, 200))
    return bars


class FakeBroker(BrokerAdapter):
    """In-memory broker for tests: fixed candles + a mutable ticker."""

    name = "fake"

    def __init__(self, bars_by_symbol: dict[str, list[OHLCVBar]], ticker: Ticker):
        self._bars = bars_by_symbol
        self.ticker = ticker

    def list_markets(self):
        return list(self._bars.keys())

    def get_ohlcv(self, symbol, timeframe, since=None, limit=500):
        return self._bars[symbol]

    def get_ticker(self, symbol):
        return self.ticker

    def get_balance(self):
        return {"USD": 1000.0}

    def place_order(self, order):
        order.id = "fake-1"
        return order

    def cancel_order(self, order_id, symbol):
        pass

    def get_open_orders(self, symbol=None):
        return []
