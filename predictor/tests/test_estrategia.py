"""Estrategia: combinacion con criterio. Mascaras de pierna sobre el marcador simulado y prob
conjunta correlacionada (funciones puras, sin red)."""
import numpy as np
import estrategia as es


def test_leg_mask_result_and_goals():
    hg = np.array([2, 1, 0, 3]); ag = np.array([0, 1, 1, 0])
    assert list(es._leg_mask(hg, ag, "H", "A", "Resultado", "Gana H")) == [True, False, False, True]
    assert list(es._leg_mask(hg, ag, "H", "A", "Goles", "Under 2.5")) == [True, True, True, False]
    assert list(es._leg_mask(hg, ag, "H", "A", "Goles", "Over 2.5")) == [False, False, False, True]


def test_leg_mask_independent_returns_none():
    hg = np.array([1]); ag = np.array([1])
    assert es._leg_mask(hg, ag, "H", "A", "Corners", "Over 6.5") is None
    assert es._leg_mask(hg, ag, "H", "A", "Prop: tiros al arco", "Mbappe O0.5") is None


def test_same_match_joint_reinforcing():
    # favorito que controla: 'H o empate' y 'Under 3.5' se solapan -> conjunta > producto (lift>1)
    hg = np.array([1, 2, 1, 0, 1]); ag = np.array([0, 0, 0, 0, 2])
    picks = [{"market": "Doble oport.", "pick": "H o empate", "prob": 0.8},
             {"market": "Goles", "pick": "Under 3.5", "prob": 0.7}]
    joint, prod, lift = es.same_match_joint({"hg": hg, "ag": ag}, "H", "A", picks)
    assert abs(joint - 0.8) < 1e-9 and lift > 1


def test_same_match_joint_mixes_independent_leg():
    # una pierna correlacionada (marcador) x una independiente (corners) -> joint = mask.mean * prob
    hg = np.array([1, 1, 0, 2]); ag = np.array([0, 0, 0, 0])
    picks = [{"market": "Resultado", "pick": "Gana H", "prob": 0.6},   # hg>ag -> [T,T,F,T] = 0.75
             {"market": "Corners", "pick": "Over 6.5", "prob": 0.65}]  # independiente -> *0.65
    joint, prod, lift = es.same_match_joint({"hg": hg, "ag": ag}, "H", "A", picks)
    assert abs(joint - 0.75 * 0.65) < 1e-9
