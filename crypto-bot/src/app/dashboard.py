"""Local Streamlit dashboard — the honest scoreboard, now fleet-aware.

Two views, chosen in the sidebar:
  - **Fleet overview**: every pipeline (each strategy = its own DB) compared side by side, so you can
    watch several leads at once and see which are actually working.
  - **Single pipeline**: the full detail for one — buckets vs "just hold", trades, fees, sweeps.

Run:  python -m src.cli dashboard              (fleet overview)
      python -m src.cli dashboard --pipeline meanrev   (jump straight to one)
Read-only: it never places or changes orders.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from ..config.settings import DATA_DIR, get_settings
from ..data.store import Store
from ..trackers.metrics import compute_metrics

st.set_page_config(page_title="crypto-bot", layout="wide")

# Password gate for public/cloud deployments. Set DASH_PASSWORD in the environment to enable.
_DASH_PW = os.environ.get("DASH_PASSWORD")
if _DASH_PW:
    if not st.session_state.get("authed"):
        entered = st.text_input("Password", type="password")
        if entered and entered == _DASH_PW:
            st.session_state["authed"] = True
            st.rerun()
        elif entered:
            st.error("Wrong password.")
        st.stop()

S = get_settings()


def discover_pipelines() -> list[str]:
    """Every pipeline is a DB in the data dir; hide the research archive."""
    names = sorted(p.stem for p in DATA_DIR.glob("*.db"))
    return [n for n in names if n != "research"]


def heartbeat_status(store) -> tuple[str, bool]:
    """(human age, alive?) from the loop's last-tick stamp. Alive = ticked within ~3 polls."""
    hb = store.get_state("heartbeat")
    poll = store.get_state("poll_seconds", 3600) or 3600
    if not hb:
        return "no tick yet", False
    age = max(0, int(time.time()) - hb // 1000)
    alive = age < max(3 * poll, 300)
    human = f"{age}s" if age < 90 else (f"{age // 60}m" if age < 5400 else f"{age // 3600}h")
    return human, alive


def _pipeline_metrics(name: str, mode: str):
    store = Store(DATA_DIR / f"{name}.db")
    cap = store.get_state(f"capital:{mode}") or {}
    trades = store.get_trades(mode)
    curve = store.get_equity_curve(mode)
    positions = store.get_state(f"positions:{mode}", []) or []
    killed = bool(store.get_state("kill_switch", False))
    m = compute_metrics(trades, curve, float(cap.get("working", 0.0)), float(cap.get("vault", 0.0)))
    last = trades[-1].closed_ts if trades else None
    return store, cap, trades, curve, positions, killed, m, last


# ---- Sidebar: mode + view selection ---------------------------------------
pipelines = discover_pipelines()
mode = st.sidebar.selectbox("Mode", ["paper", "backtest", "live"], index=0)
forced = os.environ.get("BOT_PIPELINE")
options = ["— Fleet overview —"] + pipelines
default_idx = options.index(forced) if forced in pipelines else 0
choice = st.sidebar.selectbox("View", options, index=default_idx)

st.title("crypto-bot — scoreboard")
st.caption("BTC is the vault. Working capital churns. The gate is: gains > losses, after fees.")


# ===========================================================================
# FLEET OVERVIEW
# ===========================================================================
if choice == "— Fleet overview —":
    if not pipelines:
        st.info("No pipelines yet. Start one, e.g.  "
                "`python -m src.cli paper --strategy meanrev --pipeline meanrev`")
        st.stop()

    rows = []
    curves = []
    for name in pipelines:
        store_i, cap, trades, curve, positions, killed, m, last = _pipeline_metrics(name, mode)
        hb_age, hb_alive = heartbeat_status(store_i)
        rows.append({
            "pipeline": name,
            "alive": ("🟢 " if hb_alive else "🔴 ") + hb_age,
            "gate": "✅" if m.passes_gate else ("—" if m.n_trades == 0 else "❌"),
            "working": round(m.final_working, 2),
            "vault": round(m.final_vault, 2),
            "total": round(m.total_value, 2),
            "trades": m.n_trades,
            "win%": round(m.win_rate * 100, 0),
            "net": round(m.net_pnl, 2),
            "maxDD%": round(m.max_drawdown * 100, 1),
            "open": len(positions),
            "kill": "🔴" if killed else "",
            "last trade": (datetime.fromtimestamp(last / 1000, tz=timezone.utc)
                           .strftime("%Y-%m-%d %H:%M") if last else "—"),
        })
        if curve:
            df = pd.DataFrame(curve)
            df["ts"] = pd.to_datetime(df["ts"], unit="ms")
            df[name] = df["working_equity"] + df["vault"]
            curves.append(df.set_index("ts")[[name]])

    st.subheader(f"All pipelines — {mode}")
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if curves:
        st.subheader("Total value over time")
        st.line_chart(pd.concat(curves, axis=1).ffill())
    st.caption("Pick a pipeline in the sidebar to drill into its trades, fees, and sweeps.")
    st.stop()


# ===========================================================================
# SINGLE PIPELINE DETAIL
# ===========================================================================
name = choice
store, cap, trades, curve, positions, killed, m, _ = _pipeline_metrics(name, mode)
working, vault = float(cap.get("working", 0.0)), float(cap.get("vault", 0.0))

_hb_age, _hb_alive = heartbeat_status(store)
st.sidebar.markdown(f"**Pipeline:** `{name}`")
st.sidebar.markdown(f"**Loop:** {'🟢 alive' if _hb_alive else '🔴 stale'} — last tick {_hb_age} ago")
st.sidebar.markdown(f"**Kill switch:** {'🔴 ENGAGED' if killed else '🟢 clear'}")
# Mobile-accessible kill switch: writes the stop flag the trading loop reads on its next tick.
if killed:
    if st.sidebar.button("🟢 Clear kill switch"):
        store.set_state("kill_switch", False)
        st.rerun()
else:
    if st.sidebar.button("🔴 Engage kill switch (flatten & stop)"):
        store.set_state("kill_switch", True)
        st.rerun()

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

st.subheader("Total value vs. doing nothing")
if curve:
    df = pd.DataFrame(curve)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    df["total_value"] = df["working_equity"] + df["vault"]
    df["hold_baseline"] = S.starting_working_capital
    st.line_chart(df.set_index("ts")[["total_value", "hold_baseline"]])
else:
    st.info("No equity snapshots yet — run backtest or paper first.")

st.subheader(f"Open positions ({len(positions)})")
if positions:
    st.dataframe(pd.DataFrame(positions), use_container_width=True, hide_index=True)
else:
    st.write("None.")

c9, c10, c11 = st.columns(3)
c9.metric("Gross profit", f"{m.gross_profit:,.2f}")
c10.metric("Gross loss", f"{m.gross_loss:,.2f}")
c11.metric("Cumulative fees", f"{m.fees_total:,.2f}")

sweeps = store.get_sweeps(mode)
st.subheader(f"Profit sweeps to vault ({len(sweeps)})")
if sweeps:
    sdf = pd.DataFrame(sweeps)
    sdf["ts"] = pd.to_datetime(sdf["ts"], unit="ms")
    st.dataframe(sdf[["ts", "profit", "swept", "working_after", "new_base", "vault_after"]],
                 use_container_width=True, hide_index=True)
else:
    st.write("No sweeps yet — working capital hasn't hit the trigger.")

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
