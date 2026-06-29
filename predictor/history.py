"""history.py - historial de predicciones con resultado para el frontend.

Cruza predictions/ + evaluations/ y devuelve los ultimos N dias
agrupados por partido, listos para el tab Track Record.
"""
import os, json, glob
from collections import defaultdict

ROOT     = os.path.dirname(os.path.abspath(__file__))
PRED_DIR = os.path.join(ROOT, "predictions")
EVAL_DIR = os.path.join(ROOT, "evaluations")

MARKET_LABEL = {
    "1x2:home": "Local gana",  "1x2:draw": "Empate",  "1x2:away": "Visita gana",
    "dc:1x": "DC Local/Emp",   "dc:x2": "DC Emp/Vis", "dc:12": "DC Sin empate",
    "over:1.5": "Goles +1.5",  "over:2.5": "Goles +2.5", "over:3.5": "Goles +3.5",
    "btts:yes": "Ambos anotan",
    "corners:over:8.5": "Corners +8.5", "corners:over:9.5": "Corners +9.5",
    "corners:over:10.5": "Corners +10.5",
    "cards:over:2.5": "Tarjetas +2.5",  "cards:over:3.5": "Tarjetas +3.5",
    "cards:over:4.5": "Tarjetas +4.5",
    "ml:home": "ML Local",
}


def _load_jsonl(directory, days=None):
    """Carga todos los JSONL de directory (opcional: solo los ultimos `days` archivos)."""
    files = sorted(glob.glob(os.path.join(directory, "*.jsonl")), reverse=True)
    if days:
        files = files[:days]
    rows = []
    for f in files:
        for line in open(f, encoding="utf-8-sig"):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def recent_games(days=14):
    """Devuelve los ultimos `days` dias de partidos evaluados.

    Retorna lista de dicts:
      {date, home, away, result, picks: [{market_label, prob, outcome, correct}]}
    ordenada por fecha desc.
    """
    preds = _load_jsonl(PRED_DIR, days=days)
    evals = _load_jsonl(EVAL_DIR, days=days)

    # indice de evaluaciones por (date, home, away, market)
    eval_idx = {}
    for e in evals:
        key = (e["date"], e["home"], e["away"], e["market"])
        eval_idx[key] = e

    # agrupar predicciones por partido
    games = defaultdict(lambda: {"picks": [], "result": None})
    for p in preds:
        gk = (p["date"], p["home"], p["away"])
        ev = eval_idx.get((p["date"], p["home"], p["away"], p["market"]))
        if ev is None:
            continue  # sin resultado todavia
        games[gk]["result"] = ev.get("result")
        games[gk]["picks"].append({
            "market": p["market"],
            "label": MARKET_LABEL.get(p["market"], p["market"]),
            "prob": round(p["prob"], 4),
            "outcome": ev["outcome"],
        })

    out = []
    for (date, home, away), g in games.items():
        if not g["picks"]:
            continue
        out.append({"date": date, "home": home, "away": away,
                    "result": g["result"], "picks": g["picks"]})

    out.sort(key=lambda x: x["date"], reverse=True)
    return out
