"""backtest_wc.py - Loop de retro CALIBRADO del Mundial 2026 (read-only, NO toca params).

Backtestea el motor de selecciones (soccer-v3) contra los partidos del Mundial YA disputados.
Mide CALIBRACION (log loss / Brier / reliability) y SESGOS SISTEMATICOS, NO marcadores exactos.
Sin fuga temporal: para cada fecha reentrena con SOLO datos anteriores (Elo rodante pre-partido).

Correr:  C:/Users/Juant/AppData/Local/Python/bin/python.exe predictor/backtest_wc.py
"""
import sys, datetime
import numpy as np
import pandas as pd
import soccer, elo

sys.stdout.reconfigure(encoding="utf-8")

WC_START = pd.Timestamp("2026-06-11")     # primer dia del Mundial 2026


def wc_fixtures(df, start=WC_START, end=None):
    if end is None:
        end = pd.Timestamp(datetime.date.today())
    t = df["tournament"].str.lower()
    m = df[(df["date"] >= start) & (df["date"] <= end) &
           t.str.contains("world cup", na=False) &
           ~t.str.contains("qualif", na=False)]
    return m.sort_values("date").reset_index(drop=True)


def _predict(models, eh, ea, home, away, neutral, rho, w):
    """Misma logica que soccer.evaluate, con Elo PRE-partido (leak-free)."""
    pois, cols, elo_m, sup = models
    ish = 0 if neutral else 1
    lh, la = soccer._lambdas(pois, cols, sup, eh, ea, home, away, ish)
    M = soccer._matrix(lh, la, rho)
    ez = soccer._elo_1x2(elo_m, eh, ea, not neutral)
    pz = soccer._1x2(M)
    blend = {o: w * ez[o] + (1 - w) * pz[o] for o in (1, 0, -1)}
    sc = np.unravel_index(np.argmax(M), M.shape)
    return blend, soccer._over25(M), lh, la, (int(sc[0]), int(sc[1]))


def backtest(start=WC_START, end=None, rho=soccer.RHO, w=soccer.ELO_W, alpha=None, df_elo=None):
    """Devuelve dict de metricas + filas por partido. Reentrena por FECHA (sin fuga)."""
    if alpha is not None:
        old_alpha, soccer.ALPHA = soccer.ALPHA, alpha   # override temporal para el sweep
    try:
        if df_elo is None:
            df = soccer.load()
            df_elo, _ = elo.compute(df)
        fx = wc_fixtures(df_elo, start, end)
        rows = []
        for d, day in fx.groupby("date"):
            models = soccer._fit_models(df_elo, d, d)[:4]                # entrena con date < d
            win = models[4] if len(models) > 4 else None
            train = df_elo[(df_elo.date < d) & (df_elo.date >= d - pd.DateOffset(years=soccer.SINCE_YEARS))]
            r = np.sign(train.home_score - train.away_score)
            base = {1: (r == 1).mean(), 0: (r == 0).mean(), -1: (r == -1).mean()}
            ob = float(((train.home_score + train.away_score) >= 3).mean())
            known = set(train.home_team) | set(train.away_team)
            for g in day.itertuples():
                if g.home_team not in known or g.away_team not in known:
                    continue
                neutral = bool(g.neutral)
                blend, ov25, lh, la, modal = _predict(models, g.elo_home_pre, g.elo_away_pre,
                                                       g.home_team, g.away_team, neutral, rho, w)
                s = int(np.sign(g.home_score - g.away_score))
                over = (g.home_score + g.away_score) >= 3
                fav = max(blend, key=blend.get)
                rows.append(dict(
                    date=g.date, home=g.home_team, away=g.away_team, neutral=neutral,
                    hs=int(g.home_score), as_=int(g.away_score), outcome=s, total=int(g.home_score + g.away_score),
                    p_home=blend[1], p_draw=blend[0], p_away=blend[-1], p_s=blend[s],
                    fav=fav, p_fav=blend[fav], fav_hit=int(fav == s),
                    base_s=base[s], p_over=ov25, over=int(over), ob=ob,
                    lh=lh, la=la, exp_total=lh + la, modal=modal,
                    exact=int(modal == (int(g.home_score), int(g.away_score)))))
        return _aggregate(rows)
    finally:
        if alpha is not None:
            soccer.ALPHA = old_alpha


def _ll(p):
    return -np.log(np.clip(p, 1e-12, 1.0))


def _aggregate(rows):
    R = pd.DataFrame(rows)
    n = len(R)
    # 1X2
    ll_model = _ll(R.p_s).mean()
    ll_base = _ll(R.base_s).mean()
    brier_1x2 = ((R[["p_home", "p_draw", "p_away"]].values -
                  np.column_stack([(R.outcome == 1), (R.outcome == 0), (R.outcome == -1)]).astype(float)) ** 2
                 ).sum(axis=1).mean()
    acc = R.fav_hit.mean()                                   # argmax == resultado
    # O/U 2.5
    p_ou = np.where(R.over == 1, R.p_over, 1 - R.p_over)
    p_ou_base = np.where(R.over == 1, R.ob, 1 - R.ob)
    ll_over = _ll(p_ou).mean()
    ll_over_base = _ll(p_ou_base).mean()
    brier_over = ((R.p_over - R.over) ** 2).mean()
    return dict(n=n, R=R,
                ll_model=ll_model, ll_base=ll_base, brier_1x2=brier_1x2, acc=acc,
                ll_over=ll_over, ll_over_base=ll_over_base, brier_over=brier_over,
                # sesgos direccionales
                p_fav_mean=R.p_fav.mean(), fav_winrate=R.fav_hit.mean(),
                p_draw_mean=R.p_draw.mean(), draw_rate=(R.outcome == 0).mean(),
                p_over_mean=R.p_over.mean(), over_rate=R.over.mean(),
                exp_total_mean=R.exp_total.mean(), total_mean=R.total.mean(),
                exact_rate=R.exact.mean())


def _reliability(R, prob_cols=("p_home", "p_draw", "p_away"), nb=5):
    """Reliability multiclase: junta las 3 probs por outcome y bucketea."""
    p, y = [], []
    out_map = {"p_home": 1, "p_draw": 0, "p_away": -1}
    for c in prob_cols:
        p.extend(R[c].tolist())
        y.extend((R.outcome == out_map[c]).astype(int).tolist())
    p, y = np.array(p), np.array(y)
    edges = np.linspace(0, 1, nb + 1)
    out = []
    ece = 0.0
    for i in range(nb):
        m = (p >= edges[i]) & (p < edges[i + 1] if i < nb - 1 else p <= edges[i + 1])
        if m.sum() == 0:
            continue
        pred, obs, cnt = p[m].mean(), y[m].mean(), int(m.sum())
        ece += cnt / len(p) * abs(pred - obs)
        out.append((edges[i], edges[i + 1], cnt, pred, obs))
    return out, ece


def _bar(x):
    return "+" if x > 0.5 else ("-" if x < -0.5 else "0")


def main():
    end = pd.Timestamp(datetime.date.today())
    df = soccer.load()
    df_elo, _ = elo.compute(df)
    fx = wc_fixtures(df_elo, WC_START, end)

    print("=" * 78)
    print(f"  SUPRA LOOP DE RETRO (CALIBRADO) - Mundial 2026  |  {soccer.VERSION}")
    print(f"  Ventana: {WC_START.date()} -> {end.date()}   ({len(fx)} partidos con resultado)")
    print("=" * 78)

    # ----- PASO 1: fixture a ciegas
    print("\n[1] FIXTURE A CIEGAS (solo enfrentamientos):")
    for g in fx.itertuples():
        loc = "neutral" if bool(g.neutral) else "local"
        print(f"    {g.date.date()}  {g.home_team} vs {g.away_team}  ({loc})")

    # ----- PASOS 2-4: predecir, revelar, evaluar
    M = backtest(WC_START, end, df_elo=df_elo)
    R = M["R"]

    print("\n[2-3] PREDICCION DE CONTROL vs RESULTADO REAL (sin fuga temporal):")
    print(f"    {'PARTIDO':<34}{'PRED 1X2 (L/E/V)':<20}{'modal':<7}{'REAL':<7}{'ok'}")
    for g in R.itertuples():
        pred = f"{g.p_home*100:4.0f}/{g.p_draw*100:3.0f}/{g.p_away*100:3.0f}"
        modal = f"{g.modal[0]}-{g.modal[1]}"
        real = f"{g.hs}-{g.as_}"
        ok = "OK" if g.fav_hit else "x"
        match = f"{g.home[:15]} v {g.away[:14]}"
        print(f"    {match:<34}{pred:<20}{modal:<7}{real:<7}{ok}")

    print("\n[4] EVALUACION (criterio = CALIBRACION, no exactitud):")
    print(f"    n = {M['n']} partidos")
    print(f"    1X2     log loss  {M['ll_model']:.3f}  vs baseline {M['ll_base']:.3f}   "
          f"({'mejor' if M['ll_model'] < M['ll_base'] else 'PEOR'} que baseline)")
    print(f"    1X2     Brier     {M['brier_1x2']:.3f}     accuracy {M['acc']*100:.1f}%")
    print(f"    O/U 2.5 log loss  {M['ll_over']:.3f}  vs baseline {M['ll_over_base']:.3f}")
    print(f"    O/U 2.5 Brier     {M['brier_over']:.3f}")

    rel, ece = _reliability(R)
    print(f"\n    Reliability 1X2 (ECE = {ece:.3f}):")
    print(f"      {'bucket':<14}{'n':>5}{'predicho':>10}{'observado':>11}")
    for lo, hi, cnt, pred, obs in rel:
        flag = "" if abs(pred - obs) < 0.08 else "  <- gap"
        print(f"      {lo*100:3.0f}-{hi*100:3.0f}%{'':<6}{cnt:>5}{pred*100:>9.1f}%{obs*100:>10.1f}%{flag}")

    print("\n    SESGOS SISTEMATICOS:")
    df_fav = M['p_fav_mean'] - M['fav_winrate']
    df_draw = M['p_draw_mean'] - M['draw_rate']
    df_over = M['p_over_mean'] - M['over_rate']
    df_tot = M['exp_total_mean'] - M['total_mean']
    print(f"      Favoritos : predigo {M['p_fav_mean']*100:.1f}%  | ganan {M['fav_winrate']*100:.1f}%  "
          f"-> {df_fav*100:+.1f} pts ({'sobreconfiado' if df_fav>0.02 else 'subconfiado' if df_fav<-0.02 else 'OK'})")
    print(f"      Empates   : predigo {M['p_draw_mean']*100:.1f}%  | ocurren {M['draw_rate']*100:.1f}%  "
          f"-> {df_draw*100:+.1f} pts")
    print(f"      Over 2.5  : predigo {M['p_over_mean']*100:.1f}%  | ocurre {M['over_rate']*100:.1f}%  "
          f"-> {df_over*100:+.1f} pts ({'alcista' if df_over>0.02 else 'bajista' if df_over<-0.02 else 'OK'})")
    print(f"      Goles tot : espero  {M['exp_total_mean']:.2f}   | real    {M['total_mean']:.2f}   "
          f"-> {df_tot:+.2f} goles")
    print(f"\n    Marcador exacto (reality-check): {M['exact_rate']*100:.1f}%  "
          f"(clavar el 100% es inalcanzable; un buen modelo ~10-12%)")

    return M, df_elo


if __name__ == "__main__":
    main()
