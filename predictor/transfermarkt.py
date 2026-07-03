"""transfermarkt.py - valor de mercado (€) de un jugador desde Transfermarkt. BEST-EFFORT.

Aporta lo que ni ESPN ni API-Football dan: una medida OBJETIVA de importancia del jugador,
para pesar cuanto duele una baja (un titular de 80M != un suplente de 3M). Alimenta al sensor
(sensor._severity usa 'valor' si esta presente).

ADVERTENCIA: es scraping. (1) viola los ToS de Transfermarkt -> uso personal/educativo; (2) el
HTML puede cambiar y romper el parser; (3) pueden empezar a bloquear (Cloudflare) cuando quieran.
Por eso: cacheado 30 dias (el valor cambia por mes), degrada a None en cualquier fallo, y NO se
llama en el path de render salvo que se active con env SENSOR_MARKET_VALUE=1.
"""
import sys, re
import requests
import cache

sys.stdout.reconfigure(encoding="utf-8")
BASE = "https://www.transfermarkt.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/120 Safari/537.36"}
TTL = 30 * 24 * 3600             # el valor de mercado cambia por mes, no por dia


def _get(url):
    return cache.cached(f"tm:{url}", TTL, lambda: requests.get(url, headers=HEADERS, timeout=20).text)


def _parse_value(html):
    """€ del bloque data-header__market-value-wrapper -> int en euros, o None.
    Formato: <span class="waehrung">€</span>60.00<span class="waehrung">m</span>."""
    m = re.search(r'market-value-wrapper.*?waehrung">[^<]*</span>\s*([\d.,]+)\s*<span[^>]*>\s*([mkbn]+)',
                  html, re.S | re.I)
    if not m:
        return None
    num = float(m.group(1).replace(",", ""))
    unit = m.group(2).lower()
    mult = {"bn": 1_000_000_000, "m": 1_000_000, "k": 1_000}.get(unit, 1)
    return int(num * mult)


def market_value(name):
    """Valor de mercado (€, int) del jugador, o None. Cacheado 30d, best-effort (None si falla)."""
    try:
        q = requests.utils.quote(name)
        search = _get(f"{BASE}/schnellsuche/ergebnis/schnellsuche?query={q}")
        link = re.search(r'href="(/[^"]+/profil/spieler/\d+)"', search)
        if not link:
            return None
        return _parse_value(_get(BASE + link.group(1)))
    except Exception:
        return None


def main():
    for name in (sys.argv[1:] or ["Harry Kane", "Lamine Yamal", "Nico Williams"]):
        v = market_value(name)
        print(f"  {name:<20} -> {('€%.1fM' % (v / 1e6)) if v else 'None'}")


if __name__ == "__main__":
    main()
