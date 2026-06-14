"""soccer.py - predictor de SELECCIONES (Mundial / internacional). CERO cuotas.

v2: combina dos senales de fuerza, las dos del MISMO dataset historico (sin API):
  - POISSON de goles (ataque/defensa por seleccion, recencia) + correccion DIXON-COLES
    (ajuste de marcadores bajos 0-0/1-0/0-1/1-1) -> de aca salen totales y BTTS.
  - ELO rodante (elo.py) -> logit multinomial -> 1X2 bien calibrado, NO comprime favoritos.
El 1X2 final es un blend Elo+Poisson; totales/BTTS salen de la matriz Poisson corregida.

Datos: martj42/international_results (CSV, 1872-presente, incluye fixtures futuras).
Correr:  C:/Users/Juant/AppData/Local/Python/bin/python.exe predictor/soccer.py [local] [visita]
         (default: Brazil Morocco, en cancha neutral)
"""
import sys, io, math, datetime
import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import PoissonRegressor, LogisticRegression, LinearRegression
import cache, elo

sys.stdout.reconfigure(encoding="utf-8")

CSV = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
SINCE_YEARS = 10          # ventana del Poisson (selecciones modernas)
HALFLIFE_DAYS = 3 * 365   # peso por recencia del Poisson (~1 ciclo de Mundial)
FRIENDLY_W = 0.5          # los amistosos pesan menos (rotacion / experimentos)
ALPHA = 0.01              # L2 del Poisson (tuneado: bate baseline; alto comprime favoritos)
MAXG = 10                 # tope de goles de la matriz de resultado
RHO = -0.06               # Dixon-Coles: correlacion de marcadores bajos (tuneado)
ELO_W = 0.85              # peso del Elo en el blend 1X2 (tuneado: Elo >> Poisson en 1X2; ll 0.97->0.88)
VERSION = "soccer-v3"     # version del modelo (cada prediccion la lleva -> no mezclar calibracion entre versiones)

ALIAS = {"brasil": "Brazil", "marruecos": "Morocco", "espana": "Spain", "francia": "France",
         "alemania": "Germany", "inglaterra": "England", "paises bajos": "Netherlands",
         "holanda": "Netherlands", "croacia": "Croatia", "mexico": "Mexico", "japon": "Japan",
         "corea del sur": "South Korea", "estados unidos": "United States", "belgica": "Belgium",
         "italia": "Italy", "portugal": "Portugal", "argentina": "Argentina", "uruguay": "Uruguay",
         "colombia": "Colombia", "suiza": "Switzerland", "dinamarca": "Denmark", "canada": "Canada"}


def load():
    txt = cache.cached("intl_results", 12 * 3600, lambda: requests.get(CSV, timeout=30).text)
    df = pd.read_csv(io.StringIO(txt)).dropna(subset=["home_score", "away_score"]).copy()
    df["date"] = pd.to_datetime(df["date"])
    return df


def resolve(name, teams):
    n = name.strip().lower()
    if name in teams:
        return name
    if n in ALIAS and ALIAS[n] in teams:
        return ALIAS[n]
    for t in teams:
        if t.lower() == n:
            return t
    for t in teams:
        if n in t.lower():
            return t
    return None


# ---------- Poisson de goles ----------
def _long(df, asof):
    rows = []
    for g in df.itertuples():
        ish = 0 if bool(g.neutral) else 1
        rows.append((g.home_team, g.away_team, g.home_score, ish, g.date, g.tournament))
        rows.append((g.away_team, g.home_team, g.away_score, 0, g.date, g.tournament))
    L = pd.DataFrame(rows, columns=["team", "opp", "goals", "is_home", "date", "tournament"])
    age = (asof - L["date"]).dt.days.clip(lower=0)
    L["w"] = (0.5 ** (age / HALFLIFE_DAYS)) * np.where(L["tournament"].eq("Friendly"), FRIENDLY_W, 1.0)
    return L


def _fit_poisson(L):
    X = pd.concat([pd.get_dummies(L["team"], prefix="atk"),
                   pd.get_dummies(L["opp"], prefix="def"),
                   L["is_home"]], axis=1).astype(float)
    model = PoissonRegressor(alpha=ALPHA, max_iter=600).fit(X.values, L["goals"], sample_weight=L["w"])
    return model, X.columns


def _lam(model, cols, team, opp, is_home):
    x = pd.Series(0.0, index=cols)
    for c in (f"atk_{team}", f"def_{opp}"):
        if c in x.index:
            x[c] = 1.0
    x["is_home"] = is_home
    return float(model.predict(x.values.reshape(1, -1))[0])


def _matrix(lh, la, rho=0.0):
    """Matriz Poisson M[i,j]=P(local i, visita j) con correccion Dixon-Coles de bajos marcadores."""
    k = np.arange(MAXG + 1)
    fact = np.array([math.factorial(int(x)) for x in k], dtype=float)
    ph = np.exp(-lh) * lh ** k / fact
    pa = np.exp(-la) * la ** k / fact
    M = np.outer(ph, pa)
    if rho:                                  # tau(i,j) de Dixon-Coles (solo afecta 0/1 goles)
        M[0, 0] *= 1 - lh * la * rho
        M[0, 1] *= 1 + lh * rho
        M[1, 0] *= 1 + la * rho
        M[1, 1] *= 1 - rho
    return M / M.sum()


def _1x2(M):
    return {1: float(np.tril(M, -1).sum()), 0: float(np.trace(M)), -1: float(np.triu(M, 1).sum())}


# ---------- Elo -> 1X2 ----------
def _fit_elo_model(win):
    """Logit multinomial: [elo_diff, dummy_localia] -> resultado (1 local / 0 empate / -1 visita)."""
    X = np.column_stack([(win.elo_home_pre - win.elo_away_pre).values,
                         np.where(win.neutral, 0.0, 1.0)])
    y = np.sign(win.home_score - win.away_score).astype(int)
    return LogisticRegression(max_iter=1000).fit(X, y)


def _elo_1x2(model, eh, ea, home_adv):
    p = model.predict_proba(np.array([[eh - ea, 1.0 if home_adv else 0.0]]))[0]
    cls = list(model.classes_)
    return {o: float(p[cls.index(o)]) for o in (1, 0, -1)}


# ---------- supremacia (Elo -> diferencia de goles) ----------
def _fit_supremacy(win, asof):
    """Regresion: diferencia de goles ~ elo_diff + dummy_localia (ponderada por recencia).
    Da la SUPREMACIA esperada desde el Elo; el TOTAL lo sigue poniendo el Poisson."""
    X = np.column_stack([(win.elo_home_pre - win.elo_away_pre).values,
                         np.where(win.neutral, 0.0, 1.0)])
    y = (win.home_score - win.away_score).values
    w = 0.5 ** ((asof - win.date).dt.days.clip(lower=0) / HALFLIFE_DAYS)
    return LinearRegression().fit(X, y, sample_weight=w)


def _lambdas(pois, cols, sup, eh, ea, home, away, ish):
    """Goles esperados COHERENTES: total del Poisson, supremacia del Elo."""
    total = _lam(pois, cols, home, away, ish) + _lam(pois, cols, away, home, 0)
    s = float(sup.predict(np.array([[eh - ea, 1.0 if ish else 0.0]]))[0])    # supremacia Elo
    return max((total + s) / 2, 0.05), max((total - s) / 2, 0.05)


# ---------- entrenamiento + evaluacion ----------
def _fit_models(df_elo, end, asof):
    win = df_elo[(df_elo.date < end) & (df_elo.date >= end - pd.DateOffset(years=SINCE_YEARS))]
    pois, cols = _fit_poisson(_long(win, asof))
    return pois, cols, _fit_elo_model(win), _fit_supremacy(win, asof), win


def _over25(M):
    return float(sum(M[i, j] for i in range(M.shape[0]) for j in range(M.shape[1]) if i + j >= 3))


def evaluate(df_elo, end, test_from, test_to, rho=RHO, w=ELO_W):
    """Entrena con la ventana que termina en `end`, testea en [test_from, test_to). Mide log loss
    de 1X2 (blend) y de Over/Under 2.5, ambos vs baseline. Sin fuga (modelos no ven el test)."""
    pois, cols, elo_m, sup, win = _fit_models(df_elo, end, end)
    r = np.sign(win.home_score - win.away_score)
    base = {1: (r == 1).mean(), 0: (r == 0).mean(), -1: (r == -1).mean()}
    ob = float(((win.home_score + win.away_score) >= 3).mean())     # baseline Over 2.5
    known = set(win.home_team) | set(win.away_team)
    te = df_elo[(df_elo.date >= test_from) & (df_elo.date < test_to)]
    llm = llb = llo = llob = n = correct = 0
    for g in te.itertuples():
        if g.home_team not in known or g.away_team not in known:
            continue
        ish = 0 if bool(g.neutral) else 1
        lh, la = _lambdas(pois, cols, sup, g.elo_home_pre, g.elo_away_pre, g.home_team, g.away_team, ish)
        M = _matrix(lh, la, rho)
        p = {o: w * _elo_1x2(elo_m, g.elo_home_pre, g.elo_away_pre, ish)[o] + (1 - w) * _1x2(M)[o]
             for o in (1, 0, -1)}
        s = int(np.sign(g.home_score - g.away_score))
        llm += -math.log(max(p[s], 1e-12))
        llb += -math.log(max(base[s], 1e-12))
        correct += (max(p, key=p.get) == s)
        pov, ov = _over25(M), (g.home_score + g.away_score) >= 3       # totales
        llo += -math.log(max(pov if ov else 1 - pov, 1e-12))
        llob += -math.log(max(ob if ov else 1 - ob, 1e-12))
        n += 1
    return dict(n=n, acc=correct / n, ll_model=llm / n, ll_base=llb / n,
                ll_over=llo / n, ll_over_base=llob / n)


def _predict_with(models, rating, local, visita, neutral=True, rho=RHO, w=ELO_W):
    """Predice un partido con modelos YA ajustados (no re-entrena por cada fixture)."""
    pois, cols, elo_m, sup = models
    ish = 0 if neutral else 1
    eh, ea = rating.get(local, elo.INIT), rating.get(visita, elo.INIT)
    lh, la = _lambdas(pois, cols, sup, eh, ea, local, visita, ish)    # goles coherentes con el Elo
    M = _matrix(lh, la, rho)
    ez = _elo_1x2(elo_m, eh, ea, not neutral)
    pz = _1x2(M)
    blend = {o: w * ez[o] + (1 - w) * pz[o] for o in (1, 0, -1)}
    over = lambda t: float(sum(M[i, j] for i in range(M.shape[0]) for j in range(M.shape[1]) if i + j >= t))
    sc = np.unravel_index(np.argmax(M), M.shape)
    btts, o25, gap = float(M[1:, 1:].sum()), over(3), eh - ea
    fav_o = max(blend, key=blend.get)
    prob_top = blend[fav_o]
    ins = [
        f"Elo {round(eh)} vs {round(ea)} ({'+' if gap >= 0 else ''}{round(gap)} para {local if gap >= 0 else visita})",
        f"Goles esperados: {local} {lh:.2f} - {visita} {la:.2f} (mas probable {int(sc[0])}-{int(sc[1])})",
        f"{'Pocos goles' if o25 < 0.5 else 'Partido abierto'}: Over 2.5 {round(o25*100)}% / BTTS {round(btts*100)}%",
    ]
    return dict(local=local, visita=visita, lh=lh, la=la, eh=eh, ea=ea, pois=pz, elo=ez, blend=blend,
                over=o25, over15=over(2), over35=over(4), btts=btts, score=(int(sc[0]), int(sc[1])),
                pick=(local if fav_o == 1 else visita if fav_o == -1 else "Empate"), prob_top=prob_top,
                level="ALTA" if prob_top >= 0.55 else "MEDIA" if prob_top >= 0.42 else "BAJA",
                market="1X2", insights=ins)


def predict(df_elo, rating, local, visita, neutral=True, rho=RHO, w=ELO_W):
    today = pd.Timestamp(datetime.date.today())
    models = _fit_models(df_elo, today + pd.Timedelta(days=1), today)[:4]
    return _predict_with(models, rating, local, visita, neutral, rho, w)


def predict_fixtures(fixtures, neutral=True):
    """fixtures: [(home, away[, neutral]), ...]. Ajusta los modelos UNA sola vez y predice todos
    (para el dashboard)."""
    df = load()
    df_elo, rating = elo.compute(df)
    teams = set(df.home_team) | set(df.away_team)
    today = pd.Timestamp(datetime.date.today())
    models = _fit_models(df_elo, today + pd.Timedelta(days=1), today)[:4]
    out = []
    for fx in fixtures:
        L, V = resolve(fx[0], teams), resolve(fx[1], teams)
        if L and V:
            out.append(_predict_with(models, rating, L, V, fx[2] if len(fx) > 2 else neutral))
    return out


def main():
    args = sys.argv[1:]
    l_in, v_in = (args + ["Brazil", "Morocco"])[:2]
    df = load()
    df_elo, rating = elo.compute(df)
    teams = set(df.home_team) | set(df.away_team)
    local, visita = resolve(l_in, teams), resolve(v_in, teams)
    if not local or not visita:
        print(f"  No reconozco: {l_in if not local else v_in!r}. Usa el nombre en ingles del dataset.")
        return

    today = pd.Timestamp(datetime.date.today())
    tf = today - pd.DateOffset(years=2)
    vb = evaluate(df_elo, tf, tf, today, RHO, ELO_W)         # blend
    vp = evaluate(df_elo, tf, tf, today, RHO, 0.0)           # solo Poisson (para comparar)
    r = predict(df_elo, rating, local, visita, neutral=True)
    fair = lambda p: f"{1 / p:.2f}" if p > 0 else "-"

    print("=" * 66)
    print(f"  PREDICTOR SELECCIONES (Elo + Poisson/Dixon-Coles)  -  {local} vs {visita}")
    print(f"  Cancha NEUTRAL (Mundial)  |  {datetime.date.today().isoformat()}")
    print("=" * 66)
    print("  VALIDACION (calibracion en internacionales recientes):")
    print(f"    1X2  log loss ...... {vb['ll_model']:.3f}   vs solo-Poisson {vp['ll_model']:.3f}   "
          f"vs baseline {vb['ll_base']:.3f}")
    print(f"    O/U 2.5  log loss .. {vb['ll_over']:.3f}   vs baseline {vb['ll_over_base']:.3f}")
    print(f"    Accuracy 1X2 ....... {vb['acc'] * 100:.1f}%   (sobre {vb['n']} partidos)\n")
    print(f"  Elo:  {local} {r['eh']:.0f}   -   {visita} {r['ea']:.0f}   (dif {r['eh'] - r['ea']:+.0f})")
    print(f"  Goles esperados (Poisson):  {local} {r['lh']:.2f}   -   {visita} {r['la']:.2f}")
    print(f"  Resultado mas probable:  {r['score'][0]}-{r['score'][1]}\n")
    b = r["blend"]
    print("  1X2 (blend Elo+Poisson):")
    print(f"    Gana {local:<14} {b[1] * 100:5.1f}%   (cuota justa {fair(b[1])})")
    print(f"    Empate{'':<14}{b[0] * 100:5.1f}%   (cuota justa {fair(b[0])})")
    print(f"    Gana {visita:<14} {b[-1] * 100:5.1f}%   (cuota justa {fair(b[-1])})")
    print(f"    [componentes -> Elo {r['elo'][1]*100:.0f}/{r['elo'][0]*100:.0f}/{r['elo'][-1]*100:.0f}  "
          f"Poisson {r['pois'][1]*100:.0f}/{r['pois'][0]*100:.0f}/{r['pois'][-1]*100:.0f}]\n")
    print("  Goles (Poisson/Dixon-Coles):")
    print(f"    Over 2.5 ........... {r['over'] * 100:5.1f}%   (cuota justa {fair(r['over'])})")
    print(f"    BTTS (ambos marcan)  {r['btts'] * 100:5.1f}%   (cuota justa {fair(r['btts'])})\n")
    h2h = df[((df.home_team == local) & (df.away_team == visita)) |
             ((df.home_team == visita) & (df.away_team == local))].tail(3)
    if len(h2h):
        print("  Historial reciente:")
        for g in h2h.itertuples():
            print(f"    {g.date.date()}  {g.home_team} {int(g.home_score)}-{int(g.away_score)} {g.away_team}  ({g.tournament})")
    print("\n  OJO: fuerza relativa por resultados (Elo + goles). NO sabe de plantel 2026,")
    print("  lesiones ni presion de Mundial. 'Cuota justa' = 1/prob, sin comision.")
    print("  Educativo. Modelo puramente estadistico - sin cuotas.\n")


if __name__ == "__main__":
    main()
