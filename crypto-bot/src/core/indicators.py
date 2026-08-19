"""Small, dependency-light technical indicators computed on OHLCV bars.

Pure functions — no I/O — so they run identically in backtest, paper, and live, and are
trivial to unit-test.
"""

from __future__ import annotations

from .types import OHLCVBar


def true_ranges(bars: list[OHLCVBar]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i].high, bars[i].low, bars[i - 1].close
        out.append(max(h - l, abs(h - pc), abs(l - pc)))
    return out


def atr(bars: list[OHLCVBar], period: int) -> float | None:
    """Average True Range over the last `period` completed bars (simple mean).

    Only looks at the tail so it stays O(period), not O(n) — this matters when the
    backtester calls it once per bar over tens of thousands of bars of deep history.
    """
    if len(bars) < period + 1:
        return None
    trs = true_ranges(bars[-(period + 1):])
    return sum(trs) / period


def donchian(bars: list[OHLCVBar], period: int) -> tuple[float, float] | None:
    """Highest high / lowest low over the `period` bars *before* the latest bar.

    Excluding the latest bar makes 'close > upper' a genuine breakout of prior range.
    """
    if len(bars) < period + 1:
        return None
    prior = bars[-(period + 1):-1]
    upper = max(b.high for b in prior)
    lower = min(b.low for b in prior)
    return upper, lower


def sma(bars: list[OHLCVBar], period: int) -> float | None:
    if len(bars) < period:
        return None
    return sum(b.close for b in bars[-period:]) / period


def stdev(bars: list[OHLCVBar], period: int) -> float | None:
    """Standard deviation of closing prices over the last `period` bars."""
    if len(bars) < period:
        return None
    closes = [b.close for b in bars[-period:]]
    mean = sum(closes) / period
    var = sum((c - mean) ** 2 for c in closes) / period
    return var ** 0.5


def kalman(bars: list[OHLCVBar], q: float = 0.001, r: float = 0.1) -> list[float]:
    """1-D constant-position Kalman smoother over closes. Lower q / higher r = smoother."""
    if not bars:
        return []
    x = bars[0].close
    p = 1.0
    out: list[float] = []
    for b in bars:
        p += q                       # predict
        k = p / (p + r)              # Kalman gain
        x = x + k * (b.close - x)    # update
        p = (1 - k) * p
        out.append(x)
    return out


def _wilder_atr_series(bars: list[OHLCVBar], period: int) -> list[float | None]:
    n = len(bars)
    tr = [0.0] * n
    for i in range(1, n):
        h, l, pc = bars[i].high, bars[i].low, bars[i - 1].close
        tr[i] = max(h - l, abs(h - pc), abs(l - pc))
    atr: list[float | None] = [None] * n
    if n <= period:
        return atr
    atr[period] = sum(tr[1:period + 1]) / period
    for i in range(period + 1, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def supertrend(
    bars: list[OHLCVBar], period: int = 10, mult: float = 3.0,
    source_vals: list[float] | None = None,
) -> tuple[list[int], list[float | None]]:
    """Return (direction, line). direction is +1 (bull) / -1 (bear) / 0 (warmup) per bar.

    `source_vals` lets you run SuperTrend on a smoothed price (e.g. the Kalman line).
    """
    n = len(bars)
    src = source_vals if source_vals is not None else [(b.high + b.low) / 2 for b in bars]
    close = [b.close for b in bars]
    atr = _wilder_atr_series(bars, period)
    direction = [0] * n
    line: list[float | None] = [None] * n
    fu = fl = None
    for i in range(n):
        if atr[i] is None:
            continue
        bu = src[i] + mult * atr[i]
        bl = src[i] - mult * atr[i]
        if fu is None:
            fu, fl = bu, bl
            direction[i] = 1
            line[i] = fl
            continue
        fu = bu if (bu < fu or close[i - 1] > fu) else fu
        fl = bl if (bl > fl or close[i - 1] < fl) else fl
        if close[i] > fu:
            direction[i] = 1
        elif close[i] < fl:
            direction[i] = -1
        else:
            direction[i] = direction[i - 1]
        line[i] = fl if direction[i] == 1 else fu
    return direction, line


def adx(bars: list[OHLCVBar], period: int = 14) -> float | None:
    """Wilder's ADX (latest value). Higher = stronger trend, direction-agnostic."""
    n = len(bars)
    if n < 2 * period + 2:
        return None
    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    tr = [0.0] * n
    for i in range(1, n):
        up = bars[i].high - bars[i - 1].high
        dn = bars[i - 1].low - bars[i].low
        plus_dm[i] = up if (up > dn and up > 0) else 0.0
        minus_dm[i] = dn if (dn > up and dn > 0) else 0.0
        h, l, pc = bars[i].high, bars[i].low, bars[i - 1].close
        tr[i] = max(h - l, abs(h - pc), abs(l - pc))

    def wilder(arr: list[float]) -> list[float | None]:
        sm: list[float | None] = [None] * n
        sm[period] = sum(arr[1:period + 1])
        for i in range(period + 1, n):
            sm[i] = sm[i - 1] - sm[i - 1] / period + arr[i]
        return sm

    tr_s, pd_s, md_s = wilder(tr), wilder(plus_dm), wilder(minus_dm)
    dx_vals: list[float] = []
    for i in range(period, n):
        if tr_s[i] and tr_s[i] > 0:
            pdi = 100 * pd_s[i] / tr_s[i]
            mdi = 100 * md_s[i] / tr_s[i]
            denom = pdi + mdi
            dx_vals.append(100 * abs(pdi - mdi) / denom if denom > 0 else 0.0)
    if len(dx_vals) < period:
        return None
    a = sum(dx_vals[:period]) / period
    for v in dx_vals[period:]:
        a = (a * (period - 1) + v) / period
    return a


def _ema_last(vals: list[float], period: int) -> float | None:
    if len(vals) < period:
        return None
    k = 2.0 / (period + 1)
    e = sum(vals[:period]) / period  # seed with SMA
    for v in vals[period:]:
        e = v * k + e * (1 - k)
    return e


def ema(bars: list[OHLCVBar], period: int) -> float | None:
    """Latest EMA of close (computed over a bounded tail for speed)."""
    return _ema_last([b.close for b in bars[-(period * 4):]], period)


def rsi(bars: list[OHLCVBar], period: int = 14) -> float | None:
    """Relative Strength Index (0-100). <30 oversold, >70 overbought."""
    if len(bars) < period + 1:
        return None
    tail = bars[-(period + 1):]
    gains = losses = 0.0
    for i in range(1, len(tail)):
        d = tail[i].close - tail[i - 1].close
        gains += d if d > 0 else 0.0
        losses += -d if d < 0 else 0.0
    avg_l = losses / period
    if avg_l == 0:
        return 100.0
    rs = (gains / period) / avg_l
    return 100.0 - 100.0 / (1.0 + rs)


def macd(bars: list[OHLCVBar], fast: int = 12, slow: int = 26, signal: int = 9):
    """Return (macd_line, signal_line, histogram) latest, or None."""
    closes = [b.close for b in bars[-(slow * 4 + signal * 4):]]
    if len(closes) < slow + signal:
        return None
    line: list[float] = []
    for i in range(slow, len(closes) + 1):
        window = closes[:i]
        ef = _ema_last(window[-fast * 4:], fast)
        es = _ema_last(window[-slow * 4:], slow)
        if ef is not None and es is not None:
            line.append(ef - es)
    if len(line) < signal:
        return None
    sig = _ema_last(line, signal)
    hist = (line[-1] - sig) if sig is not None else None
    return line[-1], sig, hist


def bollinger_pctb(bars: list[OHLCVBar], period: int = 20, k: float = 2.0) -> float | None:
    """%b: 0 at lower band, 1 at upper band (can exceed). Below 0 = very oversold."""
    if len(bars) < period:
        return None
    closes = [b.close for b in bars[-period:]]
    mean = sum(closes) / period
    sd = (sum((c - mean) ** 2 for c in closes) / period) ** 0.5
    if sd == 0:
        return 0.5
    lower, upper = mean - k * sd, mean + k * sd
    return (bars[-1].close - lower) / (upper - lower)


def stochastic_k(bars: list[OHLCVBar], period: int = 14) -> float | None:
    """Stochastic %K (0-100). <20 oversold, >80 overbought."""
    if len(bars) < period:
        return None
    window = bars[-period:]
    hi = max(b.high for b in window)
    lo = min(b.low for b in window)
    if hi == lo:
        return 50.0
    return 100.0 * (bars[-1].close - lo) / (hi - lo)


def roc(bars: list[OHLCVBar], period: int) -> float | None:
    """Rate of change (trailing return) over `period` bars."""
    if len(bars) < period + 1:
        return None
    past = bars[-(period + 1)].close
    return (bars[-1].close / past - 1.0) if past > 0 else None


def returns_std(bars: list[OHLCVBar], period: int) -> float | None:
    """Std-dev of per-bar returns — a normalized volatility gauge for ranking setups."""
    if len(bars) < period + 1:
        return None
    closes = [b.close for b in bars[-(period + 1):]]
    rets = [
        (closes[i] - closes[i - 1]) / closes[i - 1]
        for i in range(1, len(closes))
        if closes[i - 1] > 0
    ]
    if not rets:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    return var ** 0.5
