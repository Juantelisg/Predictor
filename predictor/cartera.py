"""cartera.py - arma los TICKETS del dia con los picks confiables del modelo y reparte tu sobre.

El usuario ingresa cuanto quiere jugar HOY (un POTE, no su bankroll). Este modulo agarra los
"picks confiables" que el dashboard ya muestra por partido (analizar._picks: mercados de equipo
con prob alta) y los **arma en tickets/combos de 2-3 piernas** segun la confianza, una pierna
por partido (asi las piernas de un ticket son de partidos distintos = independientes -> la prob
conjunta es el producto, honesto). Despues reparte el POTE entre los tickets.

Criterio de armado (el del modelo):
  - una pierna por partido = su pick confiable mas firme,
  - 3 piernas si las tres son ALTA (>=65%), si no 2 (no apilar incertidumbre),
  - un sobrante suelto queda como ticket de 1 pierna (single).
Reparto: proporcional a la prob CONJUNTA (el ticket mas probable se lleva mas), con tope por
ticket y el caso de "uno solo se lleva todo". Es LINEAL en el pote -> el frontend escala
`share x pote` en vivo, sin recalcular.

HONESTIDAD: estos tickets se arman por CONFIANZA del modelo, no por valor vs la cuota (las
piernas de goles/BTTS/doble no tienen cuota). Combinar picks NO garantiza +EV: mas premio,
menos probable. La capa de valor vs mercado (edge 1X2) sigue en el tab del Mundial por partido.

Uso:
  python cartera.py --fecha=2026-06-25 --pote=10
"""
import sys, datetime
sys.stdout.reconfigure(encoding="utf-8")

CAP_SHARE = 0.6        # ningun ticket se lleva mas del 60% del pote
ALTA = 0.65            # umbral de confianza ALTA (decide 2 vs 3 piernas)
LEVELS = {"ALTA": 3, "MEDIA": 2, "BAJA": 1}


def _lvl(p):
    return "ALTA" if p >= 0.65 else "MEDIA" if p >= 0.55 else "BAJA"


def _capped_alloc(weights, pote, cap_share=CAP_SHARE):
    """Reparte `pote` proporcional a `weights` (>0), con tope `cap_share*pote` por item.
    El excedente de los topados se reparte entre el resto (water-filling). Un solo item
    fundable se lleva todo el pote."""
    alloc = [0.0] * len(weights)
    free = {i for i in range(len(weights)) if weights[i] > 0}
    if not free or pote <= 0:
        return alloc
    if len(free) == 1:
        alloc[next(iter(free))] = pote
        return alloc
    cap = cap_share * pote
    remaining = pote
    while free:
        tw = sum(weights[i] for i in free)
        over = [i for i in free if remaining * weights[i] / tw > cap + 1e-9]
        if not over:
            for i in free:
                alloc[i] += remaining * weights[i] / tw
            break
        for i in over:
            alloc[i] = cap
            remaining -= cap
            free.discard(i)
    return alloc


def _family(market):
    """Familia de mercado de un pick (para diversificar: no todas dobles)."""
    m = (market or "").lower()
    if "doble" in m:
        return "doble"
    if "result" in m:
        return "resultado"
    if "gol" in m:
        return "goles"
    if "btts" in m or "marcan" in m:
        return "btts"
    if "corner" in m or "rner" in m:
        return "corners"
    return m


def confident_legs(games):
    """Una pierna por partido, pero DIVERSIFICANDO familias de mercado (no todas dobles):
    el partido mas confiado se queda con su mejor pick; cada siguiente agarra su pick de mas
    prob cuya familia este menos usada. Asi los tickets mezclan resultado/goles/BTTS/doble.
    games = [{game, picks:[{market,pick,prob,level}]}]. Salta los partidos sin picks."""
    cand = [(g["game"], sorted(g["picks"], key=lambda p: p["prob"], reverse=True))
            for g in games if g.get("picks")]
    cand.sort(key=lambda gp: gp[1][0]["prob"], reverse=True)      # los mas confiados eligen primero
    legs, used = [], {}
    for game, picks in cand:
        best = min(picks, key=lambda p: (used.get(_family(p["market"]), 0), -p["prob"]))   # familia menos usada, luego mas prob
        used[_family(best["market"])] = used.get(_family(best["market"]), 0) + 1
        legs.append({"game": game, "market": best["market"], "pick": best["pick"],
                     "prob": round(best["prob"], 4), "level": best.get("level") or _lvl(best["prob"])})
    legs.sort(key=lambda l: l["prob"], reverse=True)
    return legs


def _ticket(legs):
    """Un ticket = combo de sus piernas. Prob conjunta = producto (piernas de partidos
    distintos -> independientes). Confianza del ticket = la de su pierna mas floja."""
    jp = 1.0
    for l in legs:
        jp *= l["prob"]
    weak = min(legs, key=lambda l: LEVELS.get(l["level"], 0))["level"]
    return {"legs": legs, "n": len(legs), "joint_prob": round(jp, 4), "leg_level": weak}


def assemble(legs):
    """Agrupa las piernas (ya ordenadas por prob) en tickets de 2-3: 3 si las tres son ALTA,
    si no 2. Un sobrante suelto = ticket de 1 pierna."""
    tickets, i = [], 0
    while i < len(legs):
        rem = len(legs) - i
        if rem == 1:
            size = 1
        elif rem >= 3 and legs[i + 2]["level"] == "ALTA":
            size = 3
        else:
            size = 2
        tickets.append(_ticket(legs[i:i + size]))
        i += size
    return tickets


def _note(n_games, n_legs, n_tickets):
    return (f"{n_tickets} tickets armados con los picks confiables de {n_legs} partidos "
            f"(uno por partido) · 3 piernas si las tres son ALTA, si no 2 · el reparto despliega "
            f"TODO tu monto, mas en el ticket mas probable. Por confianza del modelo, NO chequeado "
            f"contra cuota: combinar no garantiza valor. Educativo, la varianza es real.")


def build(cards):
    """Payload de la cartera: tickets con su TAJADA por $1 de pote (`share`). El frontend
    escala con el monto en vivo. `cards` = tarjetas del Mundial (cada una con analysis.picks)."""
    games = [{"game": f'{c["home"]} vs {c["away"]}', "picks": (c.get("analysis") or {}).get("picks")}
             for c in cards if (c.get("analysis") or {}).get("picks")]
    legs = confident_legs(games)
    tickets = assemble(legs)
    shares = _capped_alloc([t["joint_prob"] for t in tickets], 1.0)
    for t, s in zip(tickets, shares):
        t["share"] = round(s, 6)
    return {"tickets": tickets, "n_games": len(games), "n_legs": len(legs),
            "note": _note(len(games), len(legs), len(tickets))}


def _cli_cards(date, ctx=None):
    """Tarjetas para el CLI (red): itera los partidos del dia y corre el analisis de cada uno.
    El path real (dashboard) reusa las tarjetas ya computadas; esto es solo para probar por consola."""
    import analizar, odds
    ctx = ctx or analizar.load_ctx()
    cards = []
    for ev in odds._events(date):
        comp = ev["competitions"][0]
        cs = {c["homeAway"]: c["team"]["displayName"] for c in comp["competitors"]}
        home, away = cs.get("home", ""), cs.get("away", "")
        an = analizar.analyze(home, away, neutral=True, ctx=ctx, date=date)
        if an.get("error"):
            continue
        cards.append({"home": home, "away": away, "analysis": an})
    return cards


def main():
    g = lambda k, d: next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith(f"--{k}=")), d)
    date = g("fecha", datetime.date.today().isoformat())
    pote = float(g("pote", "10"))
    data = build(_cli_cards(date))
    print("=" * 74)
    print(f"  TICKETS DEL DIA  ·  {date}  ·  sobre = ${pote:.2f}")
    print("=" * 74)
    if not data["tickets"]:
        print("\n  Sin picks confiables para armar tickets en esa fecha.\n")
        return
    print(f"  {data['n_legs']} picks confiables (uno por partido) -> {len(data['tickets'])} tickets\n")
    deployed = 0.0
    for i, t in enumerate(data["tickets"], 1):
        amt = t["share"] * pote
        deployed += amt
        print(f"  TICKET {i}  ·  {t['n']} pierna(s)  ·  confianza {t['leg_level']}  ·  "
              f"conjunta {t['joint_prob']*100:.1f}%  ·  ${amt:.2f}")
        for l in t["legs"]:
            print(f"      - {l['game']:<26} {l['market']}: {l['pick']:<22} {l['prob']*100:>5.1f}%")
        print()
    print(f"  TOTAL DESPLEGADO: ${deployed:.2f}")
    print("\n  Tickets por confianza del modelo, NO chequeados contra cuota (combinar no garantiza")
    print("  valor: mas premio, menos probable). La capa de valor vs cuota esta por partido.\n")


if __name__ == "__main__":
    main()
