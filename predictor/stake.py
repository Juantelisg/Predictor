"""stake.py - cuanto apostar: Kelly fraccional escalado por confianza. CERO promesas.

Traduce (probabilidad calibrada, cuota, confianza) -> tamano del ticket y TIER
(fuerte/moderado/bajo/pasar). Kelly da el crecimiento optimo del bankroll; se usa SIEMPRE
fraccional (nunca full: Kelly con prob inflada revienta el bankroll) y escalado por la
confianza del modelo. Para combos, el tamano sale de la prob CONJUNTA del simulador
(simulate.py), no del producto de marginales.

Esta es la Fase 3 del PLAN: consume el edge (Fase 2) y la prob calibrada (Fase 1).
Hoy se prueba con cuotas de ejemplo (la ingesta real de cuotas es Fase 2).

Uso:
  python stake.py --p=0.55 --odds=2.10 --conf=0.8     # un pick
"""
import sys

KELLY_BASE = 0.5     # tope: nunca mas que half-Kelly (la confianza lo baja desde aca)
CAP = 0.05           # nunca mas del 5% del bankroll en un solo ticket
MIN_EV = 0.02        # EV por unidad < 2% -> pasar (no vale la varianza)
MIN_CONF = 0.45      # confianza por debajo de esto -> pasar (> CONF_MIN=0.40 de uncertainty, para
                     # que el piso data-starved REALMENTE gatille PASAR; antes 0.40 == piso -> nunca disparaba)


def stake(p, decimal_odds, confidence, bankroll=1000.0):
    """p = prob CALIBRADA del modelo; decimal_odds = cuota decimal (de-vigeada idealmente);
    confidence in [0,1] = cuan firme es la prob (muestra/calibracion del mercado).
    Devuelve tier, fraccion del bankroll y monto. EV<MIN_EV o conf baja -> PASAR."""
    d = decimal_odds
    ev = p * d - 1.0                       # valor esperado por unidad apostada
    if ev < MIN_EV or confidence < MIN_CONF or d <= 1.0:
        return {"tier": "PASAR", "frac": 0.0, "amount": 0.0, "ev": ev,
                "reason": "EV bajo" if ev < MIN_EV else "confianza baja"}
    f_full = ev / (d - 1.0)                 # fraccion de Kelly completo
    lam = KELLY_BASE * confidence          # la confianza escala el Kelly (0.5 max)
    frac = min(lam * f_full, CAP)
    tier = "FUERTE" if frac >= 0.03 else "MODERADO" if frac >= 0.015 else "BAJO"
    return {"tier": tier, "frac": round(frac, 4), "amount": round(frac * bankroll, 2),
            "ev": round(ev, 4), "kelly_full": round(f_full, 4)}


def stake_combo(joint_p, leg_odds, confidence, bankroll=1000.0):
    """Combo correlacion-aware: joint_p = prob CONJUNTA del simulador (no producto);
    leg_odds = lista de cuotas decimales por pierna -> cuota del combo = su producto."""
    d = 1.0
    for o in leg_odds:
        d *= o
    return stake(joint_p, d, confidence, bankroll)


def _fmt(r, label=""):
    if r["tier"] == "PASAR":
        return f"  {label:<22} PASAR  (EV {r['ev']*100:+.1f}%, {r.get('reason','')})"
    return (f"  {label:<22} {r['tier']:<9} {r['frac']*100:4.1f}% del bankroll = "
            f"${r['amount']:.2f}   (EV {r['ev']*100:+.1f}%, Kelly full {r['kelly_full']*100:.1f}%)")


def main():
    g = lambda k, d=None: next((float(a.split("=")[1]) for a in sys.argv[1:] if a.startswith(f"--{k}=")), d)
    p, odds, conf = g("p"), g("odds"), g("conf", 0.7)
    bank = g("bank", 1000.0)
    if p is None or odds is None:
        print('  Uso: stake.py --p=0.55 --odds=2.10 --conf=0.8 [--bank=1000]')
        print("\n  Ejemplos (bankroll $1000, conf 0.7):")
        for pp, oo in [(0.55, 2.10), (0.60, 1.80), (0.50, 1.95), (0.70, 1.60), (0.45, 2.50)]:
            print(_fmt(stake(pp, oo, 0.7), f"p={pp} @ {oo}"))
        return
    print(_fmt(stake(p, odds, conf, bank), f"p={p} @ {odds} conf={conf}"))


if __name__ == "__main__":
    main()
