from __future__ import annotations

from src.core.ict import has_displacement, last_bullish_fvg, swept_low
from src.core.types import OHLCVBar, Ticker
from src.strategy.ict import ICTStrategy


def _bar(ts, o, h, l, c):
    return OHLCVBar(ts, o, h, l, c, 100)


def _scenario():
    """Flat, then a swept low, a bullish displacement forming an FVG, then a retrace into the gap."""
    bars = []
    ts = 0
    for _ in range(29):                       # 0..28 flat around 100
        bars.append(_bar(ts, 100.0, 100.2, 99.8, 100.0)); ts += 3_600_000
    bars.append(_bar(ts, 99.7, 99.6 + 0.0, 99.0, 99.5)); ts += 3_600_000   # 29: sweep low (99.0)
    bars.append(_bar(ts, 99.5, 102.1, 99.4, 102.0)); ts += 3_600_000       # 30: displacement up
    bars.append(_bar(ts, 101.2, 102.5, 101.0, 101.8)); ts += 3_600_000     # 31: gap-up -> FVG [99.6,101.0]
    bars.append(_bar(ts, 101.0, 101.1, 100.1, 100.3)); ts += 3_600_000     # 32: retrace into gap
    return bars


def test_primitives_detect_the_setup():
    bars = _scenario()
    sw = swept_low(bars, 3, len(bars))
    assert sw is not None and abs(sw[1] - 99.0) < 1e-9
    fvg = last_bullish_fvg(bars, sw[0], len(bars))
    assert fvg is not None
    _, gap_low, gap_high = fvg
    assert gap_low < gap_high and gap_low <= 100.3 <= gap_high  # last close sits inside the gap


def test_ict_emits_long_bracket_on_retrace():
    bars = _scenario()
    tk = Ticker("ETH/USD", 100.29, 100.31, 100.3, bars[-1].ts)
    b = ICTStrategy(window=30, disp_mult=0.5, fvg_max_age=10, r_multiple=2.0).evaluate("ETH/USD", bars, tk)
    assert b is not None and b.side.value == "buy"
    assert b.sl_price < b.entry_price < b.tp_price
    # target is ~2R from entry
    assert abs((b.tp_price - b.entry_price) - 2 * (b.entry_price - b.sl_price)) < 1e-6


def test_ict_no_setup_when_flat():
    flat = [_bar(i * 3_600_000, 100, 100.2, 99.8, 100) for i in range(40)]
    assert ICTStrategy().evaluate("ETH/USD", flat) is None
