"""Local Streamlit dashboard — the honest scoreboard.

Run with:  python -m src.cli dashboard   (or: streamlit run src/app/dashboard.py)

Shows both buckets (working capital + BTC vault) against a "just hold" baseline, open
positions, the full trade log, cumulative fees, net-expectancy metrics, sweep events, and
the kill-switch state. Read-only: it never places or changes orders.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from ..config.settings import get_settings
from ..data.store import Store
from ..trackers.metrics import compute_metrics

st.set_page_config(page_title="crypto-bot", layout="wide")

s = get_settings()
store = Store(s.db_path)

st.title("crypto-bot — scoreboard")
st.caption("BTC is the vault. Working capital churns. The gate is: gains > losses, after fees.")

mode = st.sidebar.selectbox("Mode", ["paper", "backtest", "live"], index=0)
kill = bool(store.get_state("kill_switch", False)) or s.kill_switch_file.exists()
st.sidebar.markdown(f"**Kill switch:** {'🔴 ENGAGED' if kill else '🟢 clear'}")

cap = store.get_state(f"capital:{mode}") or {}
trades = store.get_trades(mode)
curve = store.get_equity_curve(mode)
sweeps = store.get_sweeps(mode)
positions = store.get_state(f"positions:{mode}", []) or []

working = float(cap.get("working", 0.0))
vault = float(cap.get("vault", 0.0))
m = compute_metrics(trades, curve, working, vault)

# ---- Headline numbers -----------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Working capital", f"{working:,.2f}")
c2.metric("BTC vault (banked)", f"{vault:,.2f}")
c3.metric("Total value", f"{m.total_value:,.2f}")
c4.metric("Net expectancy gate", "PASS ✅" if m.passes_gate else "FAIL ❌")

c5, c6, c7, c8 = st.columns(4)
c5.metric("Trades", f"{m.n_trades}")
c6.metric("Win rate", f"{m.win_rate:.1%}")
pf = "∞" if m.profit_factor == float("inf") else f"{m.profit_factor:.2f}"
c7.metric("Profit factor", pf)
c8.metric("Max drawdown", f"{m.max_drawdown:.1%}")

# ---- Equity curve vs. "just hold" baseline --------------------------------
st.subheader("Total value vs. doing nothing")
if curve:
    df = pd.DataFrame(curve)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    df["total_value"] = df["working_equity"] + df["vault"]
    df["hold_baseline"] = s.starting_working_capital
    st.line_chart(df.set_index("ts")[["total_value", "hold_baseline"]])
else:
    st.info("No equity snapshots yet — run backtest or paper first.")

# ---- Open positions -------------------------------------------------------
st.subheader(f"Open positions ({len(positions)})")
if positions:
    st.dataframe(pd.DataFrame(positions), use_container_width=True, hide_index=True)
else:
    st.write("None.")

# ---- Fees + net --------------------------------------------------------
c9, c10, c11 = st.columns(3)
c9.metric("Gross profit", f"{m.gross_profit:,.2f}")
c10.metric("Gross loss", f"{m.gross_loss:,.2f}")
c11.metric("Cumulative fees", f"{m.fees_total:,.2f}")

# ---- Sweeps ---------------------------------------------------------------
st.subheader(f"Profit sweeps to vault ({len(sweeps)})")
if sweeps:
    sdf = pd.DataFrame(sweeps)
    sdf["ts"] = pd.to_datetime(sdf["ts"], unit="ms")
    st.dataframe(sdf[["ts", "profit", "swept", "working_after", "new_base", "vault_after"]],
                 use_container_width=True, hide_index=True)
else:
    st.write("No sweeps yet — working capital hasn't hit the trigger.")

# ---- Trade log ------------------------------------------------------------
st.subheader(f"Trade log ({len(trades)})")
if trades:
    rows = [
        {
            "closed": datetime.fromtimestamp(t.closed_ts / 1000, tz=timezone.utc),
            "symbol": t.symbol, "reason": t.exit_reason,
            "entry": t.entry_price, "exit": t.exit_price,
            "net_pnl": t.net_pnl, "fees": t.fees,
        }
        for t in trades
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.write("No trades yet.")
