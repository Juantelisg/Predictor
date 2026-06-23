"""lecturas.py - arma el PAQUETE para redactar las lecturas de contexto en vivo del dia.

La lectura que muestra el dashboard (summary + context + sources) la REDACTA un modelo con
investigacion en vivo (WebSearch): un script Python no puede buscar ni escribir prosa. Lo
que SI es reusable y vive aca: (1) listar los partidos del Mundial del dia con su `gid` de
Linemate, (2) adjuntar el snapshot del modelo (1X2 calibrado, totales, picks, XI) para tener
todo a la vista al redactar, y (3) cargar/guardar el JSON que consume app.py.

Flujo (la pieza creativa la pone el modelo, no el script). Lo orquesta dashboard.bat:
  - `lecturas.py missing` -> exit 1 si faltan lecturas hoy (gate rapido, sin red = no bloquea).
  - si faltan, el .bat invoca `claude -p` que: corre `packet`, investiga en vivo y escribe el JSON.
  - relanzar el mismo dia = `missing` da 0 -> arranque instantaneo (no se regenera).
  `lecturas.py packet [fecha]` es el material para redactar (gid + cuadro del modelo).

Schema de cada entrada (keyed por gid de Linemate, lo que espera app.py):
  "<gid>": {
    "summary": "veredicto en una linea",
    "context": ["sede/hora", "grupo/forma", "bajas", "XI probable", "senal cuant", "lectura del modelo"],
    "sources": [{"title": "...", "url": "..."}],
    "generated_at": "YYYY-MM-DD"
  }

Correr:  C:/Users/Juant/AppData/Local/Python/bin/python.exe predictor/lecturas.py packet [fecha]
"""
import os, sys, json, datetime
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

import linemate

LECT_DIR = os.path.join(ROOT, "data", "lecturas")   # mismo dir que lee app.py


def _art(ts):
    """Timestamp UTC ISO de Linemate -> (fecha, 'HH:MM') en hora argentina (UTC-3, sin DST)."""
    dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")) - datetime.timedelta(hours=3)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")


def path(date):
    return os.path.join(LECT_DIR, f"{date}.json")


def load(date):
    """Lecturas ya guardadas del dia. {} si no hay archivo."""
    p = path(date)
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8-sig") as f:
        return json.load(f)


def save(date, entries):
    """Mergea `entries` (gid -> lectura) sobre lo ya guardado y escribe el JSON utf-8."""
    os.makedirs(LECT_DIR, exist_ok=True)
    data = load(date)
    data.update(entries)
    with open(path(date), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return path(date)


def games_today(date):
    """Partidos del Mundial de `date` (hora ARG) desde Linemate: gid + equipos + hora."""
    out = []
    for g in linemate.games("wc"):
        ts = g.get("timestamp")
        if not ts:
            continue
        d_art, t_art = _art(ts)
        if d_art != date:                          # Linemate trae ventana movil -> filtrar por dia ARG
            continue
        h = g.get("homeTeamData", {}).get("info", {})
        a = g.get("awayTeamData", {}).get("info", {})
        out.append({"gid": g.get("id"), "home": h.get("name"), "away": a.get("name"),
                    "home_code": h.get("code"), "away_code": a.get("code"), "time": t_art,
                    "status": g.get("status")})
    out.sort(key=lambda x: x["time"])
    return out


def missing(date):
    """Estado de las lecturas del dia. Devuelve exit-code: 1 si falta alguna (gate del .bat), 0 si no.
    Tolerante: si no puede leer la slate (sin red), NO bloquea el arranque -> 0."""
    try:
        games = games_today(date)
    except Exception as e:
        print(f"  no pude leer la slate ({e}); sigo sin generar.")
        return 0
    if not games:
        print(f"  sin partidos WC hoy ({date}); nada que generar.")
        return 0
    falta = [g for g in games if g["gid"] not in load(date)]
    if falta:
        print(f"  faltan {len(falta)}/{len(games)} lecturas: "
              + ", ".join(f"{g['home']} vs {g['away']}" for g in falta))
        return 1
    print(f"  lecturas del dia completas ({len(games)}/{len(games)}).")
    return 0


def packet(date):
    """Imprime, por partido del dia: gid + snapshot del modelo (1X2 calibrado, totales, picks, XI).
    Es el material para redactar la lectura; deja claro que gids ya tienen lectura y cuales no."""
    import analizar                                  # import pesado solo cuando se necesita el cuadro
    games = games_today(date)
    have = load(date)
    pct = lambda x: f"{x*100:.0f}%"
    print(f"  PAQUETE DE LECTURAS  {date}  ({len(games)} partidos WC, hora ARG)\n")
    if not games:
        print("  (sin partidos del Mundial hoy)")
        return
    ctx = analizar.load_ctx()                       # carga/fitea una vez para todos
    for g in games:
        mark = "OK lectura ya escrita" if g["gid"] in have else "FALTA lectura"
        print("=" * 72)
        print(f"  {g['time']}  {g['home']} vs {g['away']}   [{g['gid']}]   -> {mark}")
        an = analizar.analyze(g["home"], g["away"], neutral=True,
                              lm_codes=[g["home_code"], g["away_code"]], league="wc", ctx=ctx, date=date)
        if an.get("error"):
            print(f"    modelo: {an['error']}")
            continue
        res = an["resultado"]
        print(f"    1X2 (calibrada):  {res[0]['label']} {pct(res[0]['cal'])}  ·  "
              f"{res[1]['label']} {pct(res[1]['cal'])}  ·  {res[2]['label']} {pct(res[2]['cal'])}")
        gl = an["goles"]
        print(f"    Goles: O1.5 {pct(gl['over15'])}  O2.5 {pct(gl['over25'])}  BTTS {pct(gl['btts'])}   "
              f"Valla: {an['home']} {pct(an['valla']['home'])}  {an['away']} {pct(an['valla']['away'])}")
        if an["picks"]:
            print("    Picks: " + "  ·  ".join(f"{p['pick']} {pct(p['prob'])}" for p in an["picks"]))
        av = an.get("availability")
        if av:
            for side in ("home", "away"):
                x = av.get(side)
                if x and x.get("starters"):
                    print(f"    XI {an[side]}: {x.get('formation','')} - "
                          + ", ".join(p["name"] for p in x["starters"][:11]))
    print("=" * 72)
    print(f"\n  Redactar las que digan FALTA y guardarlas en {path(date)}")


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "packet"
    date = next((a for a in args[1:] if not a.startswith("--")), datetime.date.today().isoformat())
    if cmd == "packet":
        packet(date)
    elif cmd == "missing":
        sys.exit(missing(date))
    else:
        print(f"  Uso: lecturas.py [packet|missing] [YYYY-MM-DD]   (comando '{cmd}' no existe)")


if __name__ == "__main__":
    main()
