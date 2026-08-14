"""Fee-aware Kraken crypto trading bot.

BTC is the vault and scoreboard; working capital churns across scanner-selected pairs
via methodical, pre-defined bracket trades. Runs in backtest / paper / live modes
through a single shared strategy interface.
"""

__version__ = "0.1.0"
