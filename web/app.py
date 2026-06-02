r"""web/app.py — backend del dashboard (estética Linemate).

Reusa el pipeline existente: scan.py para el análisis de equipos (consenso multi-book,
cuotas, confianza, edge) y availability.py para jugadores (abridores/lesionados/XI).
NO recalcula nada nuevo — expone lo que el modelo ya produce, en JSON, para el front.

Levantar:
    cd C:\bets
    C:\Users\Juant\AppData\Local\Python\bin\python.exe -m uvicorn web.app:app --port 8800
Abrir: http://localhost:8800
"""
import sys, os, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)   # para importar scan / availability del directorio padre

from fastapi import FastAPI
from fastapi.responses import FileResponse
import scan, availability
from sports_skills import markets

app = FastAPI()
WEB = os.path.dirname(os.path.abspath(__file__))

SPORTS = [{"key": "mlb", "label": "MLB"}, {"key": "nba", "label": "NBA"},
          {"key": "soccer", "label": "Fútbol"}]


@app.get("/")
def index():
    return FileResponse(os.path.join(WEB, "index.html"))


@app.get("/api/sports")
def sports():
    return SPORTS


@app.get("/api/slate")
def slate(sport: str = "mlb", date: str = None):
    """Partidos del día con análisis de EQUIPOS (ganador): confianza, cuota, edge."""
    date = date or datetime.date.today().isoformat()

    if sport == "soccer":   # 3 vías, otra fuente -> módulo aparte
        import soccer_odds
        games = soccer_odds.fetch_soccer_slate(date)
        for g in games:
            g["edge"] = None
            g["is_candidate"] = False   # fútbol no tiene ancla cross-source todavía
        return {"sport": sport, "date": date, "games": games}

    try:
        games = markets.get_todays_markets(sport=sport, date=date).get("data", {}).get("games", [])
    except Exception:
        return {"sport": sport, "date": date, "games": []}   # nunca 500: tab vacío
    book_odds = scan.fetch_book_odds(sport)
    out = []
    for g in games:
        hn, an = g["home"]["name"], g["away"]["name"]
        rec = {
            "event_id": g["event_id"], "away": an, "home": hn,
            "away_abbr": g["away"].get("abbreviation"), "home_abbr": g["home"].get("abbreviation"),
            "start_time": g.get("start_time"), "status": g.get("status"),
            "fair_home": None, "fair_away": None, "odds_home": None, "odds_home_book": None,
            "odds_away": None, "odds_away_book": None, "n_books": 0, "pm_home": None,
            "edge": None, "is_candidate": False,
        }
        # Solo análisis PRE-PARTIDO. Live/finalizado: las odds son en vivo y no sirven
        # para edge pregame -> se muestra el partido marcado, sin números engañosos.
        if g.get("status") == "not_started":
            entries = book_odds.get(frozenset({hn.lower(), an.lower()}))
            books = scan.pick_nearest(entries, g.get("start_time")) if entries else None
            cb = scan.consensus_and_best(books, hn, an) if books else None
            if cb:
                fair_h, fair_a, best_h, best_a, nb = cb
                pm_h, _pm_a, _liq, _spr = scan.polymarket_prices(sport, hn, an)
                edge = round(abs(fair_h - pm_h), 4) if pm_h is not None else None
                rec.update({
                    "fair_home": round(fair_h, 3), "fair_away": round(fair_a, 3),
                    "odds_home": best_h[1], "odds_home_book": best_h[0],
                    "odds_away": best_a[1], "odds_away_book": best_a[0],
                    "n_books": nb, "pm_home": round(pm_h, 3) if pm_h is not None else None,
                    "edge": edge, "is_candidate": bool(edge and edge >= scan.MODERATE_MIN),
                })
        out.append(rec)
    return {"sport": sport, "date": date, "games": out}


@app.get("/api/recommendations")
def recommendations(date: str = None):
    """Jugadas que Opus recomendó (predictions/ con action=APOSTAR) para la fecha."""
    import json
    date = date or datetime.date.today().isoformat()
    path = os.path.join(ROOT, "predictions", f"{date}.jsonl")
    recs = []
    if os.path.exists(path):
        for line in open(path, encoding="utf-8-sig"):
            line = line.strip()
            if not line:
                continue
            try:
                p = json.loads(line)
            except Exception:
                continue
            if p.get("action") != "APOSTAR":
                continue
            recs.append({
                "match": p.get("match"), "selection": p.get("selection"),
                "sport": p.get("sport"), "bet_type": p.get("bet_type"),
                "model_prob": p.get("model_prob"), "market_prob": p.get("market_prob"),
                "edge": p.get("edge"), "book_odds": p.get("book_odds_american") or p.get("book_odds"),
                "book": p.get("book"), "stake_pct": p.get("stake_pct"),
                "confidence": p.get("confidence"), "reason": p.get("reasoning_summary"),
            })
    return {"date": date, "recommendations": recs}


@app.get("/api/players")
def players(sport: str, home: str = None, away: str = None, event_id: str = None, date: str = None):
    """Disponibilidad de JUGADORES de un partido (abridores/lesionados/XI). Props: pendiente."""
    date = date or datetime.date.today().isoformat()
    if sport == "mlb":
        av = availability.for_game("mlb", date=date)
        match = f"{away} @ {home}"
        return {"type": "mlb", "starters": av["starters"].get(match), "lineup": av["lineups"].get(match)}
    if sport == "nba":
        return availability.for_game("nba", home=home, away=away)
    return availability.for_game(sport, event_id=event_id)
