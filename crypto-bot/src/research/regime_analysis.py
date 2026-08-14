"""Regime analysis: which strategy earns in which market season?

Runs each strategy over deep history with the regime classifier attached, then buckets every
closed trade by the season it was ENTERED in and reports net P&L / win-rate / expectancy per
season. This is what tells us how to route: e.g. "mean-reversion earns in RANGE, bleeds in BEAR."

Run:  python -m src.research.regime_analysis --tfs 1d 4h
"""

from __future__ import annotations

import argparse
from collections import defaultdict

from ..config.settings import Settings
from ..data.store import Store
from ..engine.backtest import Backtester
from ..regime.classifier import RegimeClassifier
from ..strategy.bracket_breakout import BracketBreakout
from ..strategy.kalman_supertrend import KalmanSuperTrend
from ..strategy.mean_reversion import MeanReversion

DEFAULT_PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "ETH/BTC", "SOL/BTC"]

STRATEGIES = {
    "breakout": lambda: BracketBreakout(channel_bars=20, tp_atr_mult=2.0, sl_atr_mult=1.0),
    "meanrev": lambda: MeanReversion(ma_bars=20, entry_z=2.0, sl_sd=3.0),
    "kalman": lambda: KalmanSuperTrend(st_mult=3.0, adx_threshold=25, tp_atr_mult=3.0,
                                       sl_atr_mult=1.0, require_flip=True),
}


def analyze(pairs, timeframes) -> None:
    s = Settings(_env_file=None)
    s.db_path = s.db_path.parent / "research.db"
    s.ensure_dirs()
    store = Store(s.db_path)
    clf = RegimeClassifier()

    for tf in timeframes:
        print(f"\n================= timeframe {tf} =================")
        for name, build in STRATEGIES.items():
            Backtester(store, build(), s, pairs, tf, regime_classifier=clf).run()
            trades = store.get_trades("backtest")
            by: dict[str, list[float]] = defaultdict(list)
            for t in trades:
                by[t.extra.get("regime", "?")].append(t.net_pnl)

            print(f"\n  {name}:")
            print(f"    {'season':<14}{'trades':>7}{'net':>10}{'win%':>7}{'exp/trade':>11}")
            # Sort seasons by net contribution so the money-makers show first.
            for season, nets in sorted(by.items(), key=lambda kv: sum(kv[1]), reverse=True):
                n = len(nets)
                net = sum(nets)
                wins = sum(1 for x in nets if x > 0)
                exp = net / n if n else 0.0
                print(f"    {season:<14}{n:>7}{net:>10.2f}{(wins/n*100 if n else 0):>6.0f}%{exp:>11.3f}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Per-regime strategy performance on deep data")
    ap.add_argument("--pairs", nargs="*", default=DEFAULT_PAIRS)
    ap.add_argument("--tfs", nargs="*", default=["1d", "4h"])
    args = ap.parse_args(argv)
    analyze(args.pairs, args.tfs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
