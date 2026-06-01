"""availability.py — disponibilidad de jugadores por deporte (input clave para Opus).

Antes de asignar model_prob, Opus necesita saber QUIÉN juega. Cada deporte tiene su forma
y su fuente; este módulo unifica el acceso con `for_game(sport, ...)`:

  - MLB    : abridores probables (+ ERA) y lineup de bateo  -> MLB Stats API (statsapi)
  - NBA    : lesionados / disponibilidad de los dos equipos -> skill nba-data get_injuries
  - Soccer : XI inicial + banco por equipo                  -> skill football-data get_event_lineups
  - NFL    : sin skill instalada (+ fuera de temporada jun) -> pendiente

`mlb_starters.py` es el helper MLB que este módulo reutiliza. XI de fútbol y lineup de
MLB se publican cerca del kickoff (~1-2h antes); si no están, se devuelve vacío (honesto).

Uso:
    from availability import for_game
    for_game("mlb",    date="2026-06-01")
    for_game("nba",    home="San Antonio Spurs", away="New York Knicks")
    for_game("soccer", event_id="401869442")

CLI (prueba):
    python availability.py nba  "San Antonio Spurs" "New York Knicks"
    python availability.py soccer 401869442
    python availability.py mlb 2026-06-01
"""
import sys, requests
from sports_skills import nba, football
from mlb_starters import probable_pitchers, STATS_BASE

SOCCER = {"soccer", "epl", "laliga", "seriea", "bundesliga", "ligue1", "ucl", "mls",
          "international-friendly"}


def mlb_lineups(date):
    """Lineup de bateo (orden) por partido, si ya está publicado. {} si no."""
    try:
        r = requests.get(f"{STATS_BASE}/schedule",
                         params={"sportId": 1, "date": date, "hydrate": "lineups,team"}, timeout=15)
        dates = r.json().get("dates", [])
        games = dates[0].get("games", []) if dates else []
        out = {}
        for g in games:
            lu = g.get("lineups", {}) or {}
            home = [p.get("fullName") for p in lu.get("homePlayers", [])]
            away = [p.get("fullName") for p in lu.get("awayPlayers", [])]
            if home or away:
                key = f"{g['teams']['away']['team']['name']} @ {g['teams']['home']['team']['name']}"
                out[key] = {"home": home, "away": away}
        return out
    except Exception:
        return {}


def nba_injuries(home_name, away_name):
    """Lesionados/disponibilidad de los dos equipos. {team: [{name, status, detail}]}."""
    try:
        teams = nba.get_injuries()["data"]["teams"]
    except Exception:
        return {}
    want = {home_name, away_name}
    nick = {home_name.split()[-1], away_name.split()[-1]}
    out = {}
    for t in teams:
        nm = t.get("team", {}).get("name") if isinstance(t.get("team"), dict) else t.get("team")
        if not nm:
            continue
        if nm in want or any(x in nm for x in nick):
            inj = t.get("injuries") or t.get("players") or []
            out[nm] = [{"name": i.get("name"), "status": i.get("status"), "detail": i.get("detail")}
                       for i in inj]
    return out


def soccer_lineups(event_id):
    """XI inicial + banco por equipo. {} si no está publicado (se publica ~1h antes)."""
    try:
        lus = football.get_event_lineups(event_id=event_id)["data"]["lineups"]
    except Exception:
        return {}
    out = {}
    for l in lus:
        nm = l.get("team", {}).get("name", "?")
        out[nm] = {"formation": l.get("formation", ""),
                   "starting": [p.get("name") for p in l.get("starting", [])],
                   "bench": [p.get("name") for p in l.get("bench", [])]}
    return out


def for_game(sport, home=None, away=None, event_id=None, date=None):
    """Dispatcher: devuelve la disponibilidad relevante según el deporte."""
    s = sport.lower()
    if s == "mlb":
        return {"type": "mlb",
                "starters": probable_pitchers(date) if date else {},
                "lineups": mlb_lineups(date) if date else {}}
    if s == "nba":
        return {"type": "nba", "injuries": nba_injuries(home, away) if home and away else {}}
    if s in SOCCER:
        return {"type": "soccer", "lineups": soccer_lineups(event_id) if event_id else {}}
    if s == "nfl":
        return {"type": "nfl", "note": "skill nfl-data no instalada; fuera de temporada en junio"}
    return {"type": s, "note": "sin fuente de disponibilidad para este deporte"}


if __name__ == "__main__":
    sport = sys.argv[1].lower() if len(sys.argv) > 1 else "mlb"
    print(f"\n  DISPONIBILIDAD -- {sport.upper()}\n")
    if sport == "nba":
        av = for_game("nba", home=sys.argv[2], away=sys.argv[3])
        for team, inj in av["injuries"].items():
            print(f"  {team}: {len(inj)} en reporte")
            for i in inj:
                print(f"      - {i['name']:<22} {i['status']:<14} {i['detail']}")
    elif sport in SOCCER:
        av = for_game("soccer", event_id=sys.argv[2])
        for team, lu in av["lineups"].items():
            print(f"  {team} ({lu['formation'] or 's/formación'}): {len(lu['starting'])} titulares")
            print(f"      XI: {', '.join(lu['starting'][:11])}")
    else:
        date = sys.argv[2] if len(sys.argv) > 2 else __import__("datetime").date.today().isoformat()
        av = for_game("mlb", date=date)
        for match, sp in av["starters"].items():
            lu = av["lineups"].get(match)
            print(f"  {match}")
            print(f"      SP: {sp['away'][0]} (ERA {sp['away'][1]}) @ {sp['home'][0]} (ERA {sp['home'][1]})")
            print(f"      lineup publicado: {'sí' if lu else 'no (se publica ~1-2h antes)'}")
    print()
