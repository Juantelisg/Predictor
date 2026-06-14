"""core.py - pipeline SPORT-AGNOSTICO del predictor. CERO cuotas.

SQLite (schema multi-deporte) -> features sin fuga temporal -> regresion logistica
interpretable -> validacion holdout + explicacion de que stats pesaron.

Lo unico sport-especifico es el LOADER de datos (ver mvp_nba.py / mlb.py): cada uno
arma `teams` y `games_rows` y llama a estas funciones. Sirve para cualquier deporte
binario (sin empate): NBA, MLB, NFL. Soccer (con empate) usa otro modelo (Poisson).
"""
import os, sqlite3
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, log_loss

ROOT = os.path.dirname(os.path.abspath(__file__))

FEATURES = ["home_l10_winpct", "away_l10_winpct", "home_l10_ptdiff", "away_l10_ptdiff",
            "home_split_winpct", "away_split_winpct", "home_rest", "away_rest"]
MIN_PREV = 5             # muestra minima de juegos previos para tener forma estable


def cargar_sqlite(teams, games_rows, sport):
    """teams = {team_id: name}; games_rows = [(game_id, date, home_id, away_id, home_score, away_score)].
    Carga al esquema (schema.sql) en memoria. Cambiar ':memory:' por una ruta para persistir."""
    con = sqlite3.connect(":memory:")
    with open(os.path.join(ROOT, "schema.sql"), encoding="utf-8") as f:
        con.executescript(f.read())
    con.executemany("INSERT OR IGNORE INTO teams(team_id, sport, name) VALUES (?, ?, ?)",
                    [(tid, sport, name) for tid, name in teams.items()])
    con.executemany("INSERT INTO games(game_id, sport, date, home_team_id, away_team_id, "
                    "home_score, away_score, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'final')",
                    [(gid, sport, d, h, a, hs, as_) for gid, d, h, a, hs, as_ in games_rows])
    con.commit()
    return con


def _team_log(games):
    """Explota cada juego en 2 filas (una por equipo) para medir forma y splits."""
    out = []
    for g in games.itertuples():
        out.append(dict(date=g.date, team=g.home_team_id, is_home=1, pts=g.home_score,
                        opp=g.away_score, win=int(g.home_score > g.away_score)))
        out.append(dict(date=g.date, team=g.away_team_id, is_home=0, pts=g.away_score,
                        opp=g.home_score, win=int(g.away_score > g.home_score)))
    return pd.DataFrame(out).sort_values("date").reset_index(drop=True)


def form(log, tid, date, side):
    """Features de forma de un equipo a `date` usando SOLO sus juegos previos (sin fuga).
    None si no hay muestra minima. Reusable para juegos historicos y para predecir proximos."""
    prev = log[(log.team == tid) & (log.date < date)]
    if len(prev) < MIN_PREV:
        return None
    l10 = prev.tail(10)
    split = prev[prev.is_home == (1 if side == "home" else 0)]
    return {
        f"{side}_l10_winpct": l10.win.mean(),
        f"{side}_l10_ptdiff": float((l10.pts - l10.opp).mean()),   # diferencial (puntos/carreras)
        f"{side}_split_winpct": split.win.mean() if len(split) else l10.win.mean(),
        f"{side}_rest": (pd.Timestamp(date) - pd.Timestamp(prev.date.max())).days,
    }


def construir_features(con):
    games = pd.read_sql("SELECT game_id, date, home_team_id, away_team_id, home_score, "
                        "away_score FROM games ORDER BY date", con)
    log = _team_log(games)
    feats = []
    for g in games.itertuples():
        fh = form(log, g.home_team_id, g.date, "home")
        fa = form(log, g.away_team_id, g.date, "away")
        if fh is None or fa is None:
            continue
        feats.append({"game_id": g.game_id, "home_id": g.home_team_id, "away_id": g.away_team_id,
                      **fh, **fa, "home_win": int(g.home_score > g.away_score)})
    return pd.DataFrame(feats)


def fit_model(df, features=FEATURES):
    """Ajusta el modelo sobre TODO df (sin holdout) y devuelve (model, scaler) para predecir nuevos."""
    scaler = StandardScaler().fit(df[features])
    model = LogisticRegression(max_iter=1000).fit(scaler.transform(df[features]), df["home_win"])
    return model, scaler


def entrenar_y_evaluar(df, features=FEATURES):
    cut = int(len(df) * 0.8)
    train, hold = df.iloc[:cut], df.iloc[cut:]      # split CRONOLOGICO (sin fuga temporal)
    scaler = StandardScaler().fit(train[features])
    model = LogisticRegression(max_iter=1000).fit(scaler.transform(train[features]), train["home_win"])

    ph = model.predict_proba(scaler.transform(hold[features]))[:, 1]
    metrics = {
        "n_train": len(train), "n_hold": len(hold), "n_features": len(features),
        "acc": accuracy_score(hold["home_win"], (ph >= 0.5).astype(int)),
        "logloss": log_loss(hold["home_win"], ph, labels=[0, 1]),
        "base_acc": accuracy_score(hold["home_win"], np.ones(len(hold), dtype=int)),  # baseline: siempre local
    }
    test = hold.iloc[-1]            # explicacion de UN partido: el ultimo del holdout (sin cherry-pick)
    xt = scaler.transform(test[features].to_frame().T)[0]
    prob = model.predict_proba([xt])[0][1]
    contrib = sorted(zip(features, model.coef_[0] * xt, test[features].values),
                     key=lambda c: abs(c[1]), reverse=True)
    return metrics, test, prob, contrib


def reportar(m, test, prob, contrib, titulo, equipo=lambda i: f"id {i}"):
    print("=" * 64)
    print(f"  {titulo}")
    print("=" * 64)
    print(f"  Train: {m['n_train']} partidos | Holdout: {m['n_hold']} | "
          f"LogisticRegression ({m.get('n_features', len(FEATURES))} features)\n")
    print("  VALIDACION (holdout cronologico):")
    print(f"    Accuracy modelo .................. {m['acc'] * 100:.1f}%")
    print(f"    Accuracy baseline (siempre local)  {m['base_acc'] * 100:.1f}%")
    print(f"    Log loss ........................ {m['logloss']:.3f}   (mas bajo = mejor; coin-flip = 0.693)\n")
    print(f"  EJEMPLO -  {equipo(int(test.home_id))} (local)  vs  {equipo(int(test.away_id))} (visita)")
    print(f"  Resultado real (holdout): {'GANO LOCAL' if test.home_win else 'GANO VISITA'}\n")
    print(f"  >> Probabilidad de victoria LOCAL: {prob * 100:.1f}%   "
          f"(favorito: {'LOCAL' if prob >= 0.5 else 'VISITA'})\n")
    print("  Stats que mas pesaron (aporte al log-odds; signo + favorece al LOCAL):")
    print(f"  {'feature':<20}{'valor':>9}{'aporte':>10}   direccion")
    print("  " + "-" * 53)
    for name, c, val in contrib[:5]:
        print(f"  {name:<20}{val:>9.2f}{c:>+10.2f}   {'LOCAL' if c > 0 else 'VISITA'}")
    print()
