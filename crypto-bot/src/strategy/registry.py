"""Strategy registry — one place to build any lead by name.

Gives each lead its own runnable pipeline (CLI --strategy, research tools) and defines the
default regime router mapping derived from the per-season analysis. Presets here reflect the
best configs found so far; tune in one place.
"""

from __future__ import annotations

from ..config.settings import PROJECT_ROOT, Settings
from ..regime.classifier import RegimeClassifier, Season
from .base import Strategy
from .bracket_breakout import BracketBreakout
from .kalman_supertrend import KalmanSuperTrend
from .lab import LabConfig, LabStrategy
from .mean_reversion import MeanReversion
from .momentum import Momentum
from .router import RegimeRouter

STRATEGY_NAMES = ["breakout", "meanrev", "kalman", "momentum", "lab", "router"]


def _load_lab_sources():
    """Load external SignalSources from an optional drop-in file: configs/lab_sources.py

    That file (if present) must define get_sources() -> list[(SignalSource, weight)]. This lets you
    wire 'unexpected' data (sentiment, reverse-Cramer, on-chain…) without touching core code.
    """
    path = PROJECT_ROOT / "configs" / "lab_sources.py"
    if not path.exists():
        return []
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("lab_sources", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return list(mod.get_sources()) if hasattr(mod, "get_sources") else []
    except Exception as e:  # noqa: BLE001
        print(f"[lab] could not load configs/lab_sources.py: {e}")
        return []


def build_strategy(name: str, settings: Settings) -> Strategy:
    name = name.lower()
    if name == "breakout":
        return BracketBreakout(
            channel_bars=settings.breakout_channel_bars,
            atr_bars=settings.atr_bars,
            tp_atr_mult=settings.take_profit_atr_mult,
            sl_atr_mult=settings.stop_loss_atr_mult,
        )
    if name == "meanrev":
        # Daily "buy capitulation" preset — our validated lead: +152 over 20 pairs, 4/5 folds.
        return MeanReversion(ma_bars=30, entry_z=2.0, sl_sd=3.0)
    if name == "kalman":
        return KalmanSuperTrend(
            st_mult=3.0, adx_threshold=25, tp_atr_mult=3.0, sl_atr_mult=1.0, require_flip=True
        )
    if name == "momentum":
        return Momentum(mom_bars=30, trend_ma=50, min_return=0.10, tp_atr_mult=3.0, sl_atr_mult=2.0)
    if name == "lab":
        # Your tuning bench. Edit configs/lab.json to adjust; falls back to broad neutral defaults.
        cfg_path = PROJECT_ROOT / "configs" / "lab.json"
        cfg = LabConfig.from_json(cfg_path) if cfg_path.exists() else LabConfig()
        return LabStrategy(cfg, sources=_load_lab_sources())
    if name == "router":
        # Season label -> specialist, from the regime analysis (FINDINGS.md).
        mapping = {
            Season.BULL.value: build_strategy("kalman", settings),    # trend up -> trend-follow
            Season.RANGE.value: build_strategy("breakout", settings),  # chop -> breakout
            Season.BEAR.value: build_strategy("meanrev", settings),    # downtrend/crash -> buy dips
        }
        return RegimeRouter(RegimeClassifier(), mapping)
    raise ValueError(f"Unknown strategy '{name}'. Choose from: {', '.join(STRATEGY_NAMES)}")
