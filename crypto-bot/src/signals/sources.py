"""Concrete signal sources + templates for wiring your own 'unexpected' data.

Ships with trivial sources (for testing/manual bias) and a worked *template* for a live external
feed — the "reverse Cramer" example — showing exactly where you'd plug an API call. The template
stays neutral (returns 0) until you provide a fetcher, so it never fabricates history in a backtest.
"""

from __future__ import annotations

from typing import Callable

from .base import SignalSource


class ConstantSource(SignalSource):
    """Always returns a fixed value. Useful for tests or a manual standing bias."""

    def __init__(self, value: float, name: str = "constant"):
        self._v = SignalSource.clamp(value)
        self.name = name

    def value(self, symbol: str, ts: int) -> float:
        return self._v


class CallableSource(SignalSource):
    """Wrap any function (symbol, ts) -> float in [-1,1] as a source. The escape hatch for anything."""

    def __init__(self, fn: Callable[[str, int], float], name: str = "callable"):
        self._fn = fn
        self.name = name

    def value(self, symbol: str, ts: int) -> float:
        try:
            return SignalSource.clamp(float(self._fn(symbol, ts)))
        except Exception:
            return 0.0


class ReverseCramerSource(SignalSource):
    """Template: fade a loud pundit. Bullish (+1) when he's bearish on the coin, and vice-versa.

    To make it real, pass `fetch_stance(symbol) -> float in [-1,1]` that reads *today's* stance from
    wherever you get it (a scraper, an API, a manual note). We negate it (that's the 'reverse'). With
    no fetcher it returns 0.0 — neutral — so backtests aren't polluted by data that didn't exist then.

    Example:
        src = ReverseCramerSource(fetch_stance=my_twitter_stance_fn)
        # my_twitter_stance_fn('BTC/USD', ts) -> +1 if he's shilling BTC today, -1 if trashing it
    """

    name = "reverse_cramer"

    def __init__(self, fetch_stance: Callable[[str], float] | None = None):
        self._fetch = fetch_stance

    def value(self, symbol: str, ts: int) -> float:
        if self._fetch is None:
            return 0.0  # neutral until wired to a live feed
        try:
            base = symbol.split("/")[0]
            return SignalSource.clamp(-float(self._fetch(base)))  # reverse his stance
        except Exception:
            return 0.0
