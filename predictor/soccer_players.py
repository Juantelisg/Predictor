"""soccer_players.py - candidatos de props de jugador para futbol de selecciones desde
API-Football (game-logs reales). Cubre lo que el feed 'trending' de Linemate NO trae
(ej: Harry Kane no aparece en Linemate WC). Calcula hit-rates propios L5/L10 por jugador
y mercado (tiros / tiros al arco / goles / asistencias / gol+asist).

API-Football FREE (key en .env, budget.py):
  - sin parametro `last` -> se consulta por season=YYYY.
  - la "season 2024" de selecciones llega hasta fines de 2025 (eliminatorias) -> data fresca.
  - quota 100/dia (budget.can_spend) + throttle por minuto -> espaciar ~6s por call.
  - los stats POR PARTIDO son inmutables -> se cachean 30 dias; solo los fixtures nuevos
    cuestan quota. La lista de fixtures del equipo se cachea 12h.

`candidates(team_name)` devuelve entradas con la MISMA forma que el panorama de Linemate
(analizar._player_panorama) para poder mergearlas en el mismo tab de jugadores.
"""
import time
import requests
import budget
import cache

BASE = budget.BASE
HEADERS = budget.HEADERS

FIX_TTL = 30 * 24 * 3600     # stats por partido: inmutables
LIST_TTL = 12 * 3600         # lista de fixtures del equipo: cambia al jugar
ID_TTL = 30 * 24 * 3600      # id de seleccion: estable
SEASONS = [2024, 2023]       # 2024 llega a fines 2025; 2023 completa hasta 10 juegos
SLEEP = 6                    # espaciar calls (throttle por minuto del plan free)
N_GAMES = 10                 # ventana de game-log
MIN_APP = 3                  # apariciones minimas para tener hit-rate creible

POS_WORD = {"G": "goalkeeper", "D": "defender", "M": "midfielder", "F": "forward"}

# (etiqueta ES, clave del stat, lineas). El GK se excluye de mercados ofensivos.
MARKETS = [
    ("tiros al arco",    "on",      [0.5, 1.5]),
    ("tiros",            "total",   [0.5, 1.5, 2.5]),
    ("goles",            "goals",   [0.5]),
    ("asistencias",      "assists", [0.5]),
    ("gol o asistencia", "ga",      [0.5]),
]


def _get(path, ttl, **params):
    """GET cacheado. El sleep anti-throttle corre SOLO en cache-miss (dentro del fetcher)."""
    def fetch():
        r = requests.get(f"{BASE}/{path}", headers=HEADERS, params=params, timeout=25).json()
        time.sleep(SLEEP)
        return r
    key = "apif:" + path + ":" + ":".join(f"{k}={v}" for k, v in sorted(params.items()))
    return cache.cached(key, ttl, fetch)


def team_id(name):
    """id de la seleccion en API-Football, None si no resuelve. name= exacto, luego search=."""
    for q in ("name", "search"):
        try:
            r = _get("teams", ID_TTL, **{q: name})
            for it in (r.get("response") or []):
                tm = it.get("team", {})
                if tm.get("national") and tm.get("id"):
                    return tm["id"]
            # sin filtro nacional: primer resultado
            resp = r.get("response") or []
            if resp and resp[0].get("team", {}).get("id"):
                return resp[0]["team"]["id"]
        except Exception:
            continue
    return None


def _recent_fixture_ids(tid):
    """Ultimos N_GAMES fixtures FINALIZADOS del equipo (viejo -> reciente). Usa season 2024
    y completa con 2023 si hacen falta. Devuelve lista de fixture ids."""
    seen = {}
    for season in SEASONS:
        try:
            r = _get("fixtures", LIST_TTL, team=tid, season=season)
        except Exception:
            continue
        for f in (r.get("response") or []):
            fi = f.get("fixture", {})
            if fi.get("status", {}).get("short") == "FT" and fi.get("id"):
                seen[fi["id"]] = fi.get("date", "")
        if len(seen) >= N_GAMES:
            break
    ordered = sorted(seen.items(), key=lambda kv: kv[1])   # por fecha asc
    return [fid for fid, _ in ordered[-N_GAMES:]]


def _val(st, kind):
    sh = st.get("shots") or {}
    go = st.get("goals") or {}
    if kind == "total":   return sh.get("total") or 0
    if kind == "on":      return sh.get("on") or 0
    if kind == "goals":   return go.get("total") or 0
    if kind == "assists": return go.get("assists") or 0
    if kind == "ga":      return (go.get("total") or 0) + (go.get("assists") or 0)
    return 0


def _team_logs(tid):
    """Game-log por jugador del equipo tid: {name: {"pos": X, "apps": [stat_dict, ...]}}
    (viejo -> reciente, solo apariciones con minutos)."""
    logs = {}
    for fid in _recent_fixture_ids(tid):
        try:
            r = _get("fixtures/players", FIX_TTL, fixture=fid)
        except Exception:
            continue
        for block in (r.get("response") or []):
            if block.get("team", {}).get("id") != tid:
                continue
            for pl in (block.get("players") or []):
                name = pl.get("player", {}).get("name")
                st = (pl.get("statistics") or [{}])[0]
                mins = (st.get("games") or {}).get("minutes")
                if not name or not mins:
                    continue
                e = logs.setdefault(name, {"pos": (st.get("games") or {}).get("position"), "apps": []})
                e["apps"].append(st)
    return logs


def _read(l5, is_over=True):
    if l5 is None:
        return ""
    return "rendimiento alto" if l5 >= 80 else "en buena forma" if l5 >= 65 else "forma regular"


def _hitrate(vals, line):
    """(hits, games, pct) para 'over line' sobre la lista de valores. None si vacio."""
    if not vals:
        return None, 0, None
    hits = sum(1 for v in vals if v > line)
    return hits, len(vals), round(hits / len(vals) * 100)


def candidates(team_name, tag=None):
    """Candidatos de props del equipo (forma de panorama). tag = nombre con el que se etiqueta
    el campo 'team' (para que el filtro por equipo del frontend matchee). [] si no hay budget,
    no resuelve el equipo o falla la API."""
    tid = team_id(team_name)
    if not tid:
        return []
    # presupuesto: peor caso = 1 lista de fixtures (x2 seasons) + N_GAMES stats. Degradar si no hay.
    try:
        budget.guard(N_GAMES + 2)
    except Exception:
        return []

    logs = _team_logs(tid)
    out = []
    for name, e in logs.items():
        pos = POS_WORD.get(e.get("pos"))
        apps = e["apps"]                       # viejo -> reciente
        if len(apps) < MIN_APP:
            continue
        for market_es, kind, lines in MARKETS:
            if pos == "goalkeeper" and kind in ("on", "total", "goals", "ga"):
                continue
            for line in lines:
                vals = [_val(st, kind) for st in apps]
                h_all, g_all, pct_all = _hitrate(vals, line)
                h5, g5, pct5 = _hitrate(vals[-5:], line)
                h10, g10, pct10 = _hitrate(vals[-10:], line)
                if g10 < MIN_APP or not h10:   # sin muestra o el over nunca ocurrio -> no es pick
                    continue
                score = (pct5 or 0) * 0.6 + (pct10 or 0) * 0.3 + min(g_all, 10) * 0.5
                out.append({
                    "who": name, "team": tag or team_name, "position": pos,
                    "market": market_es, "over": True, "side": f"over {line}", "line": line,
                    "l5": pct5, "l10": pct10, "season": pct_all,
                    "games": g5, "games_l5": g5, "hits_l5": h5,
                    "games_l10": g10, "hits_l10": h10,
                    "read": _read(pct5), "signal": "", "_src": "apifootball", "_score": score,
                })
    out.sort(key=lambda r: r.pop("_score"), reverse=True)
    return out


if __name__ == "__main__":
    import sys, json
    sys.stdout.reconfigure(encoding="utf-8")
    name = sys.argv[1] if len(sys.argv) > 1 else "England"
    print(f"  budget: {budget.status()}")
    c = candidates(name)
    print(f"  {name}: {len(c)} candidatos")
    for r in c[:25]:
        print(f"    {r['who']:<22} {r['market']:<16} {r['side']:<10} "
              f"L5 {r['hits_l5']}/{r['games_l5']} ({r['l5']}%)  L10 {r['hits_l10']}/{r['games_l10']} ({r['l10']}%)  [{r['position']}]")
