"""clv.py - Closing Line Value: medimos si le ganamos al CIERRE del mercado. CERO feature.

CLV es el indicador LIDER de edge y el de MENOR varianza: si tomas un precio mejor que el de
cierre de forma consistente, tu edge es real aunque los resultados todavia no se acumulen.
Es METRICA DE VALIDACION, no input del modelo (no viola el guardrail de "cuotas nunca feature").

Como funciona: snapshot() guarda la cuota 1X2 actual de cada partido (odds_snapshots). Corriendo
en el loop, el ULTIMO snapshot antes del inicio ~= cierre. report() compara, por cada apuesta
logueada, el precio que tomamos vs ese cierre (en precio y en prob de-vigeada).

Honesto: ESPN pickcenter = una casa (DraftKings), y "cierre" = ultimo snapshot que alcanzamos a
tomar, no el cierre oficial. El CLV se ACUMULA desde que el loop empieza a snapshotear (no es
retroactivo: ESPN free no da cuotas historicas).

Uso:
  python clv.py snapshot [fecha]   # guarda las cuotas actuales (correr en el loop)
  python clv.py report             # CLV de las apuestas con cierre capturado
"""
import os, sys, datetime
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db, odds, edge


def snapshot(date=None, con=None):
    """Guarda la cuota 1X2 actual de los partidos de `date` (3 filas por partido)."""
    date = date or datetime.date.today().isoformat()
    own = con is None
    con = con or db.connect()
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    n = 0
    for ev in odds._events(date):
        cs = {c["homeAway"]: c["team"]["displayName"] for c in ev["competitions"][0]["competitors"]}
        home, away = cs.get("home", ""), cs.get("away", "")
        od = odds.wc_1x2(home, away, date)
        if not od:
            continue
        for side in ("home", "draw", "away"):
            con.execute("INSERT OR REPLACE INTO odds_snapshots "
                        "(date, home, away, side, decimal_odds, provider, ts) VALUES (?,?,?,?,?,?,?)",
                        (date, home, away, side, od[side], od.get("provider", "?"), ts))
            n += 1
    con.commit()
    if own:
        con.close()
    print(f"  snapshot {date}: {n} cuotas guardadas (ts {ts})")
    return n


def _closing(date, home, away, con):
    """Ultimo snapshot (cierre) de cada lado de un partido. None si no hay snapshots."""
    rows = db.query("SELECT side, decimal_odds, ts FROM odds_snapshots "
                    "WHERE date=? AND home=? AND away=? ORDER BY ts", (date, home, away), con=con)
    if not rows:
        return None
    close = {}
    for r in rows:                          # ts ascendente -> el ultimo de cada lado queda
        close[r["side"]] = r["decimal_odds"]
    return close if {"home", "draw", "away"} <= set(close) else None


def clv_rows(con=None):
    own = con is None
    con = con or db.connect()
    bets = db.query("SELECT date, home, away, side, odds, p_market FROM bets", con=con)
    out = []
    for b in bets:
        close = _closing(b["date"], b["home"], b["away"], con)
        if not close:
            continue
        side_close = close[b["side"]]
        p_close = edge.devig([close["home"], close["draw"], close["away"]])
        idx = {"home": 0, "draw": 1, "away": 2}[b["side"]]
        out.append({"date": b["date"], "home": b["home"], "away": b["away"], "side": b["side"],
                    "odds_taken": b["odds"], "odds_close": side_close,
                    "p_market_open": b["p_market"], "p_market_close": round(p_close[idx], 4),
                    "clv_prob": round(p_close[idx] - b["p_market"], 4),     # + = el mercado se movio a favor
                    "beat_close": int(b["odds"] > side_close)})
    if own:
        con.close()
    return out


def report(con=None):
    rows = clv_rows(con)
    print("=" * 70)
    print("  CLOSING LINE VALUE  (precio tomado vs cierre · ESPN/DraftKings)")
    print("=" * 70)
    if not rows:
        print("  Sin apuestas con cierre capturado todavia. El CLV se acumula desde que el loop")
        print("  empieza a snapshotear cuotas (clv.snapshot corre en loop.py). No es retroactivo.")
        return
    beat = sum(r["beat_close"] for r in rows)
    avg_clv = sum(r["clv_prob"] for r in rows) / len(rows)
    print(f"  {len(rows)} apuestas con cierre  |  le ganamos al cierre: {beat}/{len(rows)} "
          f"({beat/len(rows)*100:.0f}%)  |  CLV medio {avg_clv*100:+.2f} pts\n")
    print(f"  {'partido':<34}{'lado':<6}{'tomada':>7}{'cierre':>8}{'CLV':>8}")
    for r in rows:
        m = f"{r['home'][:15]} v {r['away'][:13]}"
        flag = " *" if r["beat_close"] else ""
        print(f"  {m:<34}{r['side']:<6}{r['odds_taken']:>7.2f}{r['odds_close']:>8.2f}"
              f"{r['clv_prob']*100:>+7.1f}%{flag}")
    print("\n  CLV+ consistente = edge real (senal de menor varianza que win/lost). Metrica, no feature.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "snapshot":
        snapshot(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        report()


if __name__ == "__main__":
    main()
