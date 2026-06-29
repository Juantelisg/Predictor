"""track.py - metricas de calibracion y ROI desde evaluations/ y bet_evals/.

Lee los JSONL locales y devuelve estructuras listas para el frontend:
  calibration_data()  -> reliability diagram + brier + ECE
  roi_summary()       -> PnL por tier desde bet_evals/
"""
import os, json, glob, math
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
EVAL_DIR = os.path.join(ROOT, "evaluations")
BET_DIR  = os.path.join(ROOT, "bet_evals")

N_BUCKETS = 10  # deciles 0-10%, 10-20%, ..., 90-100%


def _load_evals(market_filter=None):
    rows = []
    for f in sorted(glob.glob(os.path.join(EVAL_DIR, "*.jsonl"))):
        for line in open(f, encoding="utf-8-sig"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if market_filter is None or r.get("market", "").startswith(market_filter):
                    rows.append(r)
            except Exception:
                pass
    return rows


def _load_bet_evals():
    rows = []
    for f in sorted(glob.glob(os.path.join(BET_DIR, "*.jsonl"))):
        for line in open(f, encoding="utf-8-sig"):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def calibration_data(market_prefix=None):
    """Reliability diagram (N_BUCKETS deciles), Brier score y ECE.

    market_prefix: None = todos, '1x2' = solo 1X2, 'over' = goles, etc.
    """
    rows = _load_evals(market_filter=market_prefix)
    if not rows:
        return {"buckets": [], "brier": None, "ece": None, "n": 0, "acc": None}

    buckets = [{"label": f"{i*10}-{(i+1)*10}%", "lo": i/N_BUCKETS, "hi": (i+1)/N_BUCKETS,
                "n": 0, "n_correct": 0, "sum_prob": 0.0}
               for i in range(N_BUCKETS)]

    brier_sum = 0.0
    n_total = len(rows)
    n_correct = 0

    for r in rows:
        p = float(r["prob"])
        o = int(r["outcome"])
        brier_sum += (p - o) ** 2
        if o == 1:
            n_correct += 1
        idx = min(int(p * N_BUCKETS), N_BUCKETS - 1)
        b = buckets[idx]
        b["n"] += 1
        b["n_correct"] += o
        b["sum_prob"] += p

    brier = round(brier_sum / n_total, 4)
    acc = round(n_correct / n_total, 4)

    ece_sum = 0.0
    out_buckets = []
    for b in buckets:
        if b["n"] == 0:
            out_buckets.append({"label": b["label"], "n": 0,
                                "actual_rate": None, "avg_prob": None})
            continue
        actual = b["n_correct"] / b["n"]
        avg_p  = b["sum_prob"]  / b["n"]
        ece_sum += (b["n"] / n_total) * abs(actual - avg_p)
        out_buckets.append({"label": b["label"], "n": b["n"],
                            "actual_rate": round(actual, 4),
                            "avg_prob": round(avg_p, 4)})

    return {"buckets": out_buckets, "brier": brier,
            "ece": round(ece_sum, 4), "n": n_total, "acc": acc}


def by_market_summary():
    """Brier y accuracy por familia de mercado."""
    families = {
        "1x2":     "1x2",
        "dc":      "dc",
        "over":    "over",
        "btts":    "btts",
        "corners": "corners",
        "cards":   "cards",
        "ml":      "ml",
    }
    out = {}
    for key, prefix in families.items():
        rows = _load_evals(market_filter=prefix)
        if not rows:
            continue
        n = len(rows)
        brier = sum((r["prob"] - r["outcome"]) ** 2 for r in rows) / n
        acc   = sum(r["outcome"] for r in rows) / n
        out[key] = {"n": n, "brier": round(brier, 4), "acc": round(acc, 4)}
    return out


def roi_summary():
    """PnL y win-rate agrupados por tier desde bet_evals/."""
    rows = _load_bet_evals()
    if not rows:
        return {"tiers": {}, "total": {"n": 0, "pnl": 0, "pnl_flat": 0}}

    tiers = defaultdict(lambda: {"n": 0, "won": 0, "pnl": 0.0, "pnl_flat": 0.0})
    total = {"n": 0, "won": 0, "pnl": 0.0, "pnl_flat": 0.0}

    for r in rows:
        t = r.get("tier", "?")
        tiers[t]["n"] += 1
        tiers[t]["won"] += int(r.get("won", 0))
        tiers[t]["pnl"] += float(r.get("pnl", 0))
        tiers[t]["pnl_flat"] += float(r.get("pnl_flat", 0))
        total["n"] += 1
        total["won"] += int(r.get("won", 0))
        total["pnl"] += float(r.get("pnl", 0))
        total["pnl_flat"] += float(r.get("pnl_flat", 0))

    out_tiers = {}
    for t, d in tiers.items():
        wr = round(d["won"] / d["n"], 4) if d["n"] else None
        out_tiers[t] = {"n": d["n"], "won": d["won"], "win_rate": wr,
                        "pnl": round(d["pnl"], 2), "pnl_flat": round(d["pnl_flat"], 2)}

    total["win_rate"] = round(total["won"] / total["n"], 4) if total["n"] else None
    total["pnl"]      = round(total["pnl"], 2)
    total["pnl_flat"] = round(total["pnl_flat"], 2)
    return {"tiers": out_tiers, "total": total}
