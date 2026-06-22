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
import soccer, elo, cache, calib

MLB_VERSION = "mlb-ml-v1"   # version del modelo MLB moneyline (no mezclar con soccer)

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
    "cs:home":  lambda h, a: a == 0,   # local valla invicta
    "cs:away":  lambda h, a: h == 0,   # visita valla invicta
    "ml:home":  lambda h, a: h > a,    # MLB moneyline: gana el local (carreras)
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
        "cs:home": float(M[:, 0].sum()),   # P(away_goals=0)
        "cs:away": float(M[0, :].sum()),   # P(home_goals=0)
    }


def _row(date, home, away, market, prob, version, ts, neutral=True):
    return {"date": date, "sport": "soccer", "home": home, "away": away, "neutral": neutral,
            "market": market, "prob": round(prob, 4), "model_version": version,
            "played": False, "ts": ts}


def _statsbomb_markets(local, visita, date, ts):
    """Cornes + tarjetas de selecciones (StatsBomb). [] si no hay datos (no fabrica)."""
    rows = []
    try:
        import statsbomb_data as sb
    except Exception:
        return rows
    try:
        c = sb.predict_corners(local, visita)
        for line, p in [("8.5", c["over85"]), ("9.5", c["over95"]), ("10.5", c["over105"])]:
            rows.append(_row(date, local, visita, f"corners:over:{line}", p, "corners-sb-v1", ts))
    except Exception:
        pass
    try:
        k = sb.predict_cards(local, visita)
        for line, p in [("2.5", k["over25"]), ("3.5", k["over35"]), ("4.5", k["over45"])]:
            rows.append(_row(date, local, visita, f"cards:over:{line}", p, "cards-sb-v1", ts))
    except Exception:
        pass
    return rows


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
    rows = [_row(date, L, V, k, p, soccer.VERSION, ts, neutral) for k, p in mk.items()]
    sb_rows = _statsbomb_markets(L, V, date, ts)
    rows += sb_rows
    _append(os.path.join(PRED_DIR, f"{date}.jsonl"), rows)
    print(f"  Registradas {len(rows)} predicciones de {L} vs {V} ({date}) -> predictions/{date}.jsonl")
    for k, p in mk.items():
        print(f"    {k:<12} {p * 100:5.1f}%")
    for sr in sb_rows:
        print(f"    {sr['market']:<16} {sr['prob'] * 100:5.1f}%")


def log_mlb(date=None):
    """Registra el moneyline de los partidos MLB no jugados de `date` (prob de gane local).
    Una fila ml:home por partido -> prob distribuida en [0,1] = muestra limpia de calibracion."""
    import mlb
    date = date or datetime.date.today().isoformat()
    preds, _ = mlb.predict_today(date)
    if not preds:
        print(f"  Sin partidos MLB no jugados para {date}.")
        return
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    rows = [{"date": date, "sport": "mlb", "home": g["home"], "away": g["away"], "neutral": False,
             "market": "ml:home", "prob": round(g["p_home"], 4), "model_version": MLB_VERSION,
             "played": False, "ts": ts} for g in preds]
    _append(os.path.join(PRED_DIR, f"{date}.jsonl"), rows)
    print(f"  Registradas {len(rows)} predicciones MLB ({date}) -> predictions/{date}.jsonl")
    for g in preds:
        print(f"    {g['home']:<22} {g['p_home'] * 100:5.1f}%  (vs {g['away']})")


def _mlb_score(home, away, date):
    """Marcador final MLB (carreras) desde statsapi, orientado a home/away del log. None si no jugado."""
    try:
        r = cache.cached(f"mlbsched:{date}", cache.TTL_RESULTS, lambda: requests.get(
            "https://statsapi.mlb.com/api/v1/schedule",
            params={"sportId": 1, "date": date}, timeout=20).json())
    except Exception:
        return None
    H, A = home.lower(), away.lower()
    for d in r.get("dates", []):
        for g in d.get("games", []):
            if g.get("status", {}).get("abstractGameState") != "Final":
                continue
            h, a = g["teams"]["home"], g["teams"]["away"]
            if "score" not in h or "score" not in a:
                continue
            hn, an = h["team"]["name"].lower(), a["team"]["name"].lower()
            if hn == H and an == A:
                return int(h["score"]), int(a["score"])
            if hn == A and an == H:                       # logueado en orden inverso
                return int(a["score"]), int(h["score"])
    return None


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


def _espn_soccer_stats(home, away, date):
    """Cornes + tarjetas amarillas TOTALES reales desde ESPN (boxscore). dict o None."""
    try:
        sj = cache.cached(f"espn_wc:{date}", cache.TTL_RESULTS, lambda: requests.get(
            "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard",
            params={"dates": date.replace("-", "")}, timeout=20).json())
    except Exception:
        return None
    H, A = home.lower(), away.lower()
    eid = None
    for ev in sj.get("events", []):
        comp = ev["competitions"][0]
        names = [c["team"]["displayName"].lower() for c in comp["competitors"]]
        if H in names and A in names and ev.get("status", {}).get("type", {}).get("completed"):
            eid = ev["id"]; break
    if not eid:
        return None
    try:
        summ = cache.cached(f"espn_wc_sum:{eid}", cache.TTL_RESULTS, lambda: requests.get(
            "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary",
            params={"event": eid}, timeout=20).json())
    except Exception:
        return None
    ct = yt = 0
    found = False
    for t in summ.get("boxscore", {}).get("teams", []):
        sd = {s.get("name"): s.get("displayValue") for s in t.get("statistics", [])}
        if "wonCorners" in sd:
            found = True
            ct += int(float(sd.get("wonCorners") or 0))
            yt += int(float(sd.get("yellowCards") or 0))
    return {"corners_total": ct, "cards_total": yt} if found else None


def evaluate():
    df = soccer.load().dropna(subset=["home_score", "away_score"])
    preds = _read_all(PRED_DIR)
    done = {(e["date"], e["home"], e["away"], e["market"], e["model_version"]) for e in _read_all(EVAL_DIR)}
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    rows, pend = [], 0
    stats_cache = {}
    for p in preds:
        if (p["date"], p["home"], p["away"], p["market"], p["model_version"]) in done:
            continue
        mkt = p["market"]
        # Cornes / tarjetas: se resuelven con conteos reales del boxscore (no del marcador)
        if mkt.startswith("corners:") or mkt.startswith("cards:"):
            key = (p["home"], p["away"], p["date"])
            if key not in stats_cache:
                stats_cache[key] = _espn_soccer_stats(*key)
            st = stats_cache[key]
            if st is None:
                pend += 1
                continue
            line = float(mkt.split(":")[2])
            total = st["corners_total"] if mkt.startswith("corners:") else st["cards_total"]
            rows.append({"date": p["date"], "home": p["home"], "away": p["away"], "market": mkt,
                         "prob": p["prob"], "model_version": p["model_version"],
                         "result": str(total), "outcome": int(total > line), "evaluated_at": ts})
            continue
        # MLB moneyline: se resuelve con las carreras finales (statsapi), no con el CSV de soccer
        if p.get("sport") == "mlb" or mkt.startswith("ml:"):
            sc = _mlb_score(p["home"], p["away"], p["date"])
            fn = RESOLVERS.get(mkt)
            if sc is None or not fn:
                pend += 1 if sc is None else 0
                continue
            h, a = sc
            rows.append({"date": p["date"], "home": p["home"], "away": p["away"], "market": mkt,
                         "prob": p["prob"], "model_version": p["model_version"],
                         "result": f"{h}-{a}", "outcome": int(fn(h, a)), "evaluated_at": ts})
            continue
        sc = _espn_soccer_score(p["home"], p["away"], p["date"]) or _find_score(df, p["home"], p["away"], p["date"])
        if sc is None:
            pend += 1
            continue
        fn = RESOLVERS.get(mkt)
        if not fn:
            continue
        h, a = sc
        rows.append({"date": p["date"], "home": p["home"], "away": p["away"], "market": mkt,
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
    cparams = calib.load()                         # recalibrador (vacio -> calibrada == cruda)
    buckets, buckets_c, fam, sport_n = {}, {}, {}, {}
    brier = ll = brier_c = ll_c = 0.0
    for e in ev:
        p, o = e["prob"], e["outcome"]
        f = e["market"].split(":")[0]
        pc = calib.apply(p, e.get("model_version", "?"), f, cparams)   # prob calibrada POR FAMILIA
        bi, bic = min(int(p * 10), 9), min(int(pc * 10), 9)
        buckets.setdefault(bi, [0, 0.0, 0])
        buckets[bi][0] += 1; buckets[bi][1] += p; buckets[bi][2] += o
        buckets_c.setdefault(bic, [0, 0.0, 0])
        buckets_c[bic][0] += 1; buckets_c[bic][1] += pc; buckets_c[bic][2] += o
        fam.setdefault(f, [0, 0.0, 0.0, 0.0, 0.0])   # n, brier, brier_c, sum_p, sum_o
        fam[f][0] += 1; fam[f][1] += (p - o) ** 2; fam[f][2] += (pc - o) ** 2
        fam[f][3] += p; fam[f][4] += o
        sport_n[e.get("sport") or ("mlb" if f == "ml" else "soccer")] = sport_n.get(
            e.get("sport") or ("mlb" if f == "ml" else "soccer"), 0) + 1
        brier += (p - o) ** 2;   ll += -math.log(max(p if o else 1 - p, 1e-12))
        brier_c += (pc - o) ** 2; ll_c += -math.log(max(pc if o else 1 - pc, 1e-12))
    n = len(ev)
    ece = sum(abs(b[1] - b[2]) for b in buckets.values()) / n     # |pred-real| ponderado = ECE
    ece_c = sum(abs(b[1] - b[2]) for b in buckets_c.values()) / n
    print(f"  CALIBRACION  ({n} predicciones evaluadas | por deporte: "
          f"{', '.join(f'{k}={v}' for k, v in sorted(sport_n.items()))})\n")
    print(f"  {'prob dicha':>11} {'n':>5} {'pred':>7} {'real':>7}")
    print("  " + "-" * 33)
    for bi in sorted(buckets):
        c, sp, hits = buckets[bi]
        print(f"  {bi*10:>3}-{bi*10+10:<3}% {c:>5} {sp/c*100:>6.1f}% {hits/c*100:>6.1f}%")
    cal_on = any(v.get("a", 1.0) != 1.0 or v.get("b", 0.0) != 0.0 for v in cparams.values())
    print(f"\n  {'metrica':<12} {'cruda':>8} {'calibrada':>10}   (mas bajo = mejor)")
    print(f"  {'Brier':<12} {brier/n:>8.4f} {brier_c/n:>10.4f}")
    print(f"  {'Log loss':<12} {ll/n:>8.4f} {ll_c/n:>10.4f}")
    print(f"  {'ECE':<12} {ece:>8.4f} {ece_c:>10.4f}")
    if not cal_on:
        print("  (recalibrador = identidad; corre 'calibrate' para fitearlo desde evaluations/)")
    print(f"\n  Por familia de mercado ({'gap = pred-real, + = sobreconfiado':<8}):")
    print(f"    {'familia':<8} {'n':>4} {'Brier':>7} {'Brier_c':>8} {'gap':>7}")
    for f in sorted(fam):
        c, b, bc, sp, so = fam[f]
        print(f"    {f:<8} {c:>4} {b/c:>7.4f} {bc/c:>8.4f} {(sp-so)/c*100:>+6.1f}%")


def calibrate():
    """Fitea el recalibrador (Platt) desde evaluations/ y lo guarda. [2] del roadmap."""
    ev = _read_all(EVAL_DIR)
    if not ev:
        print("  Sin evaluaciones para calibrar.")
        return
    params = calib.fit(ev)
    calib.save(params)
    print(f"  Recalibradores fiteados (Platt, in-sample) -> data/calibrators.json")
    for ver, pr in sorted(params.items()):
        eff = "identidad (n insuficiente)" if pr["a"] == 1.0 and pr["b"] == 0.0 else \
              f"a={pr['a']:.3f}  b={pr['b']:+.3f}  ({'estira' if pr['a'] > 1 else 'comprime'})"
        print(f"    {ver:<16} n={pr['n']:<4} {eff}")
    print("  Corre 'report' para ver Brier/log loss antes vs despues.")


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
    elif cmd == "log-mlb":
        log_mlb(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "eval":
        evaluate()
    elif cmd == "report":
        report()
    elif cmd == "calibrate":
        calibrate()
    elif cmd == "selftest":
        selftest()
    else:
        print("  uso: feedback.py [log <local> <visita> | log-mlb [fecha] | "
              "eval | report | calibrate | selftest]")
