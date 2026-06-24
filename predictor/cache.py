"""cache.py - cache JSON con TTL, local al predictor (sin dependencias del proyecto viejo).

Evita re-fetchear durante el desarrollo. Las stats APIs (statsapi.mlb.com, etc.) son
gratis, asi que el TTL es por comodidad, no por quota.
"""
import os, json, time, hashlib

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cache")

# Politica de TTL por VOLATILIDAD del dato (la cache es el multiplicador de requests:
# cada fetch elige su TTL segun cuanto cambia el dato -> protege la quota escasa).
TTL_LIVE = 5 * 60                # lineups / abridor de hoy / clima: cambian hasta ~1h antes
TTL_SLATE = 60 * 60             # partidos del dia
TTL_RESULTS = 3 * 60 * 60       # resultados / scores recientes
TTL_HIST = 24 * 60 * 60         # game-logs, stats de temporada: casi estaticos en el dia
TTL_STATIC = 7 * 24 * 60 * 60   # perfiles historicos de equipo (corners/cards): dias


def _fetch_retry(fetcher, tries=3, backoff=1.2):
    """Llama a fetcher() con reintentos: las APIs (ESPN/statsapi) sueltan ConnectionReset
    transitorios -> reintentar evita que un blip de red tumbe un paso del loop."""
    for i in range(tries):
        try:
            return fetcher()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(backoff * (i + 1))


def cached(key, ttl_sec, fetcher):
    """Devuelve el valor cacheado si esta fresco; si no, llama a fetcher() y lo guarda."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, hashlib.md5(key.encode()).hexdigest() + ".json")
    if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < ttl_sec:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    value = _fetch_retry(fetcher)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(value, f)
    except Exception:
        pass
    return value
