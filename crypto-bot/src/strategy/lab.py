"""The Strategy Lab — a broad, fully-tunable composite you shape over time.

Philosophy: assume nothing. It blends many indicators — some momentum-flavoured (trend, MACD, ROC,
Donchian, SuperTrend), some mean-reversion-flavoured (RSI, Bollinger, Stochastic) — each producing a
signal in [-1,+1] (+1 = bullish). At equal default weights these partly cancel, so out of the box the
lab is a *neutral canvas*: you lean it by turning knobs (weights/periods/enables) in a JSON config, and
you can blend in any external `SignalSource` (sentiment, reverse-Cramer, on-chain…). Long-only spot.

Every parameter lives in `LabConfig` and is loadable from JSON — see `configs/lab.example.json` and
`docs/LAB.md`. Nothing here is tuned to win; it's the bench where YOU make it win.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..core.indicators import (
    atr, bollinger_pctb, donchian, ema, macd, roc, rsi, sma, stochastic_k, supertrend,
)
from ..core.indicators import adx as adx_ind
from ..core.types import Bracket, OHLCVBar, Side, Ticker
from ..signals.base import SignalSource
from .base import Strategy


def _clamp(x: float) -> float:
    return max(-1.0, min(1.0, x))


@dataclass
class LabConfig:
    # ---- Signal toggles + weights (weight can be negative to FADE a signal) ----
    use_trend: bool = True;        w_trend: float = 1.0;  ema_fast: int = 12;  ema_slow: int = 26
    use_rsi: bool = True;          w_rsi: float = 1.0;    rsi_period: int = 14
    use_macd: bool = True;         w_macd: float = 1.0;   macd_fast: int = 12; macd_slow: int = 26; macd_signal: int = 9
    use_bollinger: bool = True;    w_bollinger: float = 1.0; bb_period: int = 20; bb_k: float = 2.0
    use_stochastic: bool = True;   w_stochastic: float = 1.0; stoch_period: int = 14
    use_roc: bool = True;          w_roc: float = 1.0;    roc_period: int = 20; roc_scale: float = 0.10
    use_donchian: bool = True;     w_donchian: float = 1.0; donchian_period: int = 20
    use_supertrend: bool = True;   w_supertrend: float = 1.0; st_period: int = 10; st_mult: float = 3.0

    # ---- Confidence / gating ----
    use_volume: bool = True;       volume_period: int = 20    # scales conviction, not direction
    use_adx_gate: bool = False;    adx_period: int = 14;  adx_min: float = 0.0  # 0 = no gate

    # ---- External signal sources (added in code; this is their overall blend weight) ----
    external_weight: float = 1.0

    # ---- Entry / exit ----
    entry_threshold: float = 0.15   # go long when the blended score >= this
    atr_period: int = 14;  tp_atr_mult: float = 2.5;  sl_atr_mult: float = 1.5;  min_rr: float = 1.0

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def from_dict(cls, d: dict) -> "LabConfig":
        known = {f for f in cls().__dict__}
        return cls(**{k: v for k, v in d.items() if k in known})

    @classmethod
    def from_json(cls, path: str | Path) -> "LabConfig":
        return cls.from_dict(json.loads(Path(path).read_text()))


class LabStrategy(Strategy):
    name = "lab"

    def __init__(self, config: LabConfig | None = None,
                 sources: list[tuple[SignalSource, float]] | None = None):
        self.c = config or LabConfig()
        self.sources = sources or []  # list of (SignalSource, weight)

    def _technical_signals(self, bars: list[OHLCVBar]) -> list[tuple[float, float]]:
        """Return list of (signal[-1,1], weight) from enabled indicators."""
        c = self.c
        close = bars[-1].close
        out: list[tuple[float, float]] = []

        if c.use_trend:
            ef, es = ema(bars, c.ema_fast), ema(bars, c.ema_slow)
            if ef and es and es > 0:
                out.append((_clamp((ef / es - 1) / 0.02), c.w_trend))  # +1 ~ fast 2% above slow
        if c.use_rsi:
            r = rsi(bars, c.rsi_period)
            if r is not None:
                out.append((_clamp((50 - r) / 50), c.w_rsi))           # oversold -> bullish
        if c.use_macd:
            m = macd(bars, c.macd_fast, c.macd_slow, c.macd_signal)
            if m and m[2] is not None and close > 0:
                out.append((_clamp((m[2] / close) / 0.01), c.w_macd))  # hist>0 -> bullish
        if c.use_bollinger:
            b = bollinger_pctb(bars, c.bb_period, c.bb_k)
            if b is not None:
                out.append((_clamp(1 - 2 * b), c.w_bollinger))         # at/below lower band -> bullish
        if c.use_stochastic:
            k = stochastic_k(bars, c.stoch_period)
            if k is not None:
                out.append((_clamp((50 - k) / 50), c.w_stochastic))
        if c.use_roc:
            rc = roc(bars, c.roc_period)
            if rc is not None:
                out.append((_clamp(rc / c.roc_scale), c.w_roc))        # rising -> bullish
        if c.use_donchian:
            ch = donchian(bars, c.donchian_period)
            if ch is not None:
                s = 1.0 if close > ch[0] else (-1.0 if close < ch[1] else 0.0)
                out.append((s, c.w_donchian))
        if c.use_supertrend:
            direction, _ = supertrend(bars, c.st_period, c.st_mult)
            if direction and direction[-1] != 0:
                out.append((float(direction[-1]), c.w_supertrend))
        return out

    def _volume_conviction(self, bars: list[OHLCVBar]) -> float:
        if not self.c.use_volume or len(bars) < self.c.volume_period:
            return 1.0
        window = bars[-self.c.volume_period:]
        avg = sum(b.volume for b in window) / len(window)
        if avg <= 0:
            return 1.0
        return max(0.5, min(1.5, bars[-1].volume / avg))  # heavier volume -> more conviction

    def evaluate(
        self, symbol: str, bars: list[OHLCVBar], ticker: Ticker | None = None
    ) -> Bracket | None:
        c = self.c
        need = max(c.ema_slow, c.macd_slow + c.macd_signal, c.bb_period, c.donchian_period,
                   c.st_period, c.atr_period, c.roc_period, 2 * c.adx_period) + 3
        if len(bars) < need:
            return None

        # Optional trend-strength gate.
        if c.use_adx_gate and c.adx_min > 0:
            a = adx_ind(bars, c.adx_period)
            if a is None or a < c.adx_min:
                return None

        signals = self._technical_signals(bars)
        num = sum(s * w for s, w in signals)
        den = sum(abs(w) for _, w in signals)

        # External sources (sentiment / reverse-Cramer / etc.) blended in.
        ts = bars[-1].ts
        for src, w in self.sources:
            try:
                v = src.value(symbol, ts)
            except Exception:
                v = 0.0
            num += c.external_weight * w * v
            den += c.external_weight * abs(w)

        if den == 0:
            return None
        composite = _clamp(num / den) * self._volume_conviction(bars)

        if composite < c.entry_threshold:
            return None

        a = atr(bars, c.atr_period)
        if a is None or a <= 0:
            return None
        entry = ticker.ask if (ticker and ticker.ask > 0) else bars[-1].close
        tp = entry + c.tp_atr_mult * a
        sl = entry - c.sl_atr_mult * a
        if sl <= 0 or tp <= entry:
            return None

        bracket = Bracket(
            symbol=symbol, side=Side.BUY, entry_price=entry, tp_price=tp, sl_price=sl,
            score=round(composite, 4),
            reason=f"lab composite {composite:+.2f} >= {c.entry_threshold} ({len(signals)} signals)",
        )
        return bracket if bracket.rr_ratio() >= c.min_rr else None
