"""Acople corners/cards <-> dominancia en el Monte Carlo (T8): el bug '*0' hacia el acople de
corners inalcanzable. Ahora el mecanismo funciona (k=0 -> independencia; k!=0 -> depende del margen)."""
import numpy as np
import simulate


def test_couple_zero_is_flat():
    am = np.array([0, 1, 2, 3], float)
    out = simulate._couple(4.0, 0.0, am)
    assert np.allclose(out, 4.0)                 # k=0 -> lambda constante (independiente del margen)


def test_couple_positive_increases_with_margin():
    am = np.array([0, 1, 2, 3], float)
    out = simulate._couple(4.0, 0.3, am)
    assert out[0] == 4.0 and np.all(np.diff(out) > 0)   # k>0 -> crece con |margen|
    assert abs(out[2] - 4.0 * np.exp(0.6)) < 1e-9


def test_couple_negative_decreases_with_margin():
    am = np.array([0, 2], float)
    out = simulate._couple(5.0, -0.2, am)
    assert out[1] < out[0]                       # k<0 -> menos conteo en blowouts


def test_couple_applies_to_corners_and_cards_symmetrically():
    # el bug era que corners tenia un '*0' extra y cards no. Ahora _couple es la MISMA para ambos.
    am = np.array([2.0])
    assert simulate._couple(9.0, 0.1, am)[0] == 9.0 * np.exp(0.2)
    assert simulate._couple(3.0, 0.1, am)[0] == 3.0 * np.exp(0.2)


def test_couple_floor_positive():
    out = simulate._couple(0.0, -5.0, np.array([10.0]))
    assert out[0] > 0                            # nunca lambda <= 0 (Poisson valido)
