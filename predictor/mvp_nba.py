"""mvp_nba.py - vertical NBA moneyline con DATOS DE EJEMPLO (sinteticos). CERO cuotas.

Prueba de concepto del pipeline: genera una temporada sintetica con senal real y la
corre por el pipeline compartido de core.py. Para datos NBA reales, reemplazar
generar_temporada() por un loader de nba_api/ESPN a las mismas tablas.

Correr:  C:/Users/Juant/AppData/Local/Python/bin/python.exe predictor/mvp_nba.py
"""
import sys
import numpy as np
import pandas as pd
import core

sys.stdout.reconfigure(encoding="utf-8")          # consola Windows cp1252 -> no romper con acentos

SEED = 7
N_TEAMS = 12
HOME_ADV = 3.0            # ventaja de localia en puntos (NBA real ~2.5-3)


def generar_temporada():
    """Temporada sintetica con senal real: cada equipo tiene una 'fuerza' latente; el
    margen = dif. de fuerzas + ventaja de localia + ruido. Asi forma y splits home/away
    correlacionan de verdad con el resultado, y el modelo tiene algo que recuperar."""
    rng = np.random.default_rng(SEED)
    teams = {t: f"Team {t:02d}" for t in range(1, N_TEAMS + 1)}
    strength = {t: rng.normal(0, 6) for t in teams}
    fixtures = [(h, a) for h in teams for a in teams if h != a]   # round-robin doble
    rng.shuffle(fixtures)
    rows, base = [], pd.Timestamp("2025-10-22")
    for i, (h, a) in enumerate(fixtures):
        margin = strength[h] - strength[a] + HOME_ADV + rng.normal(0, 11)
        total = rng.normal(225, 9)
        hp, ap = round((total + margin) / 2), round((total - margin) / 2)
        rows.append((i + 1, (base + pd.Timedelta(days=i // 4)).date().isoformat(), h, a, hp, ap))
    return teams, rows


def main():
    teams, rows = generar_temporada()
    con = core.cargar_sqlite(teams, rows, "nba")
    df = core.construir_features(con)
    m, test, prob, contrib = core.entrenar_y_evaluar(df)
    core.reportar(m, test, prob, contrib, "NBA Moneyline (dataset de ejemplo sintetico)",
                  equipo=lambda i: teams.get(i, f"id {i}"))
    print("  Dataset de ejemplo (seed fijo). Para datos reales: loader de nba_api/ESPN.")
    print("  Educativo. Modelo puramente estadistico - sin cuotas.\n")


if __name__ == "__main__":
    main()
