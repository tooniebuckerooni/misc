"""Deep historical-data fetcher for research/backtesting.

Kraken's public OHLC API only serves the most recent ~720 candles and won't page further back
(verified empirically). To validate strategies we need years of history, so this pulls deep
candles from an exchange whose API DOES paginate backward (default: Binance.US — 1000 bars/call,
years available; Binance global is geo-blocked in many regions). Data lands in the same SQLite
`candles` table the backtester already reads.

Provenance note: research uses this deep data (majors differ by pennies across venues, which is
irrelevant for judging edge); live EXECUTION always uses Kraken. Store candles under the source
symbol name (e.g. BTC/USDT) so it's clear where the data came from.
"""

from __future__ import annotations

import os
import time

from ..core.types import OHLCVBar
from .feed import timeframe_ms
from .store import Store


class HistoryFetcher:
    def __init__(self, exchange_id: str = "binanceus", enable_rate_limit: bool = True):
        try:
            import ccxt
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("ccxt is required: pip install ccxt") from e
        if not hasattr(ccxt, exchange_id):
            raise ValueError(f"Unknown ccxt exchange: {exchange_id}")
        self.exchange_id = exchange_id
        self.ex = getattr(ccxt, exchange_id)({"enableRateLimit": enable_rate_limit})
        # Respect proxy / CA env vars (see KrakenBroker) so it works behind a proxy.
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        if proxy:
            self.ex.proxies = {"http": proxy, "https": proxy}
        ca = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
        if ca:
            self.ex.verify = ca

    def has_symbol(self, symbol: str) -> bool:
        try:
            self.ex.load_markets()
            return symbol in self.ex.markets
        except Exception:  # noqa: BLE001
            return False

    def fetch_deep(
        self, symbol: str, timeframe: str, since_ms: int, per_call: int = 1000
    ) -> list[OHLCVBar]:
        """Page forward from `since_ms` to now, accumulating de-duplicated candles."""
        tf_ms = timeframe_ms(timeframe)
        now = int(time.time() * 1000)
        since = since_ms
        seen: dict[int, OHLCVBar] = {}
        while since < now:
            batch = self.ex.fetch_ohlcv(symbol, timeframe, since=since, limit=per_call)
            if not batch:
                break
            for r in batch:
                seen[int(r[0])] = OHLCVBar(int(r[0]), r[1], r[2], r[3], r[4], r[5])
            new_since = int(batch[-1][0]) + tf_ms
            if new_since <= since:  # no forward progress — stop
                break
            since = new_since
            if len(batch) < per_call:  # reached the current edge
                break
        return [seen[t] for t in sorted(seen)]

    def backfill_deep(
        self, store: Store, symbol: str, timeframe: str, since_ms: int
    ) -> int:
        bars = self.fetch_deep(symbol, timeframe, since_ms)
        return store.upsert_candles(symbol, timeframe, bars)
