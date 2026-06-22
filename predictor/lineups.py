"""lineups.py - XI confirmado de selecciones desde ESPN (gratis). CONTEXTO, no feature del modelo.

El modelo soccer es team-level (Elo/Poisson, sin features de jugador), asi que el XI NO entra
al modelo: se SURFACEA como contexto para que el usuario vea quien juega / quien falta (ej.
favorito que sale con suplentes). ESPN `rosters` trae formacion + 11 titulares; se llena
~1h antes del kickoff (antes devuelve vacio -> None).

Uso:
  python lineups.py "Spain" "Saudi Arabia" 2026-06-21
"""
import sys, datetime
import requests
import cache

sys.stdout.reconfigure(encoding="utf-8")
SB = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world"


def _events(date):
    return cache.cached(f"espn_wc:{date}", cache.TTL_RESULTS, lambda: requests.get(
        f"{SB}/scoreboard", params={"dates": date.replace("-", "")}, timeout=20).json()).get("events", [])


def _summary(eid):
    return cache.cached(f"espn_wc_sum:{eid}", cache.TTL_LIVE, lambda: requests.get(
        f"{SB}/summary", params={"event": eid}, timeout=20).json())


def _team_xi(r):
    starters = [p for p in r.get("roster", []) if p.get("starter")]
    out = []
    for p in starters:
        pos = p.get("position")
        pos = pos.get("abbreviation") if isinstance(pos, dict) else pos
        out.append({"name": p.get("athlete", {}).get("displayName", "?"), "pos": pos})
    return {"formation": r.get("formation"), "starters": out}


def wc_xi(home, away, date):
    """{home:{formation,starters[]}, away:{...}} orientado a home/away del input. None si no publicado."""
    H, A = home.lower(), away.lower()
    for ev in _events(date):
        comp = ev["competitions"][0]
        names = {c["team"]["displayName"].lower() for c in comp["competitors"]}
        if H not in names or A not in names:
            continue
        ros = _summary(ev["id"]).get("rosters") or []
        by = {}
        for r in ros:
            tn = r.get("team", {}).get("displayName", "").lower()
            xi = _team_xi(r)
            if xi["starters"]:
                by[tn] = xi
        if not by:
            return None
        return {"home": by.get(H), "away": by.get(A)}
    return None


def main():
    args = [a for a in sys.argv[1:]]
    if len(args) < 2:
        print('  Uso: lineups.py "<local>" "<visita>" [fecha]')
        return
    date = args[2] if len(args) > 2 else datetime.date.today().isoformat()
    xi = wc_xi(args[0], args[1], date)
    if not xi:
        print(f"  XI aun no publicado (sale ~1h antes del kickoff).")
        return
    for side, lbl in (("home", args[0]), ("away", args[1])):
        t = xi.get(side)
        if not t:
            print(f"  {lbl}: sin datos"); continue
        print(f"  {lbl}  ({t['formation']}):")
        print("    " + ", ".join(f"{p['name']}" for p in t["starters"]))


if __name__ == "__main__":
    main()
