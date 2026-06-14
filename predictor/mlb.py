"""mlb.py - vertical MLB moneyline con DATOS REALES (MLB Stats API). CERO cuotas.

Features de forma de equipo (core.py) + ABRIDOR: ERA rodante del pitcher probable de cada
equipo, calculada SOLO con sus aperturas previas a la fecha (sin fuga) y regresada a la media
de liga para muestras chicas. El abridor es el factor dominante en MLB.

Correr:  C:/Users/Juant/AppData/Local/Python/bin/python.exe predictor/mlb.py [season]
"""
import sys, datetime, requests
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import cache, core

sys.stdout.reconfigure(encoding="utf-8")
B = "https://statsapi.mlb.com/api/v1"   # MLB Stats API (gratis, sin key)
LG_ERA = 4.20        # ERA de liga (fallback / blanco del shrink; se recomputa de los datos)
SHRINK_IP = 18.0     # innings-fantasma de regresion a la media (~3 aperturas)


def fetch_games(season):
    """Resultados de temporada regular finalizados + abridor probable de cada equipo.
    Devuelve teams={id:name}, rows=[(game_id,date,home_id,away_id,home_runs,away_runs)],
    sp_map={game_id:(home_sp_id, away_sp_id)}. 1 llamada, cacheada 6h."""
    def _f():
        r = requests.get(f"{B}/schedule",
                         params={"sportId": 1, "startDate": f"{season}-03-01", "endDate": f"{season}-11-30",
                                 "gameType": "R", "hydrate": "probablePitcher"}, timeout=45).json()
        teams, rows, spmap = {}, [], {}
        for d in r.get("dates", []):
            for g in d.get("games", []):
                if g.get("status", {}).get("abstractGameState") != "Final":
                    continue
                h, a = g["teams"]["home"], g["teams"]["away"]
                if "score" not in h or "score" not in a:
                    continue
                gid = g["gamePk"]
                teams[h["team"]["id"]] = h["team"]["name"]
                teams[a["team"]["id"]] = a["team"]["name"]
                rows.append((gid, g["gameDate"][:10], h["team"]["id"], a["team"]["id"], h["score"], a["score"]))
                spmap[gid] = [(h.get("probablePitcher") or {}).get("id"), (a.get("probablePitcher") or {}).get("id")]
        return teams, rows, spmap
    teams, rows, spmap = cache.cached(f"mlbgames2:{season}", 6 * 3600, _f)
    seen, uniq = set(), []                                 # statsapi repite gamePk (reprogramados)
    for rrow in rows:
        if rrow[0] not in seen:
            seen.add(rrow[0]); uniq.append(tuple(rrow))
    spmap = {int(k): tuple(v) for k, v in spmap.items()}   # JSON del cache: claves str->int, listas->tuplas
    return {int(k): v for k, v in teams.items()}, uniq, spmap


def _ip(s):
    """'6.2' (6 entradas y 2/3) -> 6.667 entradas."""
    w, _, f = str(s or "0").partition(".")
    return int(w) + (int(f) / 3 if f else 0)


def fetch_pitcher_log(pid, season):
    """Game-log de pitcheo: [{date, er, ip}] por aparicion. Cacheado 6h."""
    def _f():
        gl = requests.get(f"{B}/people/{pid}/stats",
                          params={"stats": "gameLog", "group": "pitching", "season": season}, timeout=15).json()
        sp = gl["stats"][0]["splits"] if gl.get("stats") and gl["stats"][0].get("splits") else []
        return [{"date": s.get("date"), "er": s["stat"].get("earnedRuns", 0), "ip": _ip(s["stat"].get("inningsPitched"))}
                for s in sp]
    return cache.cached(f"mlbpit:{pid}:{season}", 6 * 3600, _f)


def _era_asof(log, date, lg):
    """ERA del pitcher usando SOLO aperturas con fecha < date (sin fuga), regresada a la media lg."""
    if not log:
        return lg
    er = sum(e["er"] for e in log if e["date"] and e["date"] < date)
    ip = sum(e["ip"] for e in log if e["date"] and e["date"] < date)
    if ip <= 0:
        return lg
    return (ip * (9 * er / ip) + SHRINK_IP * lg) / (ip + SHRINK_IP)   # promedio ponderado con la liga


def build_sp_era(sp_map, rows, season):
    """{game_id: (home_sp_era, away_sp_era)} con ERA rodante hasta la fecha de cada juego."""
    pids = {p for pair in sp_map.values() for p in pair if p}
    with ThreadPoolExecutor(max_workers=10) as ex:
        logs = dict(zip(pids, ex.map(lambda p: fetch_pitcher_log(p, season), pids)))
    tot_er = sum(e["er"] for lg in logs.values() for e in lg)
    tot_ip = sum(e["ip"] for lg in logs.values() for e in lg)
    lg_era = 9 * tot_er / tot_ip if tot_ip else LG_ERA      # media de liga de los datos
    out = {}
    for gid, d, h, a, hr, ar in rows:
        hsp, asp = sp_map.get(gid, (None, None))
        out[gid] = (_era_asof(logs.get(hsp), d, lg_era), _era_asof(logs.get(asp), d, lg_era))
    return out, lg_era


def fetch_slate(date):
    """Partidos de `date` NO jugados aun (status Preview) con ids de equipo y abridor probable."""
    def _f():
        return requests.get(f"{B}/schedule", params={"sportId": 1, "date": date,
                            "hydrate": "probablePitcher"}, timeout=20).json()
    r = cache.cached(f"mlbslate:{date}", cache.TTL_LIVE, _f)
    out = []
    for d in r.get("dates", []):
        for g in d.get("games", []):
            if g.get("status", {}).get("abstractGameState") != "Preview":
                continue                                  # solo los que NO se jugaron aun
            h, a = g["teams"]["home"], g["teams"]["away"]
            out.append({"home_id": h["team"]["id"], "away_id": a["team"]["id"],
                        "home": h["team"]["name"], "away": a["team"]["name"], "time": g.get("gameDate", "")[11:16],
                        "home_sp": (h.get("probablePitcher") or {}).get("id"),
                        "away_sp": (a.get("probablePitcher") or {}).get("id"),
                        "home_sp_name": (h.get("probablePitcher") or {}).get("fullName", "?"),
                        "away_sp_name": (a.get("probablePitcher") or {}).get("fullName", "?")})
    return out


def _mlb_insights(fav, dog, fsp, fe, dsp, de, lg, fav_wp, fav_pd, dog_wp):
    """Bullets reales del modelo: abridor + forma. CERO cuotas, describe el porque del numero."""
    out = []
    if de - fe >= 0.4:
        out.append(f"Ventaja de abridor: {fsp} {fe:.2f} ERA vs {dsp} {de:.2f}")
    elif abs(fe - lg) < 0.01 or abs(de - lg) < 0.01:
        out.append("Un abridor sin historial 2026 (ERA = media de liga) -> lectura mas floja")
    else:
        out.append(f"Abridores parejos: {fsp} {fe:.2f} vs {dsp} {de:.2f}")
    out.append(f"{fav}: {fav_wp*100:.0f}% de victorias en sus ultimos 10 (dif. carreras {fav_pd:+.1f})")
    out.append(f"{dog}: {dog_wp*100:.0f}% en sus ultimos 10")
    return out


def predict_today(date=None):
    """Predice los partidos de hoy no jugados. Coeficientes entrenados con la temporada PASADA
    completa (robusto); forma y ERA del abridor de la temporada ACTUAL (sin fuga)."""
    date = date or datetime.date.today().isoformat()
    season = int(date[:4])
    feats = core.FEATURES + ["home_sp_era", "away_sp_era"]

    # 1) entrenar coeficientes con la temporada pasada completa
    teams_t, rows_t, sp_t = fetch_games(season - 1)
    dft = core.construir_features(core.cargar_sqlite(teams_t, rows_t, "mlb"))
    era_t, lg = build_sp_era(sp_t, rows_t, season - 1)
    dft["home_sp_era"] = dft.game_id.map(lambda g: era_t.get(g, (lg, lg))[0])
    dft["away_sp_era"] = dft.game_id.map(lambda g: era_t.get(g, (lg, lg))[1])
    model, scaler = core.fit_model(dft, feats)

    # 2) forma de la temporada ACTUAL (juegos ya jugados)
    _, rows_c, _ = fetch_games(season)
    dfc = pd.DataFrame(rows_c, columns=["game_id", "date", "home_team_id", "away_team_id", "home_score", "away_score"])
    log = core._team_log(dfc)

    # 3) partidos de hoy + ERA rodante de cada abridor en la temporada actual
    games = fetch_slate(date)
    pids = {g[k] for g in games for k in ("home_sp", "away_sp") if g[k]}
    with ThreadPoolExecutor(max_workers=10) as ex:
        plog = dict(zip(pids, ex.map(lambda p: fetch_pitcher_log(p, season), pids)))
    era = lambda pid: _era_asof(plog.get(pid), date, lg) if pid else lg

    preds = []
    for g in games:
        fh, fa = core.form(log, g["home_id"], date, "home"), core.form(log, g["away_id"], date, "away")
        if fh is None or fa is None:
            continue
        eh_, ea_ = era(g["home_sp"]), era(g["away_sp"])
        row = {**fh, **fa, "home_sp_era": eh_, "away_sp_era": ea_}
        p = float(model.predict_proba(scaler.transform(pd.DataFrame([row])[feats]))[0][1])
        fav_home = p >= 0.5
        prob = p if fav_home else 1 - p
        fav, dog = (g["home"], g["away"]) if fav_home else (g["away"], g["home"])
        fsp, fe = (g["home_sp_name"], eh_) if fav_home else (g["away_sp_name"], ea_)
        dsp, de = (g["away_sp_name"], ea_) if fav_home else (g["home_sp_name"], eh_)
        ff, dff = (fh, fa) if fav_home else (fa, fh)
        side, oside = ("home", "away") if fav_home else ("away", "home")
        preds.append({**g, "p_home": p, "h_era": round(eh_, 2), "a_era": round(ea_, 2),
                      "pick": fav, "opp": dog, "market": "Moneyline", "prob": prob,
                      "level": "ALTA" if prob >= 0.62 else "MEDIA" if prob >= 0.56 else "BAJA",
                      "insights": _mlb_insights(fav, dog, fsp, fe, dsp, de, lg,
                                                ff[f"{side}_l10_winpct"], ff[f"{side}_l10_ptdiff"],
                                                dff[f"{oside}_l10_winpct"])})
    preds.sort(key=lambda x: x["prob"], reverse=True)
    return preds, lg


def today():
    date = sys.argv[2] if len(sys.argv) > 2 else datetime.date.today().isoformat()
    preds, lg = predict_today(date)
    print(f"  MLB - LECTURA DEL DIA  {date}  ({len(preds)} partidos no jugados | ERA liga ~{lg:.2f})")
    print(f"  Prob = victoria del equipo; favorito segun forma + abridor (ERA rodante, sin cuotas)\n")
    print(f"  {'FAVORITO':<22}{'prob':>6}   {'vs':<22}{'abridores (ERA)':>26}")
    print("  " + "-" * 82)
    for p in preds:
        if p["p_home"] >= 0.5:
            fav, dog, pf = p["home"], p["away"], p["p_home"]
            sp = f"{p['home_sp_name']} {p['h_era']:.2f} / {p['away_sp_name']} {p['a_era']:.2f}"
        else:
            fav, dog, pf = p["away"], p["home"], 1 - p["p_home"]
            sp = f"{p['away_sp_name']} {p['a_era']:.2f} / {p['home_sp_name']} {p['h_era']:.2f}"
        print(f"  {fav:<22}{pf*100:>5.0f}%   {dog:<22}{sp:>26}")
    print("\n  Educativo. Prob calibrada (~57% acc en 2025), no certeza. La varianza de MLB es alta.\n")


def main():
    season = int(sys.argv[1]) if len(sys.argv) > 1 else datetime.date.today().year
    teams, rows, sp_map = fetch_games(season)
    if len(rows) < 200:
        print(f"  Solo {len(rows)} juegos finalizados en {season} (muestra chica). Proba: python predictor/mlb.py 2025")
        if not rows:
            return
    con = core.cargar_sqlite(teams, rows, "mlb")
    df = core.construir_features(con)
    era, lg_era = build_sp_era(sp_map, rows, season)
    df["home_sp_era"] = df["game_id"].map(lambda g: era.get(g, (lg_era, lg_era))[0])
    df["away_sp_era"] = df["game_id"].map(lambda g: era.get(g, (lg_era, lg_era))[1])
    feats = core.FEATURES + ["home_sp_era", "away_sp_era"]

    m, test, prob, contrib = core.entrenar_y_evaluar(df, feats)
    core.reportar(m, test, prob, contrib, f"MLB Moneyline {season} (datos reales + abridor)",
                  equipo=lambda i: teams.get(i, f"id {i}"))
    print(f"  {len(rows)} partidos | ERA liga {lg_era:.2f} | abridor = ERA rodante hasta la fecha (sin fuga).\n")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "today":
        today()
    else:
        main()
