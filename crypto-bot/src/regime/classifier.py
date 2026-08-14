"""Market-regime ("season") classifier.

The premise: no single strategy works in every market. So first label the season, then let a
router apply the strategy that fits it. Definitions are deliberately simple and transparent —
trend direction from price vs a long MA, trend *strength* from ADX, and a relative volatility
flag from a fast/slow ATR ratio. Simple rules generalise; clever ones overfit.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..core.indicators import adx, atr, sma
from ..core.types import OHLCVBar


class Season(str, Enum):
    BULL = "bull"        # trending up
    BEAR = "bear"        # trending down
    RANGE = "range"      # no strong trend (chop)
    UNKNOWN = "unknown"  # not enough data


@dataclass
class Regime:
    season: Season
    high_vol: bool
    adx: float | None
    vol_ratio: float | None

    @property
    def label(self) -> str:
        base = self.season.value
        return f"{base}+highvol" if self.high_vol else base


class RegimeClassifier:
    def __init__(
        self,
        trend_ma: int = 50,
        adx_period: int = 14,
        adx_trend: float = 22.0,
        fast_atr: int = 14,
        slow_atr: int = 50,
        vol_ratio_high: float = 1.3,
    ):
        self.trend_ma = trend_ma
        self.adx_period = adx_period
        self.adx_trend = adx_trend
        self.fast_atr = fast_atr
        self.slow_atr = slow_atr
        self.vol_ratio_high = vol_ratio_high

    def classify(self, bars: list[OHLCVBar]) -> Regime:
        need = max(self.trend_ma, self.slow_atr, 2 * self.adx_period + 2) + 2
        if len(bars) < need:
            return Regime(Season.UNKNOWN, False, None, None)

        ma = sma(bars, self.trend_ma)
        a = adx(bars, self.adx_period)
        fast = atr(bars, self.fast_atr)
        slow = atr(bars, self.slow_atr)
        price = bars[-1].close

        vol_ratio = (fast / slow) if (fast and slow and slow > 0) else None
        high_vol = bool(vol_ratio and vol_ratio >= self.vol_ratio_high)

        if ma is None or a is None:
            return Regime(Season.UNKNOWN, high_vol, a, vol_ratio)

        if a >= self.adx_trend:
            season = Season.BULL if price >= ma else Season.BEAR
        else:
            season = Season.RANGE
        return Regime(season, high_vol, a, vol_ratio)
