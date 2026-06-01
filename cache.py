"""cache.py — caché de archivos JSON con TTL.

Reduce requests contra APIs con quota (The Odds API: 500/mes). Guarda la respuesta
cruda (JSON-serializable) en data/cache/ y la reusa si tiene menos de `ttl_sec`.
"""
import os, json, time, hashlib

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(ROOT, "data", "cache")


def cached(key, ttl_sec, fetcher):
    """Devuelve el valor cacheado si está fresco; si no, llama a fetcher() y lo guarda."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, hashlib.md5(key.encode()).hexdigest() + ".json")
    if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < ttl_sec:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    value = fetcher()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(value, f)
    except Exception:
        pass
    return value
