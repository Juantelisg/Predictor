"""Props de jugador (Fase 2): gate por rol (posicion) + contraccion Beta-Binomial de la tasa +
seleccion por banda. Funciones puras (sin red)."""
import espn_players as ep


def test_role_classification():
    assert ep._role("G") == "gk"
    assert ep._role("CD-L") == "def"
    assert ep._role("LB") == "def"
    assert ep._role("RB") == "def"
    assert ep._role("F") == "att"
    assert ep._role("AM-R") == "att"
    assert ep._role("LM") == "att"


def test_shrink_pulls_small_sample_toward_base():
    # 5/5 = 100% crudo, base 0.55, K=5 -> se contrae bien por debajo de 1.0 (anti-sobreconfianza)
    p = ep._shrink(5, 5, 0.55)
    assert 0.7 < p < 0.8
    assert ep._shrink(0, 0, 0.5) is None       # sin juegos -> None


def test_select_props_bands_dedups_and_headline_only():
    cands = [
        {"who": "A", "market": "tiros al arco",    "line": 0.5, "p": 0.72},
        {"who": "A", "market": "gol o asistencia", "line": 0.5, "p": 0.65},   # dedup: A ya elegido
        {"who": "B", "market": "tapadas",          "line": 1.5, "p": 0.61},
        {"who": "C", "market": "tiros",            "line": 0.5, "p": 0.80},   # no titular -> fuera
        {"who": "D", "market": "tiros al arco",    "line": 0.5, "p": 0.50},   # bajo gate -> fuera
        {"who": "E", "market": "tiros al arco",    "line": 0.5, "p": 0.95},   # sobre techo -> fuera
    ]
    sel = ep.select_props(cands, per_player=1)
    assert [c["who"] for c in sel] == ["A", "B"]
