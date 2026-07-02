"""edge.py - capa de VALOR: compara la prob calibrada del modelo vs la cuota de-vigeada.
CERO copia del mercado (la cuota es benchmark, nunca feature del modelo).

Pipeline de la Fase 2 del PLAN: prob_calibrada (Fase 1) + cuota -> de-vig -> edge ->
GATE de calibracion -> (si pasa) -> stake/tier (Fase 3). El gate es lo que evita apostar
el propio error: un mercado NO calificado (no calibrado / data-starved) NO genera edge.

La ingesta de cuotas en vivo (API-Football, con budget.py) es el paso siguiente; aca esta
la logica pura, testeable con cuotas de ejemplo.

Uso:
  python edge.py     # demo de la cadena completa con cuotas de ejemplo
"""
import sys
import stake

sys.stdout.reconfigure(encoding="utf-8")

# familias de mercado CALIFICADAS para edge (calibradas + con volumen). El resto -> no apostar
# hasta juntar muestra. Se actualiza desde feedback.report (gate de calibracion del PLAN).
QUALIFIED = {"1x2", "dc", "over"}      # 2026-06-21: las de n>=40 y bien calibradas
MIN_EDGE = 0.03                        # edge minimo (prob) para considerar un pick
MAX_EDGE = 0.10                        # edge enorme vs mercado LIQUIDO = probable error del modelo,
                                       # NO valor. Flag SOSPECHOSO hasta forward-testear (no apostar a ciegas)
W_BET = 0.5                            # peso del modelo en la prob de DECISION: p_bet = W_BET*p_cal +
                                       # (1-W_BET)*p_fair. Descuenta el winner's curse (edge grande vs book
                                       # sharp = mas probable error del modelo que valor). 0.5 hasta que el
                                       # forward-test demuestre por familia que se le puede subir.
OVERROUND_MIN = 1.00                   # overround crudo (suma de 1/cuota) valido; fuera de rango = corrupta.
OVERROUND_MAX = 1.20
DRAW_MAX = 0.33                        # fair del empate por encima de esto -> el mercado pricea un regimen
                                       # (incentivo/info) que el modelo team-level NO ve -> 1X2 NO-APTO
                                       # (no fabricar edge en AMBOS lados, causa raiz del ROI negativo).
ODDS_MAX = 4.0                         # cuota mayor a esto = zona longshot: calibracion no probada y de-vig
                                       # ruidoso -> NO-APTO hasta demostrar calibracion forward en esa zona.


def devig(decimal_odds):
    """De-vig proporcional: normaliza las implicitas (1/cuota) a sumar 1. Saca el margen
    de la casa. decimal_odds = cuotas de los outcomes mutuamente excluyentes del mercado."""
    imp = [1.0 / o for o in decimal_odds]
    s = sum(imp)
    return [i / s for i in imp]


def devig_power(decimal_odds):
    """De-vig por POTENCIA: fair_i = q_i^k con k tal que las fair sumen 1 (q_i = 1/cuota).
    A diferencia del proporcional, saca MAS margen de los longshots (donde el book carga mas vig:
    sesgo favorito-longshot). Sin esto, la fair de cuotas altas queda inflada -> edges falsos de
    empate/longshot (la causa #1 del ROI -40% del forward-test)."""
    q = [1.0 / o for o in decimal_odds]
    lo, hi = 0.2, 10.0
    for _ in range(80):                        # biseccion: sum(q_i^k) es decreciente en k -> k tal que =1
        k = (lo + hi) / 2.0
        if sum(qi ** k for qi in q) > 1.0:
            lo = k
        else:
            hi = k
    p = [qi ** ((lo + hi) / 2.0) for qi in q]
    s = sum(p)
    return [pi / s for pi in p]                # normaliza el residuo numerico


def edge_market(model_probs, decimal_odds, family, bankroll=1000.0, confidence=0.7):
    """model_probs y decimal_odds = listas alineadas por outcome de UN mercado (para 1x2: home/draw/away).
    Devuelve por outcome: prob modelo, prob mercado de-vigeada (power para 3-vias), p_bet (shrunk hacia
    el mercado), edge, y veredicto/stake. Gates: mercado corrupto / regimen de empate / longshot /
    familia no calibrada -> NO-APTO; el stake sale de p_bet (no del p_model crudo)."""
    overround = sum(1.0 / o for o in decimal_odds)
    three_way = len(decimal_odds) >= 3
    fair = devig_power(decimal_odds) if three_way else devig(decimal_odds)
    qualified = family in QUALIFIED
    block = None                               # bloqueo a nivel MERCADO (afecta todos los outcomes)
    if not (OVERROUND_MIN <= overround <= OVERROUND_MAX):
        block = f"overround {overround:.3f} fuera de [{OVERROUND_MIN:.2f},{OVERROUND_MAX:.2f}] (cuota corrupta)"
    elif family == "1x2" and three_way and fair[1] > DRAW_MAX:
        block = f"empate fair {fair[1]*100:.0f}% > {DRAW_MAX*100:.0f}% = mercado pricea regimen que el modelo no ve"
    out = []
    for pm, d, pmk in zip(model_probs, decimal_odds, fair):
        e = pm - pmk
        p_bet = W_BET * pm + (1 - W_BET) * pmk       # prob de decision: shrunk hacia el mercado sharp
        if block:
            verdict = {"tier": "NO-APTO", "reason": block}
        elif not qualified:
            verdict = {"tier": "NO-APTO", "reason": f"familia '{family}' sin calibracion suficiente"}
        elif d > ODDS_MAX:
            verdict = {"tier": "NO-APTO", "reason": f"cuota {d} > {ODDS_MAX:.1f} (longshot: calibracion no probada)"}
        elif e < MIN_EDGE:
            verdict = {"tier": "PASAR", "reason": f"edge {e*100:+.1f}% < {MIN_EDGE*100:.0f}%"}
        elif e > MAX_EDGE:
            verdict = {"tier": "SOSPECHOSO", "reason": f"edge {e*100:+.1f}% > {MAX_EDGE*100:.0f}% vs book liquido "
                       f"= probable error del modelo. Forward-test antes de creerle"}
        else:
            verdict = stake.stake(p_bet, d, confidence, bankroll)   # stake con la prob SHRUNK, no la cruda
        out.append({"p_model": pm, "p_market": round(pmk, 4), "p_bet": round(p_bet, 4),
                    "edge": round(e, 4), "odds": d, **verdict})
    return out


def _demo(title, family, names, model_probs, odds):
    print(f"\n  {title}   (familia: {family}, {'CALIFICADA' if family in QUALIFIED else 'NO calificada'})")
    print(f"    {'outcome':<14} {'modelo':>7} {'mercado':>8} {'edge':>7}   veredicto")
    print("    " + "-" * 60)
    for nm, r in zip(names, edge_market(model_probs, odds, family)):
        v = r["tier"]
        extra = (f"{r['frac']*100:.1f}% = ${r['amount']}" if v in ("FUERTE", "MODERADO", "BAJO")
                 else r.get("reason", ""))
        print(f"    {nm:<14} {r['p_model']*100:>6.1f}% {r['p_market']*100:>7.1f}% "
              f"{r['edge']*100:>+6.1f}%   {v:<9} {extra}")


def main():
    print("=" * 70)
    print("  CADENA DE VALOR (demo con cuotas de ejemplo)  -  modelo -> de-vig -> edge -> stake")
    print("=" * 70)
    # 1X2 calificado: modelo ve mas al local que el mercado -> edge
    _demo("Partido A - 1X2", "1x2", ["Local", "Empate", "Visita"],
          [0.58, 0.25, 0.17], [1.95, 3.60, 4.50])
    # over calificado pero el modelo coincide con el mercado -> PASAR
    _demo("Partido A - Over 2.5", "over", ["Over 2.5", "Under 2.5"],
          [0.52, 0.48], [1.90, 1.90])
    # cornes NO calificado -> NO-APTO aunque parezca haber edge (data-starved)
    _demo("Partido A - Cornes O8.5", "corners", ["Over 8.5", "Under 8.5"],
          [0.70, 0.30], [2.10, 1.72])
    print("\n  El GATE protege de apostar el propio error: cornes/tarjetas no apuestan hasta")
    print("  calibrar (ver feedback.report). La ingesta de cuotas en vivo = API-Football + budget.py.\n")


if __name__ == "__main__":
    main()
