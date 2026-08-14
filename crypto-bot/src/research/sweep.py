"""Strategy search: parameter sweep with a train/test split.

Backfills real Kraken candles once (cached in a dedicated research DB), then backtests a grid of
strategy configs across pairs and timeframes. Every config is scored on an in-sample TRAIN slice
and an out-of-sample TEST slice. A config only earns trust if it clears the net-expectancy gate
on BOTH — a config that wins on train and loses on test is overfit, not an edge.

Run:  python -m src.research.sweep --bars 720
(Set REQUESTS_CA_BUNDLE if you are behind a proxy — see README.)
"""

from __future__ import annotations

import argparse
import itertools

from ..config.settings import Settings
from ..data.feed import DataFeed
from ..data.store import Store
from ..engine.backtest import Backtester
from ..strategy.bracket_breakout import BracketBreakout
from ..strategy.mean_reversion import MeanReversion

DEFAULT_PAIRS = ["BTC/USD", "ETH/USD", "SOL/USD", "ETH/BTC", "SOL/BTC"]
DEFAULT_TFS = ["1h", "4h", "1d"]


def _breakout_grid():
    for ch, tp, sl in itertools.product([20, 30, 55], [1.5, 2.0, 3.0], [1.0, 1.5]):
        yield (
            f"breakout ch{ch} tp{tp} sl{sl}",
            lambda ch=ch, tp=tp, sl=sl: BracketBreakout(
                channel_bars=ch, atr_bars=14, tp_atr_mult=tp, sl_atr_mult=sl, min_rr=1.0
            ),
        )


def _meanrev_grid():
    for ma, z, sl in itertools.product([20, 30], [1.5, 2.0, 2.5], [1.0, 1.5, 2.0]):
        yield (
            f"meanrev ma{ma} z{z} sl{sl}",
            lambda ma=ma, z=z, sl=sl: MeanReversion(
                ma_bars=ma, entry_z=z, sl_sd=sl, min_rr=1.0
            ),
        )


def _ts_range(store: Store, pairs: list[str], tf: str) -> tuple[int, int] | None:
    lo, hi = None, None
    for p in pairs:
        bars = store.get_candles(p, tf)
        if not bars:
            continue
        lo = bars[0].ts if lo is None else min(lo, bars[0].ts)
        hi = bars[-1].ts if hi is None else max(hi, bars[-1].ts)
    if lo is None:
        return None
    return lo, hi


def run_sweep(pairs: list[str], timeframes: list[str], bars: int, split: float = 0.7) -> list[dict]:
    s = Settings(_env_file=None)
    s.db_path = s.db_path.parent / "research.db"
    s.ensure_dirs()
    store = Store(s.db_path)

    from ..brokers.kraken import KrakenBroker

    feed = DataFeed(KrakenBroker(), store)

    results: list[dict] = []
    for tf in timeframes:
        print(f"\n=== timeframe {tf} ===")
        for p in pairs:
            try:
                n = feed.backfill(p, tf, bars)
                print(f"  backfilled {p:<10} {n}")
            except Exception as e:  # noqa: BLE001
                print(f"  {p:<10} FAILED {type(e).__name__}: {str(e)[:80]}")

        rng = _ts_range(store, pairs, tf)
        if not rng:
            print("  no data, skipping")
            continue
        lo, hi = rng
        split_ts = lo + int((hi - lo) * split)

        configs = list(_breakout_grid()) + list(_meanrev_grid())
        for label, build in configs:
            bt = Backtester(store, build(), s, pairs, tf)
            m_tr = bt.run(ts_start=lo, ts_end=split_ts)
            m_te = bt.run(ts_start=split_ts, ts_end=None)
            results.append(
                {
                    "tf": tf, "label": label,
                    "tr_net": m_tr.net_pnl, "tr_pf": m_tr.profit_factor,
                    "tr_n": m_tr.n_trades, "tr_gate": m_tr.passes_gate,
                    "te_net": m_te.net_pnl, "te_pf": m_te.profit_factor,
                    "te_n": m_te.n_trades, "te_gate": m_te.passes_gate,
                }
            )
    return results


def _fmt_pf(x: float) -> str:
    return "inf" if x == float("inf") else f"{x:.2f}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Strategy parameter sweep with train/test split")
    ap.add_argument("--pairs", nargs="*", default=DEFAULT_PAIRS)
    ap.add_argument("--tfs", nargs="*", default=DEFAULT_TFS)
    ap.add_argument("--bars", type=int, default=720)
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args(argv)

    results = run_sweep(args.pairs, args.tfs, args.bars)

    # Robust = passes the gate on BOTH train and test (not overfit).
    robust = [r for r in results if r["tr_gate"] and r["te_gate"] and r["te_n"] >= 5]
    robust.sort(key=lambda r: r["te_net"], reverse=True)

    print("\n" + "=" * 78)
    print(f"SWEEP DONE: {len(results)} configs tested. "
          f"{len(robust)} pass the gate on BOTH train & test (robust).")
    print("=" * 78)
    if not robust:
        print("No configuration held up out-of-sample. That's a real answer: no tradeable edge")
        print("in this grid on this data. Do NOT go live. Next: new signals/features, not more fitting.")
        # Show the least-bad test performers for context.
        ctx = sorted(results, key=lambda r: r["te_net"], reverse=True)[:8]
        print("\nBest TEST net (still not robust), for context:")
        for r in ctx:
            print(f"  {r['tf']:>3} {r['label']:<26} "
                  f"test net={r['te_net']:+8.2f} pf={_fmt_pf(r['te_pf']):>5} n={r['te_n']:>3} "
                  f"gate={'Y' if r['te_gate'] else 'N'}")
        return 0

    print(f"\n{'tf':>3} {'config':<26} {'train_net':>9} {'test_net':>9} "
          f"{'te_pf':>6} {'te_n':>5}")
    for r in robust[: args.top]:
        print(f"{r['tf']:>3} {r['label']:<26} {r['tr_net']:>9.2f} {r['te_net']:>9.2f} "
              f"{_fmt_pf(r['te_pf']):>6} {r['te_n']:>5}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
