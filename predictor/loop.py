"""loop.py - orquestador del loop completo del supra-modelo (la "cadencia"). CERO cuotas-feature.

Corre TODA la cadena idempotente en un solo comando, en orden de dependencia:
  Loop A (calibrar el modelo):  log WC pre-partido + MLB -> eval -> re-fit Platt -> report
  Loop B (forward-test del edge): log candidatas -> eval -> report
  Persistencia:                  sync JSONL -> SQLite (db.py)

Cada paso esta aislado (si uno falla, los demas siguen). Pensado para:
  - correr al abrir el dashboard (dashboard.bat ya lo invoca), o
  - una tarea programada de Windows para correrlo desatendido (ver README / ofrecer).

Uso:
  python loop.py            # cadencia de hoy
  python loop.py 2026-06-22 # cadencia de una fecha puntual
"""
import os, sys, datetime, traceback

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feedback, pnl, db, clv, bankroll, prop_value


def _step(name, fn):
    print("\n" + "=" * 70)
    print(f"  >> {name}")
    print("=" * 70)
    try:
        fn()
        return True
    except Exception as e:
        print(f"  [FALLO] {name}: {e}")
        traceback.print_exc()
        return False


def run(date=None):
    date = date or datetime.date.today().isoformat()
    print(f"  LOOP DEL SUPRA-MODELO  -  {date}  -  corrida {datetime.datetime.now().isoformat(timespec='seconds')}")
    steps = [
        ("CLV · snapshot de cuotas (para closing line value)", lambda: clv.snapshot(date)),
        ("Loop A · log WC pre-partido (anti-leakage)", lambda: feedback.log_wc(date)),
        ("Loop A · log MLB", lambda: feedback.log_mlb(date)),
        ("Loop A · eval (resuelve lo jugado)", feedback.evaluate),
        ("Loop A · re-fit recalibrador (Platt, shrink)", feedback.calibrate),
        ("Loop A · report de calibracion", feedback.report),
        ("Loop B · log candidatas de edge", lambda: pnl.log_bets(date)),
        ("Loop B · eval de apuestas", pnl.eval_bets),
        ("Loop B · forward-test del edge (ROI)", pnl.report),
        ("Loop C · props +EV multi-book · log flags (Linemate)", lambda: prop_value.log_props(date)),
        ("Persistencia · sync JSONL -> SQLite", lambda: _print_sync(db.sync())),
        ("Ledger · bankroll + drawdown + stop-loss", bankroll.report),
        ("CLV · report (precio tomado vs cierre)", clv.report),
    ]
    ok = sum(_step(n, f) for n, f in steps)
    print("\n" + "=" * 70)
    print(f"  CADENCIA COMPLETA: {ok}/{len(steps)} pasos OK")
    print("=" * 70)


def _print_sync(counts):
    for t, n in counts.items():
        print(f"    {t:<14} {n:>5} filas")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else None)
