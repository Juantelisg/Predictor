"""analizar.py - cuadro de analisis combinado en una sola corrida. CERO cuotas.

Operativiza el formato de analisis: junta el predictor estadistico (soccer + corners/
tarjetas StatsBomb) con los trends de Linemate (validacion cruzada / contexto). Aplica
el recalibrador (calib.py) al 1X2 -> prob CRUDA y CALIBRADA: la brecha entre ambas es
una senal de fiabilidad ([5] del roadmap; un intervalo formal queda pendiente).

`analyze()` devuelve un dict estructurado (lo consume el CLI y tambien el dashboard via
app.py). Las odds de Linemate son SOLO contexto de mercado, nunca edge (regla de oro).

Uso:
  python analizar.py "Paraguay" "Turkey" --lm=PAR,TUR
  python analizar.py "United States" "Australia" --home --lm=AUS,USA
  python analizar.py "Brazil" "Haiti"                 # sin Linemate (omitir --lm)
"""
import sys
import soccer, elo, calib

sys.stdout.reconfigure(encoding="utf-8")


def _lvl(p):
    return "ALTA" if p >= 0.65 else "MEDIA" if p >= 0.55 else "BAJA"


def load_ctx():
    """(df, df_elo, rating, models) - lo caro de cargar + fitear. Reutilizable entre partidos:
    los 4 modelos se fitean UNA sola vez aca (no por partido)."""
    df = soccer.load()
    df_elo, rating = elo.compute(df)
    models = soccer.fit_today(df_elo)
    return df, df_elo, rating, models


def _linemate_trends(lm_codes, league):
    """Trends de Linemate del partido, limpios (hit-rates redondeados). [] si falla/no hay."""
    if not lm_codes:
        return []
    try:
        import linemate as lm
        out = []
        for t in lm.game_trends(league, *lm_codes):
            sp = t.get("splits", {})
            rnd = lambda v: round(v) if isinstance(v, (int, float)) else None
            out.append({"who": t["who"], "market": t["market"], "side": (t.get("side") or "")[:1].upper(),
                        "line": t.get("line"), "l5": rnd(sp.get("LAST_5")), "l10": rnd(sp.get("LAST_10")),
                        "season": rnd(sp.get("SEASON")), "matchup": rnd(sp.get("MATCHUP")),
                        "signal": t.get("signal", "")})
        return out
    except Exception:
        return []


def _picks(home, away, resultado, doble, goles, corners):
    """Picks confiables (deterministas): mercados de equipo con prob >= 62%, ordenados.
    Las tarjetas se excluyen a proposito (el modelo las SOBREESTIMA)."""
    cand = []
    res = max(resultado, key=lambda x: x["cal"])
    cand.append({"market": "Resultado", "pick": res["label"], "prob": res["cal"]})
    dk = max(doble, key=doble.get)
    names = {"1X": f"{home} o empate", "X2": f"{away} o empate", "12": "Sin empate"}
    cand.append({"market": "Doble oport.", "pick": names[dk], "prob": doble[dk]})
    cand.append({"market": "Goles", "pick": "Over 1.5", "prob": goles["over15"]})
    o25 = goles["over25"]
    cand.append({"market": "Goles", "pick": "Over 2.5" if o25 >= 0.5 else "Under 2.5", "prob": max(o25, 1 - o25)})
    bt = goles["btts"]
    cand.append({"market": "BTTS", "pick": "Ambos marcan" if bt >= 0.5 else "No ambos", "prob": max(bt, 1 - bt)})
    if corners:
        cand.append({"market": "Corners", "pick": "Over 8.5", "prob": corners["o85"]})
    for c in cand:
        c["prob"] = round(c["prob"], 4)
        c["level"] = _lvl(c["prob"])
    picks = sorted([c for c in cand if c["prob"] >= 0.62], key=lambda c: c["prob"], reverse=True)
    return picks[:5]


def _availability(home, away, date, league):
    """XI confirmado (ESPN) como CONTEXTO. [] si no hay. No entra al modelo (es team-level)."""
    if league != "wc" or not date:
        return None
    try:
        import lineups
        return lineups.wc_xi(home, away, date)
    except Exception:
        return None


def analyze(local, visita, neutral=True, lm_codes=None, league="wc", ctx=None, date=None):
    """Cuadro de analisis como dict. ctx=(df,df_elo,rating,models) opcional para no recargar.
    date (YYYY-MM-DD) opcional -> agrega el XI confirmado de ESPN como contexto."""
    df, df_elo, rating, models = ctx if ctx else load_ctx()
    teams = set(df.home_team) | set(df.away_team)
    L, V = soccer.resolve(local, teams), soccer.resolve(visita, teams)
    if not L or not V:
        return {"error": f"No reconozco: {local if not L else visita}"}
    r = soccer.predict(df_elo, rating, L, V, neutral=neutral, df_all=df, models=models)
    cp = calib.load()
    cal = lambda p: round(calib.apply(p, soccer.VERSION, "1x2", cp), 4)
    b = r["blend"]

    resultado = [{"label": f"Gana {L}", "prob": round(b[1], 4), "cal": cal(b[1])},
                 {"label": "Empate", "prob": round(b[0], 4), "cal": cal(b[0])},
                 {"label": f"Gana {V}", "prob": round(b[-1], 4), "cal": cal(b[-1])}]
    doble = {"1X": round(b[1] + b[0], 4), "X2": round(b[0] + b[-1], 4), "12": round(b[1] + b[-1], 4)}
    goles = {"over15": round(r["over15"], 4), "over25": round(r["over"], 4),
             "over35": round(r["over35"], 4), "btts": round(r["btts"], 4)}
    valla = {"home": round(r["cs_home"], 4), "away": round(r["cs_away"], 4)}

    corners = cards = None
    try:
        import statsbomb_data as sb
        c = sb.predict_corners(L, V)
        corners = {"exp": c["total_exp"], "o85": round(c["over85"], 4),
                   "o95": round(c["over95"], 4), "o105": round(c["over105"], 4)}
    except Exception:
        pass
    try:
        import statsbomb_data as sb
        k = sb.predict_cards(L, V)
        cards = {"exp": k["total_exp"], "o25": round(k["over25"], 4),
                 "o35": round(k["over35"], 4), "o45": round(k["over45"], 4)}
    except Exception:
        pass

    return {"home": L, "away": V, "neutral": neutral, "version": soccer.VERSION,
            "resultado": resultado, "doble": doble, "goles": goles, "valla": valla,
            "corners": corners, "cards": cards,
            "form": {"home": r.get("form_home"), "away": r.get("form_away")},
            "linemate": _linemate_trends(lm_codes, league),
            "availability": _availability(L, V, date, league),
            "picks": _picks(L, V, resultado, doble, goles, corners)}


def run(local, visita, neutral=True, lm_codes=None, league="wc"):
    d = analyze(local, visita, neutral=neutral, lm_codes=lm_codes, league=league)
    if d.get("error"):
        print(f"  {d['error']}")
        return
    L, V, res = d["home"], d["away"], d["resultado"]
    pct = lambda x: f"{x*100:.0f}%"

    print("=" * 72)
    print(f"  ANALISIS  {L} vs {V}   ({'cancha neutral' if neutral else L + ' de local'})")
    print("=" * 72)
    print(f"  1X2 (modelo {d['version']})        {'cruda':>7} {'calibrada':>10}")
    print(f"    {res[0]['label']:<22} {res[0]['prob']*100:>6.1f}% {res[0]['cal']*100:>9.1f}%")
    print(f"    {res[1]['label']:<22} {res[1]['prob']*100:>6.1f}% {res[1]['cal']*100:>9.1f}%")
    print(f"    {res[2]['label']:<22} {res[2]['prob']*100:>6.1f}% {res[2]['cal']*100:>9.1f}%")
    dbl = d["doble"]
    print(f"    Doble:  1X {pct(dbl['1X'])}   X2 {pct(dbl['X2'])}   12 {pct(dbl['12'])}")
    g = d["goles"]
    print(f"  Goles:  Over1.5 {pct(g['over15'])}   Over2.5 {pct(g['over25'])}   "
          f"Over3.5 {pct(g['over35'])}   BTTS {pct(g['btts'])}")
    print(f"  Valla invicta:  {L} {pct(d['valla']['home'])}   {V} {pct(d['valla']['away'])}")
    if d["corners"]:
        c = d["corners"]
        print(f"  Corners (exp {c['exp']}):  O8.5 {pct(c['o85'])}   O9.5 {pct(c['o95'])}")
    if d["cards"]:
        k = d["cards"]
        print(f"  Tarjetas (exp {k['exp']}):  O3.5 {pct(k['o35'])}   O4.5 {pct(k['o45'])}   "
              f"(ojo: el modelo SOBREESTIMA tarjetas)")

    if d["linemate"]:
        print(f"\n  LINEMATE - {len(d['linemate'])} trends (validacion cruzada):")
        for t in d["linemate"]:
            l10 = f"{t['l10']}%" if t['l10'] is not None else "-"
            sea = f"{t['season']}%" if t['season'] is not None else "-"
            print(f"    {t['who'][:22]:<22} {t['market'][:17]:<17} {t['side']}{t['line']:<5} "
                  f"L10={l10:<5} SEA={sea:<5} sig={t['signal']}")

    print(f"\n  PICKS CONFIABLES:")
    for p in d["picks"]:
        print(f"    {p['market']:<14} {p['pick']:<22} {p['prob']*100:>5.1f}%  [{p['level']}]")

    print("\n  Cruda = modelo; calibrada = tras recalibrador (calib.py, in-sample; las 3 vias")
    print("  del 1X2 calibradas pueden no sumar 100). Educativo, sin cuotas.\n")


def main():
    args = sys.argv[1:]
    non_flags = [a for a in args if not a.startswith("--")]
    if len(non_flags) < 2:
        print('  Uso: analizar.py "<local>" "<visita>" [--home] [--lm=COD1,COD2] [--league=wc]')
        return
    neutral = "--home" not in args
    lm = next((a.split("=", 1)[1].split(",") for a in args if a.startswith("--lm=")), None)
    league = next((a.split("=", 1)[1] for a in args if a.startswith("--league=")), "wc")
    run(non_flags[0], non_flags[1], neutral=neutral, lm_codes=lm, league=league)


if __name__ == "__main__":
    main()
