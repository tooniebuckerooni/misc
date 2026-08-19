"""Strategy progress scorecard — a %complete toward a *provable* winner.

Turns backtest results into a motivating checklist: each milestone you hit (enough trades, net
positive after fees, profit factor, drawdown control, …) adds to the bar. Tune the lab, re-run the
backtest, watch it climb. 100% here means "clears the bar we'd want before trusting it" — the final,
non-negotiable confidence still comes from out-of-sample walk-forward (a separate, harder gate).
"""

from __future__ import annotations

from ..trackers.metrics import Metrics

# (label, weight, predicate over Metrics). Weights sum to 100.
MILESTONES = [
    (">= 30 trades (enough to mean anything)", 10, lambda m: m.n_trades >= 30),
    ("net positive after fees", 20, lambda m: m.net_pnl > 0),
    ("gate: sum of gains > sum of losses", 20, lambda m: m.passes_gate),
    ("profit factor >= 1.3", 20, lambda m: m.profit_factor >= 1.3),
    ("max drawdown <= 25%", 15, lambda m: m.max_drawdown <= 0.25),
    ("win rate >= 35%", 10, lambda m: m.win_rate >= 0.35),
    ("positive expectancy per trade", 5, lambda m: m.expectancy > 0),
]


def evaluate_progress(m: Metrics) -> tuple[int, list[tuple[str, bool, int]]]:
    """Return (percent_complete, [(label, done, weight), ...])."""
    rows: list[tuple[str, bool, int]] = []
    pct = 0
    for label, weight, pred in MILESTONES:
        done = m.n_trades > 0 and bool(pred(m))
        if done:
            pct += weight
        rows.append((label, done, weight))
    return pct, rows
