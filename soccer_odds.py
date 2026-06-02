"""soccer_odds.py — cartelera de fútbol desde The Odds API (mercado 3 vías 1X2).

El fútbol no se maneja como MLB/NBA: ESPN (football-data) y The Odds API cubren ligas
distintas, y las top-5 europeas están fuera de temporada en junio. Por eso la cartelera
se arma desde las ligas de fútbol ACTIVAS en The Odds API (Brasil, Libertadores, etc.),
con consenso multi-book de-vigged a 3 resultados: local / empate / visitante.

No hay ancla de prediction market para estas ligas (Polymarket no las cubre), así que
el fútbol muestra cartelera + confianza, pero por ahora sin edge cross-source.
"""
import os, datetime, statistics, requests
from dotenv import load_dotenv
from sports_skills import betting
import cache

ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(ROOT, "config", ".env"))
KEY = os.getenv("THE_ODDS_API_KEY", "")
TTL = 15 * 60
MAX_LEAGUES = 8   # tope de ligas a consultar por carga (cuida el quota)


def american_to_decimal(a):
    a = float(a)
    return 1 + (a / 100.0 if a > 0 else 100.0 / abs(a))


def _parse(ts):
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _active_soccer_keys():
    if not KEY:
        return []
    sports = cache.cached("oddsapi:sportslist", TTL,
                          lambda: requests.get("https://api.the-odds-api.com/v4/sports",
                                               params={"apiKey": KEY}, timeout=15).json())
    return [s["key"] for s in sports if s["key"].startswith("soccer_") and s.get("active")]


def _league_odds(league_key):
    def _f():
        r = requests.get(f"https://api.the-odds-api.com/v4/sports/{league_key}/odds",
                         params={"apiKey": KEY, "regions": "us,uk,eu",
                                 "markets": "h2h", "oddsFormat": "american"}, timeout=15)
        r.raise_for_status()
        return r.json()
    try:
        return cache.cached(f"oddsapi:{league_key}:h2h", TTL, _f)
    except Exception:
        return []


def _consensus_3way(books, home_l, away_l):
    """Mediana de-vigged de local/empate/visita + mejor cuota por resultado."""
    fh, fd, fa = [], [], []
    best = {}
    for title, prices in books:
        ph, pa, pd = prices.get(home_l), prices.get(away_l), prices.get("draw")
        if None in (ph, pa, pd):
            continue
        try:
            o = betting.devig(odds=f"{ph},{pd},{pa}", format="american")["data"]["outcomes"]
        except Exception:
            continue
        fh.append(float(o[0]["fair_prob"])); fd.append(float(o[1]["fair_prob"])); fa.append(float(o[2]["fair_prob"]))
        for nm, pr in (("home", ph), ("draw", pd), ("away", pa)):
            dec = american_to_decimal(pr)
            if nm not in best or dec > best[nm][1]:
                best[nm] = (title, dec, pr)
    if not fh:
        return None
    return statistics.median(fh), statistics.median(fd), statistics.median(fa), best, len(fh)


def fetch_soccer_slate(date):
    """Partidos de fútbol del día (UTC) con confianza 3 vías y mejor cuota por resultado."""
    now = datetime.datetime.now(datetime.timezone.utc)
    out = []
    for k in _active_soccer_keys()[:MAX_LEAGUES]:
        league = k.replace("soccer_", "").replace("_", " ").title()
        for g in _league_odds(k):
            dt = _parse(g.get("commence_time"))
            if date and (not dt or dt.date().isoformat() != date):
                continue
            home, away = g["home_team"], g["away_team"]
            books = []
            for bk in g.get("bookmakers", []):
                h2h = next((m for m in bk["markets"] if m["key"] == "h2h"), None)
                if h2h:
                    books.append((bk["title"], {o["name"].lower(): o["price"] for o in h2h["outcomes"]}))
            cb = _consensus_3way(books, home.lower(), away.lower())
            rec = {
                "event_id": g.get("id"), "league": league,
                "home": home, "away": away,
                "home_abbr": home[:3].upper(), "away_abbr": away[:3].upper(),
                "start_time": g.get("commence_time"),
                "status": "not_started" if (dt and dt > now) else "live",
                "fair_home": None, "fair_draw": None, "fair_away": None,
                "odds_home": None, "odds_draw": None, "odds_away": None,
                "odds_home_book": None, "n_books": 0,
            }
            if cb and rec["status"] == "not_started":
                fh, fd, fa, best, nb = cb
                rec.update({
                    "fair_home": round(fh, 3), "fair_draw": round(fd, 3), "fair_away": round(fa, 3),
                    "odds_home": best.get("home", [None, None, None])[2],
                    "odds_draw": best.get("draw", [None, None, None])[2],
                    "odds_away": best.get("away", [None, None, None])[2],
                    "odds_home_book": best.get("home", [None])[0], "n_books": nb,
                })
            out.append(rec)
    return out


if __name__ == "__main__":
    import sys
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    games = fetch_soccer_slate(date)
    print(f"\n  FÚTBOL -- {date} -- {len(games)} partidos\n")
    for g in games:
        conf = ""
        if g["fair_home"] is not None:
            conf = f"L{int(g['fair_home']*100)}% / X{int(g['fair_draw']*100)}% / V{int(g['fair_away']*100)}%"
        print(f"  [{g['league']:<22}] {g['away']} @ {g['home']:<24} {g['status']:<12} {conf}")
    print()
