"""slate.py - arma los partidos de HOY desde fuentes GRATIS (tier workhorse). Cero quota escasa.

Es el paso (1) del flujo de quota: lo barato/ilimitado identifica que se juega hoy y saca todo
lo que pueda. Las APIs escasas (API-Football) se reservan para despues, puntual y targeted.

Fuentes: MLB Stats API (MLB), CSV internacional (selecciones), ESPN (NBA/NFL/otros). Todas
gratis y sin key. Cacheadas con la politica de cache.py.

Correr:  C:/Users/Juant/AppData/Local/Python/bin/python.exe predictor/slate.py [YYYY-MM-DD]
"""
import sys, io, datetime
import requests
import pandas as pd
import cache

sys.stdout.reconfigure(encoding="utf-8")
MLB_B = "https://statsapi.mlb.com/api/v1"
INTL_CSV = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
ESPN = "https://site.api.espn.com/apis/site/v2/sports"


def mlb_today(date):
    r = cache.cached(f"slate_mlb:{date}", cache.TTL_SLATE, lambda: requests.get(
        f"{MLB_B}/schedule", params={"sportId": 1, "date": date, "hydrate": "probablePitcher"}, timeout=20).json())
    out = []
    for d in r.get("dates", []):
        for g in d.get("games", []):
            h, a = g["teams"]["home"], g["teams"]["away"]
            ap = (a.get("probablePitcher") or {}).get("fullName", "?")
            hp = (h.get("probablePitcher") or {}).get("fullName", "?")
            out.append({"away": a["team"]["name"], "home": h["team"]["name"],
                        "time": g.get("gameDate", "")[11:16], "extra": f"SP {ap} vs {hp}"})
    return out


def soccer_today(date):
    txt = cache.cached("intl_results", cache.TTL_RESULTS, lambda: requests.get(INTL_CSV, timeout=30).text)
    df = pd.read_csv(io.StringIO(txt))
    t = df[df.date == date]
    return [{"away": r.away_team, "home": r.home_team, "time": "",
             "extra": r.tournament + (" (neutral)" if bool(r.neutral) else "")} for r in t.itertuples()]


def espn_today(sport, league, date):
    try:
        r = cache.cached(f"slate_espn:{league}:{date}", cache.TTL_SLATE, lambda: requests.get(
            f"{ESPN}/{sport}/{league}/scoreboard", params={"dates": date.replace("-", "")}, timeout=20).json())
    except Exception:
        return []
    out = []
    for ev in r.get("events", []):
        c = (ev.get("competitions", [{}])[0]).get("competitors", [])
        nm = {x.get("homeAway"): x.get("team", {}).get("displayName") for x in c}
        out.append({"away": nm.get("away", "?"), "home": nm.get("home", "?"), "time": ev.get("date", "")[11:16],
                    "extra": ev.get("status", {}).get("type", {}).get("shortDetail", "")})
    return out


def slate(date=None):
    date = date or datetime.date.today().isoformat()
    return {
        "MLB": mlb_today(date),
        "Soccer (selecciones)": soccer_today(date),
        "NBA": espn_today("basketball", "nba", date),
        "NFL": espn_today("football", "nfl", date),
    }


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    s = slate(date)
    print(f"  SLATE {date}  (fuentes gratis - tier workhorse, cero quota escasa)\n")
    for sport, games in s.items():
        print(f"  {sport}: {len(games)} partidos")
        for g in games[:12]:
            print(f"    {g['time']:>5}  {g['away']} @ {g['home']}   {g['extra']}")
        if len(games) > 12:
            print(f"    ... +{len(games) - 12} mas")
        print()
    try:
        import budget
        b = budget.status()
        if b.get("remaining") is not None:
            print(f"  Presupuesto API-Football (escaso): {b['remaining']}/{b['limit']} restantes hoy "
                  f"-> reservar para lineups/corners/player-props del momento clave.")
    except Exception as e:
        print(f"  (budget no disponible: {e})")


if __name__ == "__main__":
    main()
