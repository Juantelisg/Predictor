"""db.py - capa de PERSISTENCIA durable del loop (SQLite, un solo archivo). CERO cuotas-feature.

El loop sigue escribiendo JSONL (append-log legible, fuente de verdad). Esta capa los INGIERE
a un SQLite consultable y persistente (data/predictor.db) -> habilita ledger de bankroll (#2),
CLV (#3) y el panel de track-record sin re-parsear archivos cada vez.

SQLite = stdlib (no se instala nada) + un archivo (no hay servidor). sync() es idempotente
(INSERT OR REPLACE por PK), asi que correrlo N veces deja el mismo estado.

Uso:
  python db.py sync     # ingiere predictions/ evaluations/ bets/ bet_evals/ -> predictor.db
  python db.py stats    # conteos por tabla
"""
import os, sys, json, sqlite3, datetime

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "data", "predictor.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    date TEXT, sport TEXT, home TEXT, away TEXT, neutral INTEGER,
    market TEXT, prob REAL, model_version TEXT, ts TEXT,
    PRIMARY KEY (date, home, away, market, model_version)
);
CREATE TABLE IF NOT EXISTS evaluations (
    date TEXT, sport TEXT, home TEXT, away TEXT, market TEXT, model_version TEXT,
    prob REAL, result TEXT, outcome INTEGER, evaluated_at TEXT,
    PRIMARY KEY (date, home, away, market, model_version)
);
CREATE TABLE IF NOT EXISTS bets (
    date TEXT, home TEXT, away TEXT, side TEXT, p_model REAL, p_market REAL,
    edge REAL, odds REAL, tier TEXT, stake REAL, ts TEXT,
    PRIMARY KEY (date, home, away, side)
);
CREATE TABLE IF NOT EXISTS bet_evals (
    date TEXT, home TEXT, away TEXT, side TEXT, edge REAL, odds REAL, tier TEXT,
    stake REAL, result TEXT, won INTEGER, pnl REAL, pnl_flat REAL, evaluated_at TEXT,
    PRIMARY KEY (date, home, away, side)
);
-- snapshots de cuota para CLV (#3): la misma seleccion en distintos momentos (open/close)
CREATE TABLE IF NOT EXISTS odds_snapshots (
    date TEXT, home TEXT, away TEXT, side TEXT, decimal_odds REAL,
    provider TEXT, ts TEXT,
    PRIMARY KEY (date, home, away, side, ts)
);
CREATE INDEX IF NOT EXISTS ix_eval_market ON evaluations (market, model_version);
CREATE INDEX IF NOT EXISTS ix_betev_date ON bet_evals (date);
"""

# (tabla, dir, columnas, default_sport) — el sync mapea cada fila JSONL a estas columnas
_SPECS = {
    "predictions": ("predictions", ["date", "sport", "home", "away", "neutral", "market",
                                     "prob", "model_version", "ts"], "soccer"),
    "evaluations": ("evaluations", ["date", "sport", "home", "away", "market", "model_version",
                                    "prob", "result", "outcome", "evaluated_at"], None),
    "bets": ("bets", ["date", "home", "away", "side", "p_model", "p_market", "edge", "odds",
                      "tier", "stake", "ts"], None),
    "bet_evals": ("bet_evals", ["date", "home", "away", "side", "edge", "odds", "tier", "stake",
                                "result", "won", "pnl", "pnl_flat", "evaluated_at"], None),
}


def connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def _read_jsonl_dir(d):
    out = []
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".jsonl"):
            with open(os.path.join(d, fn), encoding="utf-8-sig") as f:   # tolera BOM de PowerShell
                out += [json.loads(ln) for ln in f if ln.strip()]
    return out


def _sport_of(row):
    """evaluations no trae 'sport'; se deriva del mercado (ml: -> mlb, resto soccer)."""
    if row.get("sport"):
        return row["sport"]
    return "mlb" if str(row.get("market", "")).startswith("ml:") else "soccer"


def sync(con=None):
    """Ingiere los 4 directorios JSONL al SQLite (idempotente). Devuelve conteos por tabla."""
    own = con is None
    con = con or connect()
    counts = {}
    for table, (dirname, cols, _) in _SPECS.items():
        rows = _read_jsonl_dir(os.path.join(ROOT, dirname))
        placeholders = ",".join("?" * len(cols))
        tuples = []
        for r in rows:
            r = dict(r)
            if "sport" in cols:
                r["sport"] = _sport_of(r)
            tuples.append(tuple(r.get(c) for c in cols))
        if tuples:
            con.executemany(f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) "
                            f"VALUES ({placeholders})", tuples)
        counts[table] = len(tuples)
    con.commit()
    if own:
        con.close()
    return counts


def query(sql, params=(), con=None):
    own = con is None
    con = con or connect()
    rows = [dict(r) for r in con.execute(sql, params).fetchall()]
    if own:
        con.close()
    return rows


def stats(con=None):
    own = con is None
    con = con or connect()
    out = {}
    for table in _SPECS:
        out[table] = con.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
    out["odds_snapshots"] = con.execute("SELECT COUNT(*) AS n FROM odds_snapshots").fetchone()["n"]
    if own:
        con.close()
    return out


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if cmd == "sync":
        c = sync()
        print(f"  sync -> {DB_PATH}")
        for t, n in c.items():
            print(f"    {t:<14} {n:>5} filas")
    else:
        s = stats()
        print(f"  {DB_PATH}")
        for t, n in s.items():
            print(f"    {t:<16} {n:>5} filas")


if __name__ == "__main__":
    main()
