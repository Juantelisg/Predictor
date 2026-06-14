"""budget.py - guardia de presupuesto de la API ESCASA (API-Football, 100 requests/dia).

API-Football es el unico cuello de botella real del sistema: las demas fuentes (statsapi,
ESPN, CSV internacional, nflverse) son ilimitadas, y football-data.org/nba_api solo piden
espaciar por minuto. Antes de gastar una request escasa, consultar can_spend().

El endpoint /status NO consume quota, asi que medir el presupuesto es gratis.
"""
import os, sys, requests

ROOT = os.path.dirname(os.path.abspath(__file__))
BASE = "https://v3.football.api-sports.io"
RESERVE = 10        # colchon: no bajar de 10 requests (margen para el momento clave del dia)


def _key():
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if line.startswith("API_FOOTBALL_KEY="):
                return line.strip().split("=", 1)[1]
    return ""


KEY = _key()
HEADERS = {"x-apisports-key": KEY}


def status():
    """Uso de hoy SIN consumir quota. {used, limit, remaining, plan, active}."""
    try:
        r = requests.get(f"{BASE}/status", headers=HEADERS, timeout=15).json().get("response", {}) or {}
        req = r.get("requests", {}) or {}
        sub = r.get("subscription", {}) or {}
        used, limit = req.get("current", 0), req.get("limit_day", 100)
        return {"used": used, "limit": limit, "remaining": max(limit - used, 0),
                "plan": sub.get("plan"), "active": sub.get("active")}
    except Exception as e:
        return {"used": None, "limit": None, "remaining": 0, "plan": None, "active": None, "error": str(e)}


def can_spend(n=1, reserve=RESERVE):
    """True si quedan al menos n+reserve requests hoy. Usar antes de un fetch escaso."""
    return status()["remaining"] >= n + reserve


def guard(n=1, reserve=RESERVE):
    """Lanza RuntimeError si no hay presupuesto -> el caller degrada a fuentes gratis."""
    if not can_spend(n, reserve):
        s = status()
        raise RuntimeError(f"Presupuesto API-Football agotado: {s['remaining']} restantes, "
                           f"pediste {n} (reserva {reserve}). Degradar a fuentes gratis.")


if __name__ == "__main__":
    s = status()
    if s.get("error"):
        print(f"  API-Football: error -> {s['error']}")
        sys.exit(0)
    print(f"  API-Football  plan={s['plan']}  activa={s['active']}")
    print(f"  Usadas hoy: {s['used']}/{s['limit']}   Restantes: {s['remaining']}   (reserva {RESERVE})")
    print(f"  Se puede gastar 1 ahora: {can_spend(1)}   |   gastar 5: {can_spend(5)}")
