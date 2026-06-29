"""Ticket: audita el ticket que arma el USUARIO (prob calibrada del modelo vs su cuota -> edge)."""
import ticket


def _an(ch=0.40, cd=0.28, ca=0.32, o15=0.74, o25=0.48, o35=0.22, btts=0.53,
        cs_home=0.30, cs_away=0.25, corners=None, picks=None):
    """Cuadro `an` minimo (sin red), con el shape que devuelve analizar.analyze."""
    return {"home": "Local", "away": "Visita",
            "resultado": [{"label": "Gana Local", "cal": ch}, {"label": "Empate", "cal": cd},
                          {"label": "Gana Visita", "cal": ca}],
            "goles": {"over15": o15, "over25": o25, "over35": o35, "btts": btts},
            "valla": {"home": cs_home, "away": cs_away},
            "corners": corners, "picks": picks or []}


# ---- implied: 1/cuota ----
def test_implied():
    assert abs(ticket.implied(2.0) - 0.5) < 1e-9
    assert abs(ticket.implied(1.25) - 0.8) < 1e-9


# ---- model_prob: resuelve cada mercado desde el cuadro calibrado ----
def test_model_prob_1x2():
    an = _an(ch=0.40, cd=0.28, ca=0.32)
    assert ticket.model_prob(an, "1x2", "home") == (0.40, "1x2")
    assert ticket.model_prob(an, "1x2", "away") == (0.32, "1x2")


def test_model_prob_dc_from_calibrated_1x2():
    an = _an(ch=0.40, cd=0.28, ca=0.32)
    p, fam = ticket.model_prob(an, "dc", "x2")          # visita o empate = away + draw
    assert abs(p - 0.60) < 1e-9 and fam == "dc"
    assert abs(ticket.model_prob(an, "dc", "12")[0] - 0.72) < 1e-9   # sin empate = home + away


def test_model_prob_over_under():
    an = _an(o25=0.48)
    assert ticket.model_prob(an, "over", "over2.5") == (0.48, "over")
    assert abs(ticket.model_prob(an, "over", "under2.5")[0] - 0.52) < 1e-9


def test_model_prob_btts_and_cs():
    an = _an(btts=0.53, cs_home=0.30)
    assert ticket.model_prob(an, "btts", "yes") == (0.53, "btts")
    assert abs(ticket.model_prob(an, "btts", "no")[0] - 0.47) < 1e-9
    assert ticket.model_prob(an, "cs", "home") == (0.30, "cs")


def test_model_prob_corners_none_when_absent():
    assert ticket.model_prob(_an(corners=None), "corners", "o8.5") == (None, "corners")
    assert ticket.model_prob(_an(corners={"o85": 0.72}), "corners", "o8.5") == (0.72, "corners")


def test_model_prob_none_on_error():
    assert ticket.model_prob({"error": "x"}, "1x2", "home") == (None, "1x2")


# ---- _verdict: la cuota manda; edge enorme = REVISAR, no valor ----
def test_verdict_valor_when_qualified_edge_positive():
    v = ticket._verdict(0.62, 0.55, "1x2")              # +7 pts, dentro de [MIN, MAX]
    assert v["tier"] == "VALOR"


def test_verdict_revisar_when_edge_huge():
    v = ticket._verdict(0.80, 0.55, "1x2")              # +25 pts vs cuota sharp -> sospechoso
    assert v["tier"] == "REVISAR"


def test_verdict_cuota_cara_when_model_below():
    v = ticket._verdict(0.45, 0.55, "1x2")
    assert v["tier"] == "CUOTA CARA"


def test_verdict_justa_when_aligned():
    v = ticket._verdict(0.56, 0.55, "1x2")              # ~igual
    assert v["tier"] == "JUSTA"


def test_verdict_contexto_when_family_not_qualified():
    v = ticket._verdict(0.70, 0.50, "btts")             # btts no calificada
    assert v["tier"] == "CONTEXTO"


def test_verdict_sin_modelo_when_prob_none():
    assert ticket._verdict(None, 0.5, "corners")["tier"] == "SIN-MODELO"


# ---- analyze_leg ----
def test_analyze_leg_full():
    an = _an(ch=0.40)
    leg = {"match": "L vs V", "market": "1x2", "pick": "home", "cuota": 2.0, "label": "Gana L"}
    r = ticket.analyze_leg(leg, an)
    assert r["model_prob"] == 0.40 and r["implied"] == 0.5
    assert r["tier"] == "CUOTA CARA"                    # 0.40 < 0.50
    assert abs(r["ev"] - (0.40 * 2.0 - 1)) < 1e-9       # EV = -0.20


# ---- combo: producto si partidos distintos; FLAG si mismo partido ----
def test_combo_product_independent():
    legs = [{"match": "A vs B", "cuota": 2.0, "model_prob": 0.5},
            {"match": "C vs D", "cuota": 2.0, "model_prob": 0.5}]
    c = ticket.combo(legs)
    assert c["same_game"] is False
    assert abs(c["cuota_total"] - 4.0) < 1e-9
    assert abs(c["joint_prob"] - 0.25) < 1e-9
    assert abs(c["implied"] - 0.25) < 1e-9


def test_combo_flags_same_game():
    legs = [{"match": "A vs B", "cuota": 1.8, "model_prob": 0.6},
            {"match": "A vs B", "cuota": 2.1, "model_prob": 0.5}]
    assert ticket.combo(legs)["same_game"] is True


def test_combo_joint_none_when_a_leg_missing_model():
    legs = [{"match": "A vs B", "cuota": 2.0, "model_prob": 0.5},
            {"match": "C vs D", "cuota": 2.0, "model_prob": None}]
    c = ticket.combo(legs)
    assert c["joint_prob"] is None and c["edge"] is None
    assert abs(c["cuota_total"] - 4.0) < 1e-9           # la cuota total no depende del modelo


# ---- analyze_ticket: combo solo si combinada y >=2 piernas ----
def test_analyze_ticket_combinada_has_combo():
    an = {"A vs B": _an(), "C vs D": _an()}
    tk = [{"match": "A vs B", "market": "over", "pick": "over1.5", "cuota": 1.4},
          {"match": "C vs D", "market": "1x2", "pick": "home", "cuota": 2.0}]
    out = ticket.analyze_ticket(tk, "combinada", an)
    assert "combo" in out and out["combo"]["n"] == 2


def test_analyze_ticket_simples_no_combo():
    an = {"A vs B": _an()}
    tk = [{"match": "A vs B", "market": "over", "pick": "over1.5", "cuota": 1.4}]
    out = ticket.analyze_ticket(tk, "simples", an)
    assert "combo" not in out and out["n"] == 1
