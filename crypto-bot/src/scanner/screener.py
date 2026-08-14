"""The scanner: scours many pairs, asks the strategy for a bracket on each, prices the true
cost of trading it (fee + spread + slippage), rejects the expensive ones, and ranks the rest.

Key principle from the plan: *obscure != cheap*. A thin book has a wide spread, so even with
identical fees it costs more to round-trip. We therefore rank by breakout strength but filter
hard on total net execution cost, and require the expected reward to actually clear that cost.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.types import Bracket, Ticker
from ..data.feed import DataFeed
from ..strategy.base import Strategy

# ccxt unified symbols (note: Kraken's native XBT is 'BTC' in ccxt). A pragmatic liquid
# starting set spanning USD / stablecoin / BTC quotes. Overridable via settings.pair_universe.
# Broad basket of liquid Kraken USD majors — breadth matters for the mean-reversion lead
# (validated on 20 pairs). Working capital churns these; profits sweep to the BTC vault.
DEFAULT_UNIVERSE = [
    "BTC/USD", "ETH/USD", "SOL/USD", "ADA/USD", "XRP/USD", "DOGE/USD", "LTC/USD",
    "LINK/USD", "DOT/USD", "AVAX/USD", "ATOM/USD", "UNI/USD", "BCH/USD", "ETC/USD",
    "XLM/USD", "ALGO/USD", "FIL/USD", "AAVE/USD", "NEAR/USD",
]


def estimate_round_trip_cost(
    spread_frac: float,
    maker_fee: float,
    taker_fee: float,
    slippage_frac: float = 0.0005,
) -> float:
    """Conservative round-trip cost as a fraction of notional.

    Entry is a post-only maker; the stop-loss exit typically crosses the book (taker) and eats
    the spread. So: maker (entry) + taker (worst-case exit) + one spread + a slippage buffer.
    """
    if spread_frac == float("inf"):
        return float("inf")
    return maker_fee + taker_fee + spread_frac + slippage_frac


@dataclass
class Candidate:
    bracket: Bracket
    ticker: Ticker


class Screener:
    def __init__(
        self,
        feed: DataFeed,
        strategy: Strategy,
        *,
        universe: list[str] | None = None,
        timeframe: str = "15m",
        lookback: int = 200,
        maker_fee: float = 0.0016,
        taker_fee: float = 0.0026,
        max_round_trip_cost: float = 0.006,
        top_n: int = 5,
    ):
        self.feed = feed
        self.strategy = strategy
        self.universe = universe or DEFAULT_UNIVERSE
        self.timeframe = timeframe
        self.lookback = lookback
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.max_round_trip_cost = max_round_trip_cost
        self.top_n = top_n

    def scan(self, exclude: set[str] | None = None) -> list[Candidate]:
        """Return up to `top_n` ranked candidates, cheapest-strong-setups first."""
        exclude = exclude or set()
        found: list[Candidate] = []

        for symbol in self.universe:
            if symbol in exclude:
                continue
            try:
                bars = self.feed.get_bars(symbol, self.timeframe, self.lookback, refresh=True)
                ticker = self.feed.get_ticker(symbol)
            except Exception:
                # A single dead/illiquid pair must never take the whole scan down.
                continue

            bracket = self.strategy.evaluate(symbol, bars, ticker)
            if bracket is None:
                continue

            cost = estimate_round_trip_cost(ticker.spread_frac, self.maker_fee, self.taker_fee)
            bracket.est_cost_frac = round(cost, 6)

            if cost > self.max_round_trip_cost:
                continue  # too expensive to churn — obscure != cheap

            reward_frac = (bracket.tp_price - bracket.entry_price) / bracket.entry_price
            if reward_frac <= cost:
                continue  # the setup can't even clear its own trading cost

            found.append(Candidate(bracket=bracket, ticker=ticker))

        # Strongest breakout first; break ties by cheaper execution.
        found.sort(key=lambda c: (c.bracket.score, -c.bracket.est_cost_frac), reverse=True)
        return found[: self.top_n]
