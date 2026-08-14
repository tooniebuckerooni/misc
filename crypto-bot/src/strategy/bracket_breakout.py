"""Default strategy: methodical Donchian breakout with ATR-based brackets (long-only spot).

Rule, evaluated on the latest closed bar:
  - If close breaks above the Donchian upper channel of the prior N bars -> propose a long.
  - Entry at the current price; take-profit = entry + tp_mult * ATR; stop = entry - sl_mult * ATR.
  - Score = breakout strength measured in ATRs (how far past the channel), so the scanner can
    rank competing setups.

Everything is pre-defined — there is no discretionary holding. If the setup's reward doesn't
clear a minimum reward:risk, we return None and let the scanner move on.
"""

from __future__ import annotations

from ..core.indicators import atr, donchian
from ..core.types import Bracket, OHLCVBar, Side, Ticker
from .base import Strategy


class BracketBreakout(Strategy):
    name = "bracket_breakout"

    def __init__(
        self,
        channel_bars: int = 20,
        atr_bars: int = 14,
        tp_atr_mult: float = 2.0,
        sl_atr_mult: float = 1.0,
        min_rr: float = 1.5,
    ):
        self.channel_bars = channel_bars
        self.atr_bars = atr_bars
        self.tp_atr_mult = tp_atr_mult
        self.sl_atr_mult = sl_atr_mult
        self.min_rr = min_rr

    def evaluate(
        self, symbol: str, bars: list[OHLCVBar], ticker: Ticker | None = None
    ) -> Bracket | None:
        need = max(self.channel_bars, self.atr_bars) + 2
        if len(bars) < need:
            return None

        channel = donchian(bars, self.channel_bars)
        a = atr(bars, self.atr_bars)
        if channel is None or a is None or a <= 0:
            return None

        upper, _lower = channel
        last = bars[-1]
        # Prefer the live ask as the realistic entry when available (we buy at the ask).
        entry = ticker.ask if (ticker and ticker.ask > 0) else last.close

        if last.close <= upper:
            return None  # no breakout

        tp = entry + self.tp_atr_mult * a
        sl = entry - self.sl_atr_mult * a
        if sl <= 0 or tp <= entry:
            return None

        breakout_strength = (last.close - upper) / a  # in ATRs past the channel
        bracket = Bracket(
            symbol=symbol,
            side=Side.BUY,
            entry_price=entry,
            tp_price=tp,
            sl_price=sl,
            score=round(breakout_strength, 4),
            reason=f"close {last.close:.6g} > {self.channel_bars}-bar high {upper:.6g} "
            f"({breakout_strength:.2f} ATR)",
        )
        if bracket.rr_ratio() < self.min_rr:
            return None
        return bracket
