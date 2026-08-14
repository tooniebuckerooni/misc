# crypto-bot

A fee-aware automated crypto trading bot for **Kraken**.

**Design in one breath:** BTC is the *vault and scoreboard*, not the trading venue. A **scanner**
scours many pairs across any quote (stablecoin / BTC / fiat) and ranks setups by *total net
execution cost* (fee + spread + slippage). The strategy trades whatever it surfaces with
**pre-defined bracket orders** (post-only limit entry + take-profit + stop-loss). Winnings pile up
in a **working-capital bucket**; when that bucket doubles, half the profit is **swept into the BTC
vault** and the bot carries on. The same strategy code runs in **backtest → paper → capped-live**,
so paper results actually predict live behaviour.

> ⚠️ No strategy is promised to be profitable. This is a rig to *prove or disprove* an edge cheaply
> before risking real money. The gate to go live is: **sum of gains > sum of losses, after fees.**

## Quick start

```bash
cd crypto-bot
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dashboard,dev]"

cp .env.example .env      # fill in Kraken keys (trade-only, NO withdrawal permission)

python -m src.cli backtest      # prove the edge on history first
python -m src.cli paper         # live prices, simulated fills
python -m src.cli dashboard     # local Streamlit monitor
python -m src.cli live          # real orders — capped + kill switch (only after paper proof)
```

## Safety

- Default mode is **paper**. `live` must be set explicitly in `.env`.
- Use a Kraken API key with **trade permission only** — withdrawals disabled.
- Hard caps: max position size, max open positions, daily-loss auto-halt.
- Kill switch: create a file named `KILL_SWITCH` in the project root (or `python -m src.cli kill`)
  to flatten and stop immediately.

## Status

Built in sections; see `git log`. Current: **Section 1 — scaffold**. Roadmap in
`/root/.claude/plans/…` (the approved plan).
