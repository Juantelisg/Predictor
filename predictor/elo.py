"""elo.py - rating Elo rodante de SELECCIONES (estilo World Football Elo) desde el CSV.

Para cada partido calcula el Elo PREVIO de cada equipo (solo info anterior -> sin fuga)
y devuelve tambien el Elo final de cada seleccion (para predecir partidos futuros).
Cero API: se computa de los mismos resultados. El K depende de la importancia del torneo
y se ajusta por la diferencia de goles (una goleada mueve mas el rating).
"""
INIT = 1500.0
HFA = 65.0          # ventaja de localia en puntos Elo (no se aplica en cancha neutral)


def _k(tournament):
    t = (tournament or "").lower()
    if "qualif" in t:
        return 40
    if "world cup" in t:
        return 60
    if any(x in t for x in ("euro", "copa am", "african cup", "asian cup", "gold cup",
                            "nations league", "confederations")):
        return 50
    if "friendly" in t:
        return 20
    return 35


def _g(gd):
    """Multiplicador por margen de victoria (World Football Elo)."""
    gd = abs(gd)
    if gd <= 1:
        return 1.0
    if gd == 2:
        return 1.5
    return (11 + gd) / 8.0


def compute(df):
    """df solo de partidos JUGADOS. Devuelve (df + elo_home_pre/elo_away_pre, rating_final)."""
    df = df.sort_values("date").reset_index(drop=True)
    rating, eh, ea = {}, [], []
    for g in df.itertuples():
        rh, ra = rating.get(g.home_team, INIT), rating.get(g.away_team, INIT)
        eh.append(rh)
        ea.append(ra)
        adv = 0.0 if bool(g.neutral) else HFA
        we = 1.0 / (1.0 + 10 ** (-(rh + adv - ra) / 400.0))   # resultado esperado del local
        gd = g.home_score - g.away_score
        w = 1.0 if gd > 0 else 0.5 if gd == 0 else 0.0
        delta = _k(g.tournament) * _g(gd) * (w - we)
        rating[g.home_team] = rh + delta
        rating[g.away_team] = ra - delta
    out = df.copy()
    out["elo_home_pre"], out["elo_away_pre"] = eh, ea
    return out, rating
