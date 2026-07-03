"""lecturas_auto.py - genera las lecturas del dia via la API de Anthropic (con web search),
para que Render sea AUTOSUFICIENTE: no necesita el CLI de Claude ni el .bat.

Se dispara al primer request tras arrancar la app (background, gateado): si faltan lecturas de
HOY y hay ANTHROPIC_API_KEY, las genera (bajas/XI reales por web search), las guarda y las
enriquece con el valor de mercado (Transfermarkt). Sin key -> no hace nada (el modelo sigue OK).

GATE clave: si ya existe la lectura committeada de hoy (generada local con el .bat y pusheada),
`lecturas.missing` devuelve [] -> NO regenera. Asi el usuario evita el costo de API committeando
local; y si no lo hace, Render se autoabastece. Ojo: en Render free el disco es efimero -> si no
esta committeada, se regenera una vez por vida del contenedor (costo de API por arranque frio).
"""
import os, sys, re, json, datetime, threading

sys.stdout.reconfigure(encoding="utf-8")

MODEL = os.environ.get("LECTURAS_MODEL", "claude-opus-4-8")   # el usuario puede bajar el costo
_lock = threading.Lock()
_tried = set()                                                # fechas ya intentadas en este proceso

PROMPT = """Genera las lecturas de contexto en vivo del Mundial 2026 para el {date} (hora argentina).

Para CADA partido de abajo, usa la herramienta de busqueda web para conseguir bajas confirmadas, XI
probable, forma reciente y situacion de grupo, y redacta en espanol una lectura con estos 4 campos:
- summary: una linea con el veredicto.
- context: 6 vinetas (sede y hora ART; grupo y forma; bajas; XI probable; una senal cuantitativa; y
  la lectura del modelo integrando los numeros de abajo).
- sources: lista de 3 objetos {{"title","url"}} con enlaces reales.
- disponibilidad: objeto {{"home": {{"bajas": [{{"jugador","pos","impacto"}}], "motivacion": ""}}, "away": {{...}}}}
  orientado a LOCAL/VISITA del partido; impacto en clave|titular|duda|suplente; motivacion en
  must-win|dead-rubber|normal; usa bajas=[] si no hay bajas.

Partidos (con los numeros calibrados del modelo, para el ultimo bullet de context):
{packet}

Devolve SOLO un objeto JSON keyed por el gid de cada partido; sin texto alrededor y sin fences ```.
Cada valor es la lectura con los 4 campos."""


def _packet_text(date, faltan):
    """Material para redactar: por partido faltante, gid + numeros calibrados del modelo."""
    import analizar
    ctx = analizar.load_ctx()
    out = []
    for g in faltan:
        an = analizar.analyze(g["home"], g["away"], neutral=True, league="wc", ctx=ctx, date=date)
        if an.get("error"):
            continue
        r = an["resultado"]
        picks = ", ".join(f'{p["pick"]} {round(p["prob"]*100)}%' for p in an.get("picks", []))
        out.append(
            f'- gid {g["gid"]} | {g["home"]} (local) vs {g["away"]} (visita) - {g["time"]} ART\n'
            f'  1X2 calibrado: {g["home"]} {round(r[0]["cal"]*100)}% / empate {round(r[1]["cal"]*100)}% / {g["away"]} {round(r[2]["cal"]*100)}%\n'
            f'  picks confiables: {picks or "ninguno"}')
    return "\n".join(out)


def _extract_json(text):
    """Objeto JSON de la respuesta (tolera fences o texto alrededor). None si no parsea."""
    t = re.sub(r"```(?:json)?", "", text).strip()
    try:
        return json.loads(t)
    except Exception:
        m = re.search(r"\{.*\}", t, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


def _run(date):
    try:
        import lecturas, transfermarkt
        faltan = lecturas.missing(date)
        if not faltan:
            return
        packet = _packet_text(date, faltan)
        if not packet:
            return
        from anthropic import Anthropic
        client = Anthropic()
        messages = [{"role": "user", "content": PROMPT.format(date=date, packet=packet)}]
        tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 20}]
        resp = None
        for _ in range(10):                          # loop de server-tool (pause_turn)
            resp = client.messages.create(model=MODEL, max_tokens=8000,
                                          thinking={"type": "adaptive"}, tools=tools, messages=messages)
            if resp.stop_reason != "pause_turn":
                break
            messages.append({"role": "assistant", "content": resp.content})
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        data = _extract_json(text)
        if not isinstance(data, dict) or not data:
            return
        lecturas.save(date, data)                    # mergea sobre lo que haya
        transfermarkt.enrich_lectura(lecturas.path(date))
    except Exception:
        pass                                         # best-effort: el modelo sigue sin lecturas


def generate(date=None):
    """Dispara la generacion de las lecturas faltantes de `date` (hoy por defecto) en un thread.
    Gateado (1 intento por fecha por proceso) y no-op sin ANTHROPIC_API_KEY. No bloquea."""
    date = date or datetime.date.today().isoformat()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return
    with _lock:
        if date in _tried:
            return
        _tried.add(date)
    threading.Thread(target=_run, args=(date,), daemon=True).start()


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    print(f"  generando lecturas de {d} (modelo {MODEL}, key {'si' if os.environ.get('ANTHROPIC_API_KEY') else 'NO'})...")
    _run(d)
    print("  listo.")
