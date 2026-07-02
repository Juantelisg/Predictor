"""Tests del recolector de disponibilidad (sensor.py, capa 1). Solo logica pura (sin red)."""
import math
import sensor


def _summary(team_id, starters, bench):
    """Arma un summary ESPN minimo con un bloque de rosters para `team_id`."""
    roster = [{"starter": True, "athlete": {"displayName": n}, "position": {"abbreviation": p}}
              for n, p in starters]
    roster += [{"starter": False, "athlete": {"displayName": n}, "position": {"abbreviation": p}}
               for n, p in bench]
    return {"rosters": [{"team": {"id": team_id}, "roster": roster}]}


def test_starters_of_solo_titulares_del_equipo():
    s = _summary(9, [("A", "G"), ("B", "F")], [("C", "M")])
    got = sensor._starters_of(s, 9)
    assert got == [{"name": "A", "pos": "G"}, {"name": "B", "pos": "F"}]
    assert sensor._starters_of(s, 205) == []          # team distinto -> vacio


def test_starters_of_match_por_id_como_string():
    s = _summary(9, [("A", "G")], [])
    assert sensor._starters_of(s, "9") == [{"name": "A", "pos": "G"}]


def test_tally_cuenta_starts_y_conserva_pos():
    xis = [[{"name": "A", "pos": "G"}, {"name": "B", "pos": "F"}],
           [{"name": "A", "pos": "G"}],
           [{"name": "A", "pos": "G"}, {"name": "B", "pos": "F"}]]
    counts = sensor._tally(xis)
    assert counts["A"] == {"pos": "G", "starts": 3}
    assert counts["B"] == {"pos": "F", "starts": 2}


def test_umbral_titular_habitual_es_mitad_hacia_arriba():
    # 3 partidos -> ceil(3/2)=2: entra quien arranco >=2
    n = 3
    counts = {"A": {"pos": "G", "starts": 3}, "B": {"pos": "F", "starts": 2},
              "C": {"pos": "M", "starts": 1}}
    thresh = math.ceil(n / 2)
    usual = sorted([nm for nm, e in counts.items() if e["starts"] >= thresh])
    assert usual == ["A", "B"]                        # C (1/3) queda afuera


# ── Alimentador B (merge IA) ──────────────────────────────────────────────────

def test_merge_lectura_fold_bajas_ia():
    av = {"home": {"team": "Spain", "ausentes": []}, "away": {"team": "Austria", "ausentes": []}}
    lect = {"disponibilidad": {"home": {"bajas": [{"jugador": "Pedri", "pos": "M", "impacto": "clave"}],
                                        "motivacion": "must-win"}}}
    sensor.merge_lectura(av, lect)
    assert av["home"]["bajas_ia"] == [{"jugador": "Pedri", "pos": "M", "impacto": "clave"}]
    assert av["home"]["motivacion"] == "must-win"
    assert av["away"]["bajas_ia"] == []               # sin datos -> lista vacia


def test_merge_lectura_noop_sin_bloque():
    av = {"home": {"team": "Spain"}, "away": {"team": "Austria"}}
    sensor.merge_lectura(av, {"summary": "algo"})      # lectura vieja sin 'disponibilidad'
    assert av["home"]["bajas_ia"] == []


# ── Capa 2 (ajuste shadow, acotado) ───────────────────────────────────────────

def test_adjust_sin_ausencias_no_mueve():
    av = {"home": {"ausentes": []}, "away": {"ausentes": []}}
    probs, delta = sensor.adjust([0.6, 0.25, 0.15], av)
    assert delta == 0.0 and abs(sum(probs) - 1.0) < 1e-6


def test_adjust_baja_al_favorito_con_mas_ausencias_y_respeta_cap():
    # local con muchas ausencias -> se le baja; delta nunca supera el cap
    av = {"home": {"ausentes": [{"name": n} for n in "ABCDEFGH"]}, "away": {"ausentes": []}}
    probs, delta = sensor.adjust([0.6, 0.25, 0.15], av)
    assert 0 < delta <= sensor.ADJ_CAP + 1e-9
    assert probs[0] < 0.6 and probs[2] > 0.15         # baja local, sube visita
    assert abs(sum(probs) - 1.0) < 1e-6               # renormaliza


def test_adjust_simetrico_favorece_al_menos_golpeado():
    av = {"home": {"ausentes": []}, "away": {"ausentes": [{"name": "X"}, {"name": "Y"}]}}
    probs, delta = sensor.adjust([0.5, 0.25, 0.25], av)
    assert delta < 0 and probs[0] > 0.5               # visita golpeada -> sube local
