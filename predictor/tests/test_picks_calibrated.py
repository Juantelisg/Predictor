"""Picks confiables: mercados de resultado (1X2/doble/BTTS) por gate calibrado, y O/U
(goles/corners/tarjetas) con LINEA DINAMICA (_best_ou elige la linea mas jugable). Toda prob
pasa por el recalibrador por familia; una linea que calibrada cae bajo el gate NO aparece."""
import analizar

ident = lambda p, fam: p


def _res(cal_home, cal_draw, cal_away):
    return [{"label": "Gana A", "cal": cal_home}, {"label": "Empate", "cal": cal_draw},
            {"label": "Gana B", "cal": cal_away}]


# ---------------------------------------------------------------- _best_ou (linea dinamica)

def test_best_ou_picks_line_closest_to_target():
    # ambas en banda [0.62, 0.85]; TARGET 0.70 -> gana la mas cercana (O7.5 = 0.68)
    b = analizar._best_ou([[6.5, 0.80], [7.5, 0.68], [8.5, 0.45]], "corners", ident, "Corners")
    assert b["pick"] == "Over 7.5"


def test_best_ou_excludes_trivial_lock():
    # O1.5 esperado ~0.90+: por encima del techo -> no es una apuesta, el modelo sube de linea
    assert analizar._best_ou([[0.5, 0.97], [1.5, 0.90]], "over", ident, "Goles") is None


def test_best_ou_under_side():
    # pocos goles: P(over 3.5)=0.30 -> el lado jugable es Under 3.5 a 0.70
    b = analizar._best_ou([[3.5, 0.30]], "over", ident, "Goles")
    assert b["pick"] == "Under 3.5" and abs(b["prob"] - 0.70) < 1e-9


def test_best_ou_none_when_coinflip():
    # nada firme -> PASAR ese mercado (honesto), no forzar una moneda
    assert analizar._best_ou([[2.5, 0.52]], "over", ident, "Goles") is None


def test_best_ou_respects_calibration():
    # crudo 0.70 (jugable) pero el calibrador lo comprime a 0.58 -> fuera de banda
    cal = lambda p, fam: 0.58 if fam == "corners" else p
    assert analizar._best_ou([[7.5, 0.70]], "corners", cal, "Corners") is None


def test_best_ou_attaches_next_line_over():
    # confiable O6.5 (0.78); la SIGUIENTE O7.5 (0.61, menos %) va como alt informativa
    b = analizar._best_ou([[6.5, 0.78], [7.5, 0.61], [8.5, 0.45]], "corners", ident, "Corners")
    assert b["pick"] == "Over 6.5"
    assert b["alt"]["pick"] == "Over 7.5" and b["alt"]["prob"] < b["prob"]


def test_best_ou_next_line_under_side():
    # pocos goles: Under 3.5 (0.70) confiable; siguiente Under 2.5 (mas exigente, menos %)
    b = analizar._best_ou([[2.5, 0.55], [3.5, 0.30]], "over", ident, "Goles")
    assert b["pick"] == "Under 3.5"
    assert b["alt"]["pick"] == "Under 2.5" and b["alt"]["prob"] < b["prob"]


# ---------------------------------------------------------------- _picks (integracion)

def test_picks_dynamic_corner_line():
    resultado = _res(0.40, 0.30, 0.30)
    doble = {"1X": 0.55, "X2": 0.55, "12": 0.55}                  # nada de resultado cruza el gate
    goles = {"btts": 0.50, "curve": [[1.5, 0.95], [2.5, 0.55]]}   # O1.5 trivial, O2.5 moneda -> sin pick
    corners = {"curve": [[6.5, 0.80], [7.5, 0.68], [8.5, 0.45]]}
    picks = analizar._picks("A", "B", resultado, doble, goles, corners, ident)
    cp = [p for p in picks if p["family"] == "corners"]
    assert len(cp) == 1 and cp[0]["pick"] == "Over 7.5"


def test_ou_pick_dropped_when_calibrated_below_gate():
    cal = lambda p, fam: 0.55 if fam == "over" else p            # 'over' se comprime bajo el gate
    goles = {"btts": 0.50, "curve": [[1.5, 0.70]]}
    picks = analizar._picks("A", "B", _res(.4, .3, .3), {"1X": .4, "X2": .4, "12": .4}, goles, None, cal)
    assert all(p["family"] != "over" for p in picks)


def test_fixed_market_kept_above_gate():
    picks = analizar._picks("A", "B", _res(0.70, 0.20, 0.10), {"1X": 0.90, "X2": 0.30, "12": 0.80},
                            {"btts": 0.50}, None, ident)
    assert any(p["family"] == "1x2" and p["prob"] >= 0.62 for p in picks)


def test_cards_now_allowed():
    assert "cards" in analizar.PICK_FAMILIES        # antes excluida a mano; ahora la protege el calibrador


def test_cards_dynamic_pick():
    goles = {"btts": 0.50}
    cards = {"curve": [[2.5, 0.80], [3.5, 0.55]]}
    picks = analizar._picks("A", "B", _res(.4, .3, .3), {"1X": .4, "X2": .4, "12": .4},
                            goles, None, ident, cards)
    kp = [p for p in picks if p["family"] == "cards"]
    assert len(kp) == 1 and kp[0]["pick"] == "Over 2.5"


def test_max_five_and_qualified_families():
    goles = {"btts": 0.80, "curve": [[2.5, 0.72]]}
    corners = {"curve": [[7.5, 0.72]]}
    cards = {"curve": [[2.5, 0.72]]}
    picks = analizar._picks("A", "B", _res(0.80, 0.10, 0.10), {"1X": 0.90, "X2": 0.20, "12": 0.90},
                            goles, corners, ident, cards)
    assert all(p["family"] in analizar.PICK_FAMILIES for p in picks)
    assert len(picks) <= 5
