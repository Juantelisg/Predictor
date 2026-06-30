"""app.py - backend del dashboard del predictor (FastAPI). CERO cuotas.

Sirve dashboard.html y expone los analisis que ya generamos por CLI como JSON:
  /api/mlb/today      -> lectura MLB del dia (favorito + abridores)
  /api/soccer/today   -> partidos de selecciones de hoy (1X2 + totales + BTTS)
  /api/budget         -> presupuesto de la API escasa

Levantar (local):
  uvicorn predictor.app:app --port 8900
  -> http://localhost:8900

Deploy (Render): ver render.yaml en la raiz del repo.
"""
import os, sys, datetime, json
from dotenv import load_dotenv
load_dotenv()

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from fastapi import FastAPI, Body
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import mlb, soccer, slate, budget, cache, analizar, linemate, odds, edge, uncertainty, cartera, ticket
import track, history

app = FastAPI(title="Predictor")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Sirve el build de React (frontend/dist/). Fallback: si no existe el build, sigue funcionando sin él.
DIST = os.path.join(ROOT, "..", "frontend", "dist")
if os.path.isdir(os.path.join(DIST, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST, "assets")), name="assets")
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
    react = os.path.join(DIST, "index.html")
    if os.path.exists(react):
        return FileResponse(react)
    return FileResponse(os.path.join(ROOT, "dashboard.html"))


@app.get("/favicon.svg")
def favicon():
    f = os.path.join(DIST, "favicon.svg")
    return FileResponse(f) if os.path.exists(f) else FileResponse(os.path.join(ROOT, "favicon.svg"), status_code=404)


@app.get("/icons.svg")
def icons():
    f = os.path.join(DIST, "icons.svg")
    return FileResponse(f) if os.path.exists(f) else FileResponse(os.path.join(ROOT, "icons.svg"), status_code=404)


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


def _edge_for(an, date):
    """Edge 1X2: modelo CALIBRADO vs cuota ESPN de-vigeada -> veredicto/tier. None si no hay cuota."""
    if not an or an.get("error") or not an.get("resultado"):
        return None
    try:
        od = odds.wc_1x2(an["home"], an["away"], date)
    except Exception:
        od = None
    if not od:
        return None
    model = [r["cal"] for r in an["resultado"]]                 # prob calibrada (Fase 1)
    conf = uncertainty.confidence("1x2", soccer.VERSION)        # confianza por n efectiva (Fase 5)
    rows = edge.edge_market(model, [od["home"], od["draw"], od["away"]], "1x2", confidence=conf)
    labels = [an["home"], "Empate", an["away"]]
    return {"provider": od["provider"],
            "rows": [{"label": labels[i], "p_model": r["p_model"], "p_market": r["p_market"],
                      "edge": r["edge"], "odds": r["odds"], "tier": r["tier"], "amount": r.get("amount", 0)}
                     for i, r in enumerate(rows)]}


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
                      "analysis_error": an.get("error"), "lectura": lect.get(gid),
                      "edge": _edge_for(an, d_art)})
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


@app.get("/api/cartera")
def api_cartera(date: str = None):
    """Cartera del dia: tickets armados con los picks confiables del Mundial (mismas tarjetas
    que el tab), con su tajada por $1 de pote. El monto lo escala el frontend en vivo (share x pote)."""
    date = date or datetime.date.today().isoformat()
    try:
        wc = cache.cached(f"cards_wc:{date}", TTL, lambda: _compute_wc(date))   # reusa las tarjetas del tab
        return cache.cached(f"cartera:{date}", TTL, lambda: cartera.build(wc.get("cards", [])))
    except Exception as e:
        return {"date": date, "tickets": [], "error": str(e)}


def _ticket_prose(prompt, timeout=240):
    """Redacta la lectura del ticket via Anthropic SDK (requiere ANTHROPIC_API_KEY).
    Devuelve el texto generado, o None si no hay key / falla (el caller usa fallback)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return (msg.content[0].text or "").strip() or None
    except Exception:
        return None


def _ticket_quant(date, kind, legs):
    """Veredicto cuantitativo del ticket reusando las tarjetas YA cacheadas del tab Mundial
    (los mismos numeros del motor de siempre: analizar.analyze). Devuelve (data, lect_by_match)."""
    wc = cache.cached(f"cards_wc:{date}", TTL, lambda: _compute_wc(date))
    an_by_match, lect_by_match = {}, {}
    for c in wc.get("cards", []):
        key = f'{c["home"]} vs {c["away"]}'
        an_by_match[key] = c.get("analysis")
        lect_by_match[key] = c.get("lectura")
    return ticket.analyze_ticket(legs, kind, an_by_match), lect_by_match


@app.post("/api/ticket/analyze")
def api_ticket(payload: dict = Body(...)):
    """Veredicto cuantitativo del ticket del usuario (modelo calibrado vs cuota, edge, combo).
    INSTANTANEO (sin Claude) -> el front lo muestra ya; la lectura llega aparte por /lectura.
    payload = {date?, kind: combinada|simples, legs: [{match, market, pick, cuota, label?}]}."""
    date = payload.get("date") or datetime.date.today().isoformat()
    legs = payload.get("legs", [])
    if not legs:
        return {"error": "ticket vacio: agrega al menos una pierna"}
    try:
        data, _ = _ticket_quant(date, payload.get("kind", "combinada"), legs)
        return {"date": date, "quant": data}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/ticket/lectura")
def api_ticket_lectura(payload: dict = Body(...)):
    """Lectura en vivo del ticket (claude -p; fallback determinista). Endpoint aparte para no
    bloquear el veredicto: el front muestra el quant al instante y rellena esto cuando llega."""
    date = payload.get("date") or datetime.date.today().isoformat()
    legs = payload.get("legs", [])
    if not legs:
        return {"error": "ticket vacio"}
    try:
        data, lect_by_match = _ticket_quant(date, payload.get("kind", "combinada"), legs)
        prose = _ticket_prose(ticket.prompt_for(data, lect_by_match))
        return {"prose": prose or ticket.fallback_lectura(data, lect_by_match),
                "prose_source": "claude" if prose else "fallback"}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/budget")
def api_budget():
    return budget.status()


# ── Track Record ─────────────────────────────────────────────────────────────

@app.get("/api/track-record")
def api_track_record(market: str = None):
    """Calibración del modelo: reliability diagram, Brier, ECE.
    ?market=1x2|over|btts|corners|cards|dc (None = todos)"""
    try:
        calib  = cache.cached(f"track:calib:{market}", 3600,
                              lambda: track.calibration_data(market))
        mkts   = cache.cached("track:by_market", 3600, track.by_market_summary)
        roi    = cache.cached("track:roi", 3600, track.roi_summary)
        return {"calibration": calib, "by_market": mkts, "roi": roi}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/history")
def api_history(days: int = 14):
    """Ultimos `days` dias de partidos evaluados con resultado por pick."""
    try:
        return cache.cached(f"history:{days}", 1800,
                            lambda: {"games": history.recent_games(days)})
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/edge/today")
def api_edge_today(date: str = None):
    """Edge matrix: todos los partidos del dia x todos los mercados x edge vs ESPN.
    Reutiliza las tarjetas WC ya cacheadas."""
    date = date or datetime.date.today().isoformat()
    try:
        wc = cache.cached(f"cards_wc:{date}", TTL, lambda: _compute_wc(date))
        rows = []
        for c in wc.get("cards", []):
            if not c.get("edge"):
                continue
            rows.append({
                "home": c["home"], "away": c["away"],
                "time": c.get("time"), "home_flag": c.get("home_flag"),
                "away_flag": c.get("away_flag"),
                "markets": c["edge"]["rows"],
                "provider": c["edge"]["provider"],
            })
        rows.sort(key=lambda r: max((m["edge"] for m in r["markets"]), default=0), reverse=True)
        return {"date": date, "rows": rows}
    except Exception as e:
        return {"date": date, "rows": [], "error": str(e)}
