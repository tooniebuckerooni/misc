# Research findings

Living log of what the search has actually shown, on **real data, out-of-sample**. The gate is
always: net expectancy positive after fees (sum of gains > sum of losses), and consistency across
walk-forward folds — never a single lucky split.

## Data

- Kraken public API caps at ~720 candles per interval and won't page further back (verified).
- Research therefore uses **deep history from Binance.US** (majors differ by pennies from Kraken —
  fine for judging edge). Ingested ~4 years (since 2022-08): 1,460 daily + 8,759 4h bars per pair
  for BTC, ETH, SOL (USDT) and ETH/BTC, SOL/BTC.
- **Execution is always Kraken.** Deep data is research-only.

## Verdict by strategy (4 years, walk-forward)

| Strategy | Timeframe | Result |
|---|---|---|
| Breakout (Donchian + ATR brackets) | 1d & 4h | ☠️ Dead. Negative OOS everywhere (PF 0.5–0.9). |
| Mean-reversion | 4h | ☠️ Dead. Hundreds of trades, net negative (−38 to −131). |
| **Mean-reversion** | **1d** | 🌱 **Lead.** Positive in 4/5 folds, +68 total, worst fold −0.78. |
| Kalman-SuperTrend + ADX | 1d | Thin / inconclusive (rare signal). |

## The lead worth nurturing (KEEP THIS)

**Daily mean-reversion: buy deep oversold dips, sell on reversion to the mean, wide stop.**

- Concept: on the daily chart of a major, when price is ~2σ below its moving average (capitulation),
  buy; take profit on reversion to the MA; use a wide stop so normal noise doesn't shake you out.
- Best configs observed (`src/strategy/mean_reversion.py`): `ma_bars≈20–30`, `entry_z≈2.0`,
  `sl_sd≈3.0`, timeframe **1d**, long-only spot.
- Why it's believable: "buy capitulation on majors" is a documented behavior, not a fitted curve.
- **Honest caveats:** rare (~18 trades in 4 years — it waits for real fear); works on 1d only, not
  4h; higher-frequency variants lose. This is a *candidate edge to validate further*, NOT a
  green light to trade real money.

### Next steps to harden the lead
- More pairs and more history (add majors; consider a second data source to cross-check).
- Proper statistics: it needs many more trades before we trust it — widen the pair universe rather
  than over-tuning parameters (overfitting risk).
- Combine with a regime filter (only take dips when the higher-timeframe trend isn't collapsing).

## Guardrail principles adopted (from r/ai_trading trust discussions)

- Limits live in the **execution layer**, never a prompt. (We have no LLM in the loop — enforced in
  `risk/guardrails.py`.)
- Keys are **trade-only, no withdrawal**; paper mode never needs real keys.
- Leaving paper for live requires a **human action**, not a flag the system flips itself.
- **Reject stale data**; every bad input must **fail closed** (tested).
- Persist an audit trail (trade ledger, equity/vault snapshots) and keep a **kill switch**.
- Open item: **correlation-aware limits** — several correlated majors can be one big bet.
