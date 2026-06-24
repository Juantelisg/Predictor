"""Persistencia: sync() es idempotente (correrlo dos veces no duplica filas)."""
import sqlite3
import db


def _mem_con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(db.SCHEMA)
    return con


def _counts(con):
    return {t: con.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"]
            for t in ("predictions", "evaluations", "bets", "bet_evals")}


def test_sync_idempotent():
    con = _mem_con()
    db.sync(con)
    c1 = _counts(con)
    db.sync(con)               # segunda corrida: REPLACE por PK -> mismos conteos
    c2 = _counts(con)
    assert c1 == c2


def test_sync_loads_predictions():
    con = _mem_con()
    db.sync(con)
    assert _counts(con)["predictions"] > 0     # hay data real del loop en predictions/


def test_schema_has_odds_snapshots():
    con = _mem_con()
    tables = {r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "odds_snapshots" in tables
