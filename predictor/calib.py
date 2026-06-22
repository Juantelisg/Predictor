"""calib.py - recalibrador (Platt scaling) fiteado sobre evaluations/. CERO cuotas.

Cierra el loop: feedback.report MIDE el desvio de calibracion; aca se CORRIGE.
Platt = regresion logistica 1-D sobre el logit de la prob del modelo:
    p_cal = sigmoid(a * logit(p) + b)
a>1 ESTIRA (corrige la sobre-compresion -> el sesgo de favoritos confirmado del proyecto);
a<1 comprime. Se fitea POR model_version (no se mezclan versiones, regla del proyecto).

Guarda en data/calibrators.json. Si n < MIN_N -> identidad: con muestra insuficiente es
mejor NO tocar la prob que sobre-ajustarla (anti auto-justificacion).

NOTA honesta v1: se fitea POOLEADO por version (todas las familias de mercado juntas) y
es IN-SAMPLE. Sirve para corregir el sesgo sistemico de compresion; la calibracion por
contexto/mercado y la validacion out-of-sample quedan para cuando haya volumen.

Uso (via feedback.py):  python feedback.py calibrate   # fitea y guarda
"""
import os, json
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
PARAMS_PATH = os.path.join(ROOT, "data", "calibrators.json")
MIN_N = 40                 # minimo de evaluaciones para fitear (si no, identidad)
SHRINK_K = 100             # shrink del Platt hacia identidad: s=n/(n+K). Con n chico (in-sample)
                           # no le creemos el estiramiento agresivo; con volumen, confiamos mas.
CALIB_VERSION = "platt-v2"


def _logit(p):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.asarray(x, float)))


def fit_one(probs, outcomes):
    """Ajusta (a, b) Platt. Identidad (1, 0) si no hay datos/variacion suficiente."""
    probs = np.asarray(probs, float)
    outcomes = np.asarray(outcomes, float)
    if len(probs) < MIN_N or outcomes.min() == outcomes.max():
        return 1.0, 0.0, len(probs)
    from sklearn.linear_model import LogisticRegression
    x = _logit(probs).reshape(-1, 1)
    m = LogisticRegression(C=1e6, solver="lbfgs").fit(x, outcomes)
    a, b, n = float(m.coef_[0][0]), float(m.intercept_[0]), len(probs)
    s = n / (n + SHRINK_K)                  # shrink hacia identidad (a=1,b=0): anti overfit in-sample
    return 1 + s * (a - 1), s * b, n


def _key(version, family):
    """Clave del recalibrador: por (version, familia de mercado). family None -> solo version."""
    return f"{version}|{family}" if family else version


def fit(evals):
    """Fitea un calibrador por (model_version, FAMILIA de mercado). Separar familias evita que
    un mercado bien calibrado (1x2) y otro sesgado (over) se promedien en un solo Platt."""
    by_key = {}
    for e in evals:
        fam = e["market"].split(":")[0]
        k = _key(e.get("model_version", "?"), fam)
        by_key.setdefault(k, ([], []))
        by_key[k][0].append(e["prob"])
        by_key[k][1].append(e["outcome"])
    params = {}
    for k, (p, o) in by_key.items():
        a, b, n = fit_one(p, o)
        params[k] = {"a": a, "b": b, "n": n, "calib_version": CALIB_VERSION}
    return params


def save(params):
    os.makedirs(os.path.dirname(PARAMS_PATH), exist_ok=True)
    with open(PARAMS_PATH, "w", encoding="utf-8") as f:
        json.dump(params, f, indent=1)


def load():
    if os.path.exists(PARAMS_PATH):
        try:
            with open(PARAMS_PATH, encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def apply(prob, version, family=None, params=None):
    """Aplica el calibrador de (version, familia) a una probabilidad (identidad si no hay).
    Si no existe el de la familia, cae al de la version sola (retrocompatible)."""
    params = params if params is not None else load()
    pr = params.get(_key(version, family)) or params.get(version)
    if not pr or (pr["a"] == 1.0 and pr["b"] == 0.0):
        return float(prob)
    return float(_sigmoid(pr["a"] * _logit(prob) + pr["b"]))
