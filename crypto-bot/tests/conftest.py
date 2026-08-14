from __future__ import annotations

import pytest

from helpers import make_flat_then_breakout
from src.core.types import Ticker


@pytest.fixture
def bars():
    return make_flat_then_breakout()


@pytest.fixture
def tight_ticker():
    ts = 40 * 900_000
    return Ticker("ETH/USD", 105.98, 106.02, 106.0, ts)
