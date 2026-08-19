"""External / alternative signal sources.

The lab strategy can blend in signals from *anything*, not just price — sentiment, a Twitter feed,
on-chain flows, funding rates, a "reverse Cramer" fade, whatever you dream up. Each such source
implements this one tiny contract and gets a weight in the blend.

The contract on purpose:
  value(symbol, ts) -> float in [-1, +1]     (+1 strongly bullish, -1 strongly bearish, 0 neutral)

Honesty rule for backtests: a live source (e.g. today's tweets) has no truthful *historical* value,
so it MUST return 0.0 when asked about a past `ts` it can't actually know. That way it stays neutral
in backtests and only speaks up live. Sources should be cheap and never raise — return 0.0 on any
error or missing data (the lab wraps calls defensively regardless).
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class SignalSource(ABC):
    name: str = "source"

    @abstractmethod
    def value(self, symbol: str, ts: int) -> float:
        """Bullish/bearish signal in [-1, 1] for `symbol` at epoch-ms `ts`. 0 = neutral/unknown."""

    @staticmethod
    def clamp(x: float) -> float:
        return max(-1.0, min(1.0, x))
