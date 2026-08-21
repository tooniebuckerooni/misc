"""Mechanical ICT primitives: liquidity sweep, displacement, Fair Value Gap (FVG).

A codifiable interpretation of the ERL->IRL / "ICT 2022" model, stripped of its discretionary and
session-timing parts (which don't translate to 24/7 crypto). These are reusable — the ICT strategy
uses them, and they can also feed the Lab as signals. Market-agnostic: the same logic applies to
crypto now and to index-futures/FX once IBKR is wired.
"""

from __future__ import annotations

from .types import OHLCVBar


def swept_low(bars: list[OHLCVBar], start: int, end: int) -> tuple[int, float] | None:
    """Find a sell-side liquidity raid in [start,end): the window's lowest low that undercut the
    prior lows before it (a stop-run). Returns (index, low) or None."""
    if end - start < 3:
        return None
    lo_idx = min(range(start, end), key=lambda k: bars[k].low)
    if lo_idx <= start:
        return None  # low is at the very edge — no 'prior' to have swept
    prior_min = min(bars[k].low for k in range(start, lo_idx))
    if bars[lo_idx].low < prior_min:
        return lo_idx, bars[lo_idx].low
    return None


def has_displacement(bars: list[OHLCVBar], start: int, end: int, atr_val: float, mult: float) -> bool:
    """A strong bullish bar (body > mult*ATR) after the sweep — the 'reaction' that repriced up."""
    for i in range(start, end):
        if bars[i].close > bars[i].open and (bars[i].close - bars[i].open) > mult * atr_val:
            return True
    return False


def last_bullish_fvg(bars: list[OHLCVBar], start: int, end: int) -> tuple[int, float, float] | None:
    """Most recent bullish Fair Value Gap in [start,end): a 3-candle imbalance where
    bars[i-2].high < bars[i].low. Returns (i, gap_low, gap_high) = (candle-1 high, candle-3 low)."""
    for i in range(end - 1, start + 1, -1):
        if bars[i - 2].high < bars[i].low:
            return i, bars[i - 2].high, bars[i].low
    return None
