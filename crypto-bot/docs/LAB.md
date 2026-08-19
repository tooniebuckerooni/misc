# The Strategy Lab — your tuning bench

The `lab` strategy is a **broad, neutral canvas** you shape into a winner over time. It blends many
indicators — momentum-flavoured (trend, MACD, ROC, Donchian, SuperTrend) and mean-reversion-flavoured
(RSI, Bollinger, Stochastic) — each emitting a signal in `[-1,+1]` (+1 = bullish). At the default equal
weights these partly cancel, so **out of the box it assumes nothing and trades rarely**. You lean it by
turning knobs, and you can blend in *any* external data source. It runs in its own isolated pipeline.

## Run it (its own pipeline)
```bash
python -m src.cli backtest --strategy lab --timeframe 1d --pipeline lab --bars 720
python -m src.cli paper    --strategy lab --timeframe 1d --pipeline lab --poll 3600
python -m src.cli dashboard --pipeline lab      # shows the %complete progress meter
```

## The tuning loop
1. Edit **`configs/lab.json`** (all 41 knobs live there).
2. Re-run the backtest.
3. Watch the **% complete toward a provable winner** climb on the dashboard (net positive, beats fees,
   profit factor, drawdown control, …).
4. When it looks good, **confirm out-of-sample** — that's the real gate:
   ```bash
   python -m src.research.walkforward --no-backfill --tf 1d --pairs BTC/USDT ETH/USDT SOL/USDT
   ```
   (or add `lab` to a sweep). A high %complete on one backtest is encouragement, not proof.

## The knobs (`configs/lab.json`)
Every signal has three controls: `use_*` (on/off), `w_*` (weight — **negative fades it**), and its
period(s). Signal *direction* (what "+1 bullish" means):
- **Oversold-bullish** (dip-buyers): `rsi`, `bollinger`, `stochastic` → +1 when stretched *down*.
- **Momentum-bullish** (trend-followers): `trend` (EMA cross), `macd`, `roc`, `donchian`, `supertrend`.

So a **positive** weight leans the strategy toward that signal's style; a **negative** weight does the
opposite. Other knobs:
- `use_volume` — scales conviction by volume vs its average (not directional).
- `use_adx_gate` / `adx_min` — only trade when trend strength (ADX) clears a bar. `0` = no gate.
- `external_weight` — overall weight of your external sources vs the technical block.
- `entry_threshold` — blended score needed to go long (higher = pickier, fewer trades).
- `atr_period`, `tp_atr_mult`, `sl_atr_mult`, `min_rr` — the bracket geometry.

### Two starter recipes
- **Dip-buyer:** raise `w_rsi`, `w_bollinger`, `w_stochastic`; set the momentum weights to `0`.
- **Trend-follower:** raise `w_trend`, `w_macd`, `w_roc`, `w_supertrend`; set the mean-reversion weights
  to `0`; consider `use_adx_gate: true`, `adx_min: 22`.

## Plugging in "unexpected" data (sentiment, reverse-Cramer, on-chain…)
1. Copy `configs/lab_sources.example.py` → `configs/lab_sources.py`.
2. Implement `get_sources()` returning `[(SignalSource, weight), ...]`.
3. Each source returns `[-1,1]` for `(symbol, ts)`. **Honesty rule:** a live feed has no truthful past,
   so return `0.0` for historical `ts` — otherwise your backtest is cheating. The shipped sources do this.
4. **No secrets in that file** — read API keys from environment variables (it may get deployed).

The `ReverseCramerSource` is a worked template: give it a `fetch_stance(asset)->[-1,1]` that reads
today's take from wherever you trust, and it *fades* it. Quiet/neutral until you wire the feed.

## What "% complete" means
Milestones on the latest backtest (weights sum to 100): ≥30 trades, net positive after fees,
gains>losses, profit factor ≥1.3, drawdown ≤25%, win rate ≥35%, positive expectancy. Hitting them all
= "clears the bar we'd want before trusting it." Final confidence still comes from walk-forward.

> Reminder: this is a bench for experiments. Keep it on its own `lab` pipeline and on paper. The proven
> `meanrev` pipeline runs independently — the lab can't disturb it.
