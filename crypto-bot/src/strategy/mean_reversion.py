"""Mean-reversion strategy (long-only spot).

Thesis opposite to the breakout: buy sharp dips that are statistically stretched below a moving
average, targeting a snap-back to the mean. Tends to trade with a higher win rate but smaller
wins — the opposite failure mode to breakouts — which is exactly why it's worth testing as a
second family in the search.

Rule on the latest closed bar:
  - z = (close - MA) / stdev(close). If z <= -entry_z (oversold) -> propose a long.
  - Take-profit = the moving average (revert to mean). Stop = entry - sl_sd * stdev.
"""

from __future__ import annotations

from ..core.indicators import sma, stdev
from ..core.types import Bracket, OHLCVBar, Side, Ticker
from .base import Strategy


class MeanReversion(Strategy):
    name = "mean_reversion"

    def __init__(
        self,
        ma_bars: int = 20,
        entry_z: float = 2.0,
        sl_sd: float = 1.5,
        min_rr: float = 1.0,
    ):
        self.ma_bars = ma_bars
        self.entry_z = entry_z
        self.sl_sd = sl_sd
        self.min_rr = min_rr

    def evaluate(
        self, symbol: str, bars: list[OHLCVBar], ticker: Ticker | None = None
    ) -> Bracket | None:
        if len(bars) < self.ma_bars + 2:
            return None
        ma = sma(bars, self.ma_bars)
        sd = stdev(bars, self.ma_bars)
        if ma is None or sd is None or sd <= 0:
            return None

        last = bars[-1]
        z = (last.close - ma) / sd
        if z > -self.entry_z:
            return None  # not stretched enough below the mean

        entry = ticker.ask if (ticker and ticker.ask > 0) else last.close
        tp = ma                       # revert to the mean
        sl = entry - self.sl_sd * sd  # stop a bit further down
        if sl <= 0 or tp <= entry:
            return None

        bracket = Bracket(
            symbol=symbol, side=Side.BUY, entry_price=entry, tp_price=tp, sl_price=sl,
            score=round(-z, 4),
            reason=f"z={z:.2f} (<= -{self.entry_z}) revert to MA{self.ma_bars}",
        )
        if bracket.rr_ratio() < self.min_rr:
            return None
        return bracket
