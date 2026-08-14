"""Shared domain types used across brokers, scanner, strategy, and engines.

Keeping these in one place means the same objects flow through backtest, paper, and live
without translation — which is what makes paper results trustworthy predictors of live.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"

    @property
    def opposite(self) -> "Side":
        return Side.SELL if self is Side.BUY else Side.BUY


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    LIMIT_POSTONLY = "limit_postonly"  # maker-only; exchange rejects if it would take


class OrderStatus(str, Enum):
    OPEN = "open"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELED = "canceled"
    REJECTED = "rejected"


@dataclass
class OHLCVBar:
    ts: int  # epoch milliseconds (bar open time)
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Ticker:
    symbol: str
    bid: float
    ask: float
    last: float
    ts: int

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread_frac(self) -> float:
        """Relative bid/ask spread — a core component of true trading cost."""
        m = self.mid
        return (self.ask - self.bid) / m if m > 0 else float("inf")


@dataclass
class Order:
    symbol: str
    side: Side
    amount: float  # in base units
    type: OrderType = OrderType.LIMIT_POSTONLY
    price: float | None = None
    reduce_only: bool = False
    id: str | None = None
    status: OrderStatus = OrderStatus.OPEN
    ts: int | None = None


@dataclass
class Fill:
    symbol: str
    side: Side
    amount: float
    price: float
    fee: float  # in quote units
    ts: int
    maker: bool
    order_id: str | None = None


@dataclass
class Bracket:
    """A fully pre-defined trade proposed by the strategy: enter, take-profit, stop-loss."""

    symbol: str
    side: Side
    entry_price: float
    tp_price: float
    sl_price: float
    score: float = 0.0            # scanner rank score (higher = better)
    est_cost_frac: float = 0.0    # estimated round-trip cost (fee + spread + slippage)
    reason: str = ""

    def rr_ratio(self) -> float:
        """Reward-to-risk based on the bracket geometry."""
        risk = abs(self.entry_price - self.sl_price)
        reward = abs(self.tp_price - self.entry_price)
        return reward / risk if risk > 0 else 0.0


@dataclass
class Position:
    symbol: str
    side: Side
    amount: float
    entry_price: float
    tp_price: float
    sl_price: float
    opened_ts: int
    entry_fee: float = 0.0


@dataclass
class TradeRecord:
    """A closed round-trip — the atom of the P&L ledger."""

    symbol: str
    side: Side
    amount: float
    entry_price: float
    exit_price: float
    opened_ts: int
    closed_ts: int
    fees: float          # total fees paid (entry + exit), quote units
    gross_pnl: float     # before fees
    net_pnl: float       # after fees — this is what the win/loss gate uses
    exit_reason: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def is_win(self) -> bool:
        return self.net_pnl > 0
