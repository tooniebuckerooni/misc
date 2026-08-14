"""Event-driven backtester.

Replays cached OHLCV across the whole universe on a single shared clock, so capital and the
position cap are enforced exactly as they would be live. Uses the *same* Strategy, RiskManager,
and CapitalManager objects as paper/live — only the fill source differs — which is what makes
backtest results a fair predictor of live behaviour.

Honesty knobs: OHLCV has no bid/ask, so we assume a spread (`backtest_spread_frac`). Entries buy
at the ask side (close * (1 + spread/2)) and pay maker fees; take-profits are maker exits; stops
cross the book (taker) and give up half the spread. When a bar spans both TP and SL we assume the
worse outcome (stop first). No look-ahead: the strategy only ever sees bars up to the current one.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..capital.manager import CapitalManager
from ..config.settings import Settings
from ..core.types import OHLCVBar, Position, Side, TradeRecord
from ..data.store import Store
from ..risk.guardrails import RiskManager
from ..strategy.base import Strategy
from ..trackers.metrics import Metrics, compute_metrics

MODE = "backtest"


@dataclass
class _Open:
    pos: Position
    cost_basis: float  # notional + entry fee reserved from working cash
    entry_regime: str = ""  # market season at entry (for regime analysis)


class Backtester:
    def __init__(
        self,
        store: Store,
        strategy: Strategy,
        settings: Settings,
        universe: list[str],
        timeframe: str,
        regime_classifier=None,
    ):
        self.store = store
        self.strategy = strategy
        self.s = settings
        self.universe = universe
        self.timeframe = timeframe
        self.spread = settings.backtest_spread_frac
        self.regime_classifier = regime_classifier

    def run(
        self, min_bars: int = 60, ts_start: int | None = None, ts_end: int | None = None
    ) -> Metrics:
        s = self.s
        self.store.reset_mode(MODE)
        cm = CapitalManager(
            self.store, MODE, s.starting_working_capital,
            s.sweep_trigger_multiple, s.sweep_profit_fraction,
        )
        # Backtest ignores the live kill switch: use a path that won't exist.
        rm = RiskManager(
            self.store, MODE,
            kill_switch_file=s.db_path.parent / ".bt_no_kill",
            max_open_positions=s.max_open_positions,
            max_position_frac=s.max_position_frac,
            max_position_abs=s.max_position_abs,
            max_daily_loss_frac=s.max_daily_loss_frac,
            min_notional=s.min_notional,
            risk_per_trade_frac=s.risk_per_trade_frac,
            max_portfolio_risk_frac=s.max_portfolio_risk_frac,
        )

        bars_by_symbol: dict[str, list[OHLCVBar]] = {}
        for sym in self.universe:
            bars = self.store.get_candles(sym, self.timeframe)
            if ts_start is not None or ts_end is not None:
                lo = ts_start if ts_start is not None else float("-inf")
                hi = ts_end if ts_end is not None else float("inf")
                bars = [b for b in bars if lo <= b.ts < hi]
            if len(bars) >= min_bars:
                bars_by_symbol[sym] = bars
        if not bars_by_symbol:
            raise RuntimeError(
                "No cached candles for the universe. Run a backfill first "
                "(the CLI 'backtest' command backfills automatically)."
            )

        # Flatten to a single time-ordered event stream: (ts, symbol, bar_index).
        events: list[tuple[int, str, int]] = []
        for sym, bars in bars_by_symbol.items():
            for i, b in enumerate(bars):
                events.append((b.ts, sym, i))
        events.sort(key=lambda e: e[0])

        open_pos: dict[str, _Open] = {}

        def available_cash() -> float:
            return cm.working - sum(o.cost_basis for o in open_pos.values())

        for ts, sym, idx in events:
            bars = bars_by_symbol[sym]
            bar = bars[idx]

            # 1) Manage an existing position on this symbol.
            if sym in open_pos:
                self._maybe_exit(sym, bar, ts, open_pos, cm)
                continue

            # 2) Otherwise look for a new entry.
            if len(open_pos) >= s.max_open_positions:
                continue
            slice_bars = bars[: idx + 1]
            bracket = self.strategy.evaluate(sym, slice_bars, ticker=None)
            if bracket is None:
                continue

            open_risk = sum(
                (o.pos.entry_price - o.pos.sl_price) * o.pos.amount for o in open_pos.values()
            )
            decision = rm.evaluate_entry(
                ts, len(open_pos), cm.working, bracket.entry_price,
                sl_price=bracket.sl_price, open_risk=open_risk,
            )
            if not decision.allowed:
                continue

            eff_entry = bracket.entry_price * (1 + self.spread / 2)  # buy at the ask
            avail = available_cash()
            max_amt = avail / (eff_entry * (1 + s.maker_fee)) if eff_entry > 0 else 0.0
            amount = min(decision.amount, max_amt)
            notional = amount * eff_entry
            if amount <= 0 or notional < s.min_notional:
                continue

            entry_fee = notional * s.maker_fee
            regime_label = (
                self.regime_classifier.classify(slice_bars).label
                if self.regime_classifier is not None else ""
            )
            open_pos[sym] = _Open(
                pos=Position(
                    symbol=sym, side=Side.BUY, amount=amount, entry_price=eff_entry,
                    tp_price=bracket.tp_price, sl_price=bracket.sl_price,
                    opened_ts=ts, entry_fee=entry_fee,
                ),
                cost_basis=notional + entry_fee,
                entry_regime=regime_label,
            )

        # Close anything still open at its last available close (mark to market).
        for sym, o in list(open_pos.items()):
            last = bars_by_symbol[sym][-1]
            self._close(sym, o, last.close, last.ts, "end", maker=True, cm=cm, open_pos=open_pos)

        trades = self.store.get_trades(MODE)
        curve = self.store.get_equity_curve(MODE)
        return compute_metrics(trades, curve, cm.working, cm.vault)

    # ---- helpers -----------------------------------------------------------
    def _maybe_exit(
        self, sym: str, bar: OHLCVBar, ts: int, open_pos: dict[str, _Open], cm: CapitalManager
    ) -> None:
        o = open_pos[sym]
        p = o.pos
        # Conservative: if the bar touches the stop, assume the stop filled first.
        if bar.low <= p.sl_price:
            exit_price = p.sl_price * (1 - self.spread / 2)  # taker, gives up half spread
            self._close(sym, o, exit_price, ts, "stop", maker=False, cm=cm, open_pos=open_pos)
        elif bar.high >= p.tp_price:
            self._close(sym, o, p.tp_price, ts, "take_profit", maker=True, cm=cm, open_pos=open_pos)

    def _close(
        self, sym: str, o: _Open, exit_price: float, ts: int, reason: str,
        maker: bool, cm: CapitalManager, open_pos: dict[str, _Open],
    ) -> None:
        p = o.pos
        fee_rate = self.s.maker_fee if maker else self.s.taker_fee
        exit_fee = p.amount * exit_price * fee_rate
        proceeds = p.amount * exit_price - exit_fee
        gross = p.amount * (exit_price - p.entry_price)
        net = proceeds - o.cost_basis  # cost_basis already includes entry fee
        trade = TradeRecord(
            symbol=sym, side=p.side, amount=p.amount,
            entry_price=p.entry_price, exit_price=exit_price,
            opened_ts=p.opened_ts, closed_ts=ts,
            fees=p.entry_fee + exit_fee, gross_pnl=gross, net_pnl=net,
            exit_reason=reason,
            extra={"regime": o.entry_regime},
        )
        self.store.record_trade(MODE, trade)
        cm.realize(net, ts)
        del open_pos[sym]
