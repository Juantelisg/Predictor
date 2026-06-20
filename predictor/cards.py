"""cards.py - predictor de tarjetas amarillas para partidos de CLUBES.

Fuente: football-data.co.uk (CSV sin key, gratis). Columnas: HY/AY (amarillas home/away).
Ajuste opcional por arbitro: si tiene historial en los datos de la liga, se aplica un factor.
Mercados: Over/Under 2.5 / 3.5 / 4.5 totales + tarjetas individuales por equipo.

Uso:
  python predictor/cards.py --league=PL "Manchester City" "Arsenal"
  python predictor/cards.py --league=PL --referee="Michael Oliver" "Chelsea" "Liverpool"

Ligas: PL (Premier League), SP1 (La Liga), D1 (Bundesliga), I1 (Serie A), F1 (Ligue 1)

NOTA: este modulo es para CLUBES. Para selecciones nacionales (Mundial) los datos de
tarjetas por equipo/jugador requieren API-Football (fase 2 del plan).
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
    "I1": "I1", "SERIEA": "I1",
    "F1": "F1", "LIGUE1": "F1",
    "E1": "E1", "CHAMPIONSHIP": "E1",
}

SEASONS = ["2526", "2425", "2324"]
MIN_GAMES = 5
REF_MIN_GAMES = 8    # minimo de partidos del arbitro para aplicar su factor


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
            needed = {"HomeTeam", "AwayTeam", "HY", "AY"}
            if not needed.issubset(df.columns):
                continue
            df["HY"] = pd.to_numeric(df["HY"], errors="coerce")
            df["AY"] = pd.to_numeric(df["AY"], errors="coerce")
            df = df.dropna(subset=["HomeTeam", "AwayTeam", "HY", "AY"]).copy()
            df["total_y"] = df["HY"] + df["AY"]
            if len(df) >= 20:
                return df, season
        except Exception:
            continue
    raise RuntimeError(f"No se pudo cargar datos para {league_key}.")


def resolve(name, teams):
    import difflib
    n = name.lower().strip()
    tl = {t.lower(): t for t in teams}
    if n in tl:
        return tl[n]
    for k, t in tl.items():
        if n in k or k in n:
            return t
    m = difflib.get_close_matches(n, tl.keys(), n=1, cutoff=0.6)
    return tl[m[0]] if m else None


def _home_stats(df, team):
    g = df[df.HomeTeam == team]
    if len(g) < MIN_GAMES:
        return None
    return {"yf": g["HY"].mean(), "ya": g["AY"].mean(), "n": len(g)}


def _away_stats(df, team):
    g = df[df.AwayTeam == team]
    if len(g) < MIN_GAMES:
        return None
    return {"yf": g["AY"].mean(), "ya": g["HY"].mean(), "n": len(g)}


def _referee_factor(df, referee):
    """Factor multiplicativo del arbitro vs promedio de la liga. Retorna 1.0 si sin datos."""
    if not referee or "Referee" not in df.columns:
        return 1.0, None
    ref_col = df["Referee"].str.lower().str.strip()
    ref_key = referee.lower().strip()
    g = df[ref_col.str.contains(ref_key, na=False)]
    if len(g) < REF_MIN_GAMES:
        return 1.0, {"n": len(g), "avg": None, "msg": "pocos partidos para el factor"}
    ref_avg = g["total_y"].mean()
    league_avg = df["total_y"].mean()
    factor = ref_avg / league_avg if league_avg > 0 else 1.0
    return round(factor, 3), {"n": len(g), "avg": round(ref_avg, 2), "league_avg": round(league_avg, 2)}


def _poisson_over(lam, threshold):
    k = int(math.floor(threshold))
    cumulative, p = 0.0, math.exp(-lam)
    for i in range(k + 1):
        cumulative += p
        p *= lam / (i + 1)
    return 1.0 - cumulative


def predict(home, away, league="PL", referee=None):
    df, season = load(league)
    teams = set(df.HomeTeam) | set(df.AwayTeam)
    H = resolve(home, teams)
    A = resolve(away, teams)
    if not H:
        raise ValueError(f"Equipo no encontrado: {home!r}")
    if not A:
        raise ValueError(f"Equipo no encontrado: {away!r}")

    sh = _home_stats(df, H)
    sa = _away_stats(df, A)
    if not sh or not sa:
        raise ValueError(f"Datos insuficientes (min {MIN_GAMES} partidos por equipo).")

    avg_yh = df["HY"].mean()
    avg_ya = df["AY"].mean()
    ref_factor, ref_info = _referee_factor(df, referee)

    # Lambda tarjetas: ataque (disciplina propia) * defensa (provoca al rival) / liga * factor_arbitro
    lh = max(sh["yf"] * sa["ya"] / avg_yh, 0.1) * ref_factor
    la = max(sa["yf"] * sh["ya"] / avg_ya, 0.1) * ref_factor

    # Total esperado y Over/Under
    total_exp = lh + la

    return dict(
        home=H, away=A, league=league.upper(), season=season,
        lh=round(lh, 2), la=round(la, 2), total_exp=round(total_exp, 2),
        ref_factor=ref_factor, ref_info=ref_info, referee=referee,
        over25=round(_poisson_over(total_exp, 2.5), 3),
        over35=round(_poisson_over(total_exp, 3.5), 3),
        over45=round(_poisson_over(total_exp, 4.5), 3),
        home_over15=round(_poisson_over(lh, 1.5), 3),
        home_over25=round(_poisson_over(lh, 2.5), 3),
        away_over15=round(_poisson_over(la, 1.5), 3),
        away_over25=round(_poisson_over(la, 2.5), 3),
        stats_home=sh, stats_away=sa,
        avg_league_yh=round(avg_yh, 2), avg_league_ya=round(avg_ya, 2),
    )


def main():
    non_flags = [a for a in sys.argv[1:] if not a.startswith("--")]
    league  = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--league=")),  "PL")
    referee = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--referee=")), None)

    if len(non_flags) < 2:
        print("  Uso: cards.py [--league=PL] [--referee='Nombre'] <local> <visita>")
        return

    home, away = non_flags[0], non_flags[1]
    try:
        r = predict(home, away, league, referee)
    except (ValueError, RuntimeError) as e:
        print(f"  Error: {e}")
        return

    fair = lambda p: f"{1/p:.2f}" if p > 0.01 else "--"

    print("=" * 62)
    print(f"  TARJETAS  {r['home']} vs {r['away']}  [{r['league']} {r['season']}]")
    print("=" * 62)
    print(f"  Amarillas esperadas: {r['home']} {r['lh']} + {r['away']} {r['la']} = {r['total_exp']}")
    print(f"  (Liga: {r['avg_league_yh']:.1f} locales / {r['avg_league_ya']:.1f} visita promedio)")
    if r["referee"] and r["ref_info"]:
        ri = r["ref_info"]
        if ri.get("avg"):
            print(f"  Arbitro {r['referee']!r}: {ri['avg']:.1f} tarj/partido "
                  f"vs liga {ri['league_avg']:.1f} -> factor x{r['ref_factor']} ({ri['n']} partidos)")
        else:
            print(f"  Arbitro {r['referee']!r}: {ri.get('msg', 'sin datos')}")
    print()

    rows = [
        ("Over 2.5 total",        r["over25"]),
        ("Over 3.5 total",        r["over35"]),
        ("Over 4.5 total",        r["over45"]),
        (f"{r['home']} Over 1.5", r["home_over15"]),
        (f"{r['home']} Over 2.5", r["home_over25"]),
        (f"{r['away']} Over 1.5", r["away_over15"]),
        (f"{r['away']} Over 2.5", r["away_over25"]),
    ]
    print(f"  {'Mercado':<24} {'Prob':>7}   {'Cuota justa':>11}")
    print("  " + "-" * 46)
    for label, p in rows:
        print(f"  {label:<24} {p*100:>6.1f}%   {fair(p):>11}")

    sh, sa = r["stats_home"], r["stats_away"]
    print(f"\n  Base historica ({r['season']}):")
    print(f"    {r['home']:<22} {sh['yf']:.2f} yf / {sh['ya']:.2f} ya  ({sh['n']} partidos local)")
    print(f"    {r['away']:<22} {sa['yf']:.2f} yf / {sa['ya']:.2f} ya  ({sa['n']} partidos visita)")
    print(f"\n  Cuota justa = 1/prob sin margen. Educativo. Solo ligas de CLUBES.\n")


if __name__ == "__main__":
    main()
