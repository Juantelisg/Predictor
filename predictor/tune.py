"""tune.py - tuning WALK-FORWARD de los hiperparametros del modelo soccer. CERO cuotas.

Las perillas del modelo (ELO_W, HALFLIFE_DAYS, SINCE_YEARS, FRIENDLY_W, ALPHA, RHO) estan
puestas a ojo. Esto las BARRE contra log loss out-of-sample en varios folds walk-forward
(entrena con el pasado, testea en una ventana futura) -> dice si el valor actual es el mejor
o hay uno que calibra mejor. NO aplica cambios solo: reporta, el cambio lo decidimos a mano.

Uso:
  python tune.py                 # barre las 6 perillas (coordinate sweep)
  python tune.py ELO_W           # barre solo una
"""
import sys
import numpy as np
import soccer, elo

sys.stdout.reconfigure(encoding="utf-8")

# folds walk-forward: (entrena < test_from, testea [test_from, test_to))
FOLDS = [("2023-01-01", "2024-01-01"), ("2024-01-01", "2025-01-01"), ("2025-01-01", "2026-06-21")]

# grilla por perilla (el valor ACTUAL del modelo va incluido para comparar)
GRID = {
    "ELO_W":         [0.70, 0.78, 0.85, 0.92, 1.0],
    "HALFLIFE_DAYS": [365, 730, 1095, 1460, 2190],
    "SINCE_YEARS":   [6, 8, 10, 12, 16],
    "FRIENDLY_W":    [0.3, 0.5, 0.7, 1.0],
    "ALPHA":         [0.001, 0.005, 0.01, 0.05, 0.1],
    "RHO":           [-0.12, -0.09, -0.06, -0.03, 0.0],
}


def _eval(df_elo, rho=None, w=None):
    """Log loss 1X2 y O/U promedio sobre los folds, con los globals actuales de soccer.
    rho/w se pasan EXPLICITO (los defaults de soccer.evaluate quedaron fijos al importar)."""
    import pandas as pd
    rho = soccer.RHO if rho is None else rho
    w = soccer.ELO_W if w is None else w
    ll1, llo = [], []
    for tf, tt in FOLDS:
        m = soccer.evaluate(df_elo, pd.Timestamp(tf), pd.Timestamp(tf), pd.Timestamp(tt), rho, w)
        ll1.append(m["ll_model"]); llo.append(m["ll_over"])
    return float(np.mean(ll1)), float(np.mean(llo))


def sweep(df_elo, param, values):
    rows = []
    for v in values:
        if param == "ELO_W":
            ll1, llo = _eval(df_elo, w=v)
        elif param == "RHO":
            ll1, llo = _eval(df_elo, rho=v)
        else:                                    # los demas son globals leidos en _fit_models
            old = getattr(soccer, param)
            setattr(soccer, param, v)
            try:
                ll1, llo = _eval(df_elo)
            finally:
                setattr(soccer, param, old)
        rows.append((v, ll1, llo))
    return rows


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    df = soccer.load()
    df_elo, _ = elo.compute(df)
    base1, baseo = _eval(df_elo)
    print(f"  TUNING walk-forward ({len(FOLDS)} folds)  |  ACTUAL: ll_1x2={base1:.4f}  ll_OU={baseo:.4f}\n")
    params = [only] if only else list(GRID)
    for p in params:
        cur = getattr(soccer, p)
        rows = sweep(df_elo, p, GRID[p])
        best = min(rows, key=lambda r: r[1])
        print(f"  {p}  (actual={cur})")
        print(f"    {'valor':>8} {'ll_1x2':>9} {'ll_OU':>9}")
        for v, ll1, llo in rows:
            flag = "  <- ACTUAL" if v == cur else ("  <- MEJOR 1X2" if v == best[0] else "")
            print(f"    {str(v):>8} {ll1:>9.4f} {llo:>9.4f}{flag}")
        gain = base1 - best[1]
        print(f"    => mejor 1X2 = {best[0]} (ll {best[1]:.4f}, "
              f"{'gana' if gain>0 else 'igual/peor'} {gain:+.4f} vs actual)\n")
    print("  Nota: in-sample del proceso de seleccion NO (folds out-of-sample), pero la grilla")
    print("  se eligio a mano -> tomar mejoras chicas con pinzas. Aplicar solo deltas claras.\n")


if __name__ == "__main__":
    main()
