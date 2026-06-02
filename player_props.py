"""player_props.py — picks de jugadores MLB por hit-rate (estilo Linemate).

Para cada bateador del lineup de un partido baja su game log (MLB Stats API) y, para
props estándar (hits, bases totales, carreras, RBI, H+R+RBI, HR), calcula con qué
frecuencia superó/no superó la línea en los últimos N partidos. Surfacea los props con
hit-rate alto. La tabla de gamelog alimenta el detalle (estilo Linemate) y a Opus.

Sin cuotas por ahora (The Odds API cobra caro las props); el hit-rate es el core.

Uso CLI: python player_props.py 2026-06-01 "Detroit Tigers" "Tampa Bay Rays"
"""
import sys, datetime, requests
import cache

B = "https://statsapi.mlb.com/api/v1"
GL_TTL = 3 * 3600   # game logs cambian 1 vez/día

# (etiqueta, stat key | None si compuesto, línea, lados_permitidos)
# "over" para eventos raros: "Under 0.5 HR" es trivial (casi nadie batea HR) -> ruido.
PROPS = [
    ("Hits", "hits", 0.5, "both"),
    ("Hits", "hits", 1.5, "both"),
    ("Bases totales", "totalBases", 1.5, "both"),
    ("Carreras", "runs", 0.5, "over"),
    ("Impulsadas", "rbi", 0.5, "over"),
    ("H+R+RBI", None, 1.5, "both"),
    ("Home Run", "homeRuns", 0.5, "over"),
]
_KEYMAP = {"hits": "H", "totalBases": "TB", "runs": "R", "rbi": "RBI", "homeRuns": "HR"}


def _season(date):
    return int(date[:4]) if date else datetime.date.today().year


def game_batters(date, away_name, home_name):
    """[(player_id, nombre, equipo, rival)] del lineup publicado del partido. [] si no hay."""
    sch = requests.get(f"{B}/schedule",
                       params={"sportId": 1, "date": date, "hydrate": "lineups,team"}, timeout=15).json()
    games = sch.get("dates", [{}])[0].get("games", []) if sch.get("dates") else []
    for g in games:
        h = g["teams"]["home"]["team"]["name"]
        a = g["teams"]["away"]["team"]["name"]
        if h == home_name and a == away_name:
            lu = g.get("lineups", {}) or {}
            out = []
            for p in lu.get("awayPlayers", []):
                out.append((p["id"], p.get("fullName"), a, h))
            for p in lu.get("homePlayers", []):
                out.append((p["id"], p.get("fullName"), h, a))
            return out
    return []


def gamelog(player_id, season):
    """Game log de bateo (lista de partidos, más viejo->más nuevo). Cacheado 3h."""
    def _f():
        gl = requests.get(f"{B}/people/{player_id}/stats",
                          params={"stats": "gameLog", "group": "hitting", "season": season}, timeout=15).json()
        sp = gl["stats"][0]["splits"] if gl.get("stats") and gl["stats"][0].get("splits") else []
        rows = []
        for s in sp:
            st = s["stat"]
            opp = (s.get("opponent") or {})
            rows.append({
                "date": s.get("date"), "opp": opp.get("abbreviation") or opp.get("name") or "",
                "H": st.get("hits", 0), "TB": st.get("totalBases", 0), "R": st.get("runs", 0),
                "RBI": st.get("rbi", 0), "HR": st.get("homeRuns", 0), "AB": st.get("atBats", 0),
            })
        return rows
    return cache.cached(f"mlbgl:{player_id}:{season}", GL_TTL, _f)


def _val(row, statkey, label):
    if label == "H+R+RBI":
        return row["H"] + row["R"] + row["RBI"]
    return row.get(_KEYMAP.get(statkey, ""), 0)


def props_for_player(pid, name, team, opp, rows, last_n=10):
    recent = rows[-last_n:] if rows else []
    if len(recent) < 3:
        return []
    out = []
    for label, statkey, line, allowed in PROPS:
        vals = [_val(r, statkey, label) for r in recent]
        n = len(vals)
        over = sum(1 for v in vals if v > line)
        over_rate, under_rate = over / n, (n - over) / n
        if allowed == "over":
            side, rate, hit = "Over", over_rate, over
        else:
            side, rate, hit = ("Over", over_rate, over) if over_rate >= under_rate else ("Under", under_rate, n - over)
        out.append({
            "player_id": pid, "player": name, "team": team, "opp": opp,
            "prop": f"{side} {line} {label}", "statkey": statkey or "HRR", "label": label,
            "line": line, "side": side, "rate": round(rate, 3), "hit": hit, "n": n,
        })
    return out


def top_picks(date, away_name, home_name, min_rate=0.7, last_n=10):
    """Props de todos los bateadores del partido con hit-rate >= min_rate, ordenados."""
    season = _season(date)
    picks = []
    for pid, name, team, opp in game_batters(date, away_name, home_name):
        rows = [r for r in gamelog(pid, season) if not r["date"] or r["date"] < date]   # solo partidos previos
        for p in props_for_player(pid, name, team, opp, rows, last_n):
            if p["rate"] >= min_rate:
                picks.append(p)
    picks.sort(key=lambda p: (p["rate"], p["hit"]), reverse=True)
    return picks


def gamelog_table(player_id, season, statkey, label, line, side, last_n=15, before=None):
    """Filas del gamelog (más nuevo primero) con el valor del stat y si el prop pegó."""
    rows = [r for r in gamelog(player_id, season) if not before or not r["date"] or r["date"] < before]
    rows = rows[-last_n:][::-1]
    out = []
    for r in rows:
        v = _val(r, statkey if statkey != "HRR" else None, label)
        hit = (v > line) if side == "Over" else (v < line)
        out.append({"date": r["date"], "opp": r["opp"], "H": r["H"], "TB": r["TB"],
                    "R": r["R"], "RBI": r["RBI"], "AB": r["AB"], "val": v, "hit": hit})
    return out


if __name__ == "__main__":
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    away, home = sys.argv[2], sys.argv[3]
    picks = top_picks(date, away, home, min_rate=0.7, last_n=10)
    print(f"\n  PLAYER PROPS -- {away} @ {home} -- {date} -- {len(picks)} picks (>=70% L10)\n")
    for p in picks[:20]:
        print(f"  {p['player']:<22} {p['prop']:<22} acertó {p['hit']}/{p['n']} ({int(p['rate']*100)}%)")
    print()
