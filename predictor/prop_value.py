"""prop_value.py - maquina +EV multi-book de props de jugador (la fuente de valor #1 del audit).

El edge NO sale de saberle mas al mercado: sale de que los ~14 books que trae Linemate DISCREPAN
entre si. La fair de consenso (mediana de-vigeada de los books de dos lados) es una estimacion
robusta de la prob real; cuando UN book ofrece un precio que supera esa fair por un margen, hay
+EV aritmetico -- el modelo de OddsJam. Se corrobora con el hit-rate propio (Beta-Binomial shrunk)
para no apostar contra nuestra propia evidencia (regla de 2 senales del CLAUDE.md).

Guardrail: la cuota es INSUMO DE VALOR, jamas feature del modelo. Esto no toca el motor (soccer.py)
ni la calibracion; es una capa de mercado pura sobre datos gratis de Linemate.

Uso:
  python prop_value.py wc              # tabla de props con fair de consenso, mejor book y +EV de hoy
  python prop_value.py log [fecha]     # loguea TODOS los flags del dia -> props_flags/  (forward-test)
  python prop_value.py report          # ROI de los flags resueltos por familia de prop y por book
"""
import os, sys, json, statistics, datetime
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import edge

ROOT = os.path.dirname(os.path.abspath(__file__))
FLAGS_DIR = os.path.join(ROOT, "props_flags")
EVAL_DIR = os.path.join(ROOT, "props_evals")

MIN_BOOKS = 3          # minimo de books con par over/under para una fair de consenso confiable
EDGE_MIN = 0.04        # +EV si el mejor precio supera la fair de consenso en >= 4% (en prob)
POP_K = 30             # Beta-Binomial: fuerza del shrink del hit-rate hacia el prior del book (0.5).
POP_P = 0.5            # prior: un book pone la linea buscando ~50/50, ese es el baseline poblacional.


def _consensus_fair(books):
    """books = {casa: {'over': dec, 'under': dec}}. Por cada casa con AMBOS lados: de-vig 2-vias ->
    fair_over. Devuelve (fair_over, fair_under, n) con la MEDIANA. None si menos de MIN_BOOKS."""
    fovers = [edge.devig([d["over"], d["under"]])[0]
              for d in books.values() if "over" in d and "under" in d]
    if len(fovers) < MIN_BOOKS:
        return None
    fo = statistics.median(fovers)
    return fo, 1.0 - fo, len(fovers)


def _best_price(books, side):
    """Mejor cuota decimal ofrecida para 'side' entre todas las casas (mejor = mas alta = mas paga)."""
    prices = [d[side] for d in books.values() if side in d]
    return max(prices) if prices else None


def _shrunk_hitrate(hits, games):
    """Hit-rate propio Beta-Binomial shrunk hacia 0.5 (el book apunta a 50/50). None sin datos.
    Con muestra chica queda cerca de 0.5 (humilde); con volumen se acerca al rate crudo."""
    if not games:
        return None
    return (hits + POP_K * POP_P) / (games + POP_K)


def evaluate_prop(row):
    """row = linemate.flatten(trend) de un jugador. Evalua AMBOS lados (over/under) a la linea del
    prop: fair de consenso vs mejor precio -> edge; corrobora con el hit-rate shrunk. Devuelve una
    lista de dicts (uno por lado con precio) con veredicto FLAG / PASAR, o [] si no hay consenso."""
    books = row.get("books") or {}
    line = row.get("line")
    cons = _consensus_fair(books)
    if not cons or line is None:
        return []
    fo, fu, nb = cons
    games = row.get("games_season")
    sea = (row.get("splits") or {}).get("SEASON")
    hits_over = round(sea / 100.0 * games) if (games and sea is not None) else None
    model_over = _shrunk_hitrate(hits_over, games) if hits_over is not None else None
    out = []
    for side, fair in (("over", fo), ("under", fu)):
        bp = _best_price(books, side)
        if not bp:
            continue
        implied = 1.0 / bp
        e_fair = fair - implied                         # edge de mercado (consenso vs mejor precio)
        model = None if model_over is None else (model_over if side == "over" else 1.0 - model_over)
        e_model = None if model is None else model - implied
        # 2 senales: el mercado (consenso) dice +EV Y el hit-rate propio no lo contradice
        corrob = e_model is not None and e_model >= 0
        flag = e_fair >= EDGE_MIN and corrob
        out.append({
            "who": row["who"], "market": row["market"], "line": line, "side": side,
            "game": row.get("game", ""), "team": row.get("team", ""), "n_books": nb,
            "fair": round(fair, 4), "best_odds": round(bp, 3), "implied": round(implied, 4),
            "edge": round(e_fair, 4), "model_prob": round(model, 4) if model is not None else None,
            "model_edge": round(e_model, 4) if e_model is not None else None,
            "verdict": "FLAG" if flag else ("PASAR-sin-corrob" if e_fair >= EDGE_MIN else "PASAR"),
        })
    return out


def find_value(league="wc"):
    """Corre la maquina sobre el slate: devuelve todas las evaluaciones de props de jugador."""
    import linemate
    out = []
    for t in linemate.trends(league):
        if t.get("type") != "player":
            continue
        out += evaluate_prop(linemate.flatten(t))
    return out


# ------------------------------------------------------------------ forward-test (log -> eval)
def _append(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _read(d):
    out = []
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".jsonl"):
                with open(os.path.join(d, fn), encoding="utf-8-sig") as f:
                    out += [json.loads(ln) for ln in f if ln.strip()]
    return out


def log_props(date=None, league="wc"):
    """Loguea TODOS los flags del dia (tambien PASAR: la muestra sin sesgo es la que calibra el
    forward-test). Idempotente por (date, who, market, line, side)."""
    date = date or datetime.date.today().isoformat()
    try:
        evals = find_value(league)
    except Exception as e:
        print(f"  no pude leer props de Linemate ({e})")
        return
    done = {(r["date"], r["who"], r["market"], r["line"], r["side"]) for r in _read(FLAGS_DIR)}
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    rows = [{**r, "date": date, "ts": ts} for r in evals
            if (date, r["who"], r["market"], r["line"], r["side"]) not in done]
    _append(os.path.join(FLAGS_DIR, f"{date}.jsonl"), rows)
    flags = [r for r in rows if r["verdict"] == "FLAG"]
    print(f"  Props {date}: {len(rows)} evaluaciones nuevas ({len(flags)} +EV FLAG) -> props_flags/{date}.jsonl")
    for r in sorted(flags, key=lambda x: -x["edge"])[:12]:
        print(f"    {r['who'][:20]:<20} {r['market'][:16]:<16} {r['side']:<5} {r['line']} @ {r['best_odds']:<5} "
              f"edge {r['edge']*100:+.1f}% ({r['n_books']} books)")


def _won(stat, line, side):
    """1 si el prop pego: over -> stat > linea; under -> stat < linea (lineas .5, sin push)."""
    return int((stat > line) == (side == "over"))


def _resolve_rows(flags, done, stat_getter, ts):
    """Nucleo PURO de la resolucion (testeable por inyeccion): por cada flag +EV no resuelto, pide
    el stat real a stat_getter(who, team, market, line, date) y arma la fila de props_evals. Si el
    getter devuelve None (stat no disponible aun) -> queda pendiente."""
    N = 10.0
    rows = []
    for f in flags:
        if f.get("verdict") != "FLAG":
            continue
        key = (f["date"], f["who"], f["market"], f["line"], f["side"])
        if key in done:
            continue
        stat = stat_getter(f["who"], f.get("team", ""), f["market"], f["line"], f["date"])
        if stat is None:
            continue
        won = _won(stat, f["line"], f["side"])
        pnl = N * (f["best_odds"] - 1) if won else -N
        rows.append({**{k: f[k] for k in ("date", "who", "market", "line", "side", "best_odds", "edge")},
                     "stat": stat, "won": won, "pnl_flat": round(pnl, 2), "evaluated_at": ts})
    return rows


def _no_stat(*a):
    """Getter por defecto: aun no hay fuente per-fixture de stats de jugador cableada. Los game-logs
    de soccer_players AGREGAN (no exponen el partido puntual) -> se inyecta un getter real cuando
    exista una fuente per-partido. Hasta entonces, todo queda pendiente (el forward-test acumula)."""
    return None


def resolve_props(stat_getter=_no_stat, date=None):
    """Resuelve los flags +EV pendientes contra el stat real (via stat_getter) -> props_evals."""
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    flags = [f for f in _read(FLAGS_DIR) if f.get("verdict") == "FLAG"]
    done = {(e["date"], e["who"], e["market"], e["line"], e["side"]) for e in _read(EVAL_DIR)}
    rows = _resolve_rows(flags, done, stat_getter, ts)
    if rows:
        _append(os.path.join(EVAL_DIR, f"{datetime.date.today().isoformat()}.jsonl"), rows)
    print(f"  Props resueltos: {len(rows)} nuevos  |  pendientes: {len(flags) - len(done) - len(rows)}")
    return len(rows)


def report():
    ev = _read(EVAL_DIR)
    flags = [f for f in _read(FLAGS_DIR) if f["verdict"] == "FLAG"]
    print("=" * 74)
    print("  FORWARD-TEST DE PROPS +EV MULTI-BOOK (Linemate)")
    print("=" * 74)
    print(f"  Flags +EV logueados: {len(flags)}  |  resueltos: {len(ev)}  |  pendientes: {len(flags) - len(ev)}")
    if not ev:
        print("\n  Sin flags resueltos todavia. La resolucion (game-logs) se acumula al cerrarse los")
        print("  partidos. Veredicto de plata recien con n>=50 resueltos (regla del audit).")
        return
    N = 10.0
    hit = sum(e["won"] for e in ev)
    roi = sum(e["pnl_flat"] for e in ev) / (len(ev) * N) * 100
    print(f"  ROI flat (${N:.0f}/unidad): {roi:+.1f}%  |  aciertos {hit}/{len(ev)}")
    by = {}
    for e in ev:
        by.setdefault(e["market"], []).append(e)
    print(f"\n  {'mercado':<20} {'n':>3} {'aciertos':>9} {'ROI_flat':>9}")
    for m in sorted(by):
        es = by[m]; n = len(es)
        r = sum(x["pnl_flat"] for x in es) / (n * N) * 100
        print(f"  {m:<20} {n:>3} {sum(x['won'] for x in es):>4}/{n:<3} {r:>+8.1f}%")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "wc"
    if cmd == "log":
        log_props(sys.argv[2] if len(sys.argv) > 2 else None)
        return
    if cmd == "resolve":
        resolve_props()
        return
    if cmd == "report":
        report()
        return
    league = cmd
    evals = find_value(league)
    flags = [e for e in evals if e["verdict"] == "FLAG"]
    print("=" * 88)
    print(f"  PROPS +EV MULTI-BOOK  {league.upper()}  -  {len(evals)} lados evaluados, {len(flags)} con +EV")
    print("=" * 88)
    print(f"  {'Jugador':<20} {'Mercado':<16} {'Lado':<6} {'Lin':>4} {'mejor':>6} {'consenso':>9} {'edge':>7} {'books':>6}")
    print("  " + "-" * 84)
    for r in sorted(evals, key=lambda x: -x["edge"]):
        tag = " +EV" if r["verdict"] == "FLAG" else ""
        print(f"  {r['who'][:19]:<20} {r['market'][:15]:<16} {r['side']:<6} {r['line']:>4} "
              f"{r['best_odds']:>6.2f} {r['fair']*100:>8.1f}% {r['edge']*100:>+6.1f}%{tag} {r['n_books']:>4}")
    print(f"\n  Fair = mediana de-vigeada del consenso multi-book. +EV = mejor precio supera la fair en")
    print(f"  >= {EDGE_MIN*100:.0f}% Y el hit-rate propio (Beta-Binomial K={POP_K}) lo corrobora. Cuota = insumo, no feature.\n")


if __name__ == "__main__":
    main()
