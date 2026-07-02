"""De-vig y la cadena de edge: el de-vig saca el margen y normaliza; el gate bloquea familias
no calificadas; SOSPECHOSO captura edges absurdos."""
import pytest
import edge


def test_devig_sums_to_one():
    for odds in ([1.95, 3.6, 4.5], [1.5, 4.0, 7.0], [2.0, 2.0]):
        fair = edge.devig(odds)
        assert abs(sum(fair) - 1.0) < 1e-9


def test_devig_removes_margin():
    odds = [1.90, 1.90]                       # -110/-110: implicitas suman 1.0526 (vig)
    raw = sum(1 / o for o in odds)
    assert raw > 1.0                          # hay margen
    assert abs(sum(edge.devig(odds)) - 1.0) < 1e-9   # de-vigeada suma 1


def test_devig_monotonic():
    fair = edge.devig([1.5, 4.0, 7.0])        # cuota mas baja -> prob mas alta
    assert fair[0] > fair[1] > fair[2]


def test_gate_blocks_unqualified_family():
    rows = edge.edge_market([0.70, 0.30], [2.10, 1.72], "corners")   # familia NO calificada
    assert all(r["tier"] == "NO-APTO" for r in rows)


def test_suspicious_huge_edge():
    rows = edge.edge_market([0.95, 0.03, 0.02], [1.95, 3.6, 4.5], "1x2")
    assert rows[0]["tier"] == "SOSPECHOSO"    # edge enorme vs book liquido = NO se apuesta


def test_pass_when_no_edge():
    rows = edge.edge_market([0.51, 0.27, 0.22], [1.95, 3.6, 4.5], "1x2")
    assert rows[0]["tier"] == "PASAR"         # edge < MIN_EDGE


def test_power_devig_shrinks_longshots():
    odds = [1.95, 3.6, 4.5]
    prop = edge.devig(odds)                   # proporcional
    powr = edge.devig_power(odds)             # potencia
    assert abs(sum(powr) - 1.0) < 1e-9
    assert powr[2] < prop[2]                  # el longshot (cuota 4.5) queda MENOR con power
    assert powr[0] > prop[0]                  # el favorito, mayor -> mata edges falsos de longshot


def test_gate_draw_regime_blocks_1x2():
    # cuotas con empate muy corto (fair del empate alta) = mercado priceando regimen -> NO-APTO
    rows = edge.edge_market([0.45, 0.30, 0.25], [2.6, 2.6, 3.4], "1x2")
    assert all(r["tier"] == "NO-APTO" for r in rows)
    assert "regimen" in rows[0]["reason"]


def test_gate_longshot_blocks_high_odds():
    # outcome con cuota > ODDS_MAX -> NO-APTO aunque el modelo vea edge (overround 1.02, valido)
    rows = edge.edge_market([0.35, 0.25, 0.40], [1.8, 3.8, 5.0], "1x2")
    assert rows[2]["tier"] == "NO-APTO" and "longshot" in rows[2]["reason"]


def test_gate_overround_blocks_corrupt():
    rows = edge.edge_market([0.5, 0.3, 0.2], [1.3, 1.3, 1.3], "1x2")   # overround ~2.3, corrupto
    assert all(r["tier"] == "NO-APTO" for r in rows)


def test_p_bet_shrinks_toward_market():
    rows = edge.edge_market([0.58, 0.25, 0.17], [1.95, 3.6, 4.5], "1x2")
    r = rows[0]
    assert r["p_market"] < r["p_bet"] < r["p_model"]   # p_bet a mitad de camino
