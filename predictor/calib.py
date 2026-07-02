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
MIN_N = 15                 # minimo de PARTIDOS UNICOS para fitear (si no, identidad). Antes eran
                           # FILAS (~3-12 por partido) -> inflaba la muestra 3-12x. Ahora cuenta partidos.
SHRINK_K = 100             # shrink del Platt hacia identidad por FILAS (fuerza del fit): s=nrows/(nrows+K).
                           # Con pocas filas no le creemos el estiramiento agresivo; con volumen, confiamos mas.
SLOPE_MIN = 0.1            # pendiente calibrada por debajo de esto -> identidad. NUNCA invertir la prob
                           # (bug real: mlb-ml|mid tenia a=-0.131 -> mas prob del modelo = menos calibrada).
                           # Una pendiente ~0 o negativa es ajuste de ruido, no senal: mejor no tocar.
CTX_MIN_MATCHES = 30       # un calibrador por CONTEXTO (fav/dog/mid) solo se activa con esta muestra de
                           # partidos; si no, identidad y apply() cae a la familia (anti sobreajuste de bucket).
CALIB_VERSION = "platt-v3"


def _logit(p):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.asarray(x, float)))


def fit_one(probs, outcomes, n_matches=None):
    """Ajusta (a, b) Platt. Identidad (1, 0) si no hay datos/variacion suficiente.
    n_matches = partidos unicos que respaldan el fit (gate de MIN_N + valor `n` devuelto). Si no
    se pasa, cae a len(probs) (retrocompat con tests). El shrink usa FILAS (fuerza del fit), pero
    el GATE y el `n` reportado usan partidos (muestra independiente honesta)."""
    probs = np.asarray(probs, float)
    outcomes = np.asarray(outcomes, float)
    n_rows = len(probs)
    n_gate = n_matches if n_matches is not None else n_rows
    if n_gate < MIN_N or outcomes.min() == outcomes.max():
        return 1.0, 0.0, n_gate
    from sklearn.linear_model import LogisticRegression
    x = _logit(probs).reshape(-1, 1)
    m = LogisticRegression(C=1e6, solver="lbfgs").fit(x, outcomes)
    a, b = float(m.coef_[0][0]), float(m.intercept_[0])
    s = n_rows / (n_rows + SHRINK_K)        # shrink hacia identidad (a=1,b=0): anti overfit in-sample
    a_s, b_s = 1 + s * (a - 1), s * b
    if a_s < SLOPE_MIN:                     # pendiente degenerada/negativa -> no invertir, identidad
        return 1.0, 0.0, n_gate
    return a_s, b_s, n_gate


def _key(version, family):
    """Clave del recalibrador: por (version, familia de mercado). family None -> solo version."""
    return f"{version}|{family}" if family else version


def context_of(prob):
    """Contexto del pick segun la magnitud de la prob: captura el eje del sesgo CONFIRMADO
    (subconfianza en favoritos). 'fav' = favorito, 'dog' = no-favorito, 'mid' = parejo."""
    return "fav" if prob >= 0.55 else "dog" if prob <= 0.45 else "mid"


def _key3(version, family, context):
    """Clave por (version, familia, contexto). Sin contexto -> cae a la clave de familia."""
    return f"{version}|{family}|{context}" if context else _key(version, family)


def fit(evals):
    """Fitea un calibrador por (model_version, FAMILIA) y tambien por (version, familia, CONTEXTO).
    Separar familias evita que un mercado bien calibrado (1x2) y otro sesgado (over) se promedien;
    el contexto refina aun mas, pero solo se ACTIVA cuando un bucket llega a MIN_N (si no, identidad
    y apply() cae a la familia). Asi se construye la maquinaria sin sobre-ajustar con muestra chica."""
    by_key = {}
    for e in evals:
        fam = e["market"].split(":")[0]
        ver = e.get("model_version", "?")
        ctx = context_of(e["prob"])
        mid = (e.get("date"), e.get("home"), e.get("away"))   # partido = muestra independiente
        keys = [(_key(ver, fam), False), (_key3(ver, fam, ctx), True)]  # familia + contexto
        if fam == "1x2":                                      # 1X2 tambien POR OUTCOME (home/draw/away
            keys.append((_key(ver, e["market"]), False))      # tienen sesgos distintos; el empate se
        for k, is_ctx in keys:                                # enmascara al poolear). Clave: version|1x2:home
            d = by_key.setdefault(k, {"p": [], "o": [], "m": set(), "ctx": is_ctx})
            d["p"].append(e["prob"]); d["o"].append(e["outcome"]); d["m"].add(mid)
    params = {}
    for k, d in by_key.items():
        nm = len(d["m"])                                      # partidos unicos (no filas correlacionadas)
        if d["ctx"] and nm < CTX_MIN_MATCHES:                 # contexto sin volumen -> identidad (cae a familia)
            a, b, n = 1.0, 0.0, nm
        else:
            a, b, n = fit_one(d["p"], d["o"], n_matches=nm)
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


def apply(prob, version, family=None, params=None, context=None):
    """Aplica el calibrador a una probabilidad. Prueba en cadena: (version,familia,contexto) ->
    (version,familia) -> (version), y usa el PRIMERO no-identidad. Asi el contexto manda cuando
    tiene volumen, y si no, cae limpio a la familia (retrocompatible; identidad si no hay nada)."""
    params = params if params is not None else load()
    keys = ([_key3(version, family, context)] if context else []) + [_key(version, family), version]
    for k in keys:
        pr = params.get(k)
        if pr and not (pr["a"] == 1.0 and pr["b"] == 0.0):
            return float(_sigmoid(pr["a"] * _logit(prob) + pr["b"]))
    return float(prob)


def apply_1x2(p_home, p_draw, p_away, version, params=None):
    """Calibra el 1X2 POR OUTCOME y RENORMALIZA a sumar 1. Dos arreglos en uno:
    (1) home/draw/away tienen sesgos distintos -> un solo Platt pooleado enmascara el del empate;
    (2) tres probs calibradas por separado NO suman 1 -> contra una cuota de-vigeada (que si suma 1)
        eso es un 'edge fantasma' de +-2pt repartido. Renormalizar lo elimina.
    Cae al calibrador pooleado de familia (version|1x2) si el per-outcome esta en identidad.
    Devuelve (home, draw, away) calibradas y normalizadas."""
    params = params if params is not None else load()

    def cal(p, outcome):
        for k in (f"{version}|1x2:{outcome}", f"{version}|1x2", version):
            pr = params.get(k)
            if pr and not (pr["a"] == 1.0 and pr["b"] == 0.0):
                return float(_sigmoid(pr["a"] * _logit(p) + pr["b"]))
        return float(p)

    ch, cd, ca = cal(p_home, "home"), cal(p_draw, "draw"), cal(p_away, "away")
    s = ch + cd + ca
    return (ch / s, cd / s, ca / s) if s > 0 else (float(p_home), float(p_draw), float(p_away))
