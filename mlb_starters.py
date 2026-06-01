"""mlb_starters.py — abridores probables + ERA vía MLB Stats API (oficial, sin key).

La skill `mlb-data` no expone probables; en baseball el abridor es el factor de
mayor peso en la línea. Este módulo cubre ese gap (#3 del MVP).

Uso como módulo:
    from mlb_starters import probable_pitchers
    probable_pitchers("2026-06-01")  # -> { "Away @ Home": {"home": (name, era), "away": (name, era)} }

Uso CLI:
    python mlb_starters.py 2026-06-01
"""
import sys, requests

STATS_BASE = "https://statsapi.mlb.com/api/v1"


def _era(pid):
    """ERA de temporada de un pitcher por id. None si no hay dato."""
    if not pid:
        return None
    try:
        r = requests.get(f"{STATS_BASE}/people/{pid}",
                         params={"hydrate": "stats(group=[pitching],type=[season])"}, timeout=10)
        stats = r.json()["people"][0].get("stats", [])
        splits = stats[0].get("splits", []) if stats else []
        return splits[0]["stat"].get("era") if splits else None
    except Exception:
        return None


def probable_pitchers(date):
    """Abridores probables + ERA por partido de la fecha (YYYY-MM-DD)."""
    r = requests.get(f"{STATS_BASE}/schedule",
                     params={"sportId": 1, "date": date, "hydrate": "probablePitcher"}, timeout=15)
    r.raise_for_status()
    dates = r.json().get("dates", [])
    games = dates[0].get("games", []) if dates else []
    out = {}
    for g in games:
        h, a = g["teams"]["home"], g["teams"]["away"]
        hp, ap = h.get("probablePitcher", {}), a.get("probablePitcher", {})
        out[f"{a['team']['name']} @ {h['team']['name']}"] = {
            "home": (hp.get("fullName"), _era(hp.get("id"))),
            "away": (ap.get("fullName"), _era(ap.get("id"))),
        }
    return out


if __name__ == "__main__":
    date = sys.argv[1] if len(sys.argv) > 1 else __import__("datetime").date.today().isoformat()
    pp = probable_pitchers(date)
    print(f"\n  ABRIDORES PROBABLES -- MLB -- {date}\n")
    for match, sp in pp.items():
        hn, he = sp["home"]; an, ae = sp["away"]
        print(f"  {match}")
        print(f"      visitante: {an or '?':<22} ERA {ae or '-'}")
        print(f"      local:     {hn or '?':<22} ERA {he or '-'}")
    print()
