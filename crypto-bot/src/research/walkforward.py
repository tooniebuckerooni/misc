"""Walk-forward robustness check.

A single train/test split is noisy. Here we cut the history into K contiguous out-of-sample
folds and ask a blunter question of each config: *does it make money in most time windows, or
just one lucky stretch?* A config is "robust" only if it is net-positive in a majority of folds
AND positive overall AND trades enough to mean anything.

Caveat baked in: searching many configs and keeping the winners is itself a form of overfitting
(multiple comparisons). Treat survivors as hypotheses to validate on fresh data, never as proof.

Run:  python -m src.research.walkforward --tfs 4h 1d --folds 4
"""

from __future__ import annotations

import argparse
import itertools
import math

from ..config.settings import Settings
from ..data.feed import DataFeed
from ..data.store import Store
from ..engine.backtest import Backtester
from ..strategy.mean_reversion import MeanReversion

DEFAULT_PAIRS = ["BTC/USD", "ETH/USD", "SOL/USD", "ETH/BTC", "SOL/BTC"]


def _grid():
    for ma, z, sl in itertools.product([20, 30, 50], [1.5, 2.0, 2.5], [1.5, 2.0, 3.0]):
        yield (
            f"meanrev ma{ma} z{z} sl{sl}",
            lambda ma=ma, z=z, sl=sl: MeanReversion(ma_bars=ma, entry_z=z, sl_sd=sl, min_rr=1.0),
        )


def _range(store, pairs, tf):
    lo = hi = None
    for p in pairs:
        bars = store.get_candles(p, tf)
        if not bars:
            continue
        lo = bars[0].ts if lo is None else min(lo, bars[0].ts)
        hi = bars[-1].ts if hi is None else max(hi, bars[-1].ts)
    return (lo, hi) if lo is not None else None


def run(pairs, timeframes, bars, folds):
    s = Settings(_env_file=None)
    s.db_path = s.db_path.parent / "research.db"
    s.ensure_dirs()
    store = Store(s.db_path)
    from ..brokers.kraken import KrakenBroker

    feed = DataFeed(KrakenBroker(), store)

    for tf in timeframes:
        for p in pairs:
            try:
                feed.backfill(p, tf, bars)
            except Exception:  # noqa: BLE001
                pass
        rng = _range(store, pairs, tf)
        if not rng:
            print(f"[{tf}] no data")
            continue
        lo, hi = rng
        edges = [lo + (hi - lo) * k // folds for k in range(folds + 1)]

        print(f"\n=== {tf}: {folds} out-of-sample folds ===")
        rows = []
        for label, build in _grid():
            fold_nets, fold_trades = [], 0
            for k in range(folds):
                m = Backtester(store, build(), s, pairs, tf).run(
                    ts_start=edges[k], ts_end=edges[k + 1]
                )
                fold_nets.append(m.net_pnl)
                fold_trades += m.n_trades
            pos = sum(1 for n in fold_nets if n > 0)
            total = sum(fold_nets)
            rows.append({
                "label": label, "pos": pos, "folds": folds, "total": total,
                "worst": min(fold_nets), "trades": fold_trades,
            })

        need = math.ceil(0.6 * folds)
        robust = [r for r in rows if r["pos"] >= need and r["total"] > 0 and r["trades"] >= 8]
        robust.sort(key=lambda r: (r["pos"], r["total"]), reverse=True)
        if robust:
            print(f"  ROBUST ({len(robust)}: positive in >= {need}/{folds} folds, total>0):")
            for r in robust:
                print(f"    {r['label']:<24} folds+ {r['pos']}/{r['folds']} "
                      f"total={r['total']:+7.2f} worst={r['worst']:+7.2f} n={r['trades']}")
        else:
            print(f"  none robust (needed positive in >= {need}/{folds} folds).")
            top = sorted(rows, key=lambda r: (r["pos"], r["total"]), reverse=True)[:5]
            for r in top:
                print(f"    ~ {r['label']:<24} folds+ {r['pos']}/{r['folds']} "
                      f"total={r['total']:+7.2f} worst={r['worst']:+7.2f} n={r['trades']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Walk-forward robustness check (mean-reversion)")
    ap.add_argument("--pairs", nargs="*", default=DEFAULT_PAIRS)
    ap.add_argument("--tfs", nargs="*", default=["4h", "1d"])
    ap.add_argument("--bars", type=int, default=720)
    ap.add_argument("--folds", type=int, default=4)
    args = ap.parse_args(argv)
    run(args.pairs, args.tfs, args.bars, args.folds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
