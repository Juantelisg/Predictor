"""Resolvers de mercados: el marcador -> outcome. Regresion de consistencia (1X2 mutuamente
excluyente, doble oportunidad coherente, over/btts/cs correctos)."""
import pytest
import feedback

R = feedback.RESOLVERS
SCORES = [(0, 0), (1, 0), (0, 1), (2, 1), (1, 1), (3, 0), (2, 2), (0, 3)]


@pytest.mark.parametrize("h,a", SCORES)
def test_1x2_exactly_one(h, a):
    one = R["1x2:home"](h, a) + R["1x2:draw"](h, a) + R["1x2:away"](h, a)
    assert one == 1, f"1X2 debe tener exactamente un verdadero para {h}-{a}, dio {one}"


@pytest.mark.parametrize("h,a", SCORES)
def test_double_chance_coherent(h, a):
    # cada doble oportunidad = union de dos resultados 1X2
    assert R["dc:1x"](h, a) == (R["1x2:home"](h, a) or R["1x2:draw"](h, a))
    assert R["dc:x2"](h, a) == (R["1x2:away"](h, a) or R["1x2:draw"](h, a))
    assert R["dc:12"](h, a) == (R["1x2:home"](h, a) or R["1x2:away"](h, a))


def test_over_lines():
    assert R["over:1.5"](1, 1) is True and R["over:1.5"](1, 0) is False
    assert R["over:2.5"](2, 1) is True and R["over:2.5"](1, 1) is False
    assert R["over:3.5"](2, 2) is True and R["over:3.5"](2, 1) is False


def test_btts_and_cs():
    assert R["btts:yes"](1, 1) is True and R["btts:yes"](2, 0) is False
    assert R["cs:home"](1, 0) is True and R["cs:home"](1, 1) is False   # local valla = visita 0
    assert R["cs:away"](0, 1) is True and R["cs:away"](1, 1) is False


def test_mlb_ml_matches_1x2_home():
    for h, a in SCORES:
        assert R["ml:home"](h, a) == R["1x2:home"](h, a)
