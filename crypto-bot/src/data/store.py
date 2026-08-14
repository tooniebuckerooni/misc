"""SQLite persistence: candle cache, trade ledger, equity/vault snapshots, sweep log,
and a small key/value store for runtime state (base, daily-loss tracking, kill flag).

One file on the local machine — no server to run. All timestamps are epoch milliseconds.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator

from ..core.types import OHLCVBar, Side, TradeRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS candles (
    symbol    TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    ts        INTEGER NOT NULL,
    open      REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (symbol, timeframe, ts)
);

CREATE TABLE IF NOT EXISTS trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    mode        TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    side        TEXT NOT NULL,
    amount      REAL NOT NULL,
    entry_price REAL NOT NULL,
    exit_price  REAL NOT NULL,
    opened_ts   INTEGER NOT NULL,
    closed_ts   INTEGER NOT NULL,
    fees        REAL NOT NULL,
    gross_pnl   REAL NOT NULL,
    net_pnl     REAL NOT NULL,
    exit_reason TEXT,
    extra       TEXT
);

CREATE TABLE IF NOT EXISTS equity_snapshots (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             INTEGER NOT NULL,
    mode           TEXT NOT NULL,
    working_equity REAL NOT NULL,
    base           REAL NOT NULL,
    vault          REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sweeps (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            INTEGER NOT NULL,
    mode          TEXT NOT NULL,
    profit        REAL NOT NULL,
    swept         REAL NOT NULL,
    working_after REAL NOT NULL,
    new_base      REAL NOT NULL,
    vault_after   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Store:
    def __init__(self, db_path: Path | str):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---- Candle cache ------------------------------------------------------
    def upsert_candles(self, symbol: str, timeframe: str, bars: Iterable[OHLCVBar]) -> int:
        rows = [
            (symbol, timeframe, b.ts, b.open, b.high, b.low, b.close, b.volume) for b in bars
        ]
        if not rows:
            return 0
        with self._conn() as c:
            c.executemany(
                "INSERT OR REPLACE INTO candles "
                "(symbol,timeframe,ts,open,high,low,close,volume) "
                "VALUES (?,?,?,?,?,?,?,?)",
                rows,
            )
        return len(rows)

    def get_candles(
        self, symbol: str, timeframe: str, since: int | None = None, limit: int | None = None
    ) -> list[OHLCVBar]:
        q = "SELECT ts,open,high,low,close,volume FROM candles WHERE symbol=? AND timeframe=?"
        args: list = [symbol, timeframe]
        if since is not None:
            q += " AND ts>=?"
            args.append(since)
        q += " ORDER BY ts ASC"
        if limit is not None:
            q += " LIMIT ?"
            args.append(limit)
        with self._conn() as c:
            rows = c.execute(q, args).fetchall()
        return [OHLCVBar(r["ts"], r["open"], r["high"], r["low"], r["close"], r["volume"]) for r in rows]

    def last_candle_ts(self, symbol: str, timeframe: str) -> int | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT MAX(ts) AS m FROM candles WHERE symbol=? AND timeframe=?",
                (symbol, timeframe),
            ).fetchone()
        return row["m"] if row and row["m"] is not None else None

    # ---- Trade ledger ------------------------------------------------------
    def record_trade(self, mode: str, t: TradeRecord) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO trades "
                "(mode,symbol,side,amount,entry_price,exit_price,opened_ts,closed_ts,"
                "fees,gross_pnl,net_pnl,exit_reason,extra) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    mode, t.symbol, t.side.value, t.amount, t.entry_price, t.exit_price,
                    t.opened_ts, t.closed_ts, t.fees, t.gross_pnl, t.net_pnl,
                    t.exit_reason, json.dumps(t.extra),
                ),
            )

    def get_trades(self, mode: str | None = None) -> list[TradeRecord]:
        q = "SELECT * FROM trades"
        args: list = []
        if mode:
            q += " WHERE mode=?"
            args.append(mode)
        q += " ORDER BY closed_ts ASC"
        with self._conn() as c:
            rows = c.execute(q, args).fetchall()
        out = []
        for r in rows:
            out.append(
                TradeRecord(
                    symbol=r["symbol"], side=Side(r["side"]), amount=r["amount"],
                    entry_price=r["entry_price"], exit_price=r["exit_price"],
                    opened_ts=r["opened_ts"], closed_ts=r["closed_ts"], fees=r["fees"],
                    gross_pnl=r["gross_pnl"], net_pnl=r["net_pnl"],
                    exit_reason=r["exit_reason"] or "",
                    extra=json.loads(r["extra"]) if r["extra"] else {},
                )
            )
        return out

    # ---- Snapshots & sweeps ------------------------------------------------
    def snapshot_equity(
        self, ts: int, mode: str, working_equity: float, base: float, vault: float
    ) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO equity_snapshots (ts,mode,working_equity,base,vault) "
                "VALUES (?,?,?,?,?)",
                (ts, mode, working_equity, base, vault),
            )

    def get_equity_curve(self, mode: str | None = None) -> list[dict]:
        q = "SELECT ts,working_equity,base,vault FROM equity_snapshots"
        args: list = []
        if mode:
            q += " WHERE mode=?"
            args.append(mode)
        q += " ORDER BY ts ASC"
        with self._conn() as c:
            return [dict(r) for r in c.execute(q, args).fetchall()]

    def record_sweep(
        self, ts: int, mode: str, profit: float, swept: float,
        working_after: float, new_base: float, vault_after: float,
    ) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO sweeps (ts,mode,profit,swept,working_after,new_base,vault_after) "
                "VALUES (?,?,?,?,?,?,?)",
                (ts, mode, profit, swept, working_after, new_base, vault_after),
            )

    def get_sweeps(self, mode: str | None = None) -> list[dict]:
        q = "SELECT * FROM sweeps"
        args: list = []
        if mode:
            q += " WHERE mode=?"
            args.append(mode)
        q += " ORDER BY ts ASC"
        with self._conn() as c:
            return [dict(r) for r in c.execute(q, args).fetchall()]

    # ---- Key/value runtime state ------------------------------------------
    def set_state(self, key: str, value) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO kv (key,value) VALUES (?,?)",
                (key, json.dumps(value)),
            )

    def get_state(self, key: str, default=None):
        with self._conn() as c:
            row = c.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default
