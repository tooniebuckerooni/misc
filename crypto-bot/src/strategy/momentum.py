"""Cross-sectional / relative-strength momentum (long-only spot).

Thesis distinct from mean-reversion: winners keep winning. Buy pairs with the strongest trailing
return that are also trending up, with an ATR bracket. The bracket's `score` is the trailing
return, so the scanner ranks pairs against each other and holds the *leaders* of the basket —
that's the cross-sectional ("relative strength") behaviour, complementary to buying dips.

Note: true per-bar cross-sectional selection happens live via the scanner's top-N ranking. In the
per-symbol backtester the position cap + risk-heat cap approximate "hold only the few strongest."
"""

from __future__ import annotations

from ..core.indicators import atr, sma
from ..core.types import Bracket, OHLCVBar, Side, Ticker
from .base import Strategy


class Momentum(Strategy):
    name = "momentum"

    def __init__(
        self,
        mom_bars: int = 30,
        trend_ma: int = 50,
        min_return: float = 0.10,
        atr_bars: int = 14,
        tp_atr_mult: float = 3.0,
        sl_atr_mult: float = 2.0,
        min_rr: float = 1.0,
    ):
        self.mom_bars = mom_bars
        self.trend_ma = trend_ma
        self.min_return = min_return
        self.atr_bars = atr_bars
        self.tp = tp_atr_mult
        self.sl = sl_atr_mult
        self.min_rr = min_rr

    def evaluate(
        self, symbol: str, bars: list[OHLCVBar], ticker: Ticker | None = None
    ) -> Bracket | None:
        need = max(self.mom_bars, self.trend_ma, self.atr_bars) + 2
        if len(bars) < need:
            return None

        past = bars[-(self.mom_bars + 1)].close
        if past <= 0:
            return None
        ret = bars[-1].close / past - 1.0
        ma = sma(bars, self.trend_ma)
        a = atr(bars, self.atr_bars)
        if ma is None or a is None or a <= 0:
            return None

        # Must be a strong mover AND in an uptrend.
        if ret < self.min_return or bars[-1].close < ma:
            return None

        entry = ticker.ask if (ticker and ticker.ask > 0) else bars[-1].close
        tp = entry + self.tp * a
        sl = entry - self.sl * a
        if sl <= 0 or tp <= entry:
            return None

        bracket = Bracket(
            symbol=symbol, side=Side.BUY, entry_price=entry, tp_price=tp, sl_price=sl,
            score=round(ret, 4),  # trailing return => cross-sectional rank
            reason=f"{self.mom_bars}-bar return {ret:.1%} > {self.min_return:.0%}, above MA{self.trend_ma}",
        )
        if bracket.rr_ratio() < self.min_rr:
            return None
        return bracket
