"""totals.py — line-shopping de totals (over/under) vía The Odds API.

Los prediction markets NO tienen totals de MLB, así que acá NO hay ancla cross-source
como en scan.py. Surfacea: total de consenso (mediana de líneas), P(over) fair de
consenso, mejor precio over/under por casa, y books cuya LÍNEA difiere del consenso
(comprar el mejor número). Cada juego queda como "needs_model": Opus pone el model_prob
del total (proyección de carreras) para decidir APOSTAR/PASAR.

Uso: python totals.py mlb [YYYY-MM-DD]
"""
import sys, os, json, datetime, statistics, requests
from dotenv import load_dotenv
from sports_skills import markets, betting
import cache

ROOT = os.path.dirname(os.path.abspath(__file__))
SETTINGS = json.load(open(os.path.join(ROOT, "config", "settings.json"), encoding="utf-8"))
load_dotenv(os.path.join(ROOT, "config", ".env"))
TTL = SETTINGS["data_sources"]["cache_ttl_minutes"] * 60
KEY = os.getenv("THE_ODDS_API_KEY", "")
SPORT = {"mlb": "baseball_mlb", "nba": "basketball_nba", "nfl": "americanfootball_nfl"}


def _parse(ts):
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def american_to_decimal(a):
    a = float(a)
    return 1 + (a / 100.0 if a > 0 else 100.0 / abs(a))


def fetch_totals(sport):
    """frozenset({home,away}) -> [(commence, [(book, ov_pt, ov_price, un_pt, un_price)])]."""
    k = SPORT.get(sport)
    if not k or not KEY:
        return {}
    def _f():
        r = requests.get(f"https://api.the-odds-api.com/v4/sports/{k}/odds",
                         params={"apiKey": KEY, "regions": "us,us2",
                                 "markets": "totals", "oddsFormat": "american"}, timeout=15)
        r.raise_for_status()
        return r.json()
    raw = cache.cached(f"oddsapi:{k}:totals", TTL, _f)
    out = {}
    for g in raw:
        rows = []
        for bk in g.get("bookmakers", []):
            t = next((m for m in bk["markets"] if m["key"] == "totals"), None)
            if not t:
                continue
            d = {o["name"]: o for o in t["outcomes"]}
            if "Over" in d and "Under" in d:
                rows.append((bk["title"], d["Over"].get("point"), d["Over"]["price"],
                             d["Under"].get("point"), d["Under"]["price"]))
        if rows:
            key = frozenset({g["home_team"].lower(), g["away_team"].lower()})
            out.setdefault(key, []).append((g.get("commence_time"), rows))
    return out


def nearest(entries, start_time):
    st = _parse(start_time)
    if st is None:
        return entries[0][1]
    return min(entries,
              key=lambda e: abs((_parse(e[0]) - st).total_seconds()) if _parse(e[0]) else 9e9)[1]


def analyze(rows):
    pts = [r[1] for r in rows if r[1] is not None]
    consensus = statistics.median(pts) if pts else None
    fairs = []
    for _, _op, opr, _up, upr in rows:
        try:
            fairs.append(betting.devig(odds=f"{opr},{upr}", format="american")["data"]["outcomes"][0]["fair_prob"])
        except Exception:
            pass
    fair_over = round(statistics.median(fairs), 3) if fairs else None
    best_over = max(rows, key=lambda r: american_to_decimal(r[2]))
    best_under = max(rows, key=lambda r: american_to_decimal(r[4]))
    off_line = sorted({r[1] for r in rows if r[1] is not None and r[1] != consensus})
    return consensus, fair_over, best_over, best_under, off_line, len(rows)


def main():
    sport = sys.argv[1].lower() if len(sys.argv) > 1 else "mlb"
    date = sys.argv[2] if len(sys.argv) > 2 else datetime.date.today().isoformat()

    games = markets.get_todays_markets(sport=sport, date=date).get("data", {}).get("games", [])
    book_totals = fetch_totals(sport)

    print(f"\n  TOTALS LINE-SHOP -- {sport.upper()} -- {date}")
    print(f"  (sin ancla de prediction market; needs_model = Opus proyecta el total)\n")
    print(f"  {'PARTIDO':<14}{'CONS':>6}{'P(over)':>9}{'  MEJOR OVER':>20}{'  MEJOR UNDER':>21}{'  LIN.DIF':>10}")
    print("  " + "-" * 84)
    for g in games:
        if g.get("status") != "not_started":
            continue
        hn, an = g["home"]["name"], g["away"]["name"]
        entries = book_totals.get(frozenset({hn.lower(), an.lower()}))
        if not entries:
            continue
        rows = nearest(entries, g.get("start_time"))
        cons, fov, bo, bu, off, nb = analyze(rows)
        bo_s = f"{bo[1]}@{bo[2]:+d}@{bo[0][:9]}"
        bu_s = f"{bu[3]}@{bu[4]:+d}@{bu[0][:9]}"
        off_s = ",".join(str(x) for x in off) if off else "-"
        print(f"  {g['short_name']:<14}{cons:>6}{(fov or 0):>9.3f}{bo_s:>20}{bu_s:>21}{off_s:>10}")
    print("\n  LIN.DIF = books cuyo total difiere del consenso (comprar el mejor numero).\n")


if __name__ == "__main__":
    main()
