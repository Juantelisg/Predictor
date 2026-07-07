"""estrategia.py - como jugar los picks con criterio (no combos random). CERO cuotas.

Toma los picks confiables del dia (analizar._picks por partido) y arma unas pocas JUGADAS
recomendadas, cada una con fundamento explicito:

  1. ANCLA (single): el pick mas firme del dia. A single, sin diluir.
  2. COMBO COHERENTE (mismo partido): un par de picks del MISMO partido cuya prob CONJUNTA
     (correlacion real via simulate: Monte Carlo del marcador) se REFUERZA (lift >= 1) -- la
     misma historia (favorito que controla: gana + pocos goles + valla). Nunca el producto ingenuo.
  3. COMBO INDEPENDIENTE (2 partidos): dos picks firmes de partidos DISTINTOS -> independientes,
     la conjunta es el producto honesto. Buena ventana de premio sin apilar piernas del mismo partido.

Rechaza lo incoherente: piernas contradictorias o same-match con lift < 1 (la simulacion las delata
con conjunta ~0), y combos cuya conjunta cae bajo la ventana minima.

Uso:
  python estrategia.py [fecha]
"""
import sys, datetime
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

MIN_JOINT = 0.40       # ventana minima de la conjunta de un combo (no apilar hasta volverlo improbable)
SIM_N = 20000          # simulaciones por partido para la conjunta correlacionada


def _line(text):
    """Numero de una etiqueta tipo 'Over 2.5' / 'Under 3.5'. None si no hay."""
    for tok in (text or "").split():
        try:
            return float(tok)
        except ValueError:
            continue
    return None


def _leg_mask(hg, ag, home, away, market, pick):
    """Boolean array del acierto de la pierna sobre los marcadores simulados, o None si la pierna
    NO correla con el marcador (corners/tarjetas/props -> se tratan como independientes)."""
    tot = hg + ag
    m = (market or "").lower()
    p = pick or ""
    if "result" in m:
        return hg > ag if p == f"Gana {home}" else ag > hg if p == f"Gana {away}" else hg == ag
    if "doble" in m:
        if p == f"{home} o empate":
            return hg >= ag
        if p == f"{away} o empate":
            return hg <= ag
        return hg != ag                                  # 'Sin empate'
    if "gol" in m:
        ln = _line(p)
        if ln is None:
            return None
        return tot < ln if p.lower().startswith("under") else tot > ln
    if "btts" in m or "marcan" in m:
        both = (hg >= 1) & (ag >= 1)
        return both if p.lower().startswith("ambos") else ~both
    return None                                          # corners / tarjetas / props: independiente


def same_match_joint(res, home, away, picks):
    """Conjunta de picks del MISMO partido: AND de las mascaras correlacionadas (marcador) por el
    producto de las marginales de las no-correlacionadas. Devuelve (joint, prod_ingenuo, lift)."""
    hg, ag = res["hg"], res["ag"]
    masks, indep = [], 1.0
    for pk in picks:
        msk = _leg_mask(hg, ag, home, away, pk["market"], pk["pick"])
        if msk is None:
            indep *= pk["prob"]
        else:
            masks.append(msk)
    joint_corr = float(np.logical_and.reduce(masks).mean()) if masks else 1.0
    joint = joint_corr * indep
    prod = float(np.prod([pk["prob"] for pk in picks]))
    return joint, prod, (joint / prod if prod else float("nan"))


def recommend(cards, sim_ctx=None):
    """Jugadas recomendadas del dia a partir de las tarjetas (cada una con analysis.picks)."""
    games = [{"home": c["home"], "away": c["away"], "time": c.get("time"),
              "picks": (c.get("analysis") or {}).get("picks") or []}
             for c in cards if (c.get("analysis") or {}).get("picks")]
    if not games:
        return {"plays": [], "note": "Sin picks confiables hoy: nada que combinar (PASAR es valido)."}

    flat = [dict(p, game=f'{g["home"]} vs {g["away"]}', home=g["home"], away=g["away"])
            for g in games for p in g["picks"]]
    flat.sort(key=lambda p: p["prob"], reverse=True)
    plays = []

    # 1. ANCLA (single)
    a = flat[0]
    plays.append({"tipo": "Ancla (single)", "legs": [a], "joint": a["prob"],
                  "rationale": f"El pick mas firme del dia: {a['market']} {a['pick']} "
                               f"({a['prob']*100:.0f}%) en {a['game']}. Jugalo a single, sin diluir."})

    # 2. COMBO COHERENTE (mismo partido, correlacion real)
    import simulate
    sim_ctx = sim_ctx or simulate._ctx()
    for g in sorted(games, key=lambda g: -max(p["prob"] for p in g["picks"])):
        if len(g["picks"]) < 2:
            continue
        pair = g["picks"][:2]
        try:
            res = simulate.simulate(g["home"], g["away"], n=SIM_N, ctx=sim_ctx)
        except Exception:
            continue
        joint, prod, lift = same_match_joint(res, g["home"], g["away"], pair)
        if lift >= 1.0 and joint >= MIN_JOINT:
            names = " + ".join(f"{p['market']} {p['pick']}" for p in pair)
            plays.append({"tipo": "Combo coherente (mismo partido)", "legs": pair, "joint": joint,
                          "lift": lift, "game": f'{g["home"]} vs {g["away"]}',
                          "rationale": f"Misma historia en {g['home']} vs {g['away']}: {names} se "
                                       f"REFUERZAN (conjunta {joint*100:.0f}% vs {prod*100:.0f}% del "
                                       f"producto ingenuo, lift {lift:.2f}x). Correlacion a favor, "
                                       f"no multiplicar marginales."})
            break

    # 3. COMBO INDEPENDIENTE (2 partidos distintos)
    indep, used = [], set()
    for p in flat:
        if p["game"] in used:
            continue
        indep.append(p)
        used.add(p["game"])
        if len(indep) == 2:
            break
    if len(indep) == 2:
        joint = indep[0]["prob"] * indep[1]["prob"]
        if joint >= MIN_JOINT:
            names = " + ".join(f"{p['market']} {p['pick']} ({p['game']})" for p in indep)
            plays.append({"tipo": "Combo independiente (2 partidos)", "legs": indep, "joint": joint,
                          "rationale": f"{names}. Partidos DISTINTOS = independientes: la conjunta es "
                                       f"el producto honesto ({joint*100:.0f}%). Buena ventana de "
                                       f"premio sin apilar piernas del mismo partido."})
    return {"plays": plays, "note": "Jugadas con criterio: ancla + combos verificados por correlacion. "
                                    "Educativo, sin cuotas; combinar nunca garantiza valor."}


def main():
    import cartera
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    cards = cartera._cli_cards(date)
    data = recommend(cards)
    print("=" * 74)
    print(f"  COMO JUGAR HOY  ·  {date}")
    print("=" * 74)
    if not data["plays"]:
        print(f"\n  {data['note']}\n")
        return
    for i, pl in enumerate(data["plays"], 1):
        print(f"\n  [{i}] {pl['tipo']}  ·  conjunta {pl['joint']*100:.0f}%")
        for l in pl["legs"]:
            g = f"  ({l['game']})" if "game" in l else ""
            print(f"        - {l['market']:<14} {l['pick']:<22} {l['prob']*100:>4.0f}%{g}")
        print(f"      -> {pl['rationale']}")
    print(f"\n  {data['note']}\n")


if __name__ == "__main__":
    main()
