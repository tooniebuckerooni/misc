"""Small, dependency-light technical indicators computed on OHLCV bars.

Pure functions — no I/O — so they run identically in backtest, paper, and live, and are
trivial to unit-test.
"""

from __future__ import annotations

from .types import OHLCVBar


def true_ranges(bars: list[OHLCVBar]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i].high, bars[i].low, bars[i - 1].close
        out.append(max(h - l, abs(h - pc), abs(l - pc)))
    return out


def atr(bars: list[OHLCVBar], period: int) -> float | None:
    """Average True Range over the last `period` completed bars (simple mean)."""
    trs = true_ranges(bars)
    if len(trs) < period:
        return None
    window = trs[-period:]
    return sum(window) / period


def donchian(bars: list[OHLCVBar], period: int) -> tuple[float, float] | None:
    """Highest high / lowest low over the `period` bars *before* the latest bar.

    Excluding the latest bar makes 'close > upper' a genuine breakout of prior range.
    """
    if len(bars) < period + 1:
        return None
    prior = bars[-(period + 1):-1]
    upper = max(b.high for b in prior)
    lower = min(b.low for b in prior)
    return upper, lower


def sma(bars: list[OHLCVBar], period: int) -> float | None:
    if len(bars) < period:
        return None
    return sum(b.close for b in bars[-period:]) / period


def returns_std(bars: list[OHLCVBar], period: int) -> float | None:
    """Std-dev of per-bar returns — a normalized volatility gauge for ranking setups."""
    if len(bars) < period + 1:
        return None
    closes = [b.close for b in bars[-(period + 1):]]
    rets = [
        (closes[i] - closes[i - 1]) / closes[i - 1]
        for i in range(1, len(closes))
        if closes[i - 1] > 0
    ]
    if not rets:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    return var ** 0.5
