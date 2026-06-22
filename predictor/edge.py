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


def devig(decimal_odds):
    """De-vig proporcional: normaliza las implicitas (1/cuota) a sumar 1. Saca el margen
    de la casa. decimal_odds = cuotas de los outcomes mutuamente excluyentes del mercado."""
    imp = [1.0 / o for o in decimal_odds]
    s = sum(imp)
    return [i / s for i in imp]


def edge_market(model_probs, decimal_odds, family, bankroll=1000.0, confidence=0.7):
    """model_probs y decimal_odds = listas alineadas por outcome de UN mercado.
    Devuelve por outcome: prob modelo, prob mercado de-vigeada, edge, y veredicto/stake.
    El GATE: si la familia no esta calificada -> veredicto NO-APOSTAR (falta calibracion)."""
    fair = devig(decimal_odds)
    qualified = family in QUALIFIED
    out = []
    for pm, d, pmk in zip(model_probs, decimal_odds, fair):
        e = pm - pmk
        if not qualified:
            verdict = {"tier": "NO-APTO", "reason": f"familia '{family}' sin calibracion suficiente"}
        elif e < MIN_EDGE:
            verdict = {"tier": "PASAR", "reason": f"edge {e*100:+.1f}% < {MIN_EDGE*100:.0f}%"}
        elif e > MAX_EDGE:
            verdict = {"tier": "SOSPECHOSO", "reason": f"edge {e*100:+.1f}% > {MAX_EDGE*100:.0f}% vs book liquido "
                       f"= probable error del modelo. Forward-test antes de creerle"}
        else:
            verdict = stake.stake(pm, d, confidence, bankroll)   # edge real -> staking Kelly
        out.append({"p_model": pm, "p_market": round(pmk, 4), "edge": round(e, 4),
                    "odds": d, **verdict})
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
