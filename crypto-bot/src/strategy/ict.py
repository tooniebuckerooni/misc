"""ICT ERL->IRL strategy (mechanical, long-only).

Codifies the setup from the Reddit post, minus the discretionary/session parts:
  1. Sell-side liquidity swept (a recent low undercut prior lows).       [ERL taken]
  2. Bullish displacement away from that low.                            [reaction]
  3. A bullish Fair Value Gap formed during the displacement.            [IRL zone]
  4. Price retraces INTO that FVG -> enter long.                         [entry]
  5. Stop beyond the swept low (invalidation); target = fixed R-multiple. [1-2R]

Honest scope: ICT is native to intraday index-futures/FX with session timing; here it's tested on
crypto as a proxy and is ready to run on IBKR instruments later. It only trades the mechanical model,
not discretion — which is exactly what we want to measure.
"""

from __future__ import annotations

from ..core.ict import has_displacement, last_bullish_fvg, swept_low
from ..core.indicators import atr
from ..core.types import Bracket, OHLCVBar, Side, Ticker
from .base import Strategy


class ICTStrategy(Strategy):
    name = "ict"

    def __init__(
        self,
        window: int = 30,          # bars to scan for the sweep + FVG
        atr_period: int = 14,
        disp_mult: float = 1.0,    # displacement bar body must exceed this * ATR
        fvg_max_age: int = 10,     # the FVG must be recent (bars)
        r_multiple: float = 2.0,   # take-profit at this * risk
        stop_buffer: float = 0.001,  # stop placed just beyond the swept low
    ):
        self.window = window
        self.atr_period = atr_period
        self.disp_mult = disp_mult
        self.fvg_max_age = fvg_max_age
        self.r_multiple = r_multiple
        self.stop_buffer = stop_buffer

    def evaluate(
        self, symbol: str, bars: list[OHLCVBar], ticker: Ticker | None = None
    ) -> Bracket | None:
        n = len(bars)
        if n < self.window + 3:
            return None
        a = atr(bars, self.atr_period)
        if a is None or a <= 0:
            return None

        start, end = n - self.window, n
        sw = swept_low(bars, start, end)
        if sw is None:
            return None
        lo_idx, lo_val = sw

        if not has_displacement(bars, lo_idx + 1, end, a, self.disp_mult):
            return None

        fvg = last_bullish_fvg(bars, lo_idx, end)
        if fvg is None:
            return None
        c_idx, gap_low, gap_high = fvg
        if c_idx < end - self.fvg_max_age:      # stale gap
            return None

        # Entry only once price has retraced INTO the imbalance.
        last = bars[-1]
        if not (gap_low <= last.close <= gap_high):
            return None

        entry = ticker.ask if (ticker and ticker.ask > 0) else last.close
        stop = lo_val * (1 - self.stop_buffer)
        if stop <= 0 or stop >= entry:
            return None
        tp = entry + self.r_multiple * (entry - stop)

        bracket = Bracket(
            symbol=symbol, side=Side.BUY, entry_price=entry, tp_price=tp, sl_price=stop,
            score=round((entry - stop) / entry, 4),  # risk fraction — smaller = tighter setup
            reason=f"ERL swept @ {lo_val:.6g}, displaced, FVG[{gap_low:.6g},{gap_high:.6g}] entry",
        )
        return bracket if bracket.rr_ratio() >= 1.0 else None
