"""Recalibrador: identidad sin datos, inversa logit/sigmoid, y la cadena de fallback por
contexto (contexto -> familia -> version)."""
import calib


def test_apply_identity_when_empty():
    assert calib.apply(0.63, "soccer-v3", "1x2", params={}) == 0.63


def test_apply_identity_param_passthrough():
    params = {"v|1x2": {"a": 1.0, "b": 0.0, "n": 5}}
    assert calib.apply(0.63, "v", "1x2", params=params) == 0.63


def test_logit_sigmoid_inverse():
    for p in (0.1, 0.37, 0.5, 0.82):
        assert abs(float(calib._sigmoid(calib._logit(p))) - p) < 1e-9


def test_fit_one_identity_below_min_n():
    a, b, n = calib.fit_one([0.5] * 10, [1, 0] * 5)   # n=10 < MIN_N
    assert (a, b) == (1.0, 0.0) and n == 10


def test_context_falls_back_to_family():
    # contexto ausente/identidad -> usa la familia (no-identidad)
    params = {"v|1x2": {"a": 1.3, "b": 0.1, "n": 50}}
    out = calib.apply(0.6, "v", "1x2", params=params, context="fav")
    assert out != 0.6 and abs(out - float(calib._sigmoid(1.3 * calib._logit(0.6) + 0.1))) < 1e-9


def test_context_wins_when_present():
    params = {"v|1x2": {"a": 1.0, "b": 0.0, "n": 5},        # familia identidad
              "v|1x2|fav": {"a": 1.5, "b": 0.0, "n": 50}}   # contexto activo
    out = calib.apply(0.6, "v", "1x2", params=params, context="fav")
    assert abs(out - float(calib._sigmoid(1.5 * calib._logit(0.6)))) < 1e-9


def test_context_of_buckets():
    assert calib.context_of(0.70) == "fav"
    assert calib.context_of(0.50) == "mid"
    assert calib.context_of(0.20) == "dog"
