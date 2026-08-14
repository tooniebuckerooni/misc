"""Kraken adapter (ccxt-backed).

Read methods work without keys. Trade methods require keys and are only exercised by the
live engine. Post-only limit orders are the default entry so we pay maker, not taker, fees.
"""

from __future__ import annotations

from ..core.types import OHLCVBar, Order, OrderStatus, OrderType, Side, Ticker
from .base import BrokerAdapter

_STATUS_MAP = {
    "open": OrderStatus.OPEN,
    "closed": OrderStatus.FILLED,
    "canceled": OrderStatus.CANCELED,
    "cancelled": OrderStatus.CANCELED,
    "expired": OrderStatus.CANCELED,
    "rejected": OrderStatus.REJECTED,
}


class KrakenBroker(BrokerAdapter):
    name = "kraken"

    def __init__(self, api_key: str = "", api_secret: str = "", enable_rate_limit: bool = True):
        try:
            import ccxt  # imported lazily so read-only tooling/tests don't require it
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("ccxt is required for the Kraken broker: pip install ccxt") from e

        self._has_keys = bool(api_key and api_secret)
        self._ex = ccxt.kraken(
            {
                "apiKey": api_key or None,
                "secret": api_secret or None,
                "enableRateLimit": enable_rate_limit,
            }
        )
        self._markets_loaded = False

    def _ensure_markets(self) -> None:
        if not self._markets_loaded:
            self._ex.load_markets()
            self._markets_loaded = True

    def _require_keys(self) -> None:
        if not self._has_keys:
            raise RuntimeError(
                "Kraken API keys are not configured. Set KRAKEN_API_KEY/KRAKEN_API_SECRET "
                "(trade-only, no withdrawal) in .env to place orders."
            )

    # ---- Market data -------------------------------------------------------
    def list_markets(self) -> list[str]:
        self._ensure_markets()
        return [
            s for s, m in self._ex.markets.items() if m.get("active", True) and m.get("spot", True)
        ]

    def get_ohlcv(
        self, symbol: str, timeframe: str, since: int | None = None, limit: int = 500
    ) -> list[OHLCVBar]:
        self._ensure_markets()
        raw = self._ex.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
        return [OHLCVBar(int(r[0]), r[1], r[2], r[3], r[4], r[5]) for r in raw]

    def get_ticker(self, symbol: str) -> Ticker:
        self._ensure_markets()
        t = self._ex.fetch_ticker(symbol)
        bid = t.get("bid") or t.get("last") or 0.0
        ask = t.get("ask") or t.get("last") or 0.0
        return Ticker(
            symbol=symbol,
            bid=float(bid),
            ask=float(ask),
            last=float(t.get("last") or bid or ask or 0.0),
            ts=int(t.get("timestamp") or 0),
        )

    # ---- Account / execution ----------------------------------------------
    def get_balance(self) -> dict[str, float]:
        self._require_keys()
        bal = self._ex.fetch_balance()
        free = bal.get("free", {}) or {}
        return {k: float(v) for k, v in free.items() if v}

    def place_order(self, order: Order) -> Order:
        self._require_keys()
        self._ensure_markets()
        params: dict = {}
        if order.reduce_only:
            params["reduceOnly"] = True

        if order.type == OrderType.MARKET:
            ccxt_type = "market"
        else:
            ccxt_type = "limit"
            if order.type == OrderType.LIMIT_POSTONLY:
                params["postOnly"] = True

        result = self._ex.create_order(
            order.symbol, ccxt_type, order.side.value, order.amount, order.price, params
        )
        order.id = str(result.get("id"))
        order.status = _STATUS_MAP.get(result.get("status", "open"), OrderStatus.OPEN)
        order.ts = int(result.get("timestamp") or 0)
        return order

    def cancel_order(self, order_id: str, symbol: str) -> None:
        self._require_keys()
        self._ex.cancel_order(order_id, symbol)

    def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        self._require_keys()
        raw = self._ex.fetch_open_orders(symbol)
        out: list[Order] = []
        for o in raw:
            out.append(
                Order(
                    symbol=o["symbol"],
                    side=Side(o["side"]),
                    amount=float(o["amount"]),
                    type=OrderType.LIMIT if o["type"] == "limit" else OrderType.MARKET,
                    price=o.get("price"),
                    id=str(o["id"]),
                    status=_STATUS_MAP.get(o.get("status", "open"), OrderStatus.OPEN),
                    ts=int(o.get("timestamp") or 0),
                )
            )
        return out

    def close(self) -> None:
        # ccxt sync client holds no persistent socket; nothing to release.
        pass
