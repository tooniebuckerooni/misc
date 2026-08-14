"""Central configuration.

All tunables live here so behaviour never depends on hard-coded magic numbers scattered
through the code. Loaded from environment / .env via pydantic-settings; safe defaults are
deliberately conservative (paper mode, small caps).
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Mode(str, Enum):
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


# Project root = crypto-bot/ (two levels up from this file: src/config/settings.py)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_prefix="",
        extra="ignore",
    )

    # ---- Credentials / mode ------------------------------------------------
    kraken_api_key: str = Field(default="", alias="KRAKEN_API_KEY")
    kraken_api_secret: str = Field(default="", alias="KRAKEN_API_SECRET")
    mode: Mode = Field(default=Mode.PAPER, alias="BOT_MODE")
    notify_webhook: str = Field(default="", alias="BOT_NOTIFY_WEBHOOK")

    # ---- Storage -----------------------------------------------------------
    db_path: Path = DATA_DIR / "bot.db"
    kill_switch_file: Path = PROJECT_ROOT / "KILL_SWITCH"

    # ---- Fees (Kraken entry volume tier; fractions, not percent) -----------
    # Uniform across most pairs; the real per-pair cost variance is spread/slippage.
    maker_fee: float = 0.0016  # 0.16%
    taker_fee: float = 0.0026  # 0.26%

    # ---- Scanner -----------------------------------------------------------
    # Pairs the scanner is allowed to consider. Empty => discover liquid pairs at runtime.
    pair_universe: list[str] = Field(default_factory=list)
    timeframe: str = "15m"
    scan_lookback_bars: int = 200
    # Reject a candidate if the estimated round-trip cost (fee+spread+slippage) exceeds this.
    max_round_trip_cost: float = 0.006  # 0.6%
    top_n_candidates: int = 5  # act on at most N best-ranked setups per scan

    # ---- Strategy (bracket breakout) --------------------------------------
    breakout_channel_bars: int = 20      # Donchian window
    take_profit_atr_mult: float = 2.0    # TP distance in ATR units
    stop_loss_atr_mult: float = 1.0      # SL distance in ATR units
    atr_bars: int = 14
    prefer_maker: bool = True            # post-only limit entries when possible

    # ---- Capital model -----------------------------------------------------
    # Amounts are in the accounting/quote unit used by the backtester (e.g. USD-equiv or
    # BTC-equiv). Live sizing is derived from actual balances.
    starting_working_capital: float = 200.0
    sweep_trigger_multiple: float = 2.0  # sweep when working equity >= multiple * base
    sweep_profit_fraction: float = 0.5   # fraction of profit moved to the BTC vault

    # ---- Risk guardrails ---------------------------------------------------
    max_open_positions: int = 3
    max_position_frac: float = 0.34      # max fraction of working equity per position
    max_position_abs: float = 100.0      # hard absolute cap per position
    max_daily_loss_frac: float = 0.10    # halt for the day after this drawdown of working equity
    min_notional: float = 5.0            # skip trades smaller than this (exchange minimums / dust)

    # ---- Backtest realism --------------------------------------------------
    # OHLCV has no bid/ask, so we assume a spread when simulating fills. Keep it honest.
    backtest_spread_frac: float = 0.001  # 0.10% assumed spread in backtest

    def ensure_dirs(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
