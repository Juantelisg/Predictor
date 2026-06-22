#!/usr/bin/env python
"""
scan.py — Slate scanner / pre-filtro determinístico de edge (MVP).

Para un deporte y fecha baja la cartelera (ESPN vía skill `markets`), las odds
multi-book (The Odds API, 16+ casas) y el precio de prediction market (skill
`polymarket`). De-vigga cada book con el skill `betting`, toma la MEDIANA como
fair consenso, y mide la DISCREPANCIA contra Polymarket. Donde divergen >=
umbral, el partido queda como CANDIDATO, con la mejor cuota disponible por lado.

Esto es el paso [A] del pipeline: NO produce picks. Surfacea dónde el mercado se
contradice consigo mismo y rankea por magnitud de la divergencia (puede ser edge
real o dato stale — eso lo adjudica Opus después, con model_prob + 2 señales).
La aritmética la hace `betting` (determinístico); el juicio lo pone Opus.

Uso:
    python scan.py <sport> [YYYY-MM-DD]
    python scan.py mlb
    python scan.py nba

Salida:
    - tabla rankeada por consola
    - candidates/<fecha>_<sport>.jsonl  (uno por candidato, para que Opus lo tome)
"""
import sys, os, json, datetime, statistics
import requests
from dotenv import load_dotenv
from sports_skills import markets, polymarket, betting
import cache

ROOT = os.path.dirname(os.path.abspath(__file__))
SETTINGS = json.load(open(os.path.join(ROOT, "config", "settings.json"), encoding="utf-8"))
load_dotenv(os.path.join(ROOT, "config", ".env"))

CACHE_TTL_SEC = SETTINGS["data_sources"]["cache_ttl_minutes"] * 60   # 15 min

ODDS_API_KEY = os.getenv("THE_ODDS_API_KEY", "")
ODDS_API_BASE = "https://api.the-odds-api.com"
ODDS_API_SPORT = {"mlb": "baseball_mlb", "nba": "basketball_nba", "nfl": "americanfootball_nfl"}

MODERATE_MIN = SETTINGS["edge_thresholds"]["moderate_min"]   # 0.02
STRONG_MIN   = SETTINGS["edge_thresholds"]["strong_min"]     # 0.05
KELLY_FRAC   = SETTINGS["kelly"]["fraction"]                 # 0.25
CAP_STRONG   = SETTINGS["kelly"]["max_stake_pct_strong"]     # 0.04
CAP_MODERATE = SETTINGS["kelly"]["max_stake_pct_moderate"]   # 0.02
BANKROLL     = SETTINGS["bankroll"]["amount"]                # 1000


def tier(edge):
    a = abs(edge)
    if a >= STRONG_MIN:   return "strong"
    if a >= MODERATE_MIN: return "moderate"
    return "pass"


def devig_moneyline(home_ml, away_ml):
    """ESPN american ML -> fair probs de-vigged (home, away). None si falla."""
    try:
        r = betting.devig(odds=f"{home_ml},{away_ml}", format="american")
        outs = r["data"]["outcomes"]
        return float(outs[0]["fair_prob"]), float(outs[1]["fair_prob"])
    except Exception:
        return None, None


def polymarket_prices(sport, home_name, away_name):
    """Precio Polymarket (prob 0-1) por equipo + liquidez. Matchea por nickname."""
    query = home_name.split()[-1]  # "San Antonio Spurs" -> "Spurs"
    try:
        r = polymarket.search_markets(sport=sport, query=query,
                                      sports_market_types="moneyline")
        # Polymarket devuelve varios mercados por partido (duplicados muertos con
        # liq ~$50 a 0.50, y el real con liq alta). Quedarse con el MAS LIQUIDO.
        best = None
        for m in r["data"]["markets"]:
            outs = {o["name"].lower(): float(o["price"]) for o in m.get("outcomes", [])}
            ph = next((p for n, p in outs.items() if n in home_name.lower()), None)
            pa = next((p for n, p in outs.items() if n in away_name.lower()), None)
            if ph is None or pa is None:
                continue
            liq = float(m.get("liquidity", 0) or 0)
            if best is None or liq > best[2]:
                best = (ph, pa, liq, float(m.get("spread", 0) or 0))
        if best:
            return best
    except Exception:
        pass
    return None, None, None, None


def american_to_decimal(a):
    a = float(a)
    return 1 + (a / 100.0 if a > 0 else 100.0 / abs(a))


def _parse(ts):
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def fetch_book_odds(sport):
    """The Odds API: dict frozenset({home,away}) -> [(commence, [(book_title, {team_lower: american})])].
    Lista por matchup porque una serie repite el mismo par de equipos en días distintos.
    Un solo request por scan. Devuelve {} si no hay key o el sport no está mapeado."""
    key = ODDS_API_SPORT.get(sport)
    if not key or not ODDS_API_KEY:
        return {}
    try:
        def _fetch():
            r = requests.get(f"{ODDS_API_BASE}/v4/sports/{key}/odds",
                             params={"apiKey": ODDS_API_KEY, "regions": "us,us2",
                                     "markets": "h2h", "oddsFormat": "american"}, timeout=15)
            r.raise_for_status()
            return r.json()
        raw = cache.cached(f"oddsapi:{key}:h2h", CACHE_TTL_SEC, _fetch)
        out = {}
        for g in raw:
            books = []
            for bk in g.get("bookmakers", []):
                h2h = next((m for m in bk["markets"] if m["key"] == "h2h"), None)
                if not h2h:
                    continue
                books.append((bk["title"], {o["name"].lower(): o["price"] for o in h2h["outcomes"]}))
            if books:
                k = frozenset({g["home_team"].lower(), g["away_team"].lower()})
                out.setdefault(k, []).append((g.get("commence_time"), books))
        return out
    except Exception:
        return {}


def pick_nearest(entries, start_time):
    """De las entradas de un matchup (serie multi-día), la del commence más cercano al partido."""
    st = _parse(start_time)
    if st is None:
        return entries[0][1]
    return min(entries,
              key=lambda e: abs((_parse(e[0]) - st).total_seconds()) if _parse(e[0]) else 9e9)[1]


def consensus_and_best(books, home_name, away_name):
    """De-vig de cada book -> (fair_home consenso=mediana, fair_away, best_home, best_away, n_books).
    best_* = (book_title, american, decimal) con la mejor cuota (mayor payout) por lado."""
    hn, an = home_name.lower(), away_name.lower()
    fair_hs, best_h, best_a = [], None, None
    for title, prices in books:
        ph, pa = prices.get(hn), prices.get(an)
        if ph is None or pa is None:
            continue
        fh, _ = devig_moneyline(ph, pa)
        if fh is None:
            continue
        fair_hs.append(fh)
        dh, da = american_to_decimal(ph), american_to_decimal(pa)
        if best_h is None or dh > best_h[2]:
            best_h = (title, ph, dh)
        if best_a is None or da > best_a[2]:
            best_a = (title, pa, da)
    if not fair_hs:
        return None
    fair_h = statistics.median(fair_hs)
    return fair_h, 1 - fair_h, best_h, best_a, len(fair_hs)


def scan(sport, date):
    res = markets.get_todays_markets(sport=sport, date=date)
    games = res.get("data", {}).get("games", [])
    book_odds = fetch_book_odds(sport)        # un solo request a The Odds API
    candidates, scanned, skipped = [], 0, []

    for g in games:
        name = g.get("short_name") or g.get("name")
        if g.get("status") != "not_started":
            skipped.append((name, "no pregame")); continue
        home_name, away_name = g["home"]["name"], g["away"]["name"]

        # Odds: preferir multi-book (The Odds API); si no, fallback a ESPN single-book.
        entries = book_odds.get(frozenset({home_name.lower(), away_name.lower()}))
        books = pick_nearest(entries, g.get("start_time")) if entries else None
        cb = consensus_and_best(books, home_name, away_name) if books else None
        if cb:
            fair_h, fair_a, best_h, best_a, n_books = cb
            fair_source = f"consensus_{n_books}books"
        else:
            eo = g.get("espn_odds") or {}
            ml = eo.get("moneyline") or {}
            if not ml.get("home") or not ml.get("away"):
                skipped.append((name, "sin odds (ni multi-book ni ESPN)")); continue
            fair_h, fair_a = devig_moneyline(ml["home"], ml["away"])
            if fair_h is None:
                skipped.append((name, "devig falló")); continue
            best_h = (eo.get("provider"), ml["home"], american_to_decimal(ml["home"]))
            best_a = (eo.get("provider"), ml["away"], american_to_decimal(ml["away"]))
            n_books, fair_source = 1, "espn_single"

        scanned += 1
        pm_h, pm_a, liq, spread = polymarket_prices(sport, home_name, away_name)
        if pm_h is None:
            skipped.append((name, "sin precio Polymarket (single-anchor → revisar a mano)")); continue

        # gap simétrico en un mercado 2-way de-vigged; lado favorecido = donde fair > PM
        gap_h = fair_h - pm_h
        if gap_h >= 0:
            side, fair, pm, best = home_name, fair_h, pm_h, best_h
        else:
            side, fair, pm, best = away_name, fair_a, pm_a, best_a
        edge = fair - pm                      # provisional: fair_devig - precio mercado
        if edge < MODERATE_MIN:
            continue                          # divergencia por debajo del umbral

        k = betting.kelly_criterion(fair_prob=fair, market_prob=pm)["data"]
        kelly_full = float(k["kelly_fraction"])
        cap = CAP_STRONG if tier(edge) == "strong" else CAP_MODERATE
        stake_pct = min(kelly_full * KELLY_FRAC, cap)
        line_shop_edge = round(fair - 1.0 / best[2], 4)   # ¿la mejor cuota supera el fair?

        candidates.append({
            "id": f"cand_{date}_{g['event_id']}_{side.split()[-1].lower()}_ml",
            "stage": "candidate",            # Opus lo promueve a prediction
            "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sport": sport, "match": f"{away_name} @ {home_name}",
            "event_id": g["event_id"], "kickoff_utc": g.get("start_time"),
            "bet_type": "moneyline", "selection": f"{side} ML",
            "book": best[0], "book_odds_american": best[1],   # mejor cuota del lado = dónde ejecutar
            "fair_prob_devigged": round(fair, 4), "fair_source": fair_source, "n_books": n_books,
            "market_prob": round(pm, 4), "market_source": "polymarket",
            "pm_liquidity": round(liq, 0), "pm_spread": spread,
            "model_prob": None,              # lo completa Opus
            "edge_provisional": round(edge, 4), "edge_tier": tier(edge),
            "line_shop_edge": line_shop_edge,
            "ev_per_unit": round(float(k["ev_per_dollar"]), 4),
            "kelly_full": round(kelly_full, 4),
            "stake_pct_provisional": round(stake_pct, 4),
            "stake_usd_provisional": round(stake_pct * BANKROLL, 2),
            "action": None,                  # lo decide Opus (APOSTAR/PASAR)
        })

    candidates.sort(key=lambda c: c["edge_provisional"], reverse=True)
    return candidates, scanned, skipped, len(games)


def main():
    if len(sys.argv) < 2:
        print("uso: python scan.py <sport> [YYYY-MM-DD]"); sys.exit(1)
    sport = sys.argv[1].lower()
    date = sys.argv[2] if len(sys.argv) > 2 else datetime.date.today().isoformat()

    cands, scanned, skipped, total = scan(sport, date)

    print(f"\n  SLATE SCAN -- {sport.upper()} -- {date}")
    print(f"  {total} partidos en cartelera | {scanned} con datos | {len(cands)} candidatos (edge >= {MODERATE_MIN:.0%})\n")
    if cands:
        print(f"  {'SELECCIÓN':<26}{'TIER':<10}{'EDGE':>7}{'  FAIR/PM':>13}{'  MEJOR CUOTA':>22}{'  STAKE':>9}")
        print("  " + "-" * 88)
        for c in cands:
            best = f"{c['book_odds_american']:+d}@{c['book']}" if isinstance(c['book_odds_american'], int) \
                   else f"{c['book_odds_american']}@{c['book']}"
            print(f"  {c['selection']:<26}{c['edge_tier']:<10}{c['edge_provisional']*100:>6.1f}%"
                  f"{c['fair_prob_devigged']*100:>7.0f}/{c['market_prob']*100:<4.0f}"
                  f"{best:>22}{c['stake_pct_provisional']*100:>7.1f}%")
    else:
        print("  Sin candidatos: el mercado y el book concuerdan en toda la cartelera (PASAR).")
    if skipped:
        print("\n  Saltados:")
        for n, why in skipped:
            print(f"    - {n}: {why}")

    out_dir = os.path.join(ROOT, "candidates")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{date}_{sport}.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        for c in cands:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"\n  -> {len(cands)} candidatos escritos en {os.path.relpath(out_path, ROOT)}")
    print("  -> siguiente: Opus analiza cada candidato (model_prob + 2 senales) y promueve a predictions/\n")


if __name__ == "__main__":
    main()
