"""simulate.py - Monte Carlo de partido para COMBOS correlacionados. CERO cuotas.

El problema que resuelve: un combo NO es el producto de las probabilidades de sus piernas,
porque las piernas estan correlacionadas (un 4-0 hace ganar al favorito Y pegar el over Y
deja la valla invicta -- las tres dependen del mismo marcador). Multiplicar marginales
da mal. La forma correcta es simular el partido N veces y contar en cuantas pegan TODAS.

Como: muestrea N marcadores de la MATRIZ CONJUNTA del modelo soccer (Poisson + Dixon-Coles)
-> las piernas de goles (1X2/over/BTTS/valla) quedan correlacionadas EXACTO y gratis.
Cornes/tarjetas se muestrean de su media StatsBomb; su acople con la dominancia es un
parametro (dominance_k, default 0 = independiente) que queda para calibrar con volumen.

Uso:
  python simulate.py "Spain" "Saudi Arabia"
  python simulate.py "Spain" "Saudi Arabia" --combo=home,over2.5,cs_home
"""
import sys
import numpy as np
import soccer, elo

sys.stdout.reconfigure(encoding="utf-8")


def _ctx():
    df = soccer.load()
    df_elo, rating = elo.compute(df)
    return df, df_elo, rating, soccer.fit_today(df_elo)


def _couple(base, k, abs_margin):
    """Lambda de corners/cards ACOPLADA a la dominancia: base * exp(k*|margen|). k=0 -> sin acople
    (marginales independientes). k!=0 -> el conteo depende del marcador simulado (correlacion real)."""
    return np.maximum(base * np.exp(k * np.asarray(abs_margin, float)), 1e-9)


def simulate(home, away, n=50000, neutral=True, ctx=None, seed=0, corner_k=0.0, card_k=0.0):
    """Devuelve dict con: marcadores (hg, ag) y un bool array por mercado (la 'sim').
    corner_k / card_k = acople de corners/cards a la dominancia (|margen|). Default 0 (independencia):
    medido en los boxscores del WC2026 (n=24) el acople es indistinguible de 0 (|r|<0.2) -> no se
    cablea un acople espurio. El MECANISMO ya funciona (bug '*0' corregido) para cuando haya volumen."""
    df, df_elo, rating, models = ctx or _ctx()
    teams = set(df.home_team) | set(df.away_team)
    L, V = soccer.resolve(home, teams), soccer.resolve(away, teams)
    if not L or not V:
        raise ValueError(f"No reconozco: {home if not L else away}")
    r = soccer.predict(df_elo, rating, L, V, neutral=neutral, models=models)
    rng = np.random.default_rng(seed)

    # marcadores: matriz conjunta del modelo, con el 1X2 reponderado al blend oficial
    # (Elo+Poisson). La UNICA incoherencia del modelo es el 1X2 (sale del Elo, no de M);
    # todo lo demas (totales/BTTS/valla) sale de M. Asi que reponderamos SOLO las 3 regiones
    # (gana local / empate / gana visita) preservando la forma del marcador dentro de cada
    # una -> 1X2 exacto y minima distorsion del resto. (Efecto lateral: los totales bajan
    # un toque porque el Elo ve menos dominancia que el Poisson puro -> mas empates.)
    M = soccer._matrix(r["lh"], r["la"], soccer.RHO)
    b = r["blend"]
    reg = [(np.tril(M, -1), b[1]), (np.diag(np.diag(M)), b[0]), (np.triu(M, 1), b[-1])]
    M = sum(R * (t / R.sum()) if R.sum() > 0 else R for R, t in reg)
    idx = rng.choice(M.size, size=n, p=M.ravel())
    hg, ag = np.divmod(idx, M.shape[1])
    tot, margin = hg + ag, hg - ag

    sims = {
        "home": hg > ag, "draw": hg == ag, "away": hg < ag,
        "1x": hg >= ag, "x2": hg <= ag, "12": hg != ag,
        "over1.5": tot >= 2, "over2.5": tot >= 3, "over3.5": tot >= 4,
        "under2.5": tot < 3, "btts": (hg >= 1) & (ag >= 1),
        "cs_home": ag == 0, "cs_away": hg == 0,
    }
    # cornes / tarjetas: media del torneo (regime, factor T5) acoplada a la dominancia (default 0)
    try:
        import regime
        cm = regime.predict("corners", L, V)["total_exp"]
        km = regime.predict("cards", L, V)["total_exp"]
        am = np.abs(margin)
        corners = rng.poisson(_couple(cm, corner_k, am), n)   # antes: '* 0' mataba el acople (bug)
        cards = rng.poisson(_couple(km, card_k, am), n)
        for ln in (8.5, 9.5, 10.5):
            sims[f"corners_over{ln}"] = corners > ln
        for ln in (2.5, 3.5, 4.5):
            sims[f"cards_over{ln}"] = cards > ln
    except Exception:
        pass

    return {"home": L, "away": V, "n": n, "hg": hg, "ag": ag, "margin": margin, "sims": sims,
            "lh": r["lh"], "la": r["la"]}


def combo(res, legs):
    """P conjunta del combo (sim) vs producto ingenuo de marginales. Devuelve (joint, prod, lift)."""
    sims = res["sims"]
    bad = [l for l in legs if l not in sims]
    if bad:
        raise ValueError(f"Piernas desconocidas: {bad}. Disponibles: {sorted(sims)}")
    arrs = [sims[l] for l in legs]
    joint = np.logical_and.reduce(arrs).mean()
    prod = float(np.prod([a.mean() for a in arrs]))
    return float(joint), prod, (joint / prod if prod else float("nan"))


def taxonomy(res):
    """Clasifica los N futuros simulados en familias de escenario (la 'taxonomia')."""
    m = res["margin"]
    return {
        "Victoria comoda local (2+)": float((m >= 2).mean()),
        "Victoria ajustada local (1)": float((m == 1).mean()),
        "Empate": float((m == 0).mean()),
        "Victoria ajustada visita (1)": float((m == -1).mean()),
        "Victoria comoda visita (2+)": float((m <= -2).mean()),
    }


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print('  Uso: simulate.py "<local>" "<visita>" [--combo=home,over2.5,...]')
        return
    res = simulate(args[0], args[1])
    L, V, n = res["home"], res["away"], res["n"]
    pct = lambda p: f"{p*100:5.1f}%"
    print("=" * 64)
    print(f"  MONTE CARLO  {L} vs {V}   ({n:,} simulaciones)")
    print("=" * 64)
    print(f"  Goles esperados: {L} {res['lh']:.2f} - {V} {res['la']:.2f}\n")
    print("  Taxonomia de escenarios:")
    for k, p in taxonomy(res).items():
        print(f"    {k:<30} {pct(p)}")
    print("\n  Marginales (sanity check vs modelo analitico):")
    for m in ("home", "draw", "away", "over2.5", "btts", "cs_home"):
        print(f"    {m:<12} {pct(res['sims'][m].mean())}")

    legs = next((a.split("=", 1)[1].split(",") for a in sys.argv[1:] if a.startswith("--combo=")), None)
    if legs:
        j, p, lift = combo(res, legs)
        print(f"\n  COMBO  {' + '.join(legs)}")
        print(f"    P conjunta (simulada, correlacion real) : {pct(j)}")
        print(f"    P producto de marginales (INGENUO)      : {pct(p)}")
        print(f"    Lift (joint/prod): {lift:.2f}x  -> multiplicar {'SUBestima' if lift>1 else 'SOBREestima'} el combo")
    print("\n  Educativo, sin cuotas. Cornes/tarjetas: independencia de la dominancia por defecto")
    print("  (acople medido ~0 con n=24 en el WC; params corner_k/card_k, activan con volumen).\n")


if __name__ == "__main__":
    main()
