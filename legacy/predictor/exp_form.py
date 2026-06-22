"""exp_form.py - EXPERIMENTO (no produccion): mide si la FORMA ajustada por rival aporta
sobre el Elo para predecir el 1X2. NO modifica soccer.py.

Idea (de los modelos publicados): la unica forma que agrega sobre un rating es el RESIDUO vs
ese rating -> cuanto rindio un equipo por encima/debajo de lo que su Elo predecia en sus
ultimos N partidos. Captura cambios recientes que el Elo todavia no incorporo (DT nuevo,
lesion, cambio tactico). Es opponent-adjusted y sin fuga (usa el Elo PREVIO al partido).

Compara, fuera de muestra (mismo split que soccer.evaluate: test = ultimos 2 anios):
  - Modelo BASE:  [elo_diff, localia]
  - Modelo FORMA: [elo_diff, localia, forma_dif_L5, forma_dif_L10]
en dos niveles: (a) Elo-1X2 aislado, (b) el blend final Elo+Poisson.

Criterio de exito: si baja el log loss / Brier OUT-OF-SAMPLE -> la forma aporta y se integra.
Si queda igual o peor -> la forma se queda como contexto de lectura (donde esta hoy).

Uso:  python exp_form.py
"""
import warnings; warnings.filterwarnings("ignore")
import sys, math, datetime
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
import soccer, elo

N1, N2 = 5, 10   # ventanas de forma (L5, L10)


def build_residuals(df_elo):
    """Por equipo: (dates, residuos) con residuo = puntos_reales - puntos_esperados_por_Elo.
    Sin fuga: usa el Elo PREVIO al partido (elo_home_pre/elo_away_pre)."""
    raw = {}
    for g in df_elo.itertuples():
        adv = 0.0 if bool(g.neutral) else elo.HFA
        we = 1.0 / (1.0 + 10 ** (-(g.elo_home_pre + adv - g.elo_away_pre) / 400.0))
        gd = g.home_score - g.away_score
        ah = 1.0 if gd > 0 else 0.5 if gd == 0 else 0.0     # puntos reales del local (1/0.5/0)
        rh = ah - we                                        # residuo del local
        raw.setdefault(g.home_team, []).append((g.date.value, rh))
        raw.setdefault(g.away_team, []).append((g.date.value, -rh))
    log = {}
    for t, lst in raw.items():
        lst.sort()
        log[t] = (np.array([x[0] for x in lst]), np.array([x[1] for x in lst]))
    return log


def form(log, team, asof_value, n):
    """Media de los ultimos n residuos del equipo ANTES de asof (sin fuga). 0.0 si no hay."""
    if team not in log:
        return 0.0
    d, r = log[team]
    i = int(np.searchsorted(d, asof_value))   # cuantos partidos con fecha < asof
    if i == 0:
        return 0.0
    return float(r[max(0, i - n):i].mean())


def features(rows, log, with_form):
    X = []
    for g in rows.itertuples():
        row = [g.elo_home_pre - g.elo_away_pre, 0.0 if bool(g.neutral) else 1.0]
        if with_form:
            f5 = form(log, g.home_team, g.date.value, N1) - form(log, g.away_team, g.date.value, N1)
            f10 = form(log, g.home_team, g.date.value, N2) - form(log, g.away_team, g.date.value, N2)
            row += [f5, f10]
        X.append(row)
    return np.array(X)


def labels(rows):
    return np.sign(rows.home_score - rows.away_score).astype(int).values


def metrics_3way(P, y, classes):
    """log loss multiclase + Brier multiclase + accuracy."""
    cls = list(classes)
    ll = brier = 0.0
    correct = 0
    for p, yi in zip(P, y):
        idx = cls.index(yi)
        ll += -math.log(max(p[idx], 1e-12))
        oneh = np.zeros(len(cls)); oneh[idx] = 1.0
        brier += float(((p - oneh) ** 2).sum())
        correct += (int(cls[int(np.argmax(p))]) == yi)
    n = len(y)
    return ll / n, brier / n, correct / n


def main():
    df = soccer.load()
    df_elo, rating = elo.compute(df)
    log = build_residuals(df_elo)

    today = pd.Timestamp(datetime.date.today())
    tf = today - pd.DateOffset(years=2)                          # mismo split que soccer.evaluate
    train = df_elo[(df_elo.date < tf) & (df_elo.date >= tf - pd.DateOffset(years=soccer.SINCE_YEARS))]
    test = df_elo[(df_elo.date >= tf) & (df_elo.date < today)]
    ytr, yte = labels(train), labels(test)

    print("=" * 70)
    print(f"  EXPERIMENTO FORMA-RESIDUAL  |  train {len(train)} partidos / test {len(test)}")
    print(f"  split: train < {tf.date()} <= test < {today.date()}  (todas las selecciones)")
    print("=" * 70)

    # ---------- (a) Elo-1X2 aislado ----------
    res = {}
    models = {}
    for tag, wf in [("BASE", False), ("FORMA", True)]:
        m = LogisticRegression(max_iter=1000).fit(features(train, log, wf), ytr)
        models[tag] = m
        P = m.predict_proba(features(test, log, wf))
        res[tag] = metrics_3way(P, yte, m.classes_)

    print("\n  (a) Elo-1X2 AISLADO            log loss     Brier      acc")
    print("  " + "-" * 56)
    for tag in ("BASE", "FORMA"):
        ll, br, ac = res[tag]
        print(f"      {tag:<8} {ll:>14.4f} {br:>10.4f} {ac*100:>7.1f}%")
    dll = res["BASE"][0] - res["FORMA"][0]
    print(f"      delta log loss (BASE - FORMA): {dll:+.4f}   ({'FORMA mejor' if dll > 0 else 'FORMA NO mejora'})")
    cf = models["FORMA"].coef_
    print(f"      coef forma (clases {list(models['FORMA'].classes_)}): L5/L10 por clase ->")
    for ci, c in enumerate(cf):
        print(f"        clase {models['FORMA'].classes_[ci]:>2}:  L5 {c[2]:+.4f}   L10 {c[3]:+.4f}")

    # ---------- (b) blend final Elo + Poisson ----------
    pois, cols, _elo_unused, sup, win = soccer._fit_models(df_elo, tf, tf)
    known = set(win.home_team) | set(win.away_team)
    base_rate = {1: (np.sign(win.home_score - win.away_score) == 1).mean(),
                 0: (np.sign(win.home_score - win.away_score) == 0).mean(),
                 -1: (np.sign(win.home_score - win.away_score) == -1).mean()}
    W = soccer.ELO_W

    def elo1x2(m, eh, ea, ish, f5, f10, wf):
        x = [[eh - ea, 1.0 if ish else 0.0] + ([f5, f10] if wf else [])]
        p = m.predict_proba(np.array(x))[0]
        cls = list(m.classes_)
        return {o: float(p[cls.index(o)]) for o in (1, 0, -1)}

    agg = {"BASE": [0.0, 0.0, 0, 0], "FORMA": [0.0, 0.0, 0, 0]}   # ll, brier, correct, n
    llbase = 0.0
    for g in test.itertuples():
        if g.home_team not in known or g.away_team not in known:
            continue
        ish = 0 if bool(g.neutral) else 1
        lh, la = soccer._lambdas(pois, cols, sup, g.elo_home_pre, g.elo_away_pre, g.home_team, g.away_team, ish)
        pz = soccer._1x2(soccer._matrix(lh, la, soccer.RHO))
        f5 = form(log, g.home_team, g.date.value, N1) - form(log, g.away_team, g.date.value, N1)
        f10 = form(log, g.home_team, g.date.value, N2) - form(log, g.away_team, g.date.value, N2)
        s = int(np.sign(g.home_score - g.away_score))
        llbase += -math.log(max(base_rate[s], 1e-12))
        for tag, wf in [("BASE", False), ("FORMA", True)]:
            ez = elo1x2(models[tag], g.elo_home_pre, g.elo_away_pre, ish, f5, f10, wf)
            bl = {o: W * ez[o] + (1 - W) * pz[o] for o in (1, 0, -1)}
            agg[tag][0] += -math.log(max(bl[s], 1e-12))
            oneh = {1: 0, 0: 0, -1: 0}; oneh[s] = 1
            agg[tag][1] += sum((bl[o] - oneh[o]) ** 2 for o in (1, 0, -1))
            agg[tag][2] += (max(bl, key=bl.get) == s)
            agg[tag][3] += 1

    n = agg["BASE"][3]
    print(f"\n  (b) BLEND Elo+Poisson (n={n})  log loss     Brier      acc")
    print("  " + "-" * 56)
    print(f"      baseline {llbase/n:>14.4f} {'-':>10} {'-':>8}")
    for tag in ("BASE", "FORMA"):
        ll, br, c, _ = agg[tag]
        print(f"      {tag:<8} {ll/n:>14.4f} {br/n:>10.4f} {c/n*100:>7.1f}%")
    dll_b = (agg["BASE"][0] - agg["FORMA"][0]) / n
    print(f"      delta log loss (BASE - FORMA): {dll_b:+.4f}   ({'FORMA mejor' if dll_b > 0 else 'FORMA NO mejora'})")

    print("\n  VEREDICTO:")
    if dll > 0 and dll_b > 0:
        print("    La forma-residual MEJORA out-of-sample en ambos niveles -> vale integrarla.")
    elif dll > 0 or dll_b > 0:
        print("    Mejora parcial/mixta -> mirar magnitud; probablemente marginal.")
    else:
        print("    La forma NO mejora sobre el Elo -> queda como contexto de lectura (no integrar).")


if __name__ == "__main__":
    main()
