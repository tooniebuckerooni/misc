"""Paper trading engine — the loop that proves the edge before real money.

Runs the exact scanner / strategy / risk / capital objects the live engine uses, but fills
orders by simulation against *live* Kraken tickers (no orders are sent). Economics mirror the
backtester: buy at the ask paying the maker fee (post-only entry), take-profit is a maker exit,
stops cross the book as taker. Open positions and capital state persist in SQLite, so the loop
survives restarts.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from ..capital.manager import CapitalManager
from ..config.settings import Settings
from ..core.types import Position, Side, TradeRecord
from ..data.feed import DataFeed, timeframe_ms
from ..data.store import Store
from ..risk.guardrails import RiskManager
from ..scanner.screener import Screener
from ..strategy.base import Strategy


@dataclass
class _Open:
    pos: Position
    cost_basis: float

    def to_dict(self) -> dict:
        p = self.pos
        return {
            "symbol": p.symbol, "side": p.side.value, "amount": p.amount,
            "entry_price": p.entry_price, "tp_price": p.tp_price, "sl_price": p.sl_price,
            "opened_ts": p.opened_ts, "entry_fee": p.entry_fee, "cost_basis": self.cost_basis,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "_Open":
        return cls(
            pos=Position(
                symbol=d["symbol"], side=Side(d["side"]), amount=d["amount"],
                entry_price=d["entry_price"], tp_price=d["tp_price"], sl_price=d["sl_price"],
                opened_ts=d["opened_ts"], entry_fee=d["entry_fee"],
            ),
            cost_basis=d["cost_basis"],
        )


class PaperEngine:
    mode = "paper"

    def __init__(
        self,
        feed: DataFeed,
        store: Store,
        strategy: Strategy,
        settings: Settings,
        screener: Screener | None = None,
    ):
        self.feed = feed
        self.store = store
        self.s = settings
        self.cm = CapitalManager(
            store, self.mode, settings.starting_working_capital,
            settings.sweep_trigger_multiple, settings.sweep_profit_fraction,
        )
        self.rm = RiskManager(
            store, self.mode,
            kill_switch_file=settings.kill_switch_file,
            max_open_positions=settings.max_open_positions,
            max_position_frac=settings.max_position_frac,
            max_position_abs=settings.max_position_abs,
            max_daily_loss_frac=settings.max_daily_loss_frac,
            min_notional=settings.min_notional,
        )
        universe = settings.pair_universe or None
        self.screener = screener or Screener(
            feed, strategy,
            universe=universe, timeframe=settings.timeframe, lookback=settings.scan_lookback_bars,
            maker_fee=settings.maker_fee, taker_fee=settings.taker_fee,
            max_round_trip_cost=settings.max_round_trip_cost, top_n=settings.top_n_candidates,
        )
        self.positions: dict[str, _Open] = {
            d["symbol"]: _Open.from_dict(d)
            for d in (store.get_state(f"positions:{self.mode}", []) or [])
        }

    # ---- persistence -------------------------------------------------------
    def _persist_positions(self) -> None:
        self.store.set_state(
            f"positions:{self.mode}", [o.to_dict() for o in self.positions.values()]
        )

    def _available_cash(self) -> float:
        return self.cm.working - sum(o.cost_basis for o in self.positions.values())

    # ---- one iteration -----------------------------------------------------
    def run_once(self, now_ts: int | None = None) -> dict:
        now = now_ts or int(time.time() * 1000)
        actions: list[str] = []

        if self.rm.kill_switch_active():
            self.flatten_all(now, "kill_switch")
            return {"ts": now, "halted": "kill_switch", "actions": ["flattened all"]}

        # 1) Manage exits on open positions.
        for sym in list(self.positions.keys()):
            t = self.feed.get_ticker(sym)
            p = self.positions[sym].pos
            if t.last >= p.tp_price:
                self._close(sym, p.tp_price, now, "take_profit", maker=True)
                actions.append(f"TP {sym} @ {p.tp_price:.6g}")
            elif t.last <= p.sl_price:
                self._close(sym, t.bid or p.sl_price, now, "stop", maker=False)
                actions.append(f"STOP {sym} @ {p.sl_price:.6g}")

        self.store.snapshot_equity(now, self.mode, self.cm.working, self.cm.base, self.cm.vault)

        # 2) Halt entries if the daily loss cap tripped, but keep managing exits above.
        if self.rm.daily_loss_halted(now, self.cm.working):
            self._persist_positions()
            return {"ts": now, "halted": "daily_loss", "actions": actions}

        # 3) Look for new entries.
        max_age_ms = timeframe_ms(self.s.timeframe) * self.s.max_staleness_bars
        for cand in self.screener.scan(exclude=set(self.positions.keys())):
            if len(self.positions) >= self.s.max_open_positions:
                break
            b = cand.bracket
            # Fail closed on a frozen/lagging price feed.
            if self.rm.is_stale(now, cand.ticker.ts, max_age_ms):
                actions.append(f"SKIP {b.symbol} (stale feed)")
                continue
            decision = self.rm.evaluate_entry(now, len(self.positions), self.cm.working, cand.ticker.ask)
            if not decision.allowed:
                continue
            entry = cand.ticker.ask
            avail = self._available_cash()
            max_amt = avail / (entry * (1 + self.s.maker_fee)) if entry > 0 else 0.0
            amount = min(decision.amount, max_amt)
            notional = amount * entry
            if amount <= 0 or notional < self.s.min_notional:
                continue
            entry_fee = notional * self.s.maker_fee
            self._enter_position(
                b.symbol, amount, entry, b.tp_price, b.sl_price, entry_fee, notional, now
            )
            actions.append(f"ENTER {b.symbol} {amount:.6g}@{entry:.6g} tp={b.tp_price:.6g} sl={b.sl_price:.6g}")

        self._persist_positions()
        return {
            "ts": now, "working": self.cm.working, "vault": self.cm.vault,
            "open": len(self.positions), "actions": actions,
        }

    # ---- entry (overridden by the live engine to place a real order) ------
    def _enter_position(
        self, symbol: str, amount: float, entry: float, tp: float, sl: float,
        entry_fee: float, notional: float, now: int,
    ) -> None:
        self.positions[symbol] = _Open(
            pos=Position(
                symbol=symbol, side=Side.BUY, amount=amount, entry_price=entry,
                tp_price=tp, sl_price=sl, opened_ts=now, entry_fee=entry_fee,
            ),
            cost_basis=notional + entry_fee,
        )

    def _on_sweep(self, swept: float) -> None:
        """Hook: paper does nothing; the live engine buys BTC with the swept amount."""

    # ---- exits -------------------------------------------------------------
    def flatten_all(self, now: int, reason: str) -> None:
        for sym in list(self.positions.keys()):
            t = self.feed.get_ticker(sym)
            self._close(sym, t.bid or self.positions[sym].pos.entry_price, now, reason, maker=False)
        self._persist_positions()

    def _close(self, sym: str, exit_price: float, ts: int, reason: str, maker: bool) -> None:
        o = self.positions[sym]
        p = o.pos
        fee_rate = self.s.maker_fee if maker else self.s.taker_fee
        exit_fee = p.amount * exit_price * fee_rate
        proceeds = p.amount * exit_price - exit_fee
        gross = p.amount * (exit_price - p.entry_price)
        net = proceeds - o.cost_basis
        self.store.record_trade(
            self.mode,
            TradeRecord(
                symbol=sym, side=p.side, amount=p.amount, entry_price=p.entry_price,
                exit_price=exit_price, opened_ts=p.opened_ts, closed_ts=ts,
                fees=p.entry_fee + exit_fee, gross_pnl=gross, net_pnl=net, exit_reason=reason,
            ),
        )
        sweep = self.cm.realize(net, ts)
        del self.positions[sym]
        if sweep is not None:
            self._on_sweep(sweep.swept)

    # ---- run loop ----------------------------------------------------------
    def run_forever(self, poll_seconds: int = 60, on_tick=None) -> None:  # pragma: no cover
        while True:
            summary = self.run_once()
            if on_tick:
                on_tick(summary)
            time.sleep(poll_seconds)
