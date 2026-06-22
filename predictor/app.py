"""app.py - backend del dashboard del predictor (FastAPI). CERO cuotas.

Sirve dashboard.html y expone los analisis que ya generamos por CLI como JSON:
  /api/mlb/today      -> lectura MLB del dia (favorito + abridores)
  /api/soccer/today   -> partidos de selecciones de hoy (1X2 + totales + BTTS)
  /api/budget         -> presupuesto de la API escasa

Levantar:
  C:/Users/Juant/AppData/Local/Python/bin/python.exe -m uvicorn app:app --port 8900 --app-dir predictor
  -> http://localhost:8900
"""
import os, sys, datetime, json
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from fastapi import FastAPI
from fastapi.responses import FileResponse
import mlb, soccer, slate, budget, cache, analizar, linemate

app = FastAPI(title="Predictor")
MLB_CAT, SOC_CAT = "#5b9cff", "#5eead4"   # color de categoria (borde lateral)
TTL = 600                                  # cache de resultados 10 min -> tabs instantaneos
LECT_DIR = os.path.join(ROOT, "data", "lecturas")   # lecturas (contexto en vivo) precomputadas

# codigo FIFA -> ISO2 para la bandera (flagcdn). Selecciones del Mundial 2026.
FIFA_ISO2 = {
    "NED": "nl", "SWE": "se", "GER": "de", "CIV": "ci", "CUW": "cw", "ECU": "ec", "JPN": "jp",
    "TUN": "tn", "KSA": "sa", "ESP": "es", "IRN": "ir", "BEL": "be", "CPV": "cv", "URU": "uy",
    "ARG": "ar", "BRA": "br", "FRA": "fr", "ENG": "gb-eng", "POR": "pt", "CRO": "hr", "USA": "us",
    "MEX": "mx", "CAN": "ca", "COL": "co", "ITA": "it", "SUI": "ch", "DEN": "dk", "POL": "pl",
    "SEN": "sn", "MAR": "ma", "NGA": "ng", "GHA": "gh", "KOR": "kr", "AUS": "au", "QAT": "qa",
    "SRB": "rs", "WAL": "gb-wls", "SCO": "gb-sct", "AUT": "at", "NOR": "no", "ALG": "dz",
    "IRQ": "iq", "JOR": "jo", "PAR": "py", "PER": "pe", "CHI": "cl", "CRC": "cr", "PAN": "pa",
    "HON": "hn", "EGY": "eg", "CMR": "cm", "RSA": "za", "UZB": "uz", "NZL": "nz", "HAI": "ht",
}


def _flag(code):
    iso = FIFA_ISO2.get((code or "").upper())
    return f"https://flagcdn.com/w160/{iso}.png" if iso else None


def _art(ts):
    """Timestamp UTC ISO de Linemate -> (fecha, 'HH:MM') en hora argentina (UTC-3, sin DST)."""
    dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")) - datetime.timedelta(hours=3)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")


def _load_lecturas(date):
    """Lecturas precomputadas (contexto en vivo) del dia. {} si no hay archivo."""
    p = os.path.join(LECT_DIR, f"{date}.json")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


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


def _compute_wc(date):
    """Partidos del Mundial de `date` (hora ARG) desde Linemate + analisis precomputado.
    Cada tarjeta trae: logos (bandera), hora ARG, el cuadro/picks del modelo y la lectura
    (contexto en vivo) si esta cacheada. Todo listo de entrada -> el desplegable es instantaneo."""
    games = linemate.games("wc")
    lect = _load_lecturas(date)
    ctx = analizar.load_ctx()                      # Elo se carga UNA vez para todos los partidos
    cards = []
    for g in games:
        ts = g.get("timestamp")
        if not ts:
            continue
        d_art, t_art = _art(ts)
        if d_art != date:                          # Linemate trae ventana movil -> filtrar por dia ARG
            continue
        h = g.get("homeTeamData", {}).get("info", {})
        a = g.get("awayTeamData", {}).get("info", {})
        gid = g.get("id")
        an = analizar.analyze(h.get("name", ""), a.get("name", ""), neutral=True,
                              lm_codes=[h.get("code"), a.get("code")], league="wc", ctx=ctx, date=d_art)
        cards.append({"gid": gid, "cat": SOC_CAT, "tag": "WC", "time": t_art, "date": d_art,
                      "status": g.get("status"), "home": h.get("name"), "away": a.get("name"),
                      "home_code": h.get("code"), "away_code": a.get("code"),
                      "home_flag": _flag(h.get("code")), "away_flag": _flag(a.get("code")),
                      "analysis": None if an.get("error") else an,
                      "analysis_error": an.get("error"), "lectura": lect.get(gid)})
    cards.sort(key=lambda c: c["time"])
    return {"date": date, "note": "Mundial 2026 · modelo estadistico (sin cuotas) · hora argentina · "
            "lectura = contexto en vivo precomputado", "cards": cards}


@app.get("/api/wc/today")
def wc_today(date: str = None):
    date = date or datetime.date.today().isoformat()
    try:
        return cache.cached(f"cards_wc:{date}", TTL, lambda: _compute_wc(date))
    except Exception as e:
        return {"date": date, "cards": [], "error": str(e)}


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
