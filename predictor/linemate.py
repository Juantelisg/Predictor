"""linemate.py - cliente de la API publica de Linemate (reemplaza el copiado manual).

La web de Linemate es una SPA que se alimenta de una API JSON publica (sin auth):
    https://api.linemate.io/api/{liga}/v1/trends/straights   -> picks jugador + equipo
    https://api.linemate.io/api/{liga}/v3/teams               -> tabla de equipos + hit records

Cada "trend" trae el mercado, la linea, el lado (over/under) y los HIT-RATES con los
mismos splits que ves en la web: LAST_5 / LAST_10 / LAST_20 / LAST_30 / SEASON /
MATCHUP (vs ese rival) / STARTER. Eso es exactamente lo que filtrabas a mano.

Uso:
  python linemate.py wc                         # todos los picks del Mundial
  python linemate.py mlb --min=70               # solo hit-rate SEASON >= 70%
  python linemate.py wc --game=USA              # un partido (substring del gameId)
  python linemate.py mlb --market=hits          # un mercado (substring del nombre)
  python linemate.py --leagues                  # lista de ligas disponibles

Sin cuotas en la salida (el hit-rate es el core); las odds quedan en el JSON crudo si
las necesitas. Educativo. Uso personal.
"""
import sys, json
import requests
import cache

sys.stdout.reconfigure(encoding="utf-8")

API = "https://api.linemate.io/api"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
           "Origin": "https://linemate.io", "Referer": "https://linemate.io/"}

# alias amigable -> slug real de la API
LEAGUES = {
    "wc": "fifa-world-cup", "worldcup": "fifa-world-cup", "fifa": "fifa-world-cup",
    "epl": "epl", "premier": "epl", "laliga": "laliga", "seriea": "seriea",
    "bundesliga": "bundesliga", "mls": "mls",
    "nba": "nba", "mlb": "mlb", "nfl": "nfl", "nhl": "nhl", "wnba": "wnba",
    "ncaab": "ncaab", "ncaaf": "ncaaf",
}

# splits que mostramos en la tabla (-> columnas)
SPLITS = ["LAST_5", "LAST_10", "SEASON", "MATCHUP"]


def _get(league_slug, path, ttl=cache.TTL_SLATE):
    url = f"{API}/{league_slug}/{path}"
    return cache.cached(f"linemate:{league_slug}:{path}", ttl,
                        lambda: requests.get(url, headers=HEADERS, timeout=30).json())


def trends(league):
    """Lista cruda de trends (straights) de la liga. league: alias o slug."""
    slug = LEAGUES.get(league.lower(), league)
    return _get(slug, "v1/trends/straights")


def _hitrate(records, line, split):
    """hitRate (%) del split para esa linea, o None si no hay datos."""
    rec = records.get(str(line)) or records.get(f"{float(line):g}") if records else None
    if not rec:
        return None
    cell = (rec.get(split) or {}).get("all") or {}
    return cell.get("hitRate") if cell.get("games") else None


def _split_cell(records, line, split):
    """Celda completa {games, hitRate, average} para una linea/split, o {}."""
    rec = records.get(str(line)) or records.get(f"{float(line):g}") if records else None
    if not rec:
        return {}
    return (rec.get(split) or {}).get("all") or {}


def _book_price(side_obj, line):
    """Cuota decimal del lado a esa linea exacta (current si coincide, si no en alternates). None."""
    if not side_obj or line is None:
        return None
    cur = side_obj.get("current") or {}
    if cur and abs((cur.get("value") if cur.get("value") is not None else -999) - line) < 1e-6:
        return (cur.get("odds") or {}).get("decimal")
    for v in (side_obj.get("alternates") or {}).values():
        if abs((v.get("value") if v.get("value") is not None else -999) - line) < 1e-6:
            return (v.get("odds") or {}).get("decimal")
    return None


def _books(market, line):
    """{book: {'over': dec, 'under': dec}} a la linea dada (solo lados presentes). Es la materia
    prima del +EV multi-book: cada casa cotiza distinto y de la DISCREPANCIA sale el valor."""
    out = {}
    for bk, sides in (market.get("books") or {}).items():
        o = _book_price((sides or {}).get("over"), line)
        u = _book_price((sides or {}).get("under"), line)
        entry = {}
        if o:
            entry["over"] = o
        if u:
            entry["under"] = u
        if entry:
            out[bk] = entry
    return out


def flatten(t):
    """Normaliza un trend al dato util: quien, que mercado/linea/lado, hit-rates y CUOTAS multi-book."""
    who = t.get("player", {}).get("fullName") if t.get("type") == "player" else t.get("team", {}).get("name")
    m = t.get("market", {})
    records = m.get("pregameHitRecords") or {}
    line = t.get("line")
    sig = next((s for s in (t.get("signals") or []) if s.get("summary")), None)
    l5_cell = _split_cell(records, line, "LAST_5")
    l10_cell = _split_cell(records, line, "LAST_10")
    sea_cell = _split_cell(records, line, "SEASON")
    return {
        "game": t.get("gameId", ""),
        "type": t.get("type"),
        "who": who or "?",
        "position": (t.get("player") or {}).get("position"),   # forward/midfielder/defender/goalkeeper
        "team": t.get("team", {}).get("code", ""),
        "opp": t.get("opposingTeam", {}).get("code", ""),
        "home": t.get("home"),
        "market": m.get("name", "?"),
        "line": line,
        "side": t.get("outcome", ""),
        "splits": {s: _hitrate(records, line, s) for s in SPLITS},
        "games_l5": l5_cell.get("games"),       # juegos reales en L5 (no slots vacíos)
        "games_l10": l10_cell.get("games"),      # juegos reales en L10
        "games_season": sea_cell.get("games"),   # juegos reales en temporada
        "avg_l5": l5_cell.get("average"),        # promedio del stat en L5 (ej: 1.4 tiros/partido)
        "books": _books(m, line),                # cuotas over/under por casa a esta linea (insumo +EV)
        "signal": sig.get("annotation") if sig else "",
        "signal_desc": sig.get("description") if sig else "",
    }


def games(league):
    """Cartelera actual (slate) de la liga."""
    slug = LEAGUES.get(league.lower(), league)
    return _get(slug, "v3/games/current")


def find_game_id(league, *subs):
    """gameId que contenga TODOS los substrings (ej. find_game_id('wc','PAR','TUR'))."""
    subs = [s.upper() for s in subs]
    for g in games(league):
        gid = (g.get("id") or "").upper()
        if all(s in gid for s in subs):
            return g["id"]
    return None


def game_trends(league, *subs):
    """Trends (flatten) de un partido, filtrados por substrings del gameId."""
    subs = [s.upper() for s in subs]
    return [r for r in (flatten(t) for t in trends(league))
            if all(s in r["game"].upper() for s in subs)]


def injuries(league, team_codes=None):
    """Lesiones de la liga (dict por equipo). team_codes: lista opcional para filtrar."""
    slug = LEAGUES.get(league.lower(), league)
    data = _get(slug, "v3/teams/injuries", ttl=cache.TTL_RESULTS)
    if team_codes and isinstance(data, dict):
        codes = {c.upper() for c in team_codes}
        return {k: v for k, v in data.items() if k.upper() in codes}
    return data


def game_context(league, *subs):
    """Detalle del partido: odds de mercado (CONTEXTO, nunca edge), win%, sede."""
    slug = LEAGUES.get(league.lower(), league)
    gid = find_game_id(league, *subs)
    if not gid:
        return None
    return _get(slug, f"v3/games/{gid}", ttl=cache.TTL_LIVE)


def _pct(v):
    return f"{v:.0f}%" if isinstance(v, (int, float)) else "-"


def main():
    args = sys.argv[1:]
    if "--leagues" in args:
        print("  Ligas:", ", ".join(sorted(set(LEAGUES.keys()))))
        return
    non_flags = [a for a in args if not a.startswith("--")]
    if not non_flags:
        print("  Uso: linemate.py <liga> [--game=X] [--market=X] [--min=70]")
        print("  Ligas:", ", ".join(sorted(set(LEAGUES.keys()))))
        return

    league = non_flags[0]
    game_f  = next((a.split("=", 1)[1].upper() for a in args if a.startswith("--game=")), None)
    mkt_f   = next((a.split("=", 1)[1].upper() for a in args if a.startswith("--market=")), None)
    min_hr  = next((float(a.split("=", 1)[1]) for a in args if a.startswith("--min=")), None)

    try:
        raw = trends(league)
    except Exception as e:
        print(f"  Error al consultar Linemate: {e}")
        return
    if not isinstance(raw, list):
        print(f"  Respuesta inesperada de la API: {str(raw)[:200]}")
        return

    rows = [flatten(t) for t in raw]
    if game_f:
        rows = [r for r in rows if game_f in r["game"].upper()]
    if mkt_f:
        rows = [r for r in rows if mkt_f in r["market"].upper()]
    if min_hr is not None:
        rows = [r for r in rows if (r["splits"].get("SEASON") or 0) >= min_hr]
    rows.sort(key=lambda r: (r["splits"].get("SEASON") or 0), reverse=True)

    if not rows:
        print(f"  Sin picks para {league} con esos filtros ({len(raw)} trends en total).")
        return

    print("=" * 92)
    print(f"  LINEMATE  {LEAGUES.get(league.lower(), league)}  -  {len(rows)} picks")
    print("=" * 92)
    hdr = f"  {'Partido':<16} {'Quien':<22} {'Mercado':<18} {'Pick':<9}"
    for s in SPLITS:
        hdr += f" {s.replace('LAST_','L'):>6}"
    print(hdr)
    print("  " + "-" * 88)
    for r in rows:
        loc = "L" if r["home"] else "V"
        pick = f"{r['side'][:1].upper()}{r['line']}"
        line = f"  {r['game'][9:]:<16} {r['who'][:21]:<22} {r['market'][:17]:<18} {pick:<9}"
        for s in SPLITS:
            line += f" {_pct(r['splits'].get(s)):>6}"
        print(line)
    print(f"\n  L5/L10 = ultimos 5/10 | SEASON = temporada | MATCHUP = vs ese rival.")
    print(f"  Pick: O/U + linea (lado que Linemate destaca). Datos de linemate.io. Educativo.\n")


if __name__ == "__main__":
    main()
