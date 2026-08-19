from __future__ import annotations

import math

from src.core.types import OHLCVBar, Ticker
from src.signals.sources import CallableSource, ConstantSource, ReverseCramerSource
from src.strategy.lab import LabConfig, LabStrategy


def _bars(n=120, start=100.0):
    bars, ts, px = [], 0, start
    for i in range(n):
        px = px * (1 + 0.004 * math.sin(i / 9) + 0.001)
        bars.append(OHLCVBar(ts, px * 0.999, px * 1.01, px * 0.99, px, 100 + (i % 5) * 20))
        ts += 86_400_000
    return bars


def test_labconfig_json_roundtrip(tmp_path):
    c = LabConfig(entry_threshold=0.42, w_rsi=-2.0, ema_fast=5)
    p = tmp_path / "lab.json"
    c.to_json(p)
    back = LabConfig.from_json(p)
    assert back.entry_threshold == 0.42 and back.w_rsi == -2.0 and back.ema_fast == 5


def test_lab_needs_enough_bars():
    assert LabStrategy(LabConfig()).evaluate("ETH/USD", _bars(10)) is None


def test_lab_external_source_can_drive_entry():
    bars = _bars()
    tk = Ticker("ETH/USD", bars[-1].close, bars[-1].close * 1.001, bars[-1].close, bars[-1].ts)
    # Strong external bullish source + zero threshold => should produce a long bracket.
    lab = LabStrategy(LabConfig(entry_threshold=0.0), sources=[(ConstantSource(1.0), 5.0)])
    b = lab.evaluate("ETH/USD", bars, tk)
    assert b is not None and b.side.value == "buy" and b.tp_price > b.entry_price > b.sl_price


def test_reverse_cramer_neutral_without_feed_but_fades_with_one():
    src = ReverseCramerSource()
    assert src.value("BTC/USD", 0) == 0.0                     # neutral until wired
    fed = ReverseCramerSource(fetch_stance=lambda base: 1.0)  # he's shilling
    assert fed.value("BTC/USD", 0) == -1.0                    # so we fade -> bearish


def test_callable_source_is_defensive():
    boom = CallableSource(lambda s, t: 1 / 0)
    assert boom.value("X", 0) == 0.0  # never raises into the strategy
