"""corners.py - predictor de corners para CLUBES y SELECCIONES NACIONALES.

Fuentes:
  CLUBES      → football-data.co.uk (CSV sin key, gratis). --league=PL|SP1|D1|I1|F1
  SELECCIONES → statsbomb_data.py (StatsBomb Open Data, libre). --intl

Modelo: Poisson ataque*defensa/liga (mismo approach Dixon-Coles aplicado a goles).
Mercados: Over/Under 8.5 / 9.5 / 10.5 totales + corners individuales por equipo.

Uso CLUBES:
  python predictor/corners.py --league=PL "Manchester City" "Arsenal"
  python predictor/corners.py --league=SP1 "Barcelona" "Real Madrid"

Uso SELECCIONES (Mundial / internacional):
  python predictor/corners.py --intl "France" "Senegal"
  python predictor/corners.py --intl "Argentina" "Algeria"
"""
import sys, io, math
import numpy as np
import pandas as pd
import requests
import cache

sys.stdout.reconfigure(encoding="utf-8")

LEAGUES = {
    "PL": "E0", "PREMIER": "E0", "E0": "E0",
    "SP1": "SP1", "LALIGA": "SP1",
    "D1": "D1", "BUNDESLIGA": "D1",
    "I1": "I1", "SERIEA": "I1", "SERIE A": "I1",
    "F1": "F1", "LIGUE1": "F1",
    "E1": "E1", "CHAMPIONSHIP": "E1",
    "SP2": "SP2", "D2": "D2",
}

SEASONS = ["2526", "2425", "2324"]  # probar en orden hasta tener suficientes datos
MIN_GAMES = 5                        # minimo de partidos para calcular stats fiables
MAXC = 25                            # tope de la distribucion Poisson de corners


_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _url(season, code):
    return f"https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"


def load(league_key):
    code = LEAGUES.get(league_key.upper().replace(" ", ""))
    if not code:
        raise ValueError(f"Liga no reconocida: {league_key!r}. Opciones: {sorted(set(LEAGUES.keys()))}")
    for season in SEASONS:
        url = _url(season, code)
        try:
            txt = cache.cached(f"fdco:{season}:{code}", cache.TTL_STATIC,
                               lambda u=url: requests.get(u, headers=_HEADERS, timeout=30).text)
            df = pd.read_csv(io.StringIO(txt), on_bad_lines="skip")
            df = df.rename(columns=str.strip)
            needed = {"HomeTeam", "AwayTeam", "HC", "AC"}
            if not needed.issubset(df.columns):
                continue
            df["HC"] = pd.to_numeric(df["HC"], errors="coerce")
            df["AC"] = pd.to_numeric(df["AC"], errors="coerce")
            df = df.dropna(subset=["HomeTeam", "AwayTeam", "HC", "AC"]).copy()
            if len(df) >= 20:
                return df, season
        except Exception:
            continue
    raise RuntimeError(f"No se pudo cargar datos para {league_key}. Verificar conexion o nombre de liga.")


def resolve(name, teams):
    import difflib
    n = name.lower().strip()
    tl = {t.lower(): t for t in teams}
    if n in tl:
        return tl[n]
    for k, t in tl.items():
        if n in k or k in n:
            return t
    # fuzzy fallback
    m = difflib.get_close_matches(n, tl.keys(), n=1, cutoff=0.6)
    return tl[m[0]] if m else None


def _home_stats(df, team):
    """Corners del equipo en partidos DE LOCAL."""
    g = df[df.HomeTeam == team]
    if len(g) < MIN_GAMES:
        return None
    return {"cf": g["HC"].mean(), "ca": g["AC"].mean(), "n": len(g)}


def _away_stats(df, team):
    """Corners del equipo en partidos DE VISITA."""
    g = df[df.AwayTeam == team]
    if len(g) < MIN_GAMES:
        return None
    return {"cf": g["AC"].mean(), "ca": g["HC"].mean(), "n": len(g)}


def _poisson_over(lam, threshold):
    """P(X > threshold) exacto para Poisson(lam)."""
    k = int(math.floor(threshold))
    cumulative, p = 0.0, math.exp(-lam)
    for i in range(k + 1):
        cumulative += p
        p *= lam / (i + 1)
    return 1.0 - cumulative


def predict(home, away, league="PL"):
    df, season = load(league)
    teams = set(df.HomeTeam) | set(df.AwayTeam)
    H = resolve(home, teams)
    A = resolve(away, teams)
    if not H:
        raise ValueError(f"Equipo no encontrado: {home!r}. Equipos disponibles: {sorted(teams)[:10]}...")
    if not A:
        raise ValueError(f"Equipo no encontrado: {away!r}. Equipos disponibles: {sorted(teams)[:10]}...")

    sh = _home_stats(df, H)
    sa = _away_stats(df, A)
    if not sh or not sa:
        raise ValueError(f"Datos insuficientes (min {MIN_GAMES} partidos). "
                         f"{H}: {sh['n'] if sh else 0} locales, {A}: {sa['n'] if sa else 0} visita.")

    # Promedios de la liga (referencia para el factor multiplicativo)
    avg_h = df["HC"].mean()   # corners local promedio de la liga
    avg_a = df["AC"].mean()   # corners visita promedio de la liga

    # Lambda: ataque_equipo * defensa_rival / media_liga
    lh = max(sh["cf"] * sa["ca"] / avg_h, 0.3)
    la = max(sa["cf"] * sh["ca"] / avg_a, 0.3)

    # Matriz conjunta (Poisson independiente)
    k = np.arange(MAXC + 1)
    fact = np.array([math.factorial(int(i)) for i in k], dtype=float)
    ph = np.exp(-lh) * lh ** k / fact
    pa = np.exp(-la) * la ** k / fact
    M = np.outer(ph, pa)
    M /= M.sum()

    def over_total(n):
        return float(sum(M[i, j] for i in range(M.shape[0]) for j in range(M.shape[1]) if i + j > n))

    return dict(
        home=H, away=A, league=league.upper(), season=season,
        lh=round(lh, 2), la=round(la, 2), total_exp=round(lh + la, 2),
        over85=round(over_total(8.5), 3),
        over95=round(over_total(9.5), 3),
        over105=round(over_total(10.5), 3),
        home_over45=round(_poisson_over(lh, 4.5), 3),
        home_over55=round(_poisson_over(lh, 5.5), 3),
        home_over65=round(_poisson_over(lh, 6.5), 3),
        away_over35=round(_poisson_over(la, 3.5), 3),
        away_over45=round(_poisson_over(la, 4.5), 3),
        away_over55=round(_poisson_over(la, 5.5), 3),
        stats_home=sh, stats_away=sa,
        avg_league_h=round(avg_h, 2), avg_league_a=round(avg_a, 2),
    )


def main():
    non_flags = [a for a in sys.argv[1:] if not a.startswith("--")]
    league  = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--league=")), "PL")
    is_intl = "--intl" in sys.argv

    if len(non_flags) < 2:
        print("  Uso clubes:       corners.py --league=PL <local> <visita>")
        print("  Uso selecciones:  corners.py --intl <local> <visita>")
        print("  Ligas clubes: PL, SP1, D1, I1, F1, E1")
        return

    home, away = non_flags[0], non_flags[1]

    if is_intl:
        try:
            import statsbomb_data as sb_data
            print("  Cargando datos StatsBomb (primera vez ~5 min)...")
            r = sb_data.predict_corners(home, away)
        except (ValueError, RuntimeError) as e:
            print(f"  Error: {e}")
            return
        fair = lambda p: f"{1/p:.2f}" if p > 0.01 else "--"
        print("=" * 62)
        print(f"  CORNERS (Intl/StatsBomb)  {r['home']} vs {r['away']}")
        print("=" * 62)
        print(f"  Corners esperados: {r['home']} {r['lh']} + {r['away']} {r['la']} = {r['total_exp']}\n")
        rows = [
            ("Over 8.5 total",        r["over85"]),
            ("Over 9.5 total",        r["over95"]),
            ("Over 10.5 total",       r["over105"]),
            (f"{r['home']} Over 4.5", r["home_over45"]),
            (f"{r['home']} Over 5.5", r["home_over55"]),
            (f"{r['away']} Over 3.5", r["away_over35"]),
            (f"{r['away']} Over 4.5", r["away_over45"]),
        ]
        print(f"  {'Mercado':<24} {'Prob':>7}   {'Cuota justa':>11}")
        print("  " + "-" * 46)
        for label, p in rows:
            print(f"  {label:<24} {p*100:>6.1f}%   {fair(p):>11}")
        sh, sa = r["stats_home"], r["stats_away"]
        print(f"\n  Base StatsBomb (WC/Euro/Copa/AFCON):")
        print(f"    {r['home']:<22} {sh['avg_corners_for']:.1f} cf / {sh['avg_corners_against']:.1f} ca")
        print(f"    {r['away']:<22} {sa['avg_corners_for']:.1f} cf / {sa['avg_corners_against']:.1f} ca")
        print(f"\n  Cuota justa = 1/prob sin margen. Educativo.\n")
        return

    try:
        r = predict(home, away, league)
    except (ValueError, RuntimeError) as e:
        print(f"  Error: {e}")
        return

    fair = lambda p: f"{1/p:.2f}" if p > 0.01 else "--"

    print("=" * 62)
    print(f"  CORNERS  {r['home']} vs {r['away']}  [{r['league']} {r['season']}]")
    print("=" * 62)
    print(f"  Corners esperados: {r['home']} {r['lh']} + {r['away']} {r['la']} = {r['total_exp']}")
    print(f"  (Liga: {r['avg_league_h']:.1f} locales / {r['avg_league_a']:.1f} visita promedio)\n")

    rows = [
        ("Over 8.5 total",         r["over85"]),
        ("Over 9.5 total",         r["over95"]),
        ("Over 10.5 total",        r["over105"]),
        (f"{r['home']} Over 4.5",  r["home_over45"]),
        (f"{r['home']} Over 5.5",  r["home_over55"]),
        (f"{r['home']} Over 6.5",  r["home_over65"]),
        (f"{r['away']} Over 3.5",  r["away_over35"]),
        (f"{r['away']} Over 4.5",  r["away_over45"]),
        (f"{r['away']} Over 5.5",  r["away_over55"]),
    ]
    print(f"  {'Mercado':<24} {'Prob':>7}   {'Cuota justa':>11}")
    print("  " + "-" * 46)
    for label, p in rows:
        print(f"  {label:<24} {p*100:>6.1f}%   {fair(p):>11}")

    sh, sa = r["stats_home"], r["stats_away"]
    print(f"\n  Base historica ({r['season']}):")
    print(f"    {r['home']:<22} {sh['cf']:.1f} cf / {sh['ca']:.1f} ca  ({sh['n']} partidos local)")
    print(f"    {r['away']:<22} {sa['cf']:.1f} cf / {sa['ca']:.1f} ca  ({sa['n']} partidos visita)")
    print(f"\n  Cuota justa = 1/prob sin margen. Educativo. Solo ligas de CLUBES.\n")


if __name__ == "__main__":
    main()
