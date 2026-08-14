"""Strategy interface.

A strategy is a pure decision function: given a symbol's recent bars (and optionally a live
ticker), propose a fully-specified `Bracket` (entry / take-profit / stop-loss) or return None.
No orders, no I/O — the engines translate a Bracket into real/simulated orders. This is what
lets one strategy object run unchanged in backtest, paper, and live.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..core.types import Bracket, OHLCVBar, Ticker


class Strategy(ABC):
    name: str = "base"

    @abstractmethod
    def evaluate(
        self, symbol: str, bars: list[OHLCVBar], ticker: Ticker | None = None
    ) -> Bracket | None:
        """Return a proposed bracket for `symbol`, or None for no setup.

        Long-only (spot): a Bracket here always means BUY the base asset now, with a
        pre-set TP and SL. `bars` are oldest-first and end on the most recently closed bar.
        """
