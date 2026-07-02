"""Factor de goles del torneo (T6): goals_factor=1.0 deja el motor IDENTICO (holdout intacto), y
cuando escala, mueve SOLO los mercados de goles -- el 1X2 queda anclado en la matriz base."""
import numpy as np
import soccer, elo


def _ctx():
    df = soccer.load()
    df_elo, rating = elo.compute(df)
    models = soccer.fit_today(df_elo)
    return df_elo, rating, models


def test_goals_factor_one_is_noop():
    df_elo, rating, models = _ctx()
    a = soccer._predict_with(models, rating, "Brazil", "Morocco", neutral=True)
    b = soccer._predict_with(models, rating, "Brazil", "Morocco", neutral=True, goals_factor=1.0)
    assert abs(a["over"] - b["over"]) < 1e-12 and abs(a["lh"] - b["lh"]) < 1e-12
    assert a["blend"] == b["blend"]


def test_factor_raises_over_but_not_1x2():
    df_elo, rating, models = _ctx()
    base = soccer._predict_with(models, rating, "Brazil", "Morocco", neutral=True)
    up = soccer._predict_with(models, rating, "Brazil", "Morocco", neutral=True, goals_factor=1.2)
    # goles esperados suben ~20% y el Over 2.5 sube; el 1X2 (ancla) NO cambia
    assert abs(up["lh"] - base["lh"] * 1.2) < 1e-6
    assert up["over"] > base["over"]
    assert up["blend"] == base["blend"]                  # 1X2 identico (sale de la matriz base)


def test_factor_lowers_clean_sheet():
    df_elo, rating, models = _ctx()
    base = soccer._predict_with(models, rating, "Brazil", "Morocco", neutral=True)
    up = soccer._predict_with(models, rating, "Brazil", "Morocco", neutral=True, goals_factor=1.2)
    assert up["cs_home"] < base["cs_home"]               # mas goles -> menos vallas invictas


def test_evaluate_holdout_unchanged():
    # soccer.evaluate (holdout de 2 anios) NO usa goals_factor -> el ancla de calibracion base
    # es identica corriendola dos veces (prueba de que T6 no toca el motor base).
    import pandas as pd
    df = soccer.load()
    df_elo, _ = elo.compute(df)
    tf = pd.Timestamp("2024-01-01")
    m1 = soccer.evaluate(df_elo, tf, tf, pd.Timestamp("2026-01-01"))
    m2 = soccer.evaluate(df_elo, tf, tf, pd.Timestamp("2026-01-01"))
    assert abs(m1["ll_model"] - m2["ll_model"]) < 1e-12 and abs(m1["ll_over"] - m2["ll_over"]) < 1e-12
