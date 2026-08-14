"""Live engine — places REAL orders on Kraken.

⚠️ EXPERIMENTAL / UNTESTED against a real account in this repo. It reuses the paper engine's
decision logic verbatim and only overrides the three points that touch real money: entry,
exit, and the vault sweep. Treat it as capped, disposable, and prove-it-tiny-first:

  - Entries are post-only limit buys (maker). We optimistically record the position at the
    limit price; real fill reconciliation (partial fills, unfilled cancels) is the next
    hardening step before trusting this with more than pocket change.
  - Take-profit exits are post-only limit sells (maker); stops are market sells (taker).
  - On a profit sweep, the swept amount is spent buying BTC on `vault_symbol` (market),
    so the vault genuinely accumulates BTC.

All guardrails (position caps, daily-loss halt, kill switch) run exactly as in paper. Do not
run this until the strategy has cleared the gate in backtest AND paper, and then only with a
trade-only API key (no withdrawal permission) and tiny caps.
"""

from __future__ import annotations

from ..brokers.base import BrokerAdapter
from ..config.settings import Settings
from ..core.types import Order, OrderType, Side
from ..data.feed import DataFeed
from ..data.store import Store
from ..scanner.screener import Screener
from ..strategy.base import Strategy
from .paper import PaperEngine


class LiveEngine(PaperEngine):
    mode = "live"

    def __init__(
        self,
        broker: BrokerAdapter,
        feed: DataFeed,
        store: Store,
        strategy: Strategy,
        settings: Settings,
        screener: Screener | None = None,
    ):
        super().__init__(feed, store, strategy, settings, screener)
        self.broker = broker

    def _enter_position(
        self, symbol, amount, entry, tp, sl, entry_fee, notional, now
    ) -> None:
        # Post-only limit buy at the intended entry (maker). Recorded optimistically.
        self.broker.place_order(
            Order(symbol=symbol, side=Side.BUY, amount=amount,
                  type=OrderType.LIMIT_POSTONLY, price=entry)
        )
        super()._enter_position(symbol, amount, entry, tp, sl, entry_fee, notional, now)

    def _close(self, sym, exit_price, ts, reason, maker) -> None:
        amount = self.positions[sym].pos.amount
        if maker:
            order = Order(symbol=sym, side=Side.SELL, amount=amount,
                          type=OrderType.LIMIT_POSTONLY, price=exit_price, reduce_only=True)
        else:
            order = Order(symbol=sym, side=Side.SELL, amount=amount,
                          type=OrderType.MARKET, reduce_only=True)
        self.broker.place_order(order)
        super()._close(sym, exit_price, ts, reason, maker)

    def _on_sweep(self, swept: float) -> None:
        # Spend the swept amount buying BTC so the vault actually holds sats.
        try:
            t = self.broker.get_ticker(self.s.vault_symbol)
            btc_amount = swept / t.ask if t.ask > 0 else 0.0
            if btc_amount > 0:
                self.broker.place_order(
                    Order(symbol=self.s.vault_symbol, side=Side.BUY, amount=btc_amount,
                          type=OrderType.MARKET)
                )
        except Exception:
            # Never let a vault-conversion hiccup crash the trading loop.
            pass
