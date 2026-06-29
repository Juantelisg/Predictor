"""Cartera: arma tickets (2-3 piernas por confianza) con los picks confiables y reparte el pote."""
import cartera


def _pk(market, pick, prob):
    return {"market": market, "pick": pick, "prob": prob, "level": cartera._lvl(prob)}


def _card(home, away, picks):
    return {"home": home, "away": away, "analysis": {"picks": picks}}


# ---- _lvl ----
def test_lvl_thresholds():
    assert cartera._lvl(0.70) == "ALTA"
    assert cartera._lvl(0.60) == "MEDIA"
    assert cartera._lvl(0.50) == "BAJA"


# ---- _capped_alloc: water-filling que despliega TODO el pote ----
def test_alloc_sums_to_pote():
    assert abs(sum(cartera._capped_alloc([3, 2, 1], 100.0)) - 100.0) < 1e-6


def test_alloc_cap_respected():
    a = cartera._capped_alloc([100, 1, 1], 100.0, cap_share=0.6)
    assert max(a) <= 60.0 + 1e-6 and abs(sum(a) - 100.0) < 1e-6


def test_alloc_single_takes_all():
    assert cartera._capped_alloc([5, 0, 0], 100.0) == [100.0, 0.0, 0.0]


def test_alloc_linear_in_pote():
    a1 = cartera._capped_alloc([3, 2, 1], 1.0)
    a10 = cartera._capped_alloc([3, 2, 1], 10.0)
    assert all(abs(x * 10 - y) < 1e-6 for x, y in zip(a1, a10))   # share x pote == alloc


# ---- confident_legs: una pierna por partido (su pick mas firme), ordenadas ----
def test_legs_top_pick_per_game():
    games = [{"game": "A vs B", "picks": [_pk("Goles", "Over 1.5", 0.70), _pk("Resultado", "Gana A", 0.66)]},
             {"game": "C vs D", "picks": [_pk("Doble", "C o empate", 0.80)]}]
    legs = cartera.confident_legs(games)
    assert [l["prob"] for l in legs] == [0.80, 0.70]          # ordenadas desc, top de cada partido
    assert legs[1]["pick"] == "Over 1.5"


def test_legs_skip_games_without_picks():
    games = [{"game": "A vs B", "picks": []}, {"game": "C vs D", "picks": [_pk("Doble", "x", 0.7)]}]
    assert len(cartera.confident_legs(games)) == 1


def test_legs_diversify_market_family():
    games = [{"game": "A vs B", "picks": [_pk("Doble oport.", "A o empate", 0.90), _pk("Goles", "Over 1.5", 0.75)]},
             {"game": "C vs D", "picks": [_pk("Doble oport.", "C o empate", 0.88), _pk("Resultado", "Gana C", 0.70)]}]
    legs = cartera.confident_legs(games)
    fams = {cartera._family(l["market"]) for l in legs}
    assert len(fams) == 2 and "doble" in fams          # mezcla, no dos dobles; el mas confiado igual entra


# ---- assemble: 3 piernas si las tres son ALTA, si no 2; sobrante = single ----
def test_assemble_three_when_all_alta():
    legs = [_pk("m", "p", 0.72), _pk("m", "p", 0.68), _pk("m", "p", 0.66)]
    for l in legs: l["game"] = "g"
    t = cartera.assemble(legs)
    assert len(t) == 1 and t[0]["n"] == 3


def test_assemble_two_when_not_all_alta():
    legs = [_pk("m", "p", 0.72), _pk("m", "p", 0.68), _pk("m", "p", 0.60)]   # 3ra es MEDIA
    for l in legs: l["game"] = "g"
    t = cartera.assemble(legs)
    assert [x["n"] for x in t] == [2, 1]                     # 2-leg + sobrante single


def test_assemble_two_legs_total():
    legs = [_pk("m", "p", 0.72), _pk("m", "p", 0.68)]
    for l in legs: l["game"] = "g"
    t = cartera.assemble(legs)
    assert len(t) == 1 and t[0]["n"] == 2


# ---- _ticket: prob conjunta = producto; confianza = la pierna mas floja ----
def test_ticket_joint_is_product():
    legs = [_pk("m", "p", 0.70), _pk("m", "p", 0.60)]
    for l in legs: l["game"] = "g"
    tk = cartera._ticket(legs)
    assert abs(tk["joint_prob"] - 0.42) < 1e-6


def test_ticket_level_is_weakest_leg():
    legs = [_pk("m", "p", 0.72), _pk("m", "p", 0.58)]        # ALTA + MEDIA
    for l in legs: l["game"] = "g"
    assert cartera._ticket(legs)["leg_level"] == "MEDIA"


# ---- build: payload con tajada por $1, suma 1 ----
def test_build_shares_sum_to_one():
    cards = [_card("A", "B", [_pk("Goles", "Over 1.5", 0.72)]),
             _card("C", "D", [_pk("Resultado", "Gana C", 0.68)]),
             _card("E", "F", [_pk("Doble", "E o empate", 0.60)])]
    data = cartera.build(cards)
    assert data["n_legs"] == 3 and data["tickets"]
    assert abs(sum(t["share"] for t in data["tickets"]) - 1.0) < 1e-6


def test_build_empty_when_no_picks():
    data = cartera.build([_card("A", "B", [])])
    assert data["tickets"] == [] and data["n_legs"] == 0
