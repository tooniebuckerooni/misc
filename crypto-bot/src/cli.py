"""Command-line entrypoint.

    python -m src.cli backtest        prove the edge on history (backfills first)
    python -m src.cli paper           paper-trade on live prices (no real orders)
    python -m src.cli live --yes      REAL orders (capped) — only after paper proof
    python -m src.cli dashboard       launch the local Streamlit monitor
    python -m src.cli status          print capital, open positions, recent trades, metrics
    python -m src.cli kill / unkill   trip / clear the kill switch
"""

from __future__ import annotations

import argparse
import sys

from .config.settings import Mode, get_settings
from .data.feed import DataFeed
from .data.store import Store
from .scanner.screener import DEFAULT_UNIVERSE
from .strategy.registry import build_strategy
from .trackers.metrics import compute_metrics, format_metrics


def _apply_overrides(s, args):
    """Let CLI flags override settings so each strategy can have its own pipeline."""
    if getattr(args, "timeframe", None):
        s.timeframe = args.timeframe
    if getattr(args, "pairs", None):
        s.pair_universe = args.pairs
    return s


def _kraken(s, with_keys: bool):
    from .brokers.kraken import KrakenBroker

    if with_keys:
        return KrakenBroker(s.kraken_api_key, s.kraken_api_secret)
    return KrakenBroker()


def _universe(s):
    return s.pair_universe or DEFAULT_UNIVERSE


def cmd_backtest(args) -> int:
    s = _apply_overrides(get_settings(), args)
    store = Store(s.db_path)
    broker = _kraken(s, with_keys=False)
    feed = DataFeed(broker, store)
    universe = _universe(s)

    print(f"Backfilling {len(universe)} pairs @ {s.timeframe} (~{args.bars} bars each)…")
    for sym in universe:
        try:
            n = feed.backfill(sym, s.timeframe, args.bars)
            print(f"  {sym:<12} {n} candles")
        except Exception as e:  # noqa: BLE001
            print(f"  {sym:<12} skipped ({e})")

    from .engine.backtest import Backtester

    bt = Backtester(store, build_strategy(args.strategy, s), s, universe, s.timeframe)
    print(f"\nRunning backtest (strategy={args.strategy})…\n")
    print(format_metrics(bt.run()))
    return 0


def cmd_paper(args) -> int:
    s = _apply_overrides(get_settings(), args)
    store = Store(s.db_path)
    feed = DataFeed(_kraken(s, with_keys=False), store)
    from .engine.paper import PaperEngine

    eng = PaperEngine(feed, store, build_strategy(args.strategy, s), s)
    print(f"PAPER | strategy={args.strategy} tf={s.timeframe} "
          f"| working={eng.cm.working:.2f} vault={eng.cm.vault:.2f} "
          f"| poll={args.poll}s | Ctrl-C to stop")
    if args.once:
        print(eng.run_once())
        return 0
    try:
        eng.run_forever(args.poll, on_tick=lambda x: print(x) if x.get("actions") else None)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


def cmd_live(args) -> int:
    s = get_settings()
    if s.mode != Mode.LIVE:
        print("Refusing: set BOT_MODE=live in .env to run live trading.")
        return 1
    if not (s.kraken_api_key and s.kraken_api_secret):
        print("Refusing: KRAKEN_API_KEY/KRAKEN_API_SECRET not set.")
        return 1
    if not args.yes:
        print("⚠️  LIVE trading places REAL orders. Re-run with --yes to confirm.")
        print("    Ensure your API key is TRADE-ONLY (no withdrawal) and caps are set.")
        return 1

    s = _apply_overrides(s, args)
    store = Store(s.db_path)
    broker = _kraken(s, with_keys=True)
    feed = DataFeed(broker, store)
    from .engine.live import LiveEngine

    eng = LiveEngine(broker, feed, store, build_strategy(args.strategy, s), s)
    print(f"🔴 LIVE | working={eng.cm.working:.2f} vault={eng.cm.vault:.2f} "
          f"| poll={args.poll}s | max/pos={s.max_position_abs} | Ctrl-C to stop")
    try:
        eng.run_forever(args.poll, on_tick=lambda x: print(x) if x.get("actions") else None)
    except KeyboardInterrupt:
        print("\nStopped (open positions remain — use 'kill' to flatten).")
    return 0


def cmd_status(args) -> int:
    s = get_settings()
    store = Store(s.db_path)
    mode = args.mode
    cap = store.get_state(f"capital:{mode}") or {}
    positions = store.get_state(f"positions:{mode}", []) or []
    trades = store.get_trades(mode)
    curve = store.get_equity_curve(mode)
    print(f"=== {mode.upper()} ===")
    print(f"working={cap.get('working', 0):.2f} base={cap.get('base', 0):.2f} "
          f"vault={cap.get('vault', 0):.2f}")
    print(f"open positions: {len(positions)}")
    for p in positions:
        print(f"  {p['symbol']} {p['amount']:.6g}@{p['entry_price']:.6g} "
              f"tp={p['tp_price']:.6g} sl={p['sl_price']:.6g}")
    if trades:
        print("\n" + format_metrics(
            compute_metrics(trades, curve, cap.get("working", 0), cap.get("vault", 0))
        ))
        print("\nlast 5 trades:")
        for t in trades[-5:]:
            print(f"  {t.symbol:<10} {t.exit_reason:<12} net={t.net_pnl:+.4f} fees={t.fees:.4f}")
    else:
        print("no trades yet.")
    return 0


def cmd_kill(args) -> int:
    s = get_settings()
    store = Store(s.db_path)
    from .risk.guardrails import RiskManager

    rm = RiskManager(store, "live", kill_switch_file=s.kill_switch_file)
    rm.set_kill(True)
    print("Kill switch ENGAGED. Running engines will flatten on their next tick.")
    return 0


def cmd_unkill(args) -> int:
    s = get_settings()
    store = Store(s.db_path)
    from .risk.guardrails import RiskManager

    rm = RiskManager(store, "live", kill_switch_file=s.kill_switch_file)
    rm.set_kill(False)
    print("Kill switch cleared.")
    return 0


def cmd_dashboard(args) -> int:
    import subprocess
    from pathlib import Path

    app = Path(__file__).resolve().parent / "app" / "dashboard.py"
    return subprocess.call(["streamlit", "run", str(app)])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="cryptobot", description="Fee-aware Kraken trading bot")
    sub = p.add_subparsers(dest="cmd", required=True)

    def _common(p):
        p.add_argument("--strategy", default="router", help="breakout | meanrev | kalman | router")
        p.add_argument("--timeframe", default=None, help="override timeframe, e.g. 1d, 4h, 15m")
        p.add_argument("--pairs", nargs="*", default=None, help="override the pair universe")

    b = sub.add_parser("backtest", help="prove the edge on history")
    b.add_argument("--bars", type=int, default=1500)
    _common(b)
    b.set_defaults(func=cmd_backtest)

    pa = sub.add_parser("paper", help="paper-trade on live prices")
    pa.add_argument("--poll", type=int, default=60)
    pa.add_argument("--once", action="store_true")
    _common(pa)
    pa.set_defaults(func=cmd_paper)

    li = sub.add_parser("live", help="REAL orders (capped)")
    li.add_argument("--poll", type=int, default=60)
    li.add_argument("--yes", action="store_true")
    _common(li)
    li.set_defaults(func=cmd_live)

    st = sub.add_parser("status", help="print state + metrics")
    st.add_argument("--mode", default="paper")
    st.set_defaults(func=cmd_status)

    sub.add_parser("kill", help="engage kill switch").set_defaults(func=cmd_kill)
    sub.add_parser("unkill", help="clear kill switch").set_defaults(func=cmd_unkill)
    sub.add_parser("dashboard", help="launch Streamlit monitor").set_defaults(func=cmd_dashboard)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
