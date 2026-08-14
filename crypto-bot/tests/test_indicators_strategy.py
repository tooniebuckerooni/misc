from __future__ import annotations

from src.core.indicators import atr, donchian, sma
from src.core.types import Ticker
from src.strategy.bracket_breakout import BracketBreakout


def test_donchian_excludes_latest_bar(bars):
    upper, lower = donchian(bars, 20)
    # The flat regime sits ~99.8-100.5; the breakout bar (last) must be excluded.
    assert upper < 105
    assert lower < upper


def test_atr_positive(bars):
    a = atr(bars, 14)
    assert a is not None and a > 0


def test_sma_none_when_insufficient():
    assert sma([], 10) is None


def test_strategy_emits_bracket_on_breakout(bars, tight_ticker):
    strat = BracketBreakout(channel_bars=20, atr_bars=14, tp_atr_mult=2.0, sl_atr_mult=1.0)
    b = strat.evaluate("ETH/USD", bars, tight_ticker)
    assert b is not None
    assert b.side.value == "buy"
    assert b.tp_price > b.entry_price > b.sl_price
    assert b.rr_ratio() >= 1.5


def test_strategy_none_without_breakout(bars):
    # Chop with no breakout: drop the final breakout bar.
    flat = bars[:-1]
    strat = BracketBreakout()
    assert strat.evaluate("ETH/USD", flat, Ticker("ETH/USD", 100.0, 100.0, 100.0, 0)) is None
