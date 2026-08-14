"""Honest router validation: learn the season->strategy map from PAST data only.

The earlier router used a mapping chosen from the whole period (in-sample). Here, for each
out-of-sample fold we:
  1. Look only at the data BEFORE the fold (expanding past window).
  2. Bucket each candidate strategy's trades by season and pick, per season, the strategy with
     the best positive expectancy on that past data (>= min trades).
  3. Build a router from that map and run it on the untouched fold.

If the auto-router is positive across folds, regime routing has genuine out-of-sample value. If
it collapses, the earlier result was in-sample luck. Either way it's the truth.

Run:  python -m src.research.router_validation --tf 1d --folds 5
"""

from __future__ import annotations

import argparse
from collections import defaultdict

from ..config.settings import Settings
from ..data.store import Store
from ..engine.backtest import Backtester
from ..regime.classifier import RegimeClassifier
from ..strategy.registry import build_strategy
from ..strategy.router import RegimeRouter

DEFAULT_PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "ETH/BTC", "SOL/BTC"]
CANDIDATES = ["breakout", "meanrev", "kalman"]


def _range(store, pairs, tf):
    lo = hi = None
    for p in pairs:
        b = store.get_candles(p, tf)
        if not b:
            continue
        lo = b[0].ts if lo is None else min(lo, b[0].ts)
        hi = b[-1].ts if hi is None else max(hi, b[-1].ts)
    return lo, hi


def derive_mapping(store, s, pairs, tf, clf, ts_start, ts_end, min_trades=5):
    """Best positive-expectancy strategy per base season, learned on [ts_start, ts_end)."""
    per_season: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for name in CANDIDATES:
        Backtester(store, build_strategy(name, s), s, pairs, tf, regime_classifier=clf).run(
            ts_start=ts_start, ts_end=ts_end
        )
        for t in store.get_trades("backtest"):
            base = t.extra.get("regime", "?").split("+")[0]
            per_season[base][name].append(t.net_pnl)

    mapping: dict[str, "object"] = {}
    chosen: dict[str, str] = {}
    for season, per in per_season.items():
        best_name, best_exp = None, 0.0
        for name, nets in per.items():
            if len(nets) >= min_trades:
                exp = sum(nets) / len(nets)
                if exp > best_exp:
                    best_exp, best_name = exp, name
        if best_name:
            mapping[season] = build_strategy(best_name, s)
            chosen[season] = f"{best_name}({best_exp:+.2f})"
    return mapping, chosen


def main(argv=None):
    ap = argparse.ArgumentParser(description="Walk-forward router with past-only mapping")
    ap.add_argument("--pairs", nargs="*", default=DEFAULT_PAIRS)
    ap.add_argument("--tf", default="1d")
    ap.add_argument("--folds", type=int, default=5)
    args = ap.parse_args(argv)

    s = Settings(_env_file=None)
    s.db_path = s.db_path.parent / "research.db"
    s.ensure_dirs()
    s.starting_working_capital = 200.0
    store = Store(s.db_path)
    clf = RegimeClassifier()

    lo, hi = _range(store, args.pairs, args.tf)
    folds = args.folds
    edges = [lo + (hi - lo) * k // folds for k in range(folds + 1)]

    print(f"Honest walk-forward on {args.tf}: map learned from PAST only, tested on each fold.\n")
    auto_total = 0.0
    auto_pos = 0
    for k in range(1, folds):  # fold 0 has no past to learn from
        train_lo, split = lo, edges[k]
        test_lo, test_hi = edges[k], edges[k + 1]
        mapping, chosen = derive_mapping(store, s, args.pairs, args.tf, clf, train_lo, split)
        router = RegimeRouter(clf, mapping)
        m = Backtester(store, router, s, args.pairs, args.tf).run(ts_start=test_lo, ts_end=test_hi)
        auto_total += m.net_pnl
        auto_pos += 1 if m.net_pnl > 0 else 0
        print(f"fold {k}: learned map {chosen}")
        print(f"        OOS net={m.net_pnl:+.2f}  trades={m.n_trades}  gate={'Y' if m.passes_gate else 'N'}\n")

    print(f"AUTO-ROUTER out-of-sample: total={auto_total:+.2f} across folds, "
          f"positive in {auto_pos}/{folds - 1}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
