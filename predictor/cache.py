"""cache.py - cache JSON con TTL, local al predictor (sin dependencias del proyecto viejo).

Evita re-fetchear durante el desarrollo. Las stats APIs (statsapi.mlb.com, etc.) son
gratis, asi que el TTL es por comodidad, no por quota.

En produccion (Render free) el disco es efimero: si el write falla, cae al in-memory
fallback (_MEM_CACHE). La semantica es la misma; solo se pierde entre reinicios.
"""
import os, json, time, hashlib, threading

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cache")

# fallback in-memory: {key: (value, expires_at)}
_MEM_CACHE: dict = {}

# single-flight: un lock por key para que varios llamadores concurrentes de la MISMA key
# (ej. el precalentamiento del arranque + el primer request del front) compartan un solo
# computo en vez de duplicarlo. Vital en Render free (0.1 vCPU): sin esto, 2 hilos harian
# el fetch de ~8s en paralelo y se estorban.
_LOCKS: dict = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(key):
    with _LOCKS_GUARD:
        lk = _LOCKS.get(key)
        if lk is None:
            lk = _LOCKS[key] = threading.Lock()
        return lk


def _read_fresh(key, ttl_sec, now):
    """(hit, value) leyendo mem + disco SIN fetchear. hit=False si no hay valor fresco."""
    if key in _MEM_CACHE:
        val, exp = _MEM_CACHE[key]
        if now < exp:
            return True, val
    try:
        path = os.path.join(CACHE_DIR, hashlib.md5(key.encode()).hexdigest() + ".json")
        if os.path.exists(path) and (now - os.path.getmtime(path)) < ttl_sec:
            with open(path, encoding="utf-8") as f:
                return True, json.load(f)
    except Exception:
        pass
    return False, None

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


def peek(key, ttl_sec):
    """Lee el cache SIN fetchear: devuelve el valor si esta fresco, None si no.
    Para endpoints no bloqueantes que disparan el build pesado en segundo plano."""
    hit, val = _read_fresh(key, ttl_sec, time.time())
    return val if hit else None


def cached(key, ttl_sec, fetcher):
    """Devuelve el valor cacheado si esta fresco; si no, llama a fetcher() y lo guarda.
    Intenta disco primero; si falla (filesystem de solo lectura / sin permisos) cae a memoria."""
    # 1. fast path sin lock: valor fresco en mem o disco
    hit, val = _read_fresh(key, ttl_sec, time.time())
    if hit:
        return val

    # 2. single-flight: un solo hilo computa por key; el resto espera y reusa el resultado
    with _lock_for(key):
        hit, val = _read_fresh(key, ttl_sec, time.time())   # otro hilo pudo poblarla mientras esperabamos
        if hit:
            return val

        value = _fetch_retry(fetcher)

        # 3. guardar en disco si es posible, siempre en memoria
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            path = os.path.join(CACHE_DIR, hashlib.md5(key.encode()).hexdigest() + ".json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(value, f)
        except Exception:
            pass
        _MEM_CACHE[key] = (value, time.time() + ttl_sec)
        return value
