"""Anti-fuga temporal: el Elo PRE-partido usa SOLO informacion anterior. Es el guardrail
mas importante del sistema (una fuga infla la calibracion en silencio)."""
import pandas as pd
import elo


def _df():
    return pd.DataFrame([
        {"date": "2020-01-01", "home_team": "A", "away_team": "B", "home_score": 2, "away_score": 0,
         "neutral": False, "tournament": "Friendly"},
        {"date": "2020-02-01", "home_team": "A", "away_team": "C", "home_score": 1, "away_score": 1,
         "neutral": True, "tournament": "FIFA World Cup"},
        {"date": "2020-03-01", "home_team": "B", "away_team": "C", "home_score": 0, "away_score": 0,
         "neutral": True, "tournament": "Friendly"},
    ]).assign(date=lambda d: pd.to_datetime(d["date"]))


def test_first_appearance_is_init():
    out, _ = elo.compute(_df())
    assert out.iloc[0].elo_home_pre == elo.INIT      # A debut -> rating inicial
    assert out.iloc[0].elo_away_pre == elo.INIT      # B debut -> rating inicial


def test_pre_rating_reflects_only_prior_games():
    out, _ = elo.compute(_df())
    # A gano el game0 -> su Elo PRE del game1 debe haber subido por encima de INIT
    assert out.iloc[1].elo_home_pre > elo.INIT
    # B perdio el game0 -> su Elo PRE del game2 debe estar por debajo de INIT
    assert out.iloc[2].elo_home_pre < elo.INIT


def test_no_future_in_pre():
    # el pre del primer partido NO puede depender de partidos futuros -> siempre INIT
    out, _ = elo.compute(_df())
    assert out.sort_values("date").iloc[0].elo_home_pre == elo.INIT
