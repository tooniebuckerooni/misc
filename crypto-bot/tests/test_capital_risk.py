from __future__ import annotations

from src.capital.manager import CapitalManager
from src.data.store import Store
from src.risk.guardrails import RiskManager


def test_sweep_matches_example(tmp_path):
    st = Store(tmp_path / "t.db")
    cm = CapitalManager(st, "backtest", 200.0, trigger_multiple=2.0, profit_fraction=0.5)
    sweep = cm.realize(200.0, 1000)  # 200 -> 400 => bank 100, carry 300
    assert sweep is not None
    assert sweep.swept == 100.0
    assert cm.working == 300.0
    assert cm.vault == 100.0
    assert cm.base == 300.0


def test_no_sweep_below_trigger(tmp_path):
    st = Store(tmp_path / "t.db")
    cm = CapitalManager(st, "backtest", 200.0)
    assert cm.realize(50.0, 1000) is None
    assert cm.working == 250.0
    assert cm.vault == 0.0


def test_capital_persists(tmp_path):
    db = tmp_path / "t.db"
    cm = CapitalManager(Store(db), "paper", 200.0)
    cm.realize(30.0, 1000)
    reloaded = CapitalManager(Store(db), "paper", 200.0)
    assert reloaded.working == 230.0


def test_risk_sizing_and_caps(tmp_path):
    st = Store(tmp_path / "t.db")
    rm = RiskManager(st, "paper", kill_switch_file=tmp_path / "K",
                     max_open_positions=3, max_position_frac=0.34, max_position_abs=100.0,
                     max_daily_loss_frac=0.10, min_notional=5.0)
    d = rm.evaluate_entry(1000, 0, 300.0, 100.0)
    assert d.allowed and abs(d.amount * 100.0 - 100.0) < 1e-9  # abs cap binds at 100
    assert not rm.evaluate_entry(1000, 3, 300.0, 100.0).allowed  # max positions


def test_daily_loss_halt(tmp_path):
    st = Store(tmp_path / "t.db")
    rm = RiskManager(st, "paper", kill_switch_file=tmp_path / "K", max_daily_loss_frac=0.10)
    assert rm.daily_loss_halted(1000, 300.0) is False  # sets baseline 300
    assert rm.daily_loss_halted(2000, 260.0) is True   # -13% > 10%


def test_is_stale_fails_closed(tmp_path):
    st = Store(tmp_path / "t.db")
    rm = RiskManager(st, "paper", kill_switch_file=tmp_path / "K")
    max_age = 3 * 900_000  # 3 x 15m bars
    now = 100 * 900_000
    assert rm.is_stale(now, None, max_age) is True           # missing -> stale
    assert rm.is_stale(now, now - 10 * 900_000, max_age) is True   # 10 bars old -> stale
    assert rm.is_stale(now, now - 1 * 900_000, max_age) is False   # 1 bar old -> fresh
    assert rm.is_stale(now, 0, max_age) is False              # unknown ts -> usable (backtest path)


def test_kill_switch(tmp_path):
    st = Store(tmp_path / "t.db")
    ksf = tmp_path / "K"
    rm = RiskManager(st, "paper", kill_switch_file=ksf)
    assert not rm.kill_switch_active()
    rm.set_kill(True)
    assert rm.kill_switch_active() and ksf.exists()
    assert not rm.evaluate_entry(1000, 0, 300.0, 100.0).allowed
    rm.set_kill(False)
    assert not rm.kill_switch_active() and not ksf.exists()
