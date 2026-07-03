"""espn_players.py - candidatos de props de jugador desde ESPN (GRATIS, ilimitado).

Sustituye a soccer_players.py (API-Football, 100/dia) para tiros al arco / goles / asistencias
/ gol+asist: el POC 2026-07-02 (Spain-France) verifico que esos stats son IDENTICOS entre ambas
fuentes. 'Tiros totales' difiere de definicion (ESPN cuenta mas) -> se computa sobre ESPN de
forma consistente, no se mezcla con API-Football.

Fuente: los `rosters` de cada `/summary` traen stats por-jugador por-partido (totalShots,
shotsOnTarget, totalGoals, goalAssists, appearances). Para la ventana L5/L10 se juntan los
partidos completados del equipo cruzando slugs de liga (Mundial + eliminatorias + amistosos +
Nations). Salida con la MISMA forma que soccer_players.candidates() para mergear en el mismo tab.
"""
import sys, datetime
import requests
import cache

sys.stdout.reconfigure(encoding="utf-8")
API = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# slugs donde juegan las selecciones: se prueban todos, los vacios no molestan (fetch gratis + cache)
SLUGS = ["fifa.world", "fifa.worldq.uefa", "fifa.worldq.conmebol", "fifa.worldq.concacaf",
         "fifa.worldq.afc", "fifa.worldq.caf", "fifa.friendly", "uefa.nations"]
SCHED_TTL = 6 * 3600             # schedule del equipo: cambia al jugar
SUM_TTL = 30 * 24 * 3600         # stats por partido: inmutables
N_GAMES, MIN_APP = 10, 3

# (etiqueta ES, stat de ESPN, lineas). '_ga' = goles+asist (derivado).
MARKETS = [
    ("tiros al arco",    "shotsOnTarget", [0.5, 1.5]),
    ("goles",            "totalGoals",    [0.5]),
    ("asistencias",      "goalAssists",   [0.5]),
    ("gol o asistencia", "_ga",           [0.5]),
    ("tiros",            "totalShots",    [0.5, 1.5, 2.5]),
]


def _json(url, ttl):
    return cache.cached(f"espnp:{url}", ttl, lambda: requests.get(url, timeout=25).json())


def _pos_word(pos):
    p = (pos or "").upper()
    if p.startswith("G"):
        return "goalkeeper"
    if "F" in p or "W" in p or p in ("ST", "CF"):
        return "forward"
    if "B" in p or p.startswith("D") or p.startswith("C"):
        return "defender"
    return "midfielder"


def team_id(name, date=None):
    """ESPN team id de la seleccion, buscando en scoreboards del Mundial (ventana ±7 dias)."""
    n = name.lower()
    base = datetime.date.fromisoformat(date) if date else datetime.date.today()
    for off in range(15):
        d = (base + datetime.timedelta(days=(off + 1) // 2 * (-1 if off % 2 else 1))).isoformat()
        try:
            sc = _json(f"{API}/fifa.world/scoreboard?dates={d.replace('-', '')}", cache.TTL_RESULTS)
        except Exception:
            continue
        for ev in sc.get("events", []):
            for c in ev["competitions"][0]["competitors"]:
                if c["team"]["displayName"].lower() == n:
                    return c["team"]["id"]
    return None


def _completed_events(tid):
    """(date, slug, event_id) de partidos completados del equipo, cruzando slugs, los N_GAMES mas
    recientes (viejo -> reciente). Dedup por event_id."""
    seen = {}
    for slug in SLUGS:
        try:
            r = _json(f"{API}/{slug}/teams/{tid}/schedule", SCHED_TTL)
        except Exception:
            continue
        for e in (r.get("events") or []):
            comp = (e.get("competitions") or [{}])[0]
            st = (comp.get("status") or {}).get("type", {}).get("name", "")
            d = (e.get("date") or "")[:10]
            if st in ("STATUS_FULL_TIME", "STATUS_FINAL") and d and e.get("id"):
                seen[e["id"]] = (d, slug)
    ordered = sorted(seen.items(), key=lambda kv: kv[1][0])
    return [(d, slug, eid) for eid, (d, slug) in ordered][-N_GAMES:]


def _player_stats(slug, eid, tid):
    """{name: {pos, stats}} del equipo tid en ese partido (solo apariciones con minutos)."""
    summ = _json(f"{API}/{slug}/summary?event={eid}", SUM_TTL)
    out = {}
    for r in (summ.get("rosters") or []):
        if str((r.get("team") or {}).get("id")) != str(tid):
            continue
        for p in (r.get("roster") or []):
            sd = {x["name"]: x.get("value") for x in (p.get("stats") or [])}
            if not sd.get("appearances"):
                continue
            name = (p.get("athlete") or {}).get("displayName")
            pos = p.get("position")
            out[name] = {"pos": pos.get("abbreviation") if isinstance(pos, dict) else pos, "stats": sd}
    return out


def _val(stats, key):
    if key == "_ga":
        return (stats.get("totalGoals") or 0) + (stats.get("goalAssists") or 0)
    return stats.get(key) or 0


def _hitrate(vals, line):
    if not vals:
        return None, 0, None
    hits = sum(1 for v in vals if v > line)
    return hits, len(vals), round(hits / len(vals) * 100)


def _read(l5):
    if l5 is None:
        return ""
    return "rendimiento alto" if l5 >= 80 else "en buena forma" if l5 >= 65 else "forma regular"


def candidates(team_name, espn_id=None, tag=None, date=None):
    """Candidatos de props del equipo (forma de panorama, igual que soccer_players). GRATIS.
    [] si no resuelve el equipo. tag = nombre para etiquetar el campo 'team' (filtro del front)."""
    tid = espn_id or team_id(team_name, date)
    if not tid:
        return []
    logs = {}                                          # name -> {"pos":.., "apps":[stats,...]}
    for d, slug, eid in _completed_events(tid):
        try:
            ps = _player_stats(slug, eid, tid)
        except Exception:
            continue
        for name, e in ps.items():
            g = logs.setdefault(name, {"pos": e["pos"], "apps": []})
            g["apps"].append(e["stats"])
    out = []
    for name, e in logs.items():
        apps = e["apps"]                               # viejo -> reciente
        if len(apps) < MIN_APP:
            continue
        pos = _pos_word(e["pos"])
        if pos == "goalkeeper":                        # todos nuestros mercados son ofensivos
            continue
        for market_es, key, lines in MARKETS:
            for line in lines:
                vals = [_val(st, key) for st in apps]
                h5, g5, pct5 = _hitrate(vals[-5:], line)
                h10, g10, pct10 = _hitrate(vals[-10:], line)
                _, gall, pctall = _hitrate(vals, line)
                if g10 < MIN_APP or not h10:           # sin muestra o el over nunca ocurrio
                    continue
                score = (pct5 or 0) * 0.6 + (pct10 or 0) * 0.3 + min(gall, 10) * 0.5
                out.append({
                    "who": name, "team": tag or team_name, "position": pos,
                    "market": market_es, "over": True, "side": f"over {line}", "line": line,
                    "l5": pct5, "l10": pct10, "season": pctall,
                    "games": g5, "games_l5": g5, "hits_l5": h5,
                    "games_l10": g10, "hits_l10": h10,
                    "read": _read(pct5), "signal": "", "_src": "espn", "_score": score,
                })
    out.sort(key=lambda r: r.pop("_score"), reverse=True)
    return out


if __name__ == "__main__":
    import json
    name = sys.argv[1] if len(sys.argv) > 1 else "Spain"
    c = candidates(name)
    print(f"  {name}: {len(c)} candidatos (ESPN, gratis)")
    for r in c[:25]:
        print(f"    {r['who'][:22]:<22} {r['market']:<16} {r['side']:<10} "
              f"L5 {r['hits_l5']}/{r['games_l5']} ({r['l5']}%)  L10 {r['hits_l10']}/{r['games_l10']} ({r['l10']}%)  [{r['position']}]")
