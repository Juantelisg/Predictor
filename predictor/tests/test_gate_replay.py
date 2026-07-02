"""Gate-replay (pendiente 2): re-puntuar candidatas forward-logueadas con los gates de edge-v2
aplicables por-apuesta (cap de longshot + excluir empates = proxy del gate de regimen)."""
import pnl


def _e(side, odds, won):
    return {"side": side, "odds": odds, "won": won, "pnl_flat": 10.0 * (odds - 1) if won else -10.0}


def test_gates_drop_longshots():
    rows = [_e("home", 2.0, 1), _e("away", 5.0, 0), _e("home", 3.9, 1)]
    kept = pnl._apply_gates(rows, 4.0)
    assert len(kept) == 2 and all(e["odds"] <= 4.0 for e in kept)   # cuota 5.0 (longshot) fuera


def test_gates_drop_draws():
    rows = [_e("home", 2.0, 1), _e("draw", 3.0, 0), _e("away", 2.5, 1)]
    kept = pnl._apply_gates(rows, 4.0)
    assert all(e["side"] != "draw" for e in kept) and len(kept) == 2


def test_gates_keep_qualifying_favorites():
    rows = [_e("home", 1.8, 1), _e("away", 2.6, 1)]
    assert pnl._apply_gates(rows, 4.0) == rows                       # ambas pasan (no longshot, no empate)
