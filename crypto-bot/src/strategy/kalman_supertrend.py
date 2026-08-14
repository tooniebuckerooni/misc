"""Kalman-SuperTrend + ADX strategy (long-only spot).

Distilled from the "0DTE Scalper" TradingView indicator, transplanted from options to crypto
spot and stripped to its defensible core: a SuperTrend computed on a Kalman-smoothed price for a
clean trend signal, gated by ADX so we only act when a trend is statistically present. Momentum
stacking (Squeeze/MACD) is deliberately dropped — fewer knobs, less overfitting.

Rule: when SuperTrend flips to bullish on the latest bar AND ADX >= threshold, go long with an
ATR-based bracket. No shorting (spot).
"""

from __future__ import annotations

from ..core.indicators import adx, atr, kalman, supertrend
from ..core.types import Bracket, OHLCVBar, Side, Ticker
from .base import Strategy


class KalmanSuperTrend(Strategy):
    name = "kalman_supertrend"

    def __init__(
        self,
        kalman_q: float = 0.001,
        kalman_r: float = 0.1,
        st_period: int = 10,
        st_mult: float = 3.0,
        adx_period: int = 14,
        adx_threshold: float = 20.0,
        atr_bars: int = 14,
        tp_atr_mult: float = 2.0,
        sl_atr_mult: float = 1.0,
        min_rr: float = 1.0,
        require_flip: bool = True,
    ):
        self.kq = kalman_q
        self.kr = kalman_r
        self.st_period = st_period
        self.st_mult = st_mult
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.atr_bars = atr_bars
        self.tp = tp_atr_mult
        self.sl = sl_atr_mult
        self.min_rr = min_rr
        self.require_flip = require_flip

    def evaluate(
        self, symbol: str, bars: list[OHLCVBar], ticker: Ticker | None = None
    ) -> Bracket | None:
        need = max(self.st_period, self.atr_bars, 2 * self.adx_period + 2) + 2
        if len(bars) < need:
            return None

        ks = kalman(bars, self.kq, self.kr)
        direction, _line = supertrend(bars, self.st_period, self.st_mult, source_vals=ks)
        a = adx(bars, self.adx_period)
        atr_val = atr(bars, self.atr_bars)
        if a is None or atr_val is None or atr_val <= 0:
            return None

        bull = direction[-1] == 1
        flipped = direction[-1] == 1 and direction[-2] != 1
        trigger = flipped if self.require_flip else bull
        if not trigger or a < self.adx_threshold:
            return None

        last = bars[-1]
        entry = ticker.ask if (ticker and ticker.ask > 0) else last.close
        tp = entry + self.tp * atr_val
        sl = entry - self.sl * atr_val
        if sl <= 0 or tp <= entry:
            return None

        bracket = Bracket(
            symbol=symbol, side=Side.BUY, entry_price=entry, tp_price=tp, sl_price=sl,
            score=round(a, 2),
            reason=f"SuperTrend bull flip, ADX {a:.1f} >= {self.adx_threshold}",
        )
        if bracket.rr_ratio() < self.min_rr:
            return None
        return bracket
