"""feedback.py - loop de retroalimentacion del predictor (Loop A: calibrar el MODELO).

El proceso que pule el sistema:
  1) log    -> registra TODAS las predicciones de un partido en predictions/ (gratis, sin API)
  2) eval   -> resuelve las que ya tienen resultado real contra el CSV -> evaluations/
               (mercados de equipo = gratis, salen del marcador)
  3) report -> tabla de calibracion (fiabilidad por bucket + Brier + log loss por mercado)

Se evalua TODO lo que el modelo predijo (no solo lo jugado): la calibracion necesita la
muestra SIN sesgo. Cero cuotas. Cada prediccion lleva model_version (no mezclar versiones).

Uso:
  python feedback.py log "Brazil" "Morocco"   # registra predicciones de hoy
  python feedback.py eval                      # resuelve las que ya se jugaron
  python feedback.py report                    # calibracion acumulada
  python feedback.py selftest                  # prueba el resolver con un partido pasado
"""
import os, sys, json, math, datetime
import requests
import soccer, elo, cache

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
PRED_DIR = os.path.join(ROOT, "predictions")
EVAL_DIR = os.path.join(ROOT, "evaluations")

# mercados de equipo resolubles SOLO con el marcador (h=goles local, a=goles visita)
RESOLVERS = {
    "1x2:home": lambda h, a: h > a,
    "1x2:draw": lambda h, a: h == a,
    "1x2:away": lambda h, a: h < a,
    "dc:1x":    lambda h, a: h >= a,
    "dc:x2":    lambda h, a: h <= a,
    "dc:12":    lambda h, a: h != a,
    "over:1.5": lambda h, a: h + a >= 2,
    "over:2.5": lambda h, a: h + a >= 3,
    "over:3.5": lambda h, a: h + a >= 4,
    "btts:yes": lambda h, a: h >= 1 and a >= 1,
}


def _append(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _read_all(d):
    out = []
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".jsonl"):
            with open(os.path.join(d, fn), encoding="utf-8-sig") as f:   # utf-8-sig: tolera BOM
                out += [json.loads(ln) for ln in f if ln.strip()]
    return out


def _markets(r, M):
    ov = lambda t: float(sum(M[i, j] for i in range(M.shape[0]) for j in range(M.shape[1]) if i + j >= t))
    b = r["blend"]
    return {
        "1x2:home": b[1], "1x2:draw": b[0], "1x2:away": b[-1],
        "dc:1x": b[1] + b[0], "dc:x2": b[0] + b[-1], "dc:12": b[1] + b[-1],
        "over:1.5": ov(2), "over:2.5": ov(3), "over:3.5": ov(4),
        "btts:yes": r["btts"],
    }


def log(local, visita, neutral=True, date=None):
    date = date or datetime.date.today().isoformat()
    df = soccer.load()
    df_elo, rating = elo.compute(df)
    teams = set(df.home_team) | set(df.away_team)
    L, V = soccer.resolve(local, teams), soccer.resolve(visita, teams)
    if not L or not V:
        print(f"  No reconozco: {local if not L else visita!r}")
        return
    r = soccer.predict(df_elo, rating, L, V, neutral=neutral)
    mk = _markets(r, soccer._matrix(r["lh"], r["la"], soccer.RHO))
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    rows = [{"date": date, "sport": "soccer", "home": L, "away": V, "neutral": neutral,
             "market": k, "prob": round(p, 4), "model_version": soccer.VERSION,
             "played": False, "ts": ts} for k, p in mk.items()]
    _append(os.path.join(PRED_DIR, f"{date}.jsonl"), rows)
    print(f"  Registradas {len(rows)} predicciones de {L} vs {V} ({date}) -> predictions/{date}.jsonl")
    for k, p in mk.items():
        print(f"    {k:<12} {p * 100:5.1f}%")


def _find_score(df, home, away, date, window=5):
    """Busca el partido jugado (equipos en cualquier orden) cerca de `date`. Devuelve
    (goles_local, goles_visita) orientado a home/away del log, o None."""
    d0 = datetime.datetime.fromisoformat(date)
    cand = df[((df.home_team == home) & (df.away_team == away)) |
              ((df.home_team == away) & (df.away_team == home))].copy()
    if cand.empty:
        return None
    cand["_d"] = (cand.date - d0).abs()
    cand = cand[cand["_d"] <= datetime.timedelta(days=window)]
    if cand.empty:
        return None
    g = cand.loc[cand["_d"].idxmin()]
    return (int(g.home_score), int(g.away_score)) if g.home_team == home else (int(g.away_score), int(g.home_score))


def _espn_soccer_score(home, away, date):
    """Marcador final desde ESPN (Mundial), mas rapido/confiable que el CSV. Devuelve
    (goles_local, goles_visita) orientado a home/away del log, o None."""
    try:
        r = cache.cached(f"espn_wc:{date}", cache.TTL_RESULTS, lambda: requests.get(
            "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard",
            params={"dates": date.replace("-", "")}, timeout=20).json())
    except Exception:
        return None
    H, A = home.lower(), away.lower()
    for ev in r.get("events", []):
        if not ev.get("status", {}).get("type", {}).get("completed"):
            continue
        sc = {x["team"]["displayName"].lower(): int(x.get("score") or 0)
              for x in ev["competitions"][0]["competitors"]}
        if H in sc and A in sc:
            return sc[H], sc[A]
    return None


def evaluate():
    df = soccer.load().dropna(subset=["home_score", "away_score"])
    preds = _read_all(PRED_DIR)
    done = {(e["date"], e["home"], e["away"], e["market"], e["model_version"]) for e in _read_all(EVAL_DIR)}
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    rows, pend = [], 0
    for p in preds:
        if (p["date"], p["home"], p["away"], p["market"], p["model_version"]) in done:
            continue
        sc = _espn_soccer_score(p["home"], p["away"], p["date"]) or _find_score(df, p["home"], p["away"], p["date"])
        if sc is None:
            pend += 1
            continue
        fn = RESOLVERS.get(p["market"])
        if not fn:
            continue
        h, a = sc
        rows.append({"date": p["date"], "home": p["home"], "away": p["away"], "market": p["market"],
                     "prob": p["prob"], "model_version": p["model_version"],
                     "result": f"{h}-{a}", "outcome": int(fn(h, a)), "evaluated_at": ts})
    if rows:
        _append(os.path.join(EVAL_DIR, f"{datetime.date.today().isoformat()}.jsonl"), rows)
    print(f"  Resueltas {len(rows)} predicciones nuevas. Pendientes (sin resultado aun): {pend}")


def report():
    ev = _read_all(EVAL_DIR)
    if not ev:
        print("  Sin evaluaciones todavia. Corre 'eval' despues de que se jueguen los partidos.")
        return
    buckets, fam, brier, ll = {}, {}, 0.0, 0.0
    for e in ev:
        p, o = e["prob"], e["outcome"]
        bi = min(int(p * 10), 9)
        buckets.setdefault(bi, [0, 0.0, 0])
        buckets[bi][0] += 1; buckets[bi][1] += p; buckets[bi][2] += o
        f = e["market"].split(":")[0]
        fam.setdefault(f, [0, 0.0])
        fam[f][0] += 1; fam[f][1] += (p - o) ** 2
        brier += (p - o) ** 2
        ll += -math.log(max(p if o else 1 - p, 1e-12))
    n = len(ev)
    print(f"  CALIBRACION  ({n} predicciones evaluadas)\n")
    print(f"  {'prob dicha':>11} {'n':>5} {'pred':>7} {'real':>7}")
    print("  " + "-" * 33)
    for bi in sorted(buckets):
        c, sp, hits = buckets[bi]
        print(f"  {bi*10:>3}-{bi*10+10:<3}% {c:>5} {sp/c*100:>6.1f}% {hits/c*100:>6.1f}%")
    print(f"\n  Brier total: {brier/n:.4f}   Log loss total: {ll/n:.4f}   (mas bajo = mejor)")
    print("  Brier por mercado:")
    for f in sorted(fam):
        c, b = fam[f]
        print(f"    {f:<6} n={c:<5} Brier={b/c:.4f}")


def selftest():
    """Prueba el resolver con el ultimo partido jugado del CSV (no toca el log real)."""
    df = soccer.load().dropna(subset=["home_score", "away_score"])
    g = df.sort_values("date").iloc[-1]
    h, a = int(g.home_score), int(g.away_score)
    print(f"  Partido de prueba: {g.home_team} {h}-{a} {g.away_team} ({g.date.date()})\n")
    for k, fn in RESOLVERS.items():
        print(f"    {k:<12} -> {'SI' if fn(h, a) else 'no'}")
    one = sum(RESOLVERS[k](h, a) for k in ("1x2:home", "1x2:draw", "1x2:away"))
    print(f"\n  Consistencia 1X2 (debe ser exactamente 1 verdadero): {one}  {'OK' if one == 1 else 'ERROR'}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "log" and len(sys.argv) >= 4:
        log(sys.argv[2], sys.argv[3])
    elif cmd == "eval":
        evaluate()
    elif cmd == "report":
        report()
    elif cmd == "selftest":
        selftest()
    else:
        print("  uso: feedback.py [log <local> <visita> | eval | report | selftest]")
