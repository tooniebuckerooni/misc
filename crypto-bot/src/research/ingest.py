"""Ingest deep historical candles into the research DB.

Run once to build the archive, then re-run sweep/walkforward with --no-backfill against it.

    python -m src.research.ingest --years 4 --tfs 1d 4h
    (set REQUESTS_CA_BUNDLE if behind a proxy)
"""

from __future__ import annotations

import argparse
import time

from ..config.settings import Settings
from ..data.history import HistoryFetcher
from ..data.store import Store

# Symbols to pull from the source exchange. USDT majors stand in for Kraken's USD pairs for
# research (price differs by pennies); BTC-quoted pairs match your "stack sats" execution.
DEFAULT_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "ETH/BTC", "SOL/BTC"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ingest deep history for research")
    ap.add_argument("--source", default="binanceus", help="ccxt exchange id for deep history")
    ap.add_argument("--symbols", nargs="*", default=DEFAULT_SYMBOLS)
    ap.add_argument("--tfs", nargs="*", default=["1d", "4h"])
    ap.add_argument("--years", type=float, default=4.0)
    args = ap.parse_args(argv)

    s = Settings(_env_file=None)
    s.db_path = s.db_path.parent / "research.db"
    s.ensure_dirs()
    store = Store(s.db_path)
    fetcher = HistoryFetcher(args.source)

    since = int(time.time() * 1000) - int(args.years * 365 * 86400 * 1000)
    print(f"Ingesting {args.years}y from {args.source} into {s.db_path}\n")
    for tf in args.tfs:
        print(f"=== {tf} ===")
        for sym in args.symbols:
            if not fetcher.has_symbol(sym):
                print(f"  {sym:<10} not listed on {args.source} — skipped")
                continue
            try:
                n = fetcher.backfill_deep(store, sym, tf, since)
                bars = store.get_candles(sym, tf)
                first = bars[0].ts if bars else 0
                import datetime
                d = datetime.datetime.utcfromtimestamp(first / 1000).date() if first else "-"
                print(f"  {sym:<10} {n:>6} candles cached, total {len(bars)}, earliest {d}")
            except Exception as e:  # noqa: BLE001
                print(f"  {sym:<10} FAILED {type(e).__name__}: {str(e)[:80]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
