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
| Kalman-SuperTrend + ADX | 1d | Not robust (0 at ≥4/5 folds). A few configs lean positive (+39, worst −9) but most have big worst folds (−41 to −57) — regime-dependent, thin. |

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

## Regime analysis — the key insight (seasons matter)

Bucketing every daily trade by the market season it was entered in (see
`src/research/regime_analysis.py`, classifier in `src/regime/classifier.py`) shows the "dead"
strategies are actually **specialists**, each earning in one season and bleeding in others:

| Season (daily) | Breakout | Mean-reversion | Kalman-SuperTrend |
|---|---|---|---|
| Bull (trend up) | +36 | −4 | **+25** |
| Range (chop) | **+88** | −16 | (no signal) |
| Bear (trend down) | −15 | **+38** | (no signal) |
| Bull + high-vol | −28 | — | +107 (thin) |

**Routing hypothesis:** trend-up → trend-following (Kalman); chop → breakout; downtrend/crash →
mean-reversion (buy capitulation). Skip each strategy's losing seasons.

**Caveat:** this mapping was chosen *after* seeing the buckets (in-sample), and some buckets are
thin (bear n=11). It MUST be validated out-of-sample via walk-forward before trusting — a router
that only looks good because we hand-picked the winners is just overfitting with extra steps.

## Router validation (walk-forward, daily, 5 folds, net P&L from $200)

| Strategy | f1 | f2 | f3 | f4 | f5 | Total | Folds+ | Trades |
|---|---|---|---|---|---|---|---|---|
| breakout | −19 | +152 | +16 | +20 | −43 | +126 | 3/5 | 199 |
| meanrev  | +43 | −1 | +10 | +4 | +12 | +69 | **4/5** | 18 |
| kalman   | +48 | −7 | +2 | +5 | −9 | +39 | 3/5 | 15 |
| router   | −14 | +30 | +60 | +42 | −7 | +111 | 3/5 | 97 |

Read honestly:
- The router is **smoother** than breakout (worst fold −14 vs −43) and beats meanrev/kalman on total,
  but does **not** dominate — breakout alone has a higher (much streakier) total.
- **Mean-reversion is the steady horse:** 4/5 folds positive, never a real loss, low magnitude.
- Caveats: the router's season→strategy map is **in-sample** (derive per-fold for a fair test), and
  it still has losing folds. Real lead, not a finished edge.

### Honest router validation (map learned from PAST only)

`src/research/router_validation.py` re-derives the season→strategy map from each fold's *past* data
and tests on the untouched fold:

| Fold | Learned map | OOS net | Trades |
|---|---|---|---|
| 1 | bull→kalman | −6.5 | 3 |
| 2 | bull→kalman, range→breakout | +34.4 | 19 |
| 3 | bear→meanrev, bull→kalman, range→breakout | +42.1 | 18 |
| 4 | full map | −6.9 | 18 |
| **Total** | | **+63**, positive 2/4 | |

- **The specialization is real:** the same map self-assembles from past data each fold (bull→kalman,
  range→breakout, bear→meanrev). Not random.
- **But not yet reliable:** +63 total with contained losses (−6.5, −6.9) but only 2/4 folds positive.
  Weaker than the in-sample +111 — the honest test removed the optimism, as it should.

### Router refinements still to try
- Use the high-vol axis in routing (router now supports label-keyed overrides).
- Size positions by regime confidence; sit out UNKNOWN/transition bars.
- More data/pairs so early folds have enough history to learn a full map (fold 1 only saw "bull").

## Intraday (4h) verdict: no season works

Ran the same per-season analysis on 4h (`regime_analysis --tfs 4h`). **Every strategy is negative in
every season** — not one positive bucket. At 4h the strategies trade ~5–6× more often (breakout: 495
range trades vs ~81 on daily) and the edge is buried under spread + fees + noise.

**Conclusion: the edge lives on the DAILY timeframe. Intraday does not work for us — stop hunting
shorter timeframes.** Concentrate research on daily (and the regime router there). Shorter = worse,
decisively, at these costs and capital.

## Wide universe (20 pairs, daily) — the decisive result

Widened to 20 liquid pairs for statistical power and re-validated:

- **Mean-reversion is THE lead.** Walk-forward (5 folds): `ma30 z2 sl3` → **+152 total, positive in
  4/5 folds** (multiple meanrev configs 4/5). Breadth turned the thin +69 into a robust +152.
- **The router got WORSE with breadth: −40 total, 1/4 folds.** Breakout's "range edge" was 5-pair
  luck (−7 in range across 20), and mean-reversion in the *range* season is toxic (−142). Routing
  learned "range→meanrev" in some folds and got destroyed OOS. **Complexity lost to simplicity.**
- A regime **filter** (meanrev but skip the range season) didn't help either: worst fold −70→−52 but
  total +152→+127. It trims winners and losers alike.

**Conclusion: the horse is plain daily mean-reversion over a broad basket** — buy ~2σ oversold dips,
revert to the mean, wide stop. Simplest thing we tried, and the most robust. Promoted as the `meanrev`
preset (`ma30 z2 sl3`); default live universe widened to 19 Kraken USD majors.

### The one real risk: correlated-crash drawdown
The single losing fold (−70) is the falling-knife failure — in a broad, correlated sell-off the
dip-buyer loads up everywhere at once and some dips keep dipping. This is a **risk-management**
problem, not a signal problem. Next work belongs here:
- Portfolio-heat / correlation cap (limit simultaneous correlated longs — the r/ai_trading point).
- A trend/vol filter to stand down in sustained free-fall.
- Position sizing scaled to how deep the dip is / how many positions are already open.

## Risk management — taming the correlated-crash drawdown

The −70 (−35%) fold was a sizing/concentration problem. Fix = **risk-based position sizing** (size so a
stop-out costs a fixed % of equity) + **portfolio-heat cap** (bound total open risk) + **diversify**
(many small bets, not few big). Walk-forward on 20 pairs, daily:

| Config | Total | Worst fold | Return/Drawdown |
|---|---|---|---|
| fixed-notional (old) | +152 | −70 (−35%) | 2.17 |
| risk 1%, heat 6%, max 3 | +16 | −14 | 1.19 |
| **risk 1%, heat 10%, max 10** | +53 | −12 (−6%) | **4.33** |
| risk 2%, heat 12%, max 12 | +77 | −25 | 3.04 |

**Takeaway:** shrinking bets alone just scales everything down; the win is *diversification under a
total-risk cap* — ret/dd ~doubles (2.2→4.3) and worst fold drops from −35% to −6% (sleepable). Absolute
return scales with capital, not bet size. Defaults set to risk 1% / heat 10% / max 10 positions.

## Guardrail principles adopted (from r/ai_trading trust discussions)

- Limits live in the **execution layer**, never a prompt. (We have no LLM in the loop — enforced in
  `risk/guardrails.py`.)
- Keys are **trade-only, no withdrawal**; paper mode never needs real keys.
- Leaving paper for live requires a **human action**, not a flag the system flips itself.
- **Reject stale data**; every bad input must **fail closed** (tested).
- Persist an audit trail (trade ledger, equity/vault snapshots) and keep a **kill switch**.
- Open item: **correlation-aware limits** — several correlated majors can be one big bet.
