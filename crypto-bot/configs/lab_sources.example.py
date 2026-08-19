"""Example external-signal wiring for the Lab strategy.

Copy this to `configs/lab_sources.py` and edit. Define `get_sources()` returning a list of
(SignalSource, weight). Weights blend against the technical signals (see LabConfig.external_weight).

Each source returns a value in [-1, 1] for (symbol, ts): +1 bullish, -1 bearish, 0 neutral.
Remember the honesty rule: a live feed has no truthful *past*, so return 0.0 for historical `ts`
(otherwise your backtest is cheating). The provided sources already follow this.
"""

from src.signals.sources import CallableSource, ConstantSource, ReverseCramerSource


# --- Example 1: fade a loud pundit ("reverse Cramer") ----------------------
def _cramer_stance_today(base_asset: str) -> float:
    """Return +1 if he's loudly bullish on this asset *today*, -1 if bearish, 0 if he's quiet.

    Wire this to whatever you trust: a scraper, a paid sentiment API, an RSS feed, even a value you
    set by hand each morning. Keep it fast and never raise. This stub is quiet (neutral) by default.
    """
    # e.g. return query_my_sentiment_service(base_asset)
    return 0.0


# --- Example 2: a plain manual bias you flip while traveling ----------------
# ConstantSource(0.2) nudges everything slightly bullish; set to 0 to disable.


def get_sources():
    return [
        (ReverseCramerSource(fetch_stance=_cramer_stance_today), 1.0),
        # (ConstantSource(0.0, "manual_bias"), 0.5),
        # (CallableSource(lambda sym, ts: 0.0, "my_custom_feed"), 1.0),
    ]
