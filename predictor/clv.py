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
    """Ultimo snapshot (cierre) de cada lado + cuantos ts distintos hay. None si no hay snapshots.
    n_snaps = timestamps distintos: con 1 solo, 'cierre' == 'apertura' y el CLV es trivialmente 0."""
    rows = db.query("SELECT side, decimal_odds, ts FROM odds_snapshots "
                    "WHERE date=? AND home=? AND away=? ORDER BY ts", (date, home, away), con=con)
    if not rows:
        return None
    close, ts_seen = {}, set()
    for r in rows:                          # ts ascendente -> el ultimo de cada lado queda
        close[r["side"]] = r["decimal_odds"]
        ts_seen.add(r["ts"])
    if not {"home", "draw", "away"} <= set(close):
        return None
    close["_n_snaps"] = len(ts_seen)
    return close


def clv_rows(con=None):
    own = con is None
    con = con or db.connect()
    bets = db.query("SELECT date, home, away, side, odds, p_market, edge_version FROM bets", con=con)
    out = []
    for b in bets:
        close = _closing(b["date"], b["home"], b["away"], con)
        if not close:
            continue
        side_close = close[b["side"]]
        p_close = edge.devig([close["home"], close["draw"], close["away"]])
        idx = {"home": 0, "draw": 1, "away": 2}[b["side"]]
        out.append({"date": b["date"], "home": b["home"], "away": b["away"], "side": b["side"],
                    "edge_version": b["edge_version"] or "edge-v1",
                    "n_snaps": close["_n_snaps"],
                    "odds_taken": b["odds"], "odds_close": side_close,
                    "p_market_open": b["p_market"], "p_market_close": round(p_close[idx], 4),
                    "clv_prob": round(p_close[idx] - b["p_market"], 4),     # + = el mercado se movio a favor
                    "beat_close": int(b["odds"] > side_close)})
    if own:
        con.close()
    return out


def _clv_summary(rows, label):
    """Linea resumen de un subconjunto: cuantas con movimiento real (n_snaps>=2), le-gana-al-cierre, CLV medio."""
    real = [r for r in rows if r["n_snaps"] >= 2]
    if not real:
        print(f"  {label:<22} sin cierre real todavia ({len(rows)} con 1 solo snapshot = CLV trivial 0)")
        return
    beat = sum(r["beat_close"] for r in real)
    avg = sum(r["clv_prob"] for r in real) / len(real)
    print(f"  {label:<22} {len(real):>3} con movimiento real  |  gana al cierre {beat}/{len(real)} "
          f"({beat/len(real)*100:.0f}%)  |  CLV medio {avg*100:+.2f} pts")


def report(con=None):
    rows = clv_rows(con)
    print("=" * 74)
    print("  CLOSING LINE VALUE  (precio tomado vs cierre · ESPN/DraftKings)")
    print("=" * 74)
    if not rows:
        print("  Sin apuestas con cierre capturado todavia. El CLV se acumula desde que el loop")
        print("  empieza a snapshotear cuotas (clv.snapshot corre en loop.py + tarea programada).")
        return
    real = [r for r in rows if r["n_snaps"] >= 2]
    print(f"  {len(rows)} apuestas con snapshot  |  {len(real)} con CIERRE REAL (>=2 snapshots a distinto ts)")
    print(f"  (cierre real / total = {len(real)/len(rows)*100:.0f}%; sin cadencia esto es ~0 -> tarea programada)\n")
    _clv_summary(rows, "TODAS")
    for v in sorted({r["edge_version"] for r in rows}):
        _clv_summary([r for r in rows if r["edge_version"] == v], v)
    print(f"\n  {'partido':<34}{'lado':<6}{'snaps':>6}{'tomada':>8}{'cierre':>8}{'CLV':>8}")
    for r in sorted(rows, key=lambda x: (-x["n_snaps"], x["date"])):
        m = f"{r['home'][:15]} v {r['away'][:13]}"
        flag = " *" if r["beat_close"] and r["n_snaps"] >= 2 else ""
        print(f"  {m:<34}{r['side']:<6}{r['n_snaps']:>6}{r['odds_taken']:>8.2f}{r['odds_close']:>8.2f}"
              f"{r['clv_prob']*100:>+7.1f}%{flag}")
    print("\n  CLV+ consistente = edge real (senal de menor varianza que win/lost). Metrica, no feature.")
    print("  Solo cuentan las de >=2 snapshots: con 1, cierre==apertura y el CLV es 0 por construccion.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "snapshot":
        snapshot(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        report()


if __name__ == "__main__":
    main()
