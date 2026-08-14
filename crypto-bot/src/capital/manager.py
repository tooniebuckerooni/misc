"""Two-bucket capital model with the profit-sweep rule.

- Working capital churns via trades. Realized P&L flows here.
- BTC vault is the scoreboard: when working equity reaches `trigger x base`, a fraction of the
  profit is swept into the vault and the base resets. The vault is never traded.

Units are the accounting/quote unit (e.g. USD-equiv in backtest). At live execution a sweep is
realised by actually buying BTC with the swept amount; that conversion lives in the live engine,
not here, so this class stays pure and unit-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..data.store import Store


@dataclass
class SweepResult:
    profit: float
    swept: float
    working_after: float
    new_base: float
    vault_after: float


class CapitalManager:
    def __init__(
        self,
        store: Store,
        mode: str,
        starting_working: float,
        trigger_multiple: float = 2.0,
        profit_fraction: float = 0.5,
    ):
        self.store = store
        self.mode = mode
        self.trigger_multiple = trigger_multiple
        self.profit_fraction = profit_fraction

        # Load persisted state (survives restarts) or initialise fresh.
        key = f"capital:{mode}"
        state = store.get_state(key)
        if state:
            self.working = float(state["working"])
            self.base = float(state["base"])
            self.vault = float(state["vault"])
        else:
            self.working = float(starting_working)
            self.base = float(starting_working)
            self.vault = 0.0
            self._persist()

    def _persist(self) -> None:
        self.store.set_state(
            f"capital:{self.mode}",
            {"working": self.working, "base": self.base, "vault": self.vault},
        )

    def realize(self, pnl: float, ts: int) -> SweepResult | None:
        """Apply a closed trade's net P&L to working capital, then maybe sweep to the vault."""
        self.working += pnl
        sweep = self._maybe_sweep(ts)
        self._persist()
        self.store.snapshot_equity(ts, self.mode, self.working, self.base, self.vault)
        return sweep

    def _maybe_sweep(self, ts: int) -> SweepResult | None:
        if self.base <= 0 or self.working < self.trigger_multiple * self.base:
            return None
        profit = self.working - self.base
        swept = self.profit_fraction * profit
        self.working -= swept
        self.vault += swept
        self.base = self.working  # reset the high-water baseline
        self.store.record_sweep(
            ts, self.mode, profit, swept, self.working, self.base, self.vault
        )
        return SweepResult(profit, swept, self.working, self.base, self.vault)

    @property
    def total_value(self) -> float:
        """Everything the bot controls: working chips + banked vault."""
        return self.working + self.vault
