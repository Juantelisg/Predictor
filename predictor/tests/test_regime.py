"""Factor de nivel del torneo (empirical-Bayes walk-forward): shrink hacia 1.0, anti-fuga temporal,
y aplicacion multiplicativa que baja el nivel sin invertir el orden entre lineas."""
import regime


def _ev(kind, date, home, away, total):
    """3 filas (una por linea) de un partido con su total real, como las escribe feedback.eval."""
    lines = regime.LINES[kind]
    return [{"date": date, "home": home, "away": away, "market": f"{kind}:over:{ln}",
             "prob": 0.5, "result": str(total), "outcome": int(total > ln),
             "model_version": f"{kind}-sb-v2"} for ln in lines]


def test_factor_identity_without_data():
    f, n = regime.tournament_factor("cards", before_date="2026-06-11", evals=[])
    assert f == 1.0 and n == 0


def test_factor_shrinks_toward_one(monkeypatch):
    monkeypatch.setattr(regime, "_model_total", lambda kind, h, a: 4.0)   # modelo dice 4
    ev = []
    for i in range(4):
        ev += _ev("cards", f"2026-06-1{i}", f"A{i}", f"B{i}", 2)          # real = 2 (mitad)
    f, n = regime.tournament_factor("cards", before_date="2026-07-01", evals=ev)
    # m_hat = sum_real/sum_modelo = (4*2)/(4*4) = 0.5; shrunk hacia 1 con K=6, n=4: (4*0.5+6)/10 = 0.8
    assert n == 4 and abs(f - 0.8) < 1e-9


def test_factor_walk_forward_excludes_current_and_future(monkeypatch):
    monkeypatch.setattr(regime, "_model_total", lambda kind, h, a: 4.0)
    ev = _ev("cards", "2026-06-15", "A", "B", 2) + _ev("cards", "2026-06-20", "C", "D", 3)
    # before_date = 2026-06-15 -> NO cuenta el del 15 (>=) ni el del 20 -> sin muestra previa
    f, n = regime.tournament_factor("cards", before_date="2026-06-15", evals=ev)
    assert n == 0 and f == 1.0


def test_factor_dedups_lines_per_game(monkeypatch):
    monkeypatch.setattr(regime, "_model_total", lambda kind, h, a: 4.0)
    ev = _ev("cards", "2026-06-15", "A", "B", 2)                          # 3 filas, 1 partido
    _, n = regime.tournament_factor("cards", before_date="2026-07-01", evals=ev)
    assert n == 1


def test_predict_factor_lowers_expected_total():
    import statsbomb_data as sb
    # dos selecciones con datos StatsBomb; factor < 1 baja el total esperado proporcional
    base = sb.predict_cards("France", "Germany")
    scaled = sb.predict_cards("France", "Germany", factor=0.7)
    assert scaled["total_exp"] < base["total_exp"]
    assert abs(scaled["total_exp"] - base["total_exp"] * 0.7) < 0.05
