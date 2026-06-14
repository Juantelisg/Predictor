"""app.py - backend del dashboard del predictor (FastAPI). CERO cuotas.

Sirve dashboard.html y expone los analisis que ya generamos por CLI como JSON:
  /api/mlb/today      -> lectura MLB del dia (favorito + abridores)
  /api/soccer/today   -> partidos de selecciones de hoy (1X2 + totales + BTTS)
  /api/budget         -> presupuesto de la API escasa

Levantar:
  C:/Users/Juant/AppData/Local/Python/bin/python.exe -m uvicorn app:app --port 8900 --app-dir predictor
  -> http://localhost:8900
"""
import os, sys, datetime
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from fastapi import FastAPI
from fastapi.responses import FileResponse
import mlb, soccer, slate, budget, cache

app = FastAPI(title="Predictor")
MLB_CAT, SOC_CAT = "#5b9cff", "#5eead4"   # color de categoria (borde lateral)
TTL = 600                                  # cache de resultados 10 min -> tabs instantaneos


@app.get("/")
def index():
    return FileResponse(os.path.join(ROOT, "dashboard.html"))


def _lvl(p):
    return "ALTA" if p >= 0.65 else "MEDIA" if p >= 0.55 else "BAJA"


def _logro(market, pick, p):
    return {"market": market, "pick": pick, "prob": round(p * 100), "level": _lvl(p)}


def _soccer_logros(g):
    """Varios mercados (logros) de un partido, derivados del MISMO modelo."""
    b, L, V = g["blend"], g["local"], g["visita"]
    fav = max(b, key=b.get)
    out = [_logro("Resultado", ("Gana " + (L if fav == 1 else V)) if fav != 0 else "Empate", b[fav])]
    dc = {"1X": (b[1] + b[0], f"{L} o empate"), "X2": (b[0] + b[-1], f"{V} o empate"),
          "12": (b[1] + b[-1], "Sin empate")}
    k = max(dc, key=lambda x: dc[x][0])
    out.append(_logro("Doble oport.", dc[k][1], dc[k][0]))
    out.append(_logro("Goles", "+1.5", g["over15"]))
    out.append(_logro("Goles", "Over 2.5", g["over"]) if g["over"] >= 0.5
               else _logro("Goles", "Under 2.5", 1 - g["over"]))
    out.append(_logro("BTTS", "Sí", g["btts"]) if g["btts"] >= 0.5
               else _logro("BTTS", "No", 1 - g["btts"]))
    return out


def _compute_mlb(date):
    preds, _ = mlb.predict_today(date)
    cards = [{"cat": MLB_CAT, "tag": "MLB", "rank": i + 1, "home": g["home"], "away": g["away"],
              "hprob": round(g["prob"] * 100), "hlevel": g["level"],
              "logros": [_logro("Ganador · ML", g["pick"], g["prob"])], "analisis": g["insights"]}
             for i, g in enumerate(preds)]
    return {"date": date, "note": "modelo validado · 57% acc (2025) · solo Moneyline por ahora · score = probabilidad",
            "cards": cards}


def _compute_soccer(date):
    fx = slate.soccer_today(date)
    preds = soccer.predict_fixtures([(g["home"], g["away"], True) for g in fx])   # WC = neutral
    preds.sort(key=lambda x: x["prob_top"], reverse=True)
    cards = [{"cat": SOC_CAT, "tag": "WC", "rank": i + 1, "home": g["local"], "away": g["visita"],
              "hprob": round(g["prob_top"] * 100), "hlevel": g["level"],
              "logros": _soccer_logros(g), "analisis": g["insights"]}
             for i, g in enumerate(preds)]
    return {"date": date, "note": "modelo validado · 60% acc 1X2 · score = probabilidad, no apuesta",
            "cards": cards}


@app.get("/api/mlb/today")
def mlb_today(date: str = None):
    date = date or datetime.date.today().isoformat()
    try:
        return cache.cached(f"cards_mlb:{date}", TTL, lambda: _compute_mlb(date))
    except Exception as e:
        return {"date": date, "cards": [], "error": str(e)}


@app.get("/api/soccer/today")
def soccer_today(date: str = None):
    date = date or datetime.date.today().isoformat()
    try:
        return cache.cached(f"cards_soccer:{date}", TTL, lambda: _compute_soccer(date))
    except Exception as e:
        return {"date": date, "cards": [], "error": str(e)}


@app.get("/api/budget")
def api_budget():
    return budget.status()
