"""sensor.py - recolector de disponibilidad (capa 1 del sensor). CERO feature del modelo.

Arma un JSON de disponibilidad estructurada que dos alimentadores llenan:

  A) DETERMINISTA (este modulo, ESPN gratis): titulares habituales derivados de los `rosters`
     de los ultimos partidos (flag `starter`, ilimitado) + XI confirmado de hoy (lineups.wc_xi,
     ~1h antes) -> deriva `ausentes` (titular habitual que NO esta en el XI de hoy).
  B) IA (Claude+WebSearch = lecturas.py): llena el MISMO esquema con lo que el feed no ve
     (impacto, motivacion, dudas de ultimo momento, bajas PRE-partido).

Por que hace falta la IA: ESPN NO publica lesiones del Mundial (`fifa.world/injuries` = []),
asi que la disponibilidad PRE-partido de selecciones la aporta B. A da el esqueleto gratis.

Todo esto es CONTEXTO: NO toca la probabilidad. El ajuste sobre la prob (capa 2) es aparte,
acotado y forward-testeado. Aca solo se RECOLECTA y ESTRUCTURA.

Uso:
  python sensor.py "Spain" "Austria" 2026-07-02
"""
import sys, math, datetime
import requests
import cache, lineups

sys.stdout.reconfigure(encoding="utf-8")
SB = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world"
N_RECENT = 5                                   # ventana de partidos para "titular habitual"


def _schedule(team_id):
    """Eventos del equipo en el Mundial (schedule ESPN). Cacheado 3h."""
    return cache.cached(f"espn_wc_sched:{team_id}", cache.TTL_RESULTS, lambda: requests.get(
        f"{SB}/teams/{team_id}/schedule", timeout=20).json()).get("events", [])


def _espn_ids(home, away, date):
    """{name: espn_team_id} para home/away del input, resolviendo por el scoreboard del dia.
    {} si no encuentra el partido. Reusa el cache de eventos compartido con lineups/odds."""
    H, A = home.lower(), away.lower()
    for ev in lineups._events(date):
        comp = ev["competitions"][0]
        cs = {c["team"]["displayName"].lower(): c["team"]["id"] for c in comp["competitors"]}
        if H in cs and A in cs:
            return {c["team"]["displayName"]: c["team"]["id"] for c in comp["competitors"]}
    return {}


def _completed_event_ids(team_id, before_date, limit=N_RECENT):
    """Ultimos `limit` eventos FINALIZADOS del equipo antes de `before_date` (reciente primero)."""
    done = []
    for ev in _schedule(team_id):
        comp = ev.get("competitions", [{}])[0]
        st = (comp.get("status") or {}).get("type", {}).get("name", "")
        d = (ev.get("date") or "")[:10]
        if st in ("STATUS_FULL_TIME", "STATUS_FINAL") and d and d < before_date and ev.get("id"):
            done.append((d, ev["id"]))
    done.sort(reverse=True)
    return [eid for _, eid in done[:limit]]


def _starters_of(summary, team_id):
    """[{name,pos}] titulares del equipo `team_id` en ese partido (de rosters). [] si no hay."""
    out = []
    for r in (summary.get("rosters") or []):
        if str((r.get("team") or {}).get("id")) != str(team_id):
            continue
        for p in (r.get("roster") or []):
            if not p.get("starter"):
                continue
            pos = p.get("position")
            pos = pos.get("abbreviation") if isinstance(pos, dict) else pos
            out.append({"name": (p.get("athlete") or {}).get("displayName", "?"), "pos": pos})
    return out


def _tally(list_of_xis):
    """list_of_xis: lista de XIs (una por partido). -> {name: {pos, starts}} agregado."""
    counts = {}
    for xi in list_of_xis:
        for p in xi:
            e = counts.setdefault(p["name"], {"pos": p["pos"], "starts": 0})
            e["starts"] += 1
    return counts


def usual_starters(team_id, before_date):
    """Titulares habituales del equipo: quien arranco en >= la mitad de los ultimos partidos.
    (name, pos, starts, of). [] si no hay partidos recientes con rosters."""
    eids = _completed_event_ids(team_id, before_date)
    if not eids:
        return [], 0
    xis = [_starters_of(lineups._summary(eid), team_id) for eid in eids]
    xis = [x for x in xis if x]                # descartar partidos sin rosters
    n = len(xis)
    if not n:
        return [], 0
    counts = _tally(xis)
    thresh = math.ceil(n / 2)
    usual = [{"name": nm, "pos": e["pos"], "starts": e["starts"], "of": n}
             for nm, e in counts.items() if e["starts"] >= thresh]
    usual.sort(key=lambda p: p["starts"], reverse=True)
    return usual, n


def _side_availability(name, team_id, date, xi_today):
    """Bloque de disponibilidad de un equipo: titulares habituales + XI de hoy (si confirmado)
    + ausentes derivados (titular habitual que no esta en el XI de hoy)."""
    usual, n = usual_starters(team_id, date)
    block = {"team": name, "usual_starters": usual, "recent_matches": n,
             "xi_status": "pendiente", "xi": None, "ausentes": []}
    if xi_today and xi_today.get("starters"):
        today_names = {p["name"] for p in xi_today["starters"]}
        block["xi_status"] = "confirmado"
        block["xi"] = xi_today["starters"]
        block["formation"] = xi_today.get("formation")
        block["ausentes"] = [{"name": p["name"], "pos": p["pos"], "fuente": "espn_derivado"}
                             for p in usual if p["name"] not in today_names]
    return block


def availability(home, away, date):
    """Disponibilidad estructurada de un partido del Mundial (alimentador determinista).
    CONTEXTO, nunca feature. La IA (lecturas) completa bajas/impacto/motivacion en este esquema."""
    ids = _espn_ids(home, away, date)
    if not ids:
        return {"home": None, "away": None, "_meta": {"source": "espn", "error": "partido no hallado"}}
    xi = lineups.wc_xi(home, away, date) or {}
    id_by_lower = {k.lower(): v for k, v in ids.items()}
    name_by_lower = {k.lower(): k for k in ids}
    out = {"_meta": {"source": "espn",
                     "note": "bajas PRE-partido via IA (lecturas); ESPN no publica injuries del Mundial"}}
    for side, raw in (("home", home), ("away", away)):
        lk = raw.lower()
        tid = id_by_lower.get(lk)
        out[side] = _side_availability(name_by_lower.get(lk, raw), tid, date, xi.get(side)) if tid else None
    return out


# ── Alimentador B (IA): merge de la lectura estructurada en el MISMO esquema ───

# peso por impacto de una baja (la IA lo etiqueta; ESPN-derivado asume 'titular')
IMPACT_W = {"clave": 1.0, "titular": 0.8, "duda": 0.4, "suplente": 0.2}


def merge_lectura(av, lectura):
    """Fold de la disponibilidad estructurada de la IA (Claude+WebSearch, lecturas.py) en el
    esquema de ESPN. Espera lectura['disponibilidad'] = {home:{bajas:[{jugador,pos,impacto}],
    motivacion}, away:{...}}. No-op si la lectura no trae el bloque (lecturas viejas). Muta av."""
    disp = (lectura or {}).get("disponibilidad") or {}
    for side in ("home", "away"):
        blk = av.get(side)
        if not blk:
            continue
        d = disp.get(side) or {}
        blk["bajas_ia"] = d.get("bajas") or []
        blk["motivacion"] = d.get("motivacion")
    return av


# ── Capa 2 (SHADOW): ajuste acotado por disponibilidad. NO se aplica a la decision. ──
# Se COMPUTA y LOGUEA (cruda vs ajustada) para forward-testear si suma. Solo cuando el
# forward-test lo valide se pasa a aplicar. Constantes tunables por el meta-agente.
ADJ_CAP = 0.04            # tope del ajuste: nunca mueve mas de 4pp
ADJ_PER_UNIT = 0.012      # pp por unidad de severidad neta de ausencias


def _severity(block):
    """Severidad de ausencias de un equipo = suma de pesos por impacto. Combina el ausente
    ESPN-derivado (titular habitual afuera del XI) con las bajas que aporta la IA."""
    if not block:
        return 0.0
    s = IMPACT_W["titular"] * len(block.get("ausentes") or [])
    for b in (block.get("bajas_ia") or []):
        s += IMPACT_W.get((b.get("impacto") or "titular").lower(), 0.4)
    return s


def adjust(probs, av, cap=ADJ_CAP):
    """SHADOW. probs=[home,draw,away] CALIBRADAS. Mueve prob del favorito segun quien tiene
    mas/peores ausencias, acotado a ±cap y renormalizado. Devuelve (probs_ajustadas, delta).
    delta>0 = se le baja al local. NO toca la decision en vivo (guardrail: sin forward-test,
    no se aplica) -> se usa para loguear cruda vs ajustada."""
    h, d, a = probs
    net = _severity(av.get("home")) - _severity(av.get("away"))     # >0 = local mas golpeado
    delta = max(-cap, min(cap, net * ADJ_PER_UNIT))
    h2, a2 = max(0.0, h - delta), max(0.0, a + delta)
    tot = h2 + d + a2
    if tot <= 0:
        return [round(h, 4), round(d, 4), round(a, 4)], 0.0
    return [round(h2 / tot, 4), round(d / tot, 4), round(a2 / tot, 4)], round(delta, 4)


def main():
    args = [a for a in sys.argv[1:]]
    if len(args) < 2:
        print('  Uso: sensor.py "<local>" "<visita>" [fecha]')
        return
    date = args[2] if len(args) > 2 else datetime.date.today().isoformat()
    av = availability(args[0], args[1], date)
    if av["_meta"].get("error"):
        print(f"  {av['_meta']['error']}"); return
    for side, lbl in (("home", args[0]), ("away", args[1])):
        b = av.get(side)
        if not b:
            print(f"\n  {lbl}: sin datos ESPN"); continue
        print(f"\n  {b['team']}  (base: {b['recent_matches']} partidos | XI hoy: {b['xi_status']})")
        print("   Titulares habituales:")
        for p in b["usual_starters"]:
            print(f"     {p['name']:<24} {p['pos'] or '?':<4} {p['starts']}/{p['of']}")
        if b["ausentes"]:
            print("   AUSENTES del XI de hoy (titular habitual afuera):")
            for p in b["ausentes"]:
                print(f"     {p['name']:<24} {p['pos'] or '?'}")
    print(f"\n  {av['_meta']['note']}")


if __name__ == "__main__":
    main()
