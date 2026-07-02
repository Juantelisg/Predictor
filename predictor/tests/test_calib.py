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


def test_slope_clamp_never_inverts():
    # datos anti-correlacionados (prob alta -> outcome 0): el Platt querria pendiente NEGATIVA.
    # El clamp SLOPE_MIN lo manda a identidad (nunca invertir la prob = el bug de mlb-ml|mid).
    probs = [0.9] * 20 + [0.1] * 20
    outcomes = [0] * 20 + [1] * 20
    a, b, n = calib.fit_one(probs, outcomes, n_matches=40)
    assert (a, b) == (1.0, 0.0)             # identidad, no inversion


def test_fit_counts_matches_not_rows():
    # 3 partidos, cada uno con 12 filas correlacionadas (36 filas). El gate cuenta PARTIDOS (3),
    # que estan por debajo de MIN_N=15 -> identidad, y el n reportado es 3 (partidos), no 36.
    evals = []
    for i in range(3):
        for mk in ("1x2:home", "1x2:draw", "1x2:away", "over:1.5", "over:2.5", "over:3.5",
                   "dc:1x", "dc:x2", "dc:12", "btts:yes", "cs:home", "cs:away"):
            evals.append({"date": f"2026-06-1{i}", "home": f"A{i}", "away": f"B{i}",
                          "market": mk, "prob": 0.6, "outcome": 1, "model_version": "v"})
    params = calib.fit(evals)
    p = params["v|1x2"]
    assert p["n"] == 3 and (p["a"], p["b"]) == (1.0, 0.0)   # 3 partidos < MIN_N -> identidad


def test_context_needs_min_matches():
    # 20 partidos (>MIN_N pero <CTX_MIN_MATCHES=30), todos favoritos: la familia se fitea, el
    # contexto |fav queda en identidad (no se activa hasta 30 partidos).
    evals = [{"date": f"2026-06-{i:02d}", "home": f"A{i}", "away": f"B{i}",
              "market": "1x2:home", "prob": 0.7, "outcome": (i % 2), "model_version": "v"}
             for i in range(20)]
    params = calib.fit(evals)
    assert params["v|1x2"]["n"] == 20                       # familia: 20 partidos
    assert (params["v|1x2|fav"]["a"], params["v|1x2|fav"]["b"]) == (1.0, 0.0)  # contexto inactivo


def test_apply_1x2_renormalizes_to_one():
    # tres calibradores per-outcome distintos: las tres probs calibradas por separado NO sumarian 1;
    # apply_1x2 las renormaliza (mata el 'edge fantasma').
    params = {"v|1x2:home": {"a": 1.3, "b": 0.2, "n": 48},
              "v|1x2:draw": {"a": 0.9, "b": -0.1, "n": 48},
              "v|1x2:away": {"a": 1.1, "b": 0.0, "n": 48}}
    ch, cd, ca = calib.apply_1x2(0.50, 0.30, 0.20, "v", params)
    assert abs(ch + cd + ca - 1.0) < 1e-12                  # suma exactamente 1
    assert ch > cd > ca > 0                                 # orden preservado (0.50>0.30>0.20), positivas


def test_apply_1x2_falls_back_to_family():
    # sin per-outcome, usa el calibrador pooleado de familia y renormaliza igual
    params = {"v|1x2": {"a": 1.4, "b": 0.1, "n": 48}}
    trio = calib.apply_1x2(0.55, 0.25, 0.20, "v", params)
    assert abs(sum(trio) - 1.0) < 1e-12


def test_fit_creates_per_outcome_1x2():
    evals = []
    for i in range(20):
        for mk, o in (("1x2:home", i % 2), ("1x2:draw", 0), ("1x2:away", (i + 1) % 2)):
            evals.append({"date": f"2026-06-{i:02d}", "home": f"A{i}", "away": f"B{i}",
                          "market": mk, "prob": 0.5, "outcome": o, "model_version": "v"})
    params = calib.fit(evals)
    assert "v|1x2:home" in params and "v|1x2:draw" in params and "v|1x2:away" in params
