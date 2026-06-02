"""prop_value.py - capa de veredicto EV+ sobre props de jugador.

Orden del pipeline (runtime): GAMELOG -> CUOTA -> VEREDICTO.
  1. player_props.top_picks(): lee el gamelog, saca hit-rate + splits (estilo Linemate).
  2. The Odds API: trae la cuota real del prop (events/{id}/odds).
  3. Veredicto: de-vigea la cuota (prob. implicita), regresa el hit-rate a la media
     (shrink hacia la tasa de temporada), compara -> edge -> APOSTAR / PASAR.

La capa de veredicto (devig/shrink/edge) es sport-agnostica; lo unico MLB-especifico
es MARKET_MAP (mis etiquetas <-> market keys de The Odds API). Para sumar NBA manana
basta otro MARKET_MAP + un candidate-gen de basquet; el resto se reusa tal cual.

Uso:
    python prop_value.py [YYYY-MM-DD] ["Away Team"] ["Home Team"]
"""
import os, sys, json, datetime, statistics, unicodedata
from concurrent.futures import ThreadPoolExecutor
import requests
from dotenv import load_dotenv
from sports_skills import betting
import player_props as pp
import backtest_props as bt
import availability
import cache

ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(ROOT, "config", ".env"))
ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY", "")
ODDS_BASE = "https://api.the-odds-api.com/v4"

# regresion a la media POBLACIONAL (Beta-Binomial): la tasa del jugador para el prop
# se regresa hacia la media de la liga con fuerza POP_K. Calibrado por backtest_props.py
# (sweep walk-forward, temporada): K=30 -> Brier 0.1856, sobre-confianza zona>=70% +0.2pts
# (vs +12.6 del modelo naive L10->temporada). El meta-agente puede re-tunear con evaluations/.
POP_K = 30
MODERATE_MIN = 0.02     # edge >= 2% -> value moderado
STRONG_MIN = 0.05       # edge >= 5% -> value fuerte

# limpieza del pool: el rate de un part-time no es confiable para reclamar edge.
MIN_AB_L10 = 2.8        # piso de ABs/juego (L10): debajo = rol part-time -> excluir
MIN_GAMES = 15          # muestra minima de temporada para confiar en el rate
MIN_BOOKS = 2           # casas minimas que ofrecen el prop (liquidez): 1 sola = linea soft no confiable
MAX_EDGE = 0.15         # edge > 15% en props liquidos no es value, es bug (linea mala/match malo) -> descartar

# mis etiquetas de player_props.PROPS  <->  market keys de The Odds API (MLB)
MARKET_MAP = {
    "Hits": "batter_hits",
    "Bases totales": "batter_total_bases",
    "Home Run": "batter_home_runs",
    "Impulsadas": "batter_rbis",
    "Carreras": "batter_runs_scored",
    "Singles": "batter_singles",
    "Dobles": "batter_doubles",
    "Bases robadas": "batter_stolen_bases",
    "Ponches": "batter_strikeouts",
    "H+R+RBI": "batter_hits_runs_rbis",
}
_INV_MARKET = {v: k for k, v in MARKET_MAP.items()}
SPORT_KEY = {"mlb": "baseball_mlb"}


def _norm(s):
    """Normaliza nombre para matchear (Yandy Diaz == Yandy Diaz, sin acentos/puntuacion)."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return "".join(c for c in s.lower() if c.isalnum() or c == " ").strip()


def find_event(sport_key, away_name, home_name):
    """Resuelve el event_id de The Odds API por nombres de equipo. Endpoint /events NO gasta quota."""
    r = requests.get(f"{ODDS_BASE}/sports/{sport_key}/events", params={"apiKey": ODDS_API_KEY}, timeout=20).json()
    if not isinstance(r, list):
        return None
    a, h = _norm(away_name), _norm(home_name)
    for e in r:
        if _norm(e["away_team"]) == a and _norm(e["home_team"]) == h:
            return e["id"]
    return None


def fetch_props(sport_key, event_id, labels, region="us"):
    """Cuotas de props. -> ({(player_norm, label, line): {'Over': price, 'Under': price}}, quota_remaining).

    Consenso multi-book: mediana del precio por lado (mismo criterio que scan.py para moneyline).
    Solo pide los markets de los que hay candidatos (cuida quota)."""
    keys = sorted({MARKET_MAP[l] for l in labels if l in MARKET_MAP})
    if not keys:
        return {}, None
    r = requests.get(f"{ODDS_BASE}/sports/{sport_key}/events/{event_id}/odds",
                     params={"apiKey": ODDS_API_KEY, "regions": region,
                             "markets": ",".join(keys), "oddsFormat": "american"}, timeout=25)
    rem = r.headers.get("x-requests-remaining")
    d = r.json()
    if not isinstance(d, dict):
        return {}, rem
    acc = {}
    for b in d.get("bookmakers", []):
        for m in b.get("markets", []):
            label = _INV_MARKET.get(m["key"])
            if not label:
                continue
            for o in m.get("outcomes", []):
                key = (_norm(o.get("description", "")), label, o.get("point"))
                acc.setdefault(key, {}).setdefault(o["name"], []).append(o["price"])
    out = {}
    for k, sides in acc.items():
        rec = {side: statistics.median(px) for side, px in sides.items()}
        rec["_n"] = min(len(px) for px in sides.values())   # casas que ofrecen AMBOS lados
        out[k] = rec
    return out, rem


def _baselines(date, season):
    """Media de la liga por (label, line) -> blanco de la regresion poblacional. Cacheada 24h
    (constantes estables; claves serializadas 'label|line' porque cache.py usa JSON)."""
    def _f():
        pids = bt._player_set(date)
        with ThreadPoolExecutor(max_workers=10) as ex:
            logs = [l for l in ex.map(lambda pid: pp.gamelog(pid, season), pids) if len(l) > bt.MIN_PRIOR]
        return {f"{lab}|{ln}": v for (lab, ln), v in bt.population_baseline(logs).items()}
    raw = cache.cached(f"propbase:{season}", 24 * 3600, _f)
    return {(p.rsplit("|", 1)[0], float(p.rsplit("|", 1)[1])): v for p, v in raw.items()}


def _model_prob(rows, label, line, side, mu):
    """P(side) calibrada: tasa del jugador (muestra previa en `rows`) regresada a la media mu (K=POP_K)."""
    overs = sum(1 for r in rows if pp._value(r, label) > line)
    p_over = (overs + POP_K * mu) / (len(rows) + POP_K)
    return (p_over if side == "Over" else 1 - p_over), overs / len(rows)


def _confirmed_starters(date, away_name, home_name):
    """Nombres normalizados del lineup confirmado del partido, o None si aun no esta publicado."""
    g = availability.mlb_lineups(date).get(f"{away_name} @ {home_name}")
    if not g:
        return None
    return {_norm(n) for n in (g.get("home", []) + g.get("away", [])) if n}


def verdict_for_game(date, away_name, home_name, sport="mlb", min_rate=0.7, last_n=10):
    sport_key = SPORT_KEY[sport]
    season = pp._season(date)
    cands = pp.top_picks(date, away_name, home_name, min_rate=min_rate, last_n=last_n)
    if not cands:
        return {"error": "sin candidatos (top_picks vacio)", "results": []}
    event_id = find_event(sport_key, away_name, home_name)
    if not event_id:
        return {"error": "no se encontro el partido en The Odds API", "results": []}
    props, rem = fetch_props(sport_key, event_id, {c["label"] for c in cands})
    baselines = _baselines(date, season)
    starters = _confirmed_starters(date, away_name, home_name)   # None si el lineup no esta publicado
    drop = {"no_lineup": set(), "part_time": set(), "sin_cuota": 0, "odds_rara": 0}

    results = []
    for c in cands:
        # --- filtro de titulares + limpieza del pool (3 senales) ---
        if starters is not None and _norm(c["player"]) not in starters:
            drop["no_lineup"].add(c["player"]); continue
        rows = [r for r in pp.gamelog(c["player_id"], season) if not r["date"] or r["date"] < date]
        avg_ab = sum(r["AB"] for r in rows[-last_n:]) / len(rows[-last_n:]) if rows else 0
        if len(rows) < MIN_GAMES or avg_ab < MIN_AB_L10:
            drop["part_time"].add(c["player"]); continue
        prices = props.get((_norm(c["player"]), c["label"], c["line"]))
        if not prices or "Over" not in prices or "Under" not in prices:
            drop["sin_cuota"] += 1; continue
        if prices["_n"] < MIN_BOOKS:     # linea de un solo book soft -> no confiable (liquidez)
            drop["odds_rara"] += 1; continue
        # --- veredicto ---
        dv = betting.devig(odds=f"{prices['Over']},{prices['Under']}", format="american")
        fair = dv["data"]["outcomes"][0 if c["side"] == "Over" else 1]["fair_prob"]
        if not (0.02 < fair < 0.98):     # backstop: devig degenerado -> no confiable
            drop["odds_rara"] += 1; continue
        mu = baselines.get((c["label"], c["line"]), c["hit"] / c["n"])
        model, over_rate = _model_prob(rows, c["label"], c["line"], c["side"], mu)
        edge = model - fair
        if abs(edge) > MAX_EDGE:         # edge absurdo (cualquier lado) -> data mala, no value real
            drop["odds_rara"] += 1; continue
        tier = "strong" if edge >= STRONG_MIN else "moderate" if edge >= MODERATE_MIN else "pass"
        season_side = over_rate if c["side"] == "Over" else 1 - over_rate
        results.append({**c, "price": prices[c["side"]], "fair": round(fair, 3),
                        "l10": round(c["hit"] / c["n"], 3), "season_rate": round(season_side, 3),
                        "season_n": len(rows), "avg_ab": round(avg_ab, 1),
                        "model": round(model, 3), "edge": round(edge, 3), "tier": tier,
                        "verdict": "APOSTAR" if tier != "pass" else "PASAR"})
    results.sort(key=lambda r: r["edge"], reverse=True)
    return {"event_id": event_id, "quota_remaining": rem, "lineup_confirmed": starters is not None,
            "dropped": {"no_lineup": len(drop["no_lineup"]), "part_time": len(drop["part_time"]),
                        "sin_cuota": drop["sin_cuota"], "odds_rara": drop["odds_rara"]}, "results": results}


def _fmt_price(p):
    p = int(p) if float(p).is_integer() else p
    return f"+{p}" if (isinstance(p, int) and p > 0) or (isinstance(p, float) and p > 0) else str(p)


if __name__ == "__main__":
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    away = sys.argv[2] if len(sys.argv) > 2 else "Detroit Tigers"
    home = sys.argv[3] if len(sys.argv) > 3 else "Tampa Bay Rays"
    out = verdict_for_game(date, away, home)
    print(f"\n  VEREDICTO PROPS -- {away} @ {home} -- {date}")
    if out.get("error"):
        print(f"  ERROR: {out['error']}\n")
        sys.exit(0)
    d = out["dropped"]
    lc = "publicado" if out["lineup_confirmed"] else "no publicado aun (filtro = props del book + ABs)"
    print(f"  quota The Odds API restante: {out['quota_remaining']}")
    print(f"  lineup confirmado: {lc}")
    print(f"  pool limpiado: -{d['no_lineup']} fuera del lineup | -{d['part_time']} part-time/muestra | "
          f"-{d['sin_cuota']} props sin cuota | -{d['odds_rara']} cuota degenerada\n")
    print(f"  {'JUGADOR':<20} {'PROP':<22} {'L10':>5} {'TEMP':>6} {'MODELO':>7} {'MERCADO':>8} {'EDGE':>7}  VEREDICTO")
    print("  " + "-" * 96)
    for r in out["results"]:
        sr = f"{int(r['season_rate']*100)}%" if r["season_rate"] is not None else "-"
        flag = {"strong": "** APOSTAR", "moderate": "*  APOSTAR", "pass": "   PASAR"}[r["tier"]]
        print(f"  {r['player'][:19]:<20} {r['prop'][:21]:<22} {int(r['l10']*100):>4}% {sr:>6} "
              f"{int(r['model']*100):>6}% {int(r['fair']*100):>7}% {r['edge']*100:>+6.1f}%  {flag}")
    print("\n  ** value fuerte (edge>=5%) | * value moderado (2-5%) | modelo: regresion poblacional Beta-Bin K=30")
    print("  pool: solo titulares con muestra confiable (lineup confirmado / props del book / ABs)")
    print("  *Educativo. Apostar implica riesgo de perdida total.*\n")
