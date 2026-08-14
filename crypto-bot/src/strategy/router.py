"""Regime router — "define the season, then apply the strategy that fits it."

Itself a Strategy, so it drops straight into backtest/paper/live: on each bar it classifies the
season and delegates to the specialist mapped to that season (or stands aside if none fits).

Mapping is keyed by regime *label* (e.g. "bull", "bull+highvol"). Lookup tries the full label
first, then falls back to the base season, so a coarse {bull,range,bear} map still covers the
high-vol variants unless you override them explicitly.
"""

from __future__ import annotations

from ..core.types import Bracket, OHLCVBar, Ticker
from ..regime.classifier import RegimeClassifier
from .base import Strategy


class RegimeRouter(Strategy):
    name = "regime_router"

    def __init__(self, classifier: RegimeClassifier, mapping: dict[str, Strategy]):
        self.classifier = classifier
        self.mapping = mapping

    def evaluate(
        self, symbol: str, bars: list[OHLCVBar], ticker: Ticker | None = None
    ) -> Bracket | None:
        regime = self.classifier.classify(bars)
        specialist = self.mapping.get(regime.label) or self.mapping.get(regime.season.value)
        if specialist is None:
            return None  # no strategy assigned to this season -> sit out
        bracket = specialist.evaluate(symbol, bars, ticker)
        if bracket is not None:
            bracket.reason = f"[{regime.label}] {bracket.reason}"
        return bracket
