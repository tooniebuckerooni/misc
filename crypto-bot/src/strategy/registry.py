"""Strategy registry — one place to build any lead by name.

Gives each lead its own runnable pipeline (CLI --strategy, research tools) and defines the
default regime router mapping derived from the per-season analysis. Presets here reflect the
best configs found so far; tune in one place.
"""

from __future__ import annotations

from ..config.settings import Settings
from ..regime.classifier import RegimeClassifier, Season
from .base import Strategy
from .bracket_breakout import BracketBreakout
from .kalman_supertrend import KalmanSuperTrend
from .mean_reversion import MeanReversion
from .router import RegimeRouter

STRATEGY_NAMES = ["breakout", "meanrev", "kalman", "router"]


def build_strategy(name: str, settings: Settings) -> Strategy:
    name = name.lower()
    if name == "breakout":
        return BracketBreakout(
            channel_bars=settings.breakout_channel_bars,
            atr_bars=settings.atr_bars,
            tp_atr_mult=settings.take_profit_atr_mult,
            sl_atr_mult=settings.stop_loss_atr_mult,
        )
    if name == "meanrev":
        # Daily "buy capitulation" preset — the slow-and-steady lead.
        return MeanReversion(ma_bars=20, entry_z=2.0, sl_sd=3.0)
    if name == "kalman":
        return KalmanSuperTrend(
            st_mult=3.0, adx_threshold=25, tp_atr_mult=3.0, sl_atr_mult=1.0, require_flip=True
        )
    if name == "router":
        # Season label -> specialist, from the regime analysis (FINDINGS.md).
        mapping = {
            Season.BULL.value: build_strategy("kalman", settings),    # trend up -> trend-follow
            Season.RANGE.value: build_strategy("breakout", settings),  # chop -> breakout
            Season.BEAR.value: build_strategy("meanrev", settings),    # downtrend/crash -> buy dips
        }
        return RegimeRouter(RegimeClassifier(), mapping)
    raise ValueError(f"Unknown strategy '{name}'. Choose from: {', '.join(STRATEGY_NAMES)}")
