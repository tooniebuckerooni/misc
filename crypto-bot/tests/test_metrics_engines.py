from __future__ import annotations

from src.config.settings import Settings
from src.core.types import Side, Ticker, TradeRecord
from src.data.feed import DataFeed
from src.data.store import Store
from src.engine.backtest import Backtester
from src.engine.paper import PaperEngine
from src.scanner.screener import Screener
from src.strategy.bracket_breakout import BracketBreakout
from src.trackers.metrics import compute_metrics

from helpers import FakeBroker


def _trade(net, fees=0.1):
    return TradeRecord("ETH/USD", Side.BUY, 1.0, 100.0, 100.0 + net, 0, 1,
                       fees=fees, gross_pnl=net + fees, net_pnl=net)


def test_metrics_gate():
    winners = [_trade(2.0), _trade(1.0)]
    losers = [_trade(-0.5)]
    m = compute_metrics(winners + losers)
    assert m.n_trades == 3
    assert m.gross_profit == 3.0
    assert m.gross_loss == 0.5
    assert m.passes_gate is True


def test_metrics_gate_fails_on_big_loss():
    # More wins than losses by count, but the loss is bigger => gate must FAIL.
    m = compute_metrics([_trade(1.0), _trade(1.0), _trade(-5.0)])
    assert m.win_rate > 0.5
    assert m.passes_gate is False


def _settings():
    s = Settings(_env_file=None)
    s.starting_working_capital = 200.0
    return s


def test_backtester_runs(tmp_path, bars):
    st = Store(tmp_path / "t.db")
    # Repeat the breakout pattern a few times so multiple trades occur.
    seq = []
    ts = 0
    for _ in range(4):
        for b in bars:
            b2 = type(b)(ts, b.open, b.high, b.low, b.close, b.volume)
            seq.append(b2)
            ts += 900_000
    st.upsert_candles("ETH/USD", "15m", seq)
    m = Backtester(st, BracketBreakout(), _settings(), ["ETH/USD"], "15m").run()
    assert m.n_trades >= 1
    assert m.fees_total > 0  # fees are actually being charged


def test_paper_engine_enter_then_tp(tmp_path, bars, tight_ticker):
    broker = FakeBroker({"ETH/USD": bars}, tight_ticker)
    st = Store(tmp_path / "t.db")
    feed = DataFeed(broker, st)
    s = _settings()
    strat = BracketBreakout()
    sc = Screener(feed, strat, universe=["ETH/USD"], timeframe="15m", lookback=200, top_n=5)
    eng = PaperEngine(feed, st, strat, s, screener=sc)

    now = 40 * 900_000
    r1 = eng.run_once(now_ts=now)
    assert len(eng.positions) == 1
    assert any("ENTER" in a for a in r1["actions"])

    pos = list(eng.positions.values())[0].pos
    broker.ticker = Ticker("ETH/USD", pos.tp_price + 0.5, pos.tp_price + 0.6, pos.tp_price + 0.55, now + 1)
    eng.run_once(now_ts=now + 900_000)
    trades = st.get_trades("paper")
    assert trades and trades[0].exit_reason == "take_profit"
    assert trades[0].net_pnl != 0.0


def test_paper_engine_kill_flattens(tmp_path, bars, tight_ticker):
    broker = FakeBroker({"ETH/USD": bars}, tight_ticker)
    st = Store(tmp_path / "t.db")
    feed = DataFeed(broker, st)
    s = _settings()
    strat = BracketBreakout()
    sc = Screener(feed, strat, universe=["ETH/USD"], timeframe="15m", lookback=200, top_n=5)
    eng = PaperEngine(feed, st, strat, s, screener=sc)
    eng.run_once(now_ts=40 * 900_000)
    assert len(eng.positions) == 1
    eng.rm.set_kill(True)
    eng.run_once(now_ts=41 * 900_000)
    assert len(eng.positions) == 0  # flattened
