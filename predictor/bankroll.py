"""bankroll.py - ledger de bankroll: curva de equity, drawdown y stop-loss. CERO promesas.

El north star del proyecto es "crecimiento de bankroll con drawdown controlado". Esto lo hace
MEDIBLE: arma la curva de equity desde las apuestas REALES resueltas (bet_evals, Kelly stake>0,
en orden cronologico), y vigila los stop-loss diario/semanal del CLAUDE.md.

Usa el PnL REAL ya staked (no re-simula sizing): refleja lo que efectivamente se arriesgo.
Honesto sobre la muestra: con pocas apuestas resueltas, la curva es ilustrativa, no veredicto.

Uso:
  python bankroll.py            # resumen del ledger (equity, drawdown, stop-loss)
"""
import os, sys, datetime
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

BANKROLL0 = 1000.0          # bankroll de referencia (CLAUDE.md)
STOP_DAILY = 0.05 * BANKROLL0   # stop-loss diario  = $50  (5%)
STOP_WEEKLY = 0.10 * BANKROLL0  # stop-loss semanal = $100 (10%)


def _resolved_bets(con=None):
    """Apuestas REALES resueltas (stake>0), ordenadas cronologicamente."""
    return db.query("SELECT date, home, away, side, tier, odds, stake, won, pnl, evaluated_at "
                    "FROM bet_evals WHERE stake > 0 ORDER BY date, evaluated_at", con=con)


def ledger(con=None):
    """Curva de equity + drawdown a partir de las apuestas reales resueltas."""
    bets = _resolved_bets(con)
    bal = peak = BANKROLL0
    max_dd = 0.0
    curve = [{"date": "inicio", "label": "bankroll inicial", "pnl": 0.0, "balance": round(bal, 2), "dd": 0.0}]
    for b in bets:
        bal += b["pnl"]
        peak = max(peak, bal)
        dd = (peak - bal) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
        curve.append({"date": b["date"], "label": f"{b['home']} v {b['away']} · {b['side']} @{b['odds']:.2f}",
                      "tier": b["tier"], "pnl": round(b["pnl"], 2), "balance": round(bal, 2),
                      "won": b["won"], "dd": round(dd, 4)})
    n = len(bets)
    staked = sum(b["stake"] for b in bets)
    pnl = sum(b["pnl"] for b in bets)
    return {"bankroll0": BANKROLL0, "n_bets": n, "staked": round(staked, 2),
            "pnl": round(pnl, 2), "balance": round(bal, 2),
            "roi": round(pnl / staked * 100, 1) if staked else 0.0,
            "growth_pct": round((bal / BANKROLL0 - 1) * 100, 1),
            "peak": round(peak, 2), "max_drawdown_pct": round(max_dd * 100, 1),
            "cur_drawdown_pct": round((peak - bal) / peak * 100, 1) if peak > 0 else 0.0,
            "curve": curve}


def _by_period(bets, period):
    """Agrupa PnL por dia ('d') o semana ISO ('w')."""
    out = {}
    for b in bets:
        d = datetime.date.fromisoformat(b["date"])
        key = b["date"] if period == "d" else f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"
        out[key] = out.get(key, 0.0) + b["pnl"]
    return out


def stop_loss_status(con=None):
    """Revisa los stop-loss diario/semanal contra el PnL de cada periodo."""
    bets = _resolved_bets(con)
    daily, weekly = _by_period(bets, "d"), _by_period(bets, "w")
    breaches = []
    for k, v in sorted(daily.items()):
        if v <= -STOP_DAILY:
            breaches.append(("DIARIO", k, round(v, 2), -STOP_DAILY))
    for k, v in sorted(weekly.items()):
        if v <= -STOP_WEEKLY:
            breaches.append(("SEMANAL", k, round(v, 2), -STOP_WEEKLY))
    return {"daily": daily, "weekly": weekly, "breaches": breaches}


def report(con=None):
    L = ledger(con)
    print("=" * 66)
    print("  LEDGER DE BANKROLL  (apuestas reales resueltas, Kelly stake>0)")
    print("=" * 66)
    if L["n_bets"] == 0:
        print("  Sin apuestas reales resueltas todavia. El ledger se llena con pnl.eval + db.sync.")
        return
    print(f"  Bankroll inicial ... ${L['bankroll0']:.0f}")
    print(f"  Apuestas ........... {L['n_bets']}   |  arriesgado ${L['staked']:.0f}")
    print(f"  PnL ................ ${L['pnl']:+.2f}   |  ROI {L['roi']:+.1f}%")
    print(f"  Balance actual ..... ${L['balance']:.2f}   ({L['growth_pct']:+.1f}% vs inicial)")
    print(f"  Pico ............... ${L['peak']:.2f}")
    print(f"  Drawdown maximo .... {L['max_drawdown_pct']:.1f}%   |  actual {L['cur_drawdown_pct']:.1f}%")
    print("\n  Curva de equity:")
    for p in L["curve"]:
        mark = "" if p["date"] == "inicio" else ("  +" if p.get("won") else "  -")
        print(f"    {p['date']:<12} ${p['balance']:>8.2f}  (dd {p['dd']*100:>4.1f}%)  {p.get('label','')}{mark}")
    s = stop_loss_status(con)
    print(f"\n  Stop-loss (CLAUDE.md): diario ${STOP_DAILY:.0f} (5%) | semanal ${STOP_WEEKLY:.0f} (10%)")
    if s["breaches"]:
        for tipo, k, v, lim in s["breaches"]:
            print(f"    [STOP {tipo}] {k}: PnL ${v:+.2f} cruzo el limite ${lim:.0f} -> PARAR y revisar")
    else:
        print("    sin cruces de stop-loss.")
    if L["n_bets"] < 30:
        print(f"\n  OJO: {L['n_bets']} apuestas = muestra chica -> curva ilustrativa, no veredicto. El loop acumula.")


if __name__ == "__main__":
    report()
