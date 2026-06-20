"""statsbomb_data.py - xG y corners de SELECCIONES desde StatsBomb Open Data (libre, sin key).

Fuente: statsbombpy (GitHub data, licencia open). Cubre torneos internacionales gratuitos:
  WC 2022/2018, Euro 2024/2020, Copa America 2024, AFCON 2023.

Retorna por seleccion (ponderado por recencia del torneo):
  avg_xg_for / avg_xg_against / avg_corners_for / avg_corners_against  (por partido)

Primera ejecucion: 5-8 min (descarga ~300 partidos de GitHub y los cachea localmente).
Siguientes llamadas: instantaneo (cache 7 dias en data/cache/).

Uso:
  python predictor/statsbomb_data.py                    # resumen de todas las selecciones
  python predictor/statsbomb_data.py France Senegal     # stats de dos equipos
  python predictor/statsbomb_data.py --corners France Senegal   # prediccion de corners
"""
import sys, os, json, warnings, math
import numpy as np

warnings.filterwarnings("ignore")   # silencia NoAuthWarning de statsbombpy

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import cache

# ---------------------------------------------------------------------------
# Competiciones libres de selecciones con pesos de recencia
# ---------------------------------------------------------------------------
COMPETITIONS = [
    {"cid": 43,   "sid": 106, "name": "FIFA World Cup 2022",   "weight": 1.0},
    {"cid": 223,  "sid": 282, "name": "Copa America 2024",     "weight": 1.0},
    {"cid": 55,   "sid": 282, "name": "UEFA Euro 2024",        "weight": 1.0},
    {"cid": 1267, "sid": 107, "name": "AFCON 2023",            "weight": 0.9},
    {"cid": 55,   "sid": 43,  "name": "UEFA Euro 2020",        "weight": 0.7},
    {"cid": 43,   "sid": 3,   "name": "FIFA World Cup 2018",   "weight": 0.5},
]

# Nombres StatsBomb -> martj42 (solo donde difieren)
SB_TO_M42 = {
    "IR Iran": "Iran",
    "United States": "United States",
    "Republic of Ireland": "Republic of Ireland",
    "Korea Republic": "South Korea",
    "Côte d'Ivoire": "Ivory Coast",
    "Guinea-Bissau": "Guinea-Bissau",
    "Burkina Faso": "Burkina Faso",
    "DR Congo": "DR Congo",
    "Cape Verde Islands": "Cape Verde",
    "Equatorial Guinea": "Equatorial Guinea",
}

MAXC = 20


def _compute():
    """Procesa todas las competiciones y retorna el dict agregado por equipo."""
    from statsbombpy import sb

    stats = {}   # team -> {xgf, xga, cf, ca, ycf, yca, w}

    def _add(team, xgf, xga, cf, ca, ycf, yca, w):
        t = stats.setdefault(team, {"xgf": 0.0, "xga": 0.0, "cf": 0.0, "ca": 0.0,
                                    "ycf": 0.0, "yca": 0.0, "w": 0.0})
        t["xgf"] += xgf * w
        t["xga"] += xga * w
        t["cf"]  += cf  * w
        t["ca"]  += ca  * w
        t["ycf"] += ycf * w
        t["yca"] += yca * w
        t["w"]   += w

    total_matches = 0
    for comp in COMPETITIONS:
        try:
            matches = sb.matches(competition_id=comp["cid"], season_id=comp["sid"])
        except Exception:
            continue
        w = comp["weight"]
        for _, m in matches.iterrows():
            try:
                ev = sb.events(match_id=m.match_id)
            except Exception:
                continue
            total_matches += 1
            type_name = ev["type"].apply(lambda x: x.get("name") if isinstance(x, dict) else x)

            # Corners: Pass con pass_type == "Corner"
            passes = ev[type_name == "Pass"]
            corners = passes[passes["pass_type"] == "Corner"] if "pass_type" in passes.columns else passes.iloc[:0]

            # xG: shots
            shots = ev[type_name == "Shot"]

            home, away = m.home_team, m.away_team
            hc = len(corners[corners["team"] == home])
            ac = len(corners[corners["team"] == away])
            hxg = float(shots[shots["team"] == home]["shot_statsbomb_xg"].sum())
            axg = float(shots[shots["team"] == away]["shot_statsbomb_xg"].sum())

            # Tarjetas amarillas por equipo (foul_committed_card / bad_behaviour_card)
            hyc = ayc = 0
            for col in ("foul_committed_card", "bad_behaviour_card"):
                if col in ev.columns:
                    yc = ev[ev[col].isin(["Yellow Card", "Second Yellow"])]
                    hyc += int((yc["team"] == home).sum())
                    ayc += int((yc["team"] == away).sum())

            # Resolver nombre (StatsBomb → martj42)
            home_r = SB_TO_M42.get(home, home)
            away_r = SB_TO_M42.get(away, away)

            _add(home_r, hxg, axg, hc, ac, hyc, ayc, w)
            _add(away_r, axg, hxg, ac, hc, ayc, hyc, w)

    # Normalizar por peso acumulado
    out = {}
    for team, v in stats.items():
        if v["w"] > 0:
            out[team] = {
                "avg_xg_for":       round(v["xgf"] / v["w"], 3),
                "avg_xg_against":   round(v["xga"] / v["w"], 3),
                "avg_corners_for":  round(v["cf"]  / v["w"], 2),
                "avg_corners_against": round(v["ca"] / v["w"], 2),
                "avg_cards_for":    round(v["ycf"] / v["w"], 2),
                "avg_cards_against": round(v["yca"] / v["w"], 2),
                "games_weighted":   round(v["w"], 1),
            }
    return out


def load():
    """Retorna el dict de stats por equipo (cacheado 7 dias)."""
    return cache.cached("statsbomb_intl_agg_v2", cache.TTL_STATIC, _compute)


def resolve(name, data):
    """Resuelve nombre de equipo al key del dict (case-insensitive, partial match)."""
    import difflib
    n = name.lower().strip()
    keys_lower = {k.lower(): k for k in data}
    if n in keys_lower:
        return keys_lower[n]
    for k, v in keys_lower.items():
        if n in k or k in n:
            return v
    m = difflib.get_close_matches(n, keys_lower.keys(), n=1, cutoff=0.6)
    return keys_lower[m[0]] if m else None


def get(team_name):
    """Stats de un equipo o None si no hay datos."""
    data = load()
    key = resolve(team_name, data)
    return data.get(key) if key else None


# ---------------------------------------------------------------------------
# Prediccion de corners para SELECCIONES (usando StatsBomb)
# ---------------------------------------------------------------------------
def predict_corners(home, away):
    """Predice corners para un partido entre selecciones con datos StatsBomb."""
    data = load()
    H = resolve(home, data)
    A = resolve(away, data)
    missing = []
    if not H: missing.append(home)
    if not A: missing.append(away)
    if missing:
        raise ValueError(f"Sin datos StatsBomb para: {missing}. Equipos disponibles: "
                         f"{sorted(data.keys())[:10]}...")

    sh = data[H]
    sa = data[A]

    # Lambda estilo Dixon-Coles: ataque_local * defensa_visita / media_del_set
    all_cf = [v["avg_corners_for"] for v in data.values()]
    all_ca = [v["avg_corners_against"] for v in data.values()]
    avg_cf = sum(all_cf) / len(all_cf)
    avg_ca = sum(all_ca) / len(all_ca)
    league_avg = (avg_cf + avg_ca) / 2

    lh = max(sh["avg_corners_for"] * sa["avg_corners_against"] / league_avg, 0.3)
    la = max(sa["avg_corners_for"] * sh["avg_corners_against"] / league_avg, 0.3)

    # Matriz Poisson
    k = np.arange(MAXC + 1)
    fact = np.array([math.factorial(int(i)) for i in k], dtype=float)
    ph = np.exp(-lh) * lh ** k / fact
    pa = np.exp(-la) * la ** k / fact
    M = np.outer(ph, pa); M /= M.sum()

    def over_total(n):
        return float(sum(M[i, j] for i in range(M.shape[0]) for j in range(M.shape[1]) if i + j > n))

    def over_team(lam, n):
        cumulative, p = 0.0, math.exp(-lam)
        ki = int(math.floor(n))
        for i in range(ki + 1):
            cumulative += p; p *= lam / (i + 1)
        return 1.0 - cumulative

    return dict(
        home=H, away=A, source="StatsBomb",
        lh=round(lh, 2), la=round(la, 2), total_exp=round(lh + la, 2),
        over85=round(over_total(8.5), 3),
        over95=round(over_total(9.5), 3),
        over105=round(over_total(10.5), 3),
        home_over45=round(over_team(lh, 4.5), 3),
        home_over55=round(over_team(lh, 5.5), 3),
        away_over35=round(over_team(la, 3.5), 3),
        away_over45=round(over_team(la, 4.5), 3),
        stats_home=sh, stats_away=sa,
    )


# ---------------------------------------------------------------------------
# Prediccion de tarjetas amarillas para SELECCIONES (usando StatsBomb)
# ---------------------------------------------------------------------------
def predict_cards(home, away):
    """Predice tarjetas amarillas TOTALES para un partido entre selecciones."""
    data = load()
    H = resolve(home, data)
    A = resolve(away, data)
    missing = [n for n, k in [(home, H), (away, A)] if not k]
    if missing:
        raise ValueError(f"Sin datos StatsBomb para: {missing}. Equipos disponibles: "
                         f"{sorted(data.keys())[:10]}...")

    sh, sa = data[H], data[A]
    all_cf = [v["avg_cards_for"] for v in data.values()]
    all_ca = [v["avg_cards_against"] for v in data.values()]
    league_avg = (sum(all_cf) / len(all_cf) + sum(all_ca) / len(all_ca)) / 2

    # ataque (indisciplina propia) * defensa (provoca al rival) / media del set
    lh = max(sh["avg_cards_for"] * sa["avg_cards_against"] / league_avg, 0.2)
    la = max(sa["avg_cards_for"] * sh["avg_cards_against"] / league_avg, 0.2)

    MAXY = 12
    k = np.arange(MAXY + 1)
    fact = np.array([math.factorial(int(i)) for i in k], dtype=float)
    ph = np.exp(-lh) * lh ** k / fact
    pa = np.exp(-la) * la ** k / fact
    M = np.outer(ph, pa); M /= M.sum()

    def over_total(n):
        return float(sum(M[i, j] for i in range(M.shape[0]) for j in range(M.shape[1]) if i + j > n))

    return dict(
        home=H, away=A, source="StatsBomb",
        lh=round(lh, 2), la=round(la, 2), total_exp=round(lh + la, 2),
        over25=round(over_total(2.5), 3),
        over35=round(over_total(3.5), 3),
        over45=round(over_total(4.5), 3),
        stats_home=sh, stats_away=sa,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    mode = "--corners" if "--corners" in sys.argv else "stats"

    print("  Cargando datos StatsBomb (puede tardar ~5 min en la primera ejecucion)...")
    data = load()
    print(f"  {len(data)} selecciones con datos.\n")

    if mode == "--corners" and len(args) >= 2:
        try:
            r = predict_corners(args[0], args[1])
            fair = lambda p: f"{1/p:.2f}" if p > 0.01 else "--"
            print("=" * 60)
            print(f"  CORNERS (Intl) {r['home']} vs {r['away']}  [StatsBomb]")
            print("=" * 60)
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
            print(f"\n  Base StatsBomb:")
            print(f"    {r['home']:<22} {sh['avg_corners_for']:.1f} cf / {sh['avg_corners_against']:.1f} ca")
            print(f"    {r['away']:<22} {sa['avg_corners_for']:.1f} cf / {sa['avg_corners_against']:.1f} ca")
        except ValueError as e:
            print(f"  Error: {e}")

    elif len(args) >= 1:
        for name in args:
            key = resolve(name, data)
            if not key:
                print(f"  {name!r}: sin datos")
                continue
            s = data[key]
            print(f"  {key}:")
            print(f"    xG for {s['avg_xg_for']:.2f} / xG against {s['avg_xg_against']:.2f}")
            print(f"    corners for {s['avg_corners_for']:.1f} / corners against {s['avg_corners_against']:.1f}")
            print(f"    (partidos equiv. ponderados: {s['games_weighted']:.1f})")
    else:
        print(f"  {'Seleccion':<25} {'xGf':>6} {'xGa':>6} {'Cf':>6} {'Ca':>6} {'G':>5}")
        print("  " + "-" * 55)
        for t, s in sorted(data.items(), key=lambda x: -x[1]["avg_xg_for"]):
            print(f"  {t:<25} {s['avg_xg_for']:>6.2f} {s['avg_xg_against']:>6.2f} "
                  f"{s['avg_corners_for']:>6.1f} {s['avg_corners_against']:>6.1f} "
                  f"{s['games_weighted']:>5.1f}")


if __name__ == "__main__":
    main()
