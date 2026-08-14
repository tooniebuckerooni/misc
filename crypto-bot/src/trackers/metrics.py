"""Performance metrics — the honest scoreboard.

The headline gate is **net expectancy**: sum of gains must exceed sum of losses AFTER fees.
Win *rate* is reported too, but it is explicitly not the gate (a few big losses can sink many
small wins). Drawdown is measured on total value (working + vault).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.types import TradeRecord


@dataclass
class Metrics:
    n_trades: int
    wins: int
    losses: int
    win_rate: float
    gross_profit: float   # sum of winning net P&L
    gross_loss: float     # sum of |losing net P&L|
    net_pnl: float
    profit_factor: float  # gross_profit / gross_loss
    avg_win: float
    avg_loss: float
    expectancy: float     # net_pnl / n_trades
    fees_total: float
    max_drawdown: float   # fraction, on total value
    final_working: float
    final_vault: float
    total_value: float

    @property
    def passes_gate(self) -> bool:
        """The plan's go-live bar: net gains exceed net losses after fees."""
        return self.n_trades > 0 and self.gross_profit > self.gross_loss


def _max_drawdown(values: list[float]) -> float:
    peak = float("-inf")
    mdd = 0.0
    for v in values:
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, (peak - v) / peak)
    return mdd


def compute_metrics(
    trades: list[TradeRecord],
    equity_curve: list[dict] | None = None,
    final_working: float = 0.0,
    final_vault: float = 0.0,
) -> Metrics:
    n = len(trades)
    wins = [t for t in trades if t.is_win]
    losses = [t for t in trades if not t.is_win]
    gross_profit = sum(t.net_pnl for t in wins)
    gross_loss = sum(-t.net_pnl for t in losses)
    net_pnl = sum(t.net_pnl for t in trades)
    fees_total = sum(t.fees for t in trades)

    values = [row["working_equity"] + row["vault"] for row in (equity_curve or [])]
    mdd = _max_drawdown(values) if values else 0.0

    return Metrics(
        n_trades=n,
        wins=len(wins),
        losses=len(losses),
        win_rate=(len(wins) / n) if n else 0.0,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_pnl=net_pnl,
        profit_factor=(gross_profit / gross_loss) if gross_loss > 0 else float("inf"),
        avg_win=(gross_profit / len(wins)) if wins else 0.0,
        avg_loss=(gross_loss / len(losses)) if losses else 0.0,
        expectancy=(net_pnl / n) if n else 0.0,
        fees_total=fees_total,
        max_drawdown=mdd,
        final_working=final_working,
        final_vault=final_vault,
        total_value=final_working + final_vault,
    )


def format_metrics(m: Metrics) -> str:
    pf = "inf" if m.profit_factor == float("inf") else f"{m.profit_factor:.2f}"
    gate = "PASS ✅" if m.passes_gate else "FAIL ❌"
    return "\n".join(
        [
            f"Trades           : {m.n_trades}  (W {m.wins} / L {m.losses}, win-rate {m.win_rate:.1%})",
            f"Gross profit     : {m.gross_profit:,.2f}",
            f"Gross loss       : {m.gross_loss:,.2f}",
            f"Net P&L          : {m.net_pnl:,.2f}   (after {m.fees_total:,.2f} fees)",
            f"Profit factor    : {pf}",
            f"Avg win / loss   : {m.avg_win:,.2f} / {m.avg_loss:,.2f}",
            f"Expectancy/trade : {m.expectancy:,.4f}",
            f"Max drawdown     : {m.max_drawdown:.1%}",
            f"Working / Vault  : {m.final_working:,.2f} / {m.final_vault:,.2f}  (total {m.total_value:,.2f})",
            f"GATE (gains>losses after fees): {gate}",
        ]
    )
