"""Hard risk guardrails — the reason 'live but capped' is safe.

Enforces: position sizing (fraction of working equity + absolute cap), max concurrent
positions, a daily-loss auto-halt, and a kill switch (file on disk or persisted flag).
Every order in paper/live passes through here; a bug can annoy you but not drain the account.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..data.store import Store


@dataclass
class RiskDecision:
    allowed: bool
    reason: str = ""
    amount: float = 0.0  # base-asset units approved (0 when not allowed)


class RiskManager:
    def __init__(
        self,
        store: Store,
        mode: str,
        *,
        kill_switch_file: Path,
        max_open_positions: int = 3,
        max_position_frac: float = 0.34,
        max_position_abs: float = 100.0,
        max_daily_loss_frac: float = 0.10,
        min_notional: float = 5.0,
    ):
        self.store = store
        self.mode = mode
        self.kill_switch_file = Path(kill_switch_file)
        self.max_open_positions = max_open_positions
        self.max_position_frac = max_position_frac
        self.max_position_abs = max_position_abs
        self.max_daily_loss_frac = max_daily_loss_frac
        self.min_notional = min_notional

    # ---- Kill switch -------------------------------------------------------
    def kill_switch_active(self) -> bool:
        return self.kill_switch_file.exists() or bool(self.store.get_state("kill_switch", False))

    def set_kill(self, on: bool) -> None:
        self.store.set_state("kill_switch", on)
        if on:
            self.kill_switch_file.touch()
        elif self.kill_switch_file.exists():
            self.kill_switch_file.unlink()

    # ---- Daily-loss auto-halt ---------------------------------------------
    @staticmethod
    def _day(ts: int) -> str:
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")

    def daily_loss_halted(self, ts: int, working_equity: float) -> bool:
        """Track the day's opening equity; halt once drawdown exceeds the cap."""
        day = self._day(ts)
        key = f"day:{self.mode}"
        state = self.store.get_state(key)
        if not state or state.get("day") != day:
            state = {"day": day, "start_equity": working_equity}
            self.store.set_state(key, state)
            return False
        start = float(state["start_equity"])
        if start <= 0:
            return False
        drawdown = (start - working_equity) / start
        return drawdown >= self.max_daily_loss_frac

    # ---- Position sizing / gate -------------------------------------------
    def evaluate_entry(
        self, ts: int, open_positions: int, working_equity: float, entry_price: float
    ) -> RiskDecision:
        if self.kill_switch_active():
            return RiskDecision(False, "kill switch active")
        if self.daily_loss_halted(ts, working_equity):
            return RiskDecision(False, "daily loss limit reached — halted for the day")
        if open_positions >= self.max_open_positions:
            return RiskDecision(False, f"max open positions ({self.max_open_positions}) reached")
        if entry_price <= 0 or working_equity <= 0:
            return RiskDecision(False, "no capital / invalid price")

        notional = min(self.max_position_frac * working_equity, self.max_position_abs)
        if notional < self.min_notional:
            return RiskDecision(False, f"notional {notional:.2f} below minimum {self.min_notional}")

        amount = notional / entry_price
        return RiskDecision(True, "ok", amount)
