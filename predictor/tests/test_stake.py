"""Staking Kelly fraccional: PASAR sin EV/confianza, cap duro, y tier/monto cuando hay valor."""
import stake


def test_pass_low_ev():
    r = stake.stake(0.50, 1.95, 0.7)          # EV negativo
    assert r["tier"] == "PASAR"


def test_pass_low_confidence():
    r = stake.stake(0.60, 2.00, 0.30)         # conf < MIN_CONF
    assert r["tier"] == "PASAR"


def test_cap_never_exceeded():
    r = stake.stake(0.90, 2.00, 1.0)          # edge enorme -> Kelly grande, pero capeado
    assert r["frac"] <= stake.CAP + 1e-9


def test_valid_bet_sizes():
    r = stake.stake(0.55, 2.10, 0.7, bankroll=1000.0)
    assert r["tier"] in ("FUERTE", "MODERADO", "BAJO")
    assert r["amount"] > 0
    assert abs(r["amount"] - r["frac"] * 1000.0) < 0.5   # frac y amount se redondean por separado


def test_confidence_scales_stake():
    hi = stake.stake(0.55, 2.10, 0.9)
    lo = stake.stake(0.55, 2.10, 0.5)
    assert hi["frac"] >= lo["frac"]           # mas confianza -> stake >=
