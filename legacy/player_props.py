"""player_props.py — motor de trends de jugadores MLB (estilo Linemate).

Para cada bateador baja su game log (MLB Stats API) y calcula hit-rates de props
(hits, bases totales, R, RBI, HR, H+R+RBI, singles, dobles, SB, ponches) sobre los
últimos N partidos. Soporta:
  - feed cross-game (trends de todos los partidos del día),
  - filtro por mercado,
  - splits del gamelog: Last 10 / Head to Head (vs rival) / Local / Visitante.

Sin cuotas todavía (el hit-rate es el core); el "valor real vs trampa" se suma luego.
"""
import sys, datetime, requests
from concurrent.futures import ThreadPoolExecutor
import cache

B = "https://statsapi.mlb.com/api/v1"
GL_TTL = 3 * 3600
TRENDS_PLAYER_CAP = 110   # tope de jugadores por carga del feed (cuida tiempo/llamadas)

# (etiqueta de mercado, línea, lados permitidos). "over" para eventos raros (under trivial).
PROPS = [
    ("Hits", 0.5, "both"), ("Hits", 1.5, "both"),
    ("Bases totales", 1.5, "both"),
    ("Carreras", 0.5, "over"), ("Impulsadas", 0.5, "over"),
    ("Home Run", 0.5, "over"), ("H+R+RBI", 1.5, "both"),
    ("Singles", 0.5, "over"), ("Dobles", 0.5, "over"),
    ("Bases robadas", 0.5, "over"), ("Ponches", 0.5, "both"),
]


def _season(date):
    return int(date[:4]) if date else datetime.date.today().year


def _value(row, label):
    if label == "H+R+RBI":
        return row["H"] + row["R"] + row["RBI"]
    if label == "Singles":
        return max(row["H"] - row["2B"] - row["3B"] - row["HR"], 0)
    g = row.get
    return {"Hits": g("H", 0), "Bases totales": g("TB", 0), "Carreras": g("R", 0), "Impulsadas": g("RBI", 0),
            "Home Run": g("HR", 0), "Dobles": g("2B", 0), "Bases robadas": g("SB", 0), "Ponches": g("K", 0)}.get(label, 0)


def _roster_batters(team_id, team_name, opp_name):
    try:
        r = requests.get(f"{B}/teams/{team_id}/roster", params={"rosterType": "active"}, timeout=15).json()
        return [(p["person"]["id"], p["person"]["fullName"], team_name, opp_name)
                for p in r.get("roster", []) if p.get("position", {}).get("type") != "Pitcher"]
    except Exception:
        return []


def _schedule(date):
    return (requests.get(f"{B}/schedule",
            params={"sportId": 1, "date": date, "hydrate": "lineups,team"}, timeout=15)
            .json().get("dates", [{}]) or [{}])[0].get("games", [])


def _batters_for_game(g):
    a, h = g["teams"]["away"], g["teams"]["home"]
    lu = g.get("lineups", {}) or {}
    out = [(p["id"], p.get("fullName"), a["team"]["name"], h["team"]["name"]) for p in lu.get("awayPlayers", [])]
    out += [(p["id"], p.get("fullName"), h["team"]["name"], a["team"]["name"]) for p in lu.get("homePlayers", [])]
    if out:
        return out
    return (_roster_batters(a["team"]["id"], a["team"]["name"], h["team"]["name"]) +
            _roster_batters(h["team"]["id"], h["team"]["name"], a["team"]["name"]))


def game_batters(date, away_name, home_name):
    for g in _schedule(date):
        if g["teams"]["home"]["team"]["name"] == home_name and g["teams"]["away"]["team"]["name"] == away_name:
            return _batters_for_game(g)
    return []


def gamelog(player_id, season):
    """Game log de bateo (viejo->nuevo). Cacheado 3h."""
    def _f():
        gl = requests.get(f"{B}/people/{player_id}/stats",
                          params={"stats": "gameLog", "group": "hitting", "season": season}, timeout=15).json()
        sp = gl["stats"][0]["splits"] if gl.get("stats") and gl["stats"][0].get("splits") else []
        rows = []
        for s in sp:
            st = s["stat"]
            rows.append({
                "date": s.get("date"), "opp": (s.get("opponent") or {}).get("name", ""), "home": bool(s.get("isHome")),
                "H": st.get("hits", 0), "2B": st.get("doubles", 0), "3B": st.get("triples", 0),
                "HR": st.get("homeRuns", 0), "TB": st.get("totalBases", 0), "R": st.get("runs", 0),
                "RBI": st.get("rbi", 0), "SB": st.get("stolenBases", 0), "K": st.get("strikeOuts", 0), "AB": st.get("atBats", 0),
            })
        return rows
    return cache.cached(f"mlbgl2:{player_id}:{season}", GL_TTL, _f)


def props_for_player(pid, name, team, opp, rows, last_n=10, market=None):
    recent = rows[-last_n:] if rows else []
    if len(recent) < 3:
        return []
    out = []
    for label, line, allowed in PROPS:
        if market and market != label:
            continue
        vals = [_value(r, label) for r in recent]
        n = len(vals)
        over = sum(1 for v in vals if v > line)
        over_rate, under_rate = over / n, (n - over) / n
        if allowed == "over":
            side, rate, hit = "Over", over_rate, over
        else:
            side, rate, hit = ("Over", over_rate, over) if over_rate >= under_rate else ("Under", under_rate, n - over)
        out.append({"player_id": pid, "player": name, "team": team, "opp": opp,
                    "prop": f"{side} {line} {label}", "label": label, "line": line, "side": side,
                    "rate": round(rate, 3), "hit": hit, "n": n})
    return out


def _gather_picks(batters, season, date, last_n, market, min_rate):
    def _work(b):
        pid, name, team, opp = b
        rows = [r for r in gamelog(pid, season) if not r["date"] or r["date"] < date]
        return [p for p in props_for_player(pid, name, team, opp, rows, last_n, market) if p["rate"] >= min_rate]
    picks = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        for res in ex.map(_work, batters):
            picks.extend(res)
    picks.sort(key=lambda p: (p["rate"], p["hit"]), reverse=True)
    return picks


def top_picks(date, away_name, home_name, min_rate=0.7, last_n=10, market=None):
    """Picks de un solo partido."""
    return _gather_picks(game_batters(date, away_name, home_name), _season(date), date, last_n, market, min_rate)


def trends(date, min_rate=0.7, last_n=10, market=None):
    """Feed cross-game: mejores props de TODOS los partidos pre-partido del día."""
    season = _season(date)
    batters, seen = [], set()
    for g in _schedule(date):
        if (g.get("status", {}) or {}).get("abstractGameState") != "Preview":
            continue   # solo pre-partido
        for b in _batters_for_game(g):
            if b[0] in seen:
                continue
            seen.add(b[0]); batters.append(b)
            if len(batters) >= TRENDS_PLAYER_CAP:
                break
        if len(batters) >= TRENDS_PLAYER_CAP:
            break
    return _gather_picks(batters, season, date, last_n, market, min_rate)[:60]


def gamelog_table(player_id, season, label, line, side, last_n=15, before=None, mode="all", opp=None):
    """Filas del gamelog (nuevo->viejo) con valor del stat y si pegó. mode: all|last10|h2h|home|away."""
    rows = [r for r in gamelog(player_id, season) if not before or not r["date"] or r["date"] < before]
    if mode == "h2h" and opp:
        rows = [r for r in rows if r["opp"] == opp]
    elif mode == "home":
        rows = [r for r in rows if r["home"]]
    elif mode == "away":
        rows = [r for r in rows if not r["home"]]
    if mode == "last10":
        rows = rows[-10:]
    rows = rows[-last_n:][::-1] if mode != "last10" else rows[::-1]
    out, hits = [], 0
    for r in rows:
        v = _value(r, label)
        hit = (v > line) if side == "Over" else (v < line)
        hits += 1 if hit else 0
        out.append({"date": r["date"], "opp": r["opp"], "home": r["home"], "H": r["H"], "TB": r["TB"],
                    "R": r["R"], "RBI": r["RBI"], "AB": r["AB"], "val": v, "hit": hit})
    return {"rows": out, "hit": hits, "n": len(out)}


if __name__ == "__main__":
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    market = sys.argv[2] if len(sys.argv) > 2 else None
    t = trends(date, min_rate=0.7, last_n=10, market=market)
    print(f"\n  TRENDS -- {date} -- {len(t)} picks{' ('+market+')' if market else ''}\n")
    for p in t[:25]:
        print(f"  {p['player']:<20} vs {p['opp'][:14]:<14} {p['prop']:<24} {p['hit']}/{p['n']} ({int(p['rate']*100)}%)")
    print()
