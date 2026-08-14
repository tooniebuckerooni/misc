"""Regime router — "define the season, then apply the strategy that fits it."

Itself a Strategy, so it drops straight into backtest/paper/live: on each bar it classifies the
season and delegates to the specialist mapped to that season (or stands aside if none fits).
This is how we combine each strategy's winning season and skip its losing ones.
"""

from __future__ import annotations

from ..core.types import Bracket, OHLCVBar, Ticker
from ..regime.classifier import RegimeClassifier, Season
from .base import Strategy


class RegimeRouter(Strategy):
    name = "regime_router"

    def __init__(self, classifier: RegimeClassifier, mapping: dict[Season, Strategy]):
        self.classifier = classifier
        self.mapping = mapping

    def evaluate(
        self, symbol: str, bars: list[OHLCVBar], ticker: Ticker | None = None
    ) -> Bracket | None:
        regime = self.classifier.classify(bars)
        specialist = self.mapping.get(regime.season)
        if specialist is None:
            return None  # no strategy assigned to this season -> sit out
        bracket = specialist.evaluate(symbol, bars, ticker)
        if bracket is not None:
            bracket.reason = f"[{regime.label}] {bracket.reason}"
        return bracket
