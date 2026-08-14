"""Broker abstraction.

Every execution venue (Kraken now, IBKR later, the paper simulator) implements this one
interface, so the scanner/strategy/engines never import a venue directly. Adding a venue is
adding a file, not a rewrite.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..core.types import OHLCVBar, Order, Ticker


class BrokerAdapter(ABC):
    """Minimal surface the rest of the bot depends on."""

    name: str = "base"

    # ---- Market data (read) ------------------------------------------------
    @abstractmethod
    def list_markets(self) -> list[str]:
        """All tradable symbols, e.g. ['ETH/USDT', 'SOL/BTC', ...]."""

    @abstractmethod
    def get_ohlcv(
        self, symbol: str, timeframe: str, since: int | None = None, limit: int = 500
    ) -> list[OHLCVBar]:
        """Historical candles, oldest first."""

    @abstractmethod
    def get_ticker(self, symbol: str) -> Ticker:
        """Current bid/ask/last — spread is a first-class trading cost."""

    # ---- Account / execution ----------------------------------------------
    @abstractmethod
    def get_balance(self) -> dict[str, float]:
        """Free balance per currency code."""

    @abstractmethod
    def place_order(self, order: Order) -> Order:
        """Submit an order; returns it populated with id/status."""

    @abstractmethod
    def cancel_order(self, order_id: str, symbol: str) -> None:
        ...

    @abstractmethod
    def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        ...

    # ---- Optional niceties (safe defaults) --------------------------------
    def can_withdraw(self) -> bool:
        """Best-effort check that the API key is trade-only. Overridden per venue."""
        return False

    def close(self) -> None:  # noqa: B027 - optional hook
        """Release any network resources."""
