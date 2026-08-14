from __future__ import annotations

from src.core.types import Ticker
from src.data.feed import DataFeed
from src.data.store import Store
from src.scanner.screener import Screener, estimate_round_trip_cost
from src.strategy.bracket_breakout import BracketBreakout

from helpers import FakeBroker


def test_cost_estimate_penalizes_spread():
    cheap = estimate_round_trip_cost(0.0004, 0.0016, 0.0026)
    pricey = estimate_round_trip_cost(0.02, 0.0016, 0.0026)
    assert pricey > cheap
    assert estimate_round_trip_cost(float("inf"), 0.0016, 0.0026) == float("inf")


def _screener(tmp_path, ticker, bars):
    broker = FakeBroker({"ETH/USD": bars}, ticker)
    feed = DataFeed(broker, Store(tmp_path / "t.db"))
    return Screener(feed, BracketBreakout(), universe=["ETH/USD"], timeframe="15m",
                    lookback=200, max_round_trip_cost=0.006, top_n=5)


def test_scan_accepts_cheap_pair(tmp_path, bars, tight_ticker):
    cands = _screener(tmp_path, tight_ticker, bars).scan()
    assert len(cands) == 1
    assert cands[0].bracket.symbol == "ETH/USD"
    assert cands[0].bracket.est_cost_frac <= 0.006


def test_scan_rejects_wide_spread(tmp_path, bars):
    wide = Ticker("ETH/USD", 104.0, 108.0, 106.0, 40 * 900_000)  # ~3.8% spread
    assert _screener(tmp_path, wide, bars).scan() == []


def test_scan_excludes_symbol(tmp_path, bars, tight_ticker):
    sc = _screener(tmp_path, tight_ticker, bars)
    assert sc.scan(exclude={"ETH/USD"}) == []
