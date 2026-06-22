"""odds.py - ingesta de cuotas 1X2 desde ESPN (pickcenter), GRATIS. CERO feature del modelo.

ESPN summary trae `pickcenter` con cuotas de casa (DraftKings) para el Mundial: moneyline
local/empate/visita. Es la MISMA fuente que ya usamos para resultados/stats -> cero costo,
cero key. La cuota es BENCHMARK de valor (Fase 2), nunca entra al modelo (regla del PLAN).

Uso:
  python odds.py 2026-06-22        # cadena completa: modelo calibrado vs cuota -> edge -> stake
"""
import sys, datetime
import requests
import cache, analizar, soccer, edge

sys.stdout.reconfigure(encoding="utf-8")
SB = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world"


def _dec(ml):
    """American moneyline -> cuota decimal."""
    ml = float(ml)
    return round(1 + (ml / 100 if ml > 0 else 100 / abs(ml)), 3)


def _events(date):
    return cache.cached(f"espn_wc:{date}", cache.TTL_RESULTS, lambda: requests.get(
        f"{SB}/scoreboard", params={"dates": date.replace("-", "")}, timeout=20).json()).get("events", [])


def _summary(eid):
    return cache.cached(f"espn_wc_sum:{eid}", cache.TTL_LIVE, lambda: requests.get(
        f"{SB}/summary", params={"event": eid}, timeout=20).json())


def wc_1x2(home, away, date):
    """Cuota 1X2 (decimal) de ESPN orientada a home/away del input. None si no hay pickcenter."""
    H, A = home.lower(), away.lower()
    for ev in _events(date):
        comp = ev["competitions"][0]
        names = {c["team"]["displayName"].lower() for c in comp["competitors"]}
        if H not in names or A not in names:
            continue
        pc = _summary(ev["id"]).get("pickcenter") or []
        if not pc:
            return None
        p = pc[0]
        try:
            d = {"home": _dec(p["homeTeamOdds"]["moneyLine"]), "draw": _dec(p["drawOdds"]["moneyLine"]),
                 "away": _dec(p["awayTeamOdds"]["moneyLine"])}
        except (KeyError, TypeError):
            return None
        espn_home = next(c["team"]["displayName"].lower() for c in comp["competitors"] if c["homeAway"] == "home")
        if espn_home != H:                          # ESPN orienta distinto -> dar vuelta local/visita
            d["home"], d["away"] = d["away"], d["home"]
        d["provider"] = p.get("provider", {}).get("name", "?")
        return d
    return None


def verdict_1x2(home, away, date, ctx=None):
    """Cadena completa para un partido: modelo CALIBRADO 1X2 vs cuota ESPN de-vigeada -> edge -> stake."""
    od = wc_1x2(home, away, date)
    if not od:
        return None
    d = analizar.analyze(home, away, ctx=ctx)
    if d.get("error"):
        return None
    res = d["resultado"]                            # [Gana L, Empate, Gana V] con prob cruda y CALIBRADA
    model = [res[0]["cal"], res[1]["cal"], res[2]["cal"]]     # usar la calibrada (Fase 1)
    odds = [od["home"], od["draw"], od["away"]]
    rows = edge.edge_market(model, odds, "1x2")
    return {"home": d["home"], "away": d["away"], "provider": od["provider"], "odds": odds, "rows": rows}


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    ctx = analizar.load_ctx()
    labels = ["Local", "Empate", "Visita"]
    print("=" * 74)
    print(f"  EDGE 1X2 (modelo calibrado vs cuota ESPN de-vigeada)  -  {date}")
    print("=" * 74)
    any_game = False
    for ev in _events(date):
        comp = ev["competitions"][0]
        cs = {c["homeAway"]: c["team"]["displayName"] for c in comp["competitors"]}
        v = verdict_1x2(cs.get("home", ""), cs.get("away", ""), date, ctx)
        if not v:
            continue
        any_game = True
        print(f"\n  {v['home']} vs {v['away']}   (cuota: {v['provider']})")
        print(f"    {'outcome':<8} {'modelo':>7} {'mercado':>8} {'cuota':>6} {'edge':>7}   veredicto")
        for nm, lb, r in zip([v["home"], "Empate", v["away"]], labels, v["rows"]):
            t = r["tier"]
            extra = (f"{r['frac']*100:.1f}% = ${r['amount']}" if t in ("FUERTE", "MODERADO", "BAJO")
                     else r.get("reason", ""))
            print(f"    {lb:<8} {r['p_model']*100:>6.1f}% {r['p_market']*100:>7.1f}% "
                  f"{r['odds']:>6.2f} {r['edge']*100:>+6.1f}%   {t:<9} {extra}")
    if not any_game:
        print("\n  Sin partidos con cuota disponible para esa fecha.")
    print("\n  Cuota = benchmark de valor (ESPN/DraftKings), nunca feature del modelo. Educativo.\n")


if __name__ == "__main__":
    main()
