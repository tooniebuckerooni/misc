"""Data feed: cached OHLCV + live tickers.

Wraps a broker and the SQLite store so candles are fetched once and reused. The backtester
reads purely from cache; paper/live top up the cache from the broker as new bars close.
"""

from __future__ import annotations

from ..brokers.base import BrokerAdapter
from ..core.types import OHLCVBar, Ticker
from .store import Store

# Approximate milliseconds per timeframe, used to decide how many bars to backfill.
_TF_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


def timeframe_ms(timeframe: str) -> int:
    if timeframe not in _TF_MS:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return _TF_MS[timeframe]


class DataFeed:
    def __init__(self, broker: BrokerAdapter, store: Store):
        self.broker = broker
        self.store = store

    def get_ticker(self, symbol: str) -> Ticker:
        return self.broker.get_ticker(symbol)

    def update(self, symbol: str, timeframe: str, limit: int = 500) -> int:
        """Fetch candles newer than what's cached and persist them. Returns rows written."""
        last = self.store.last_candle_ts(symbol, timeframe)
        since = last + 1 if last is not None else None
        bars = self.broker.get_ohlcv(symbol, timeframe, since=since, limit=limit)
        return self.store.upsert_candles(symbol, timeframe, bars)

    def get_bars(
        self, symbol: str, timeframe: str, lookback: int, refresh: bool = True
    ) -> list[OHLCVBar]:
        """Return the most recent `lookback` bars, refreshing the cache first if asked."""
        if refresh:
            self.update(symbol, timeframe, limit=max(lookback, 100))
        bars = self.store.get_candles(symbol, timeframe)
        return bars[-lookback:] if lookback and len(bars) > lookback else bars

    def backfill(self, symbol: str, timeframe: str, target_bars: int) -> int:
        """Page backwards to build up history for backtesting. Returns total rows written."""
        written = 0
        tf_ms = timeframe_ms(timeframe)
        # Start from (now - target_bars * tf) and walk forward in pages.
        import time

        now = int(time.time() * 1000)
        since = now - target_bars * tf_ms
        while since < now:
            bars = self.broker.get_ohlcv(symbol, timeframe, since=since, limit=720)
            if not bars:
                break
            written += self.store.upsert_candles(symbol, timeframe, bars)
            new_since = bars[-1].ts + tf_ms
            if new_since <= since:  # no progress — avoid infinite loop
                break
            since = new_since
            if len(bars) < 720:  # reached the current edge
                break
        return written
