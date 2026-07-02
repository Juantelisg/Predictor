"""Picks confiables (T9): usan prob CALIBRADA por familia y el gate PICK_FAMILIES. Un pick que
crudo daba >=62% pero calibrado cae por debajo NO aparece; cards nunca entra."""
import analizar


def _res(cal_home, cal_draw, cal_away):
    return [{"label": "Gana A", "cal": cal_home}, {"label": "Empate", "cal": cal_draw},
            {"label": "Gana B", "cal": cal_away}]


def test_pick_dropped_when_calibrated_below_threshold():
    # over15 crudo 0.70 (>=62%), pero cal_fn lo comprime a 0.55 -> NO debe aparecer
    resultado = _res(0.40, 0.30, 0.30)
    doble = {"1X": 0.40, "X2": 0.40, "12": 0.40}
    goles = {"over15": 0.70, "over25": 0.50, "btts": 0.50}
    cal = lambda p, fam: 0.55 if fam == "over" else p     # 'over' se comprime bajo el umbral
    picks = analizar._picks("A", "B", resultado, doble, goles, None, cal)
    assert all(p["family"] != "over" for p in picks)       # over quedo por debajo de 62% -> fuera


def test_pick_kept_when_calibrated_above_threshold():
    resultado = _res(0.70, 0.20, 0.10)                     # Resultado calibrado 70% -> confiable
    doble = {"1X": 0.90, "X2": 0.30, "12": 0.80}
    goles = {"over15": 0.50, "over25": 0.50, "btts": 0.50}
    picks = analizar._picks("A", "B", resultado, doble, goles, None, lambda p, f: p)
    assert any(p["family"] == "1x2" and p["prob"] >= 0.62 for p in picks)


def test_corners_uses_calibrated_prob():
    resultado = _res(0.40, 0.30, 0.30)
    doble = {"1X": 0.40, "X2": 0.40, "12": 0.40}
    goles = {"over15": 0.50, "over25": 0.50, "btts": 0.50}
    corners = {"o85": 0.70}
    # sin calibrar entraria (0.70); calibrado a 0.58 -> fuera
    cal = lambda p, fam: 0.58 if fam == "corners" else p
    picks = analizar._picks("A", "B", resultado, doble, goles, corners, cal)
    assert all(p["family"] != "corners" for p in picks)


def test_cards_family_never_in_picks():
    assert "cards" not in analizar.PICK_FAMILIES


def test_only_qualified_families_selected():
    resultado = _res(0.80, 0.10, 0.10)
    doble = {"1X": 0.90, "X2": 0.20, "12": 0.90}
    goles = {"over15": 0.90, "over25": 0.80, "btts": 0.80}
    corners = {"o85": 0.90}
    picks = analizar._picks("A", "B", resultado, doble, goles, corners, lambda p, f: p)
    assert all(p["family"] in analizar.PICK_FAMILIES for p in picks)
    assert len(picks) <= 5
