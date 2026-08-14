# Run the mean-reversion bot at home (paper first)

This is the step-by-step for running our one validated lead — **daily mean-reversion** — as its own
isolated pipeline on your own computer. Start on paper; go live only later, tiny and capped.

> **Reality check.** We've rigorously tested a handful of strategies and *one* survived out-of-sample:
> daily mean-reversion (buy deep dips across a broad basket, revert to the mean, wide stop), with
> risk-based sizing. It cleared 4/5 walk-forward folds over 4 years with a ~−6% worst fold. That's a
> real, boring, slow-and-steady edge — **not** a money printer. Keep looking for more indicators; this
> is one horse, run in its own lane. Nothing here is financial advice.

---

## 1. Prerequisites
- **Python 3.11+** and **git**.
- A **Kraken** account.

## 2. Get the code
```bash
git clone <your-repo-url> && cd misc/crypto-bot
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dashboard]"
```

## 3. Kraken API key — TRADE ONLY (no withdrawal)
Only needed for **live**; paper uses public data and needs no key. When you do create one
(Kraken → Settings → API):
- Enable **Query Funds** and **Create & Modify Orders**.
- Leave **Withdraw Funds DISABLED.** A leaked trade-only key cannot move your coins out.

```bash
cp .env.example .env
# edit .env: set KRAKEN_API_KEY / KRAKEN_API_SECRET. Leave BOT_MODE=paper for now.
```

## 4. (Optional) Sanity backtest
Confirms the pipeline runs end-to-end on real data before you watch it live:
```bash
python -m src.cli backtest --strategy meanrev --timeframe 1d --pipeline meanrev --bars 720
```

## 5. Paper-trade it (recommended: run this for weeks first)
```bash
python -m src.cli paper --strategy meanrev --timeframe 1d --pipeline meanrev --poll 3600
```
- `--pipeline meanrev` gives it its **own database** (`data/meanrev.db`) and **own kill switch**
  (`KILL_SWITCH_meanrev`), so other experiments never touch it.
- `--poll 3600` checks hourly — plenty for a daily strategy.
- It places **no real orders**; it simulates fills against live Kraken prices and records everything.

Keep it running after you close the terminal:
```bash
# macOS/Linux
nohup python -m src.cli paper --strategy meanrev --timeframe 1d --pipeline meanrev --poll 3600 > meanrev.log 2>&1 &
# or use tmux/screen; on a always-on box, a systemd service is cleanest.
```

## 6. Watch it
```bash
python -m src.cli status --pipeline meanrev            # quick text summary + metrics
python -m src.cli dashboard --pipeline meanrev         # live Streamlit scoreboard in your browser
```
The dashboard shows working capital vs the "just hold" line, the BTC vault, open positions, every
trade, cumulative fees, and the net-expectancy gate.

## 7. Kill switch (always available)
```bash
python -m src.cli kill --pipeline meanrev      # flattens on next tick and stops entering
python -m src.cli unkill --pipeline meanrev    # resume
```

## 8. Going live later (only after paper convinces you)
1. Paper-trade long enough to trust it (weeks, ideally across a down move).
2. In `.env` set `BOT_MODE=live`, confirm the key is trade-only, and keep caps small
   (`data/settings` defaults: 1% risk/trade, 10% total heat, max 10 positions).
3. Start tiny:
   ```bash
   python -m src.cli live --strategy meanrev --timeframe 1d --pipeline meanrev --yes --poll 3600
   ```
> Live execution is still **experimental** in this repo (real order placement works, but fill
> reconciliation is basic). Use pocket-change amounts until you've watched it behave.

## 9. Adding a new indicator later (keep exploring)
Any new idea is a `Strategy` subclass in `src/strategy/`, registered in
`src/strategy/registry.py`. Then it gets the *same* toolchain, in its own lane:
```bash
python -m src.cli backtest --strategy <name> --timeframe 1d --pipeline <name>
python -m src.research.walkforward --no-backfill --tf 1d --pairs ...   # validate OOS
python -m src.cli paper --strategy <name> --pipeline <name>            # separate DB, no collision
```
Validate every new lead the same way we did here — walk-forward, after fees — before trusting it.
See `research/FINDINGS.md` for what's already been tested (and what died).
