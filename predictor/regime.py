"""regime.py - factor de NIVEL del torneo para cards/corners (empirical-Bayes, walk-forward).

El problema (audit T5): la base StatsBomb 2018-24 sobreestima las tarjetas del WC2026 (+28% gap).
No es un sesgo por equipo -- es de NIVEL: el arbitraje/estilo del torneo en curso da menos amarillas
que los torneos historicos. Corners, con la misma arquitectura, casi no tiene sesgo -> confirma que
el problema es el nivel, no la forma.

Fix: un multiplicador m tal que total_real ~ m * total_modelo, estimado con los partidos del WC YA
jugados y SHRUNK hacia 1.0 (sin ajuste) por cantidad de partidos (empirical-Bayes, K=12). Preserva
la diferenciacion entre equipos (es multiplicativo) y corrige solo el nivel. Walk-forward: para
predecir el partido del dia D solo usa partidos anteriores a D -> cero fuga temporal.

Fuente de los totales reales: evaluations/ (las filas cards:/corners: traen el total en 'result',
cosechado por feedback._espn_soccer_stats de los boxscores de ESPN).

Uso:
  python regime.py                 # factor actual de cards y corners + backtest walk-forward v1 vs v2
"""
import os, sys, json, datetime
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import statsbomb_data as sb

ROOT = os.path.dirname(os.path.abspath(__file__))
EVAL_DIR = os.path.join(ROOT, "evaluations")
K = 6                      # shrink del factor cards/corners hacia 1.0 por partidos observados (EB).
                           # Balance: corrige rapido cuando hay muestra, humilde al arranque del torneo.
GOALS_K = 20               # shrink del factor de GOLES (mas conservador: pega a 4 mercados a la vez).
LINES = {"cards": [2.5, 3.5, 4.5], "corners": [8.5, 9.5, 10.5]}
_OVERKEY = {"cards": {2.5: "over25", 3.5: "over35", 4.5: "over45"},
            "corners": {8.5: "over85", 9.5: "over95", 10.5: "over105"}}


def _read_evals():
    out = []
    if os.path.isdir(EVAL_DIR):
        for fn in sorted(os.listdir(EVAL_DIR)):
            if fn.endswith(".jsonl"):
                with open(os.path.join(EVAL_DIR, fn), encoding="utf-8-sig") as f:
                    out += [json.loads(ln) for ln in f if ln.strip()]
    return out


def _actual_totals(kind, before_date, evals):
    """{(date,home,away): total_real} de partidos con resultado de cards/corners ANTERIORES a
    before_date. Dedup por partido (las 3 lineas comparten el mismo total en 'result')."""
    out = {}
    for e in evals:
        if not e["market"].startswith(kind + ":"):
            continue
        if before_date and e["date"] >= before_date:
            continue
        try:
            out[(e["date"], e["home"], e["away"])] = float(e["result"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _model_total(kind, home, away):
    """total esperado del modelo v1 (sin factor) para ese matchup, o None si no hay datos StatsBomb."""
    try:
        r = sb.predict_corners(home, away) if kind == "corners" else sb.predict_cards(home, away)
        return r["total_exp"]
    except Exception:
        return None


def tournament_factor(kind, before_date=None, evals=None):
    """Multiplicador de nivel (shrunk) de partidos < before_date. Devuelve (factor, n_partidos).
    n=0 -> factor 1.0 (arranque del torneo: sin evidencia, no ajusta)."""
    evals = evals if evals is not None else _read_evals()
    actuals = _actual_totals(kind, before_date, evals)
    sum_a = sum_b = 0.0
    for (d, h, a), tot in actuals.items():
        base = _model_total(kind, h, a)
        if base and base > 0:
            sum_a += tot
            sum_b += base
    if sum_b <= 0:
        return 1.0, 0
    n = len(actuals)
    m_hat = sum_a / sum_b                       # razon total_real / total_modelo agregada
    return (n * m_hat + K * 1.0) / (n + K), n   # shrink hacia 1.0 (sin ajuste) por muestra


def predict(kind, home, away, before_date=None, evals=None):
    """Prediccion v2 (con factor de torneo) de cards/corners para un partido. Mismo dict que sb."""
    f, _ = tournament_factor(kind, before_date, evals)
    return sb.predict_corners(home, away, factor=f) if kind == "corners" else sb.predict_cards(home, away, factor=f)


# ------------------------------------------------------------------ factor de GOLES del torneo
def goals_factor(before_date=None):
    """Multiplicador de nivel de GOLES del WC (razon goles_reales / goles_esperados por el modelo),
    shrunk hacia 1.0 con GOALS_K. Corrige el sesgo bajista del Poisson (espera ~2.5, el WC da ~2.9).
    Se aplica SOLO a los mercados de goles (no al 1X2). Devuelve [factor, n_partidos].

    El 'esperado' se estima con un fit unico del modelo actual (rapido) -> es calibracion de NIVEL
    agregada, no una prediccion; la leve fuga no afecta la validez de la prediccion futura. La
    validacion estricta walk-forward vive en backtest_wc (goals_regime). Cacheado (los WC cierran
    de a poco por dia)."""
    def _compute():
        import pandas as pd
        import soccer, elo, backtest_wc
        df = soccer.load()
        df_elo, rating = elo.compute(df)
        fx = backtest_wc.wc_fixtures(df_elo).dropna(subset=["home_score", "away_score"])
        if before_date:
            fx = fx[fx["date"] < pd.Timestamp(before_date)]
        if len(fx) == 0:
            return [1.0, 0]
        models = soccer.fit_today(df_elo)
        sr = se = 0.0
        for g in fx.itertuples():
            r = soccer._predict_with(models, rating, g.home_team, g.away_team, neutral=bool(g.neutral))
            se += r["lh"] + r["la"]
            sr += g.home_score + g.away_score
        if se <= 0:
            return [1.0, 0]
        n = len(fx)
        m_hat = sr / se
        return [(n * m_hat + GOALS_K * 1.0) / (n + GOALS_K), n]

    import cache
    return cache.cached(f"wc_goals_factor:{before_date or 'today'}", cache.TTL_RESULTS, _compute)


# ------------------------------------------------------------------ backtest walk-forward v1 vs v2
def _brier_gap(kind):
    """Reconstruye walk-forward las predicciones de cada linea de `kind` desde evaluations/.
    v1 = prob guardada (sin factor). v2 = recomputada con el factor de partidos ANTERIORES.
    Devuelve (n, brier_v1, brier_v2, gap_v1, gap_v2) -- gap = pred_media - real_media (+ = sobreconf)."""
    evals = _read_evals()
    rows = [e for e in evals if e["market"].startswith(kind + ":")]
    n = 0
    b1 = b2 = sp1 = sp2 = so = 0.0
    for e in sorted(rows, key=lambda x: x["date"]):
        line = float(e["market"].split(":")[2])
        o = e["outcome"]
        p1 = e["prob"]                                          # v1 (guardada)
        try:
            f, _ = tournament_factor(kind, e["date"], evals)   # SOLO partidos anteriores a este
            r = sb.predict_corners(e["home"], e["away"], factor=f) if kind == "corners" \
                else sb.predict_cards(e["home"], e["away"], factor=f)
            p2 = r[_OVERKEY[kind][line]]
        except Exception:
            continue
        n += 1
        b1 += (p1 - o) ** 2; b2 += (p2 - o) ** 2
        sp1 += p1; sp2 += p2; so += o
    if not n:
        return 0, 0, 0, 0, 0
    return n, b1 / n, b2 / n, (sp1 - so) / n, (sp2 - so) / n


def main():
    print("=" * 70)
    print("  FACTOR DE NIVEL DEL TORNEO (empirical-Bayes walk-forward, K={})".format(K))
    print("=" * 70)
    for kind in ("cards", "corners"):
        f, nprev = tournament_factor(kind)
        print(f"  {kind:<8} factor ACTUAL = {f:.3f}  (de {nprev} partidos WC observados)")
    print("\n  BACKTEST walk-forward (v1 sin factor vs v2 con factor de partidos ANTERIORES):")
    print(f"  {'kind':<8} {'n':>4} {'Brier_v1':>9} {'Brier_v2':>9} {'gap_v1':>8} {'gap_v2':>8}")
    for kind in ("cards", "corners"):
        n, b1, b2, g1, g2 = _brier_gap(kind)
        print(f"  {kind:<8} {n:>4} {b1:>9.4f} {b2:>9.4f} {g1*100:>+7.1f}% {g2*100:>+7.1f}%")
    print("\n  Criterio T5: cards Brier_v2 < 0.22 y |gap_v2| < 8pt; corners no empeora. Walk-forward,")
    print("  no in-sample. El factor se estima con SOLO partidos anteriores a cada prediccion.")


if __name__ == "__main__":
    main()
