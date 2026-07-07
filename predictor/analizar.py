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


_CTX_MEMO = {}   # {"fp": fingerprint, "ctx": (df, df_elo, rating, models)} - una sola entrada


def load_ctx():
    """(df, df_elo, rating, models) - lo caro de cargar + fitear. Reutilizable entre partidos:
    los 4 modelos se fitean UNA sola vez aca (no por partido).

    Memoizado en proceso por fingerprint del dataset (filas + fecha maxima): mientras el CSV
    de resultados no cambie, se reusa el fit y se evita re-fitear (~2.5-4s) en cada computo
    frio (cada expiracion de TTL, cada endpoint). soccer.load() ya lee del cache de 12h, asi
    que sacar el fingerprint cuesta ~100ms."""
    df = soccer.load()
    fp = (len(df), str(df["date"].max()))
    if _CTX_MEMO.get("fp") == fp:
        return _CTX_MEMO["ctx"]
    df_elo, rating = elo.compute(df)
    models = soccer.fit_today(df_elo)
    ctx = (df, df_elo, rating, models)
    _CTX_MEMO["fp"], _CTX_MEMO["ctx"] = fp, ctx
    return ctx


# mercado de Linemate -> etiqueta en español para el panorama de jugadores
MARKET_ES = {"SHOTS": "tiros", "SHOTS_ON_TARGET": "tiros al arco", "GOALS": "goles",
             "GOAL_OR_ASSIST": "gol o asistencia", "ASSISTS": "asistencias", "TACKLES": "entradas",
             "CARDS": "tarjetas", "PASSES": "pases", "SAVES": "atajadas", "FOULS": "faltas",
             "GOAL": "goles", "ANYTIME_GOALSCORER": "gol en cualquier momento"}

# posición → set de mercados relevantes para esa posición
_POS_MARKETS = {
    "forward":    {"GOALS", "SHOTS", "SHOTS_ON_TARGET", "GOAL_OR_ASSIST", "ASSISTS",
                   "ANYTIME_GOALSCORER", "GOAL"},
    "midfielder": {"SHOTS_ON_TARGET", "GOAL_OR_ASSIST", "ASSISTS", "PASSES",
                   "KEY_PASSES", "TACKLES", "SHOTS"},
    "defender":   {"TACKLES", "CLEARANCES", "CARDS", "GOALS", "GOAL_OR_ASSIST"},
    "goalkeeper": {"SAVES", "GOALS_CONCEDED"},
}


def _market_ok_for_position(market_key, position):
    """True si el mercado es relevante para esa posición. Sin posición: acepta todo."""
    if not position:
        return True
    allowed = _POS_MARKETS.get(position.lower())
    return allowed is None or market_key in allowed


def _quality_ok(mk, side, line, l5, l10, games_l5, games_season, avg_l5):
    """True si el prop pasa los filtros de calidad mínima."""
    is_over = (side or "").lower().startswith("over")

    # Necesitamos al menos 3 juegos reales en L5
    if (games_l5 or 0) < 3:
        return False

    # UNDER trivial: el jugador nunca hace el stat → no es señal, es trivialidad
    # (ej: CB con 0% SOT under 0.5 = trivialmente cierto, cero valor predictivo)
    if not is_over and (line or 0) <= 0.5 and (l5 or 0) <= 15:
        return False

    # Gate de hit-rate para OVER: mínimo 60% en L5 (3 de 5 juegos)
    if is_over:
        if l5 is None:
            return False
        if l5 < 60:
            # aceptar si L10 es fuerte y L5 está razonablemente arriba
            if (l10 or 0) < 65 or l5 < 50:
                return False

    # Gate para UNDER: OVER hit-rate <= 35% en L5 (= UNDER ocurre >= 65%)
    if not is_over:
        if l5 is None:
            return False
        under_rate = 100 - l5
        if under_rate < 65:
            return False

    return True


def _panorama_read(l5, is_over):
    """Etiqueta de forma. Strings sincronizados con ReadBadge del frontend (hot=alto/warm=buena/cold=bajo)."""
    if l5 is None:
        return ""
    if is_over:
        return "rendimiento alto" if l5 >= 80 else "en buena forma" if l5 >= 65 else "forma regular"
    under_rate = 100 - l5
    return "muy constante" if under_rate >= 80 else "constante" if under_rate >= 65 else ""


def _player_panorama(lm_codes, league):
    """Props de jugadores del partido filtrados por posición y calidad mínima.
    Solo muestra señales con base estadística real: posición relevante, mínimo 3 juegos,
    hit-rate significativo. [] si no hay datos o falla."""
    if not lm_codes:
        return []
    try:
        import linemate as lm
        rnd = lambda v: round(v) if isinstance(v, (int, float)) else None
        out = []
        for t in lm.game_trends(league, *lm_codes):
            if t.get("type") != "player":
                continue
            mk = (t.get("market") or "").upper()
            pos = t.get("position")
            if not _market_ok_for_position(mk, pos):
                continue

            sp = t.get("splits", {})
            l5 = sp.get("LAST_5")
            l10 = sp.get("LAST_10")
            season = sp.get("SEASON")
            side = t.get("side") or ""
            line = t.get("line")
            games_l5 = t.get("games_l5")
            games_l10 = t.get("games_l10")
            games_season = t.get("games_season")
            avg_l5 = t.get("avg_l5")

            if not _quality_ok(mk, side, line, l5, l10, games_l5, games_season, avg_l5):
                continue

            # aciertos absolutos desde el % crudo (para mostrar "4/5", "6/10")
            hits = lambda rate, g: round((rate / 100) * g) if (rate is not None and g) else None
            hits_l5, hits_l10 = hits(l5, games_l5), hits(l10, games_l10)

            is_over = side.lower().startswith("over")
            # Score: pesa más L5, tiebreak por games_season (más muestra = más confiable)
            score = (l5 or 0) * 0.6 + (l10 or l5 or 0) * 0.3 + min(games_season or 0, 20) * 0.5
            out.append({
                "who": t["who"],
                "team": (t.get("team") or "").upper(),
                "position": pos,
                "market": MARKET_ES.get(mk, mk.replace("_", " ").lower()),
                "over": is_over,
                "side": side,
                "line": line,
                "l5": rnd(l5),
                "l10": rnd(l10),
                "season": rnd(season),
                "games": games_l5,
                "games_l5": games_l5,
                "hits_l5": hits_l5,
                "games_l10": games_l10,
                "hits_l10": hits_l10,
                "avg": round(avg_l5, 2) if avg_l5 is not None else None,
                "read": _panorama_read(l5, is_over),
                "signal": t.get("signal", ""),
                "_score": score,
            })
        out.sort(key=lambda r: r.pop("_score"), reverse=True)
        return out
    except Exception:
        return []


def _linemate_trends(lm_codes, league):
    """Trends de EQUIPO de Linemate (los de jugador van al panorama). [] si falla/no hay."""
    if not lm_codes:
        return []
    try:
        import linemate as lm
        out = []
        for t in lm.game_trends(league, *lm_codes):
            if t.get("type") == "player":            # jugadores -> _player_panorama
                continue
            sp = t.get("splits", {})
            rnd = lambda v: round(v) if isinstance(v, (int, float)) else None
            out.append({"who": t["who"], "market": t["market"], "side": (t.get("side") or "")[:1].upper(),
                        "line": t.get("line"), "l5": rnd(sp.get("LAST_5")), "l10": rnd(sp.get("LAST_10")),
                        "season": rnd(sp.get("SEASON")), "matchup": rnd(sp.get("MATCHUP")),
                        "signal": t.get("signal", "")})
        return out
    except Exception:
        return []


# familias APTAS para 'picks confiables'. Con LINEA DINAMICA + calibracion por familia, cards ya
# no se excluye a mano: su calibrador (cards-sb-v2) + el factor de torneo (regime) + el gate la
# protegen igual que al resto. El modelo elige la linea mas jugable, no una fija.
PICK_FAMILIES = {"1x2", "dc", "over", "btts", "corners", "cards"}

# Banda jugable, derivada del estilo del usuario (cuota decimal ~1.30-1.60 = prob implicita ~62-77%).
PICK_GATE = 0.62      # piso de prob calibrada para ser 'pick confiable' (= gate historico)
PICK_TARGET = 0.70    # sweet spot (~cuota 1.43): a igualdad, se prefiere la linea mas cercana a esto
PICK_CEIL = 0.85      # techo SOLO para O/U: por encima la linea es trivial (lock) -> subir de linea


def _best_ou(curve, family, cal_fn, market_label):
    """Elige la linea O/U mas jugable de un mercado con distribucion (goles/corners/tarjetas).
    curve = [[linea, P(over)], ...]. Por linea: calibra P(over) por familia, toma el lado mas
    probable, y se queda con la que cae en la banda [GATE, CEIL] mas cercana al TARGET. None si
    ninguna linea tiene lectura firme (= PASAR ese mercado, honesto). Reemplaza la linea fija.

    Ademas adjunta 'alt' = la SIGUIENTE linea del mismo lado, un escalon mas exigente (menos %,
    mas cerca de lo esperado): Over -> linea+1, Under -> linea-1. Es informativa (no pasa el gate,
    no se combina en tickets): 'la confiable y seguido la siguiente'."""
    ladder = sorted(((line, cal_fn(p_over, family)) for line, p_over in (curve or [])),
                    key=lambda x: x[0])
    pside = lambda pc: pc if pc >= 0.5 else 1 - pc              # prob del lado mas probable
    best_i = None
    for i, (line, pc) in enumerate(ladder):
        p = pside(pc)
        if not (PICK_GATE <= p <= PICK_CEIL):
            continue
        if best_i is None or abs(p - PICK_TARGET) < abs(pside(ladder[best_i][1]) - PICK_TARGET):
            best_i = i
    if best_i is None:
        return None
    line, pc = ladder[best_i]
    side, p = ("Over", pc) if pc >= 0.5 else ("Under", 1 - pc)
    pick = {"market": market_label, "family": family, "pick": f"{side} {line}", "prob": p}
    nb = best_i + 1 if side == "Over" else best_i - 1           # escalon mas exigente del mismo lado
    if 0 <= nb < len(ladder):
        nline, npc = ladder[nb]
        np_ = npc if side == "Over" else 1 - npc
        if 0 < np_ < 1:
            pick["alt"] = {"pick": f"{side} {nline}", "prob": round(np_, 4)}
    return pick


def _picks(home, away, resultado, doble, goles, corners, cal_fn, cards=None):
    """Picks confiables (deterministas). Mercados de resultado (1X2/doble/BTTS) con prob CALIBRADA
    >= GATE (sin techo: una doble alta es un pick valido), y mercados O/U (goles/corners/tarjetas)
    con LINEA DINAMICA: _best_ou ofrece la linea mas jugable segun lo esperado, no una fija. Toda
    prob pasa por el recalibrador por familia (cal_fn)."""
    names = {"1X": f"{home} o empate", "X2": f"{away} o empate", "12": "Sin empate"}
    top = max(resultado, key=lambda x: x["cal"])
    dc = max(doble, key=doble.get)
    bt = cal_fn(goles["btts"], "btts")
    bt_side, bt_p = ("Ambos marcan", bt) if bt >= 0.5 else ("No ambos", 1 - bt)
    fixed = [
        {"market": "Resultado", "family": "1x2", "pick": top["label"], "prob": top["cal"]},
        {"market": "Doble oport.", "family": "dc", "pick": names[dc], "prob": doble[dc]},
        {"market": "BTTS", "family": "btts", "pick": bt_side, "prob": bt_p},
    ]
    picks = [c for c in fixed if c["family"] in PICK_FAMILIES and c["prob"] >= PICK_GATE]
    for curve_dict, fam, label in ((goles, "over", "Goles"),
                                   (corners, "corners", "Corners"),
                                   (cards, "cards", "Tarjetas")):
        if curve_dict and curve_dict.get("curve"):
            b = _best_ou(curve_dict["curve"], fam, cal_fn, label)
            if b:
                picks.append(b)
    for c in picks:
        c["prob"] = round(c["prob"], 4)
        c["level"] = _lvl(c["prob"])
    picks.sort(key=lambda c: c["prob"], reverse=True)
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
    gf = 1.0                                          # factor de nivel de goles del torneo (T6, solo WC)
    if league == "wc":
        try:
            import regime
            gf = regime.goals_factor(before_date=date)[0]
        except Exception:
            pass
    r = soccer.predict(df_elo, rating, L, V, neutral=neutral, df_all=df, models=models, goals_factor=gf)
    cp = calib.load()
    b = r["blend"]
    ch, cd, ca = calib.apply_1x2(b[1], b[0], b[-1], soccer.VERSION, cp)   # per-outcome + renorm (suma 1)

    resultado = [{"label": f"Gana {L}", "prob": round(b[1], 4), "cal": round(ch, 4)},
                 {"label": "Empate", "prob": round(b[0], 4), "cal": round(cd, 4)},
                 {"label": f"Gana {V}", "prob": round(b[-1], 4), "cal": round(ca, 4)}]
    # doble oportunidad DERIVADA del 1X2 calibrado (misma info; no se fitea un calibrador dc aparte)
    doble = {"1X": round(ch + cd, 4), "X2": round(cd + ca, 4), "12": round(ch + ca, 4)}
    # cal_fn: recalibrador por familia. corners/cards usan su version v2; el resto soccer-v3.
    # (si una familia no tiene calibrador -> identidad; si el gate OOS la desactivo -> raw, seguro.)
    def cal_fn(p, fam):
        ver = {"corners": "corners-sb-v2", "cards": "cards-sb-v2"}.get(fam, soccer.VERSION)
        return calib.apply(p, ver, fam, cp, context=calib.context_of(p))

    goles = {"over15": round(r["over15"], 4), "over25": round(r["over"], 4),
             "over35": round(r["over35"], 4), "btts": round(r["btts"], 4),
             "curve": r.get("goals_curve"),        # P(over) por linea -> linea de goles dinamica

             # cruda Y calibrada por mercado (T9): el producto/ticket usan la calibrada
             "over15_cal": round(cal_fn(r["over15"], "over"), 4),
             "over25_cal": round(cal_fn(r["over"], "over"), 4),
             "over35_cal": round(cal_fn(r["over35"], "over"), 4),
             "btts_cal": round(cal_fn(r["btts"], "btts"), 4)}
    valla = {"home": round(r["cs_home"], 4), "away": round(r["cs_away"], 4),
             "home_cal": round(cal_fn(r["cs_home"], "cs"), 4), "away_cal": round(cal_fn(r["cs_away"], "cs"), 4)}

    corners = cards = None
    try:
        import regime
        c = regime.predict("corners", L, V)          # factor de nivel del torneo (v2)
        corners = {"exp": c["total_exp"], "o85": round(c["over85"], 4),
                   "o95": round(c["over95"], 4), "o105": round(c["over105"], 4),
                   "curve": c.get("curve")}          # P(over) por linea -> linea de corners dinamica
    except Exception:
        pass
    try:
        import regime
        k = regime.predict("cards", L, V)            # v2: corrige la sobreestimacion de amarillas
        cards = {"exp": k["total_exp"], "o25": round(k["over25"], 4),
                 "o35": round(k["over35"], 4), "o45": round(k["over45"], 4),
                 "curve": k.get("curve")}            # P(over) por linea -> linea de tarjetas dinamica
    except Exception:
        pass

    return {"home": L, "away": V, "neutral": neutral, "version": soccer.VERSION,
            "resultado": resultado, "doble": doble, "goles": goles, "valla": valla,
            "corners": corners, "cards": cards,
            "form": {"home": r.get("form_home"), "away": r.get("form_away")},
            "last_games": {"home": r.get("last_home") or [], "away": r.get("last_away") or []},
            "linemate": _linemate_trends(lm_codes, league),
            "panorama": _player_panorama(lm_codes, league),
            "availability": _availability(L, V, date, league),
            "picks": _picks(L, V, resultado, doble, goles, corners, cal_fn, cards)}


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
        alt = f"   -> siguiente: {p['alt']['pick']} {p['alt']['prob']*100:.0f}%" if p.get("alt") else ""
        print(f"    {p['market']:<14} {p['pick']:<22} {p['prob']*100:>5.1f}%  [{p['level']}]{alt}")

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
