"""tracker.py - planilla de trabajo compartida (consola + usuario), en vivo y sin Office.

La capa HUMANA entre el motor y el bolsillo. Vuelca los logros a jugar de cada partido del dia a:
  - data/tracker/AAAA-MM-DD.csv   -> el dato (portable: LibreOffice / import a Google Sheets)
  - data/tracker/tracker.html     -> VISTA EN VIVO (se auto-refresca cada 5s en el navegador)

Loop: la consola refresca los numeros del modelo SIN pisar lo anotado (merge por key =
Partido+Mercado+Pick). El usuario mira el HTML en split-screen; para anotar (Decision/Notas/Stake)
se lo dice a la consola y esta edita el CSV. El cierre (Resultado/PnL) se completa post-partido.

Uso:
  python tracker.py [fecha]        # genera/refresca la planilla (hoy por defecto)
"""
import os, sys, csv, html, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

import app  # reusa el pipeline del modelo (mismos numeros que la web)

TRACKER_DIR = os.path.join(ROOT, "data", "tracker")
HTML_PATH = os.path.join(TRACKER_DIR, "tracker.html")   # estable -> bookmark fijo del split-screen

COLS = ["Hora", "Partido", "Ronda", "Mercado", "Pick", "Prob %", "Confianza", "Cuota",
        "Edge %", "Tier", "Contexto", "Decision", "Stake", "Notas", "Cumplió", "Resultado", "PnL"]
# columnas que el refresh NO pisa (lo que aporta el humano / el cierre post-partido)
# "Cumplió" = ✓/✗ del pick liquidado a los 90' (cierre post-partido, como Resultado/PnL)
PRESERVE = {"Contexto", "Decision", "Stake", "Notas", "Cumplió", "Resultado", "PnL"}


def _key(row):
    return (row["Partido"], row["Mercado"], row["Pick"])


def _model_rows(date):
    """Filas del modelo: por partido, los picks confiables (los 'logros a jugar'). Si un partido
    no tiene picks, emite al menos su favorito 1X2 para que igual aparezca en la planilla."""
    data = app._compute_wc(date)
    rows = []
    for c in data.get("cards", []):
        an = c.get("analysis")
        if not an or not an.get("resultado"):
            continue
        partido = f'{c["home"]} vs {c["away"]}'
        edge_by_label = {r["label"]: r for r in (c.get("edge") or {}).get("rows", [])}
        summary = (c.get("lectura") or {}).get("summary", "") if c.get("lectura") else ""
        picks = an.get("picks") or []
        if not picks:
            fav = max(an["resultado"], key=lambda r: r["cal"])
            picks = [{"market": "Resultado 1X2", "pick": fav["label"],
                      "prob": fav["cal"], "level": app._lvl(fav["cal"])}]
        for p in picks:
            team = p["pick"].replace("Gana ", "").strip()   # pick 1X2 = "Gana X" -> label edge = "X"
            e = edge_by_label.get(team) or edge_by_label.get(p["pick"])
            rows.append({
                "Hora": c["time"], "Partido": partido, "Ronda": c.get("tag", ""),
                "Mercado": p["market"], "Pick": p["pick"],
                "Prob %": round(p["prob"] * 100), "Confianza": p.get("level", ""),
                "Cuota": (e or {}).get("odds", ""),
                "Edge %": round(e["edge"] * 100, 1) if e else "",
                "Tier": (e or {}).get("tier", ""),
                "Contexto": summary, "Decision": "", "Stake": "", "Notas": "",
                "Resultado": "", "PnL": "",
            })
    rows.sort(key=lambda r: (r["Hora"], -r["Prob %"]))
    return rows


def _read_existing(path):
    """{key: {col: valor}} de la planilla previa (CSV) para preservar lo anotado. {} si no existe."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {(r.get("Partido"), r.get("Mercado"), r.get("Pick")): r
                for r in csv.DictReader(f) if r.get("Partido")}


def _merge(model_rows, existing):
    """Sobre las filas del modelo, reinyecta las columnas preservables ya anotadas. Ademas conserva
    filas que el usuario haya agregado a mano (keys que ya no estan en el modelo) al final."""
    seen = set()
    for row in model_rows:
        prev = existing.get(_key(row))
        if prev:
            for col in PRESERVE:
                if prev.get(col) not in (None, ""):
                    row[col] = prev[col]
        seen.add(_key(row))
    extras = [v for k, v in existing.items() if k not in seen and any(v.get(c) for c in PRESERVE)]
    return model_rows + extras


def _write_csv(path, rows):
    os.makedirs(TRACKER_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:   # BOM -> Excel/Sheets lo importan bien
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLS})


# hue semantico (token de Linear) por estado -> el badge lo tinta (fondo/borde) via color-mix
_CONF = {"ALTA": "var(--color-green)", "MEDIA": "var(--color-yellow)", "BAJA": "var(--color-red)"}
_TIER = {"VALOR": "var(--color-green)", "PASAR": "var(--color-yellow)",
         "SOSPECHOSO": "var(--color-orange)", "NO-APTO": "var(--color-red)"}


def _badge(v, hue):
    """Chip estilo Linear: fondo tintado + texto saturado + borde tenue del mismo hue."""
    return f'<td style="text-align:center"><span class="badge" style="--h:{hue}">{v}</span></td>'


def _render_html(path, rows, date):
    """Vista en vivo: tabla oscura que se auto-refresca cada 5s (meta refresh -> anda con file://)."""
    now = datetime.datetime.now().strftime("%H:%M:%S")

    def cell(row, col):
        v = html.escape(str(row.get(col, "") or ""))
        if col == "Confianza" and row.get(col) in _CONF:
            return _badge(v, _CONF[row[col]])
        if col == "Tier" and row.get(col) in _TIER:
            return _badge(v, _TIER[row[col]])
        if col == "Decision" and row.get(col):
            hue = "var(--color-green)" if row[col] == "JUGAR" else "var(--color-red)" if row[col] == "PASAR" else "var(--color-yellow)"
            return _badge(v, hue)
        if col == "Cumplió" and row.get(col):
            hue = "var(--color-green)" if "✓" in row[col] else "var(--color-red)" if "✗" in row[col] else "var(--color-yellow)"
            return _badge(v, hue)
        align = "left" if col in ("Partido", "Mercado", "Pick", "Contexto", "Notas") else "center"
        return f'<td style="text-align:{align}">{v}</td>'

    head = "".join(f"<th>{html.escape(c)}</th>" for c in COLS)
    body = "".join("<tr>" + "".join(cell(r, c) for c in COLS) + "</tr>" for r in rows)
    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="5">
<title>Tracker {date}</title>
<style>
 /* design tokens: Linear.app [data-theme=dark] */
 :root{{
  --bg:#08090a; --panel:#0f1011; --hover:#141516;
  --border:#23252a; --border-2:#34343a;
  --text:#f7f8f8; --text-2:#d0d6e0; --text-3:#8a8f98;
  --accent:#7170ff; --color-green:#27a644; --color-yellow:#f0bf00; --color-red:#eb5757; --color-orange:#fc7840;
  --font:"Inter Variable","Inter","SF Pro Display",-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;
 }}
 body{{background:var(--bg);color:var(--text);font:13px/1.5 var(--font);
  font-feature-settings:"cv01","ss03";-webkit-font-smoothing:antialiased;margin:0;padding:20px}}
 h1{{font-size:18px;font-weight:590;letter-spacing:-.012em;margin:0 0 3px}}
 .count{{color:var(--accent);font-weight:590}}
 .sub{{color:var(--text-3);font-size:12px;margin:0 0 14px}}
 table{{border-collapse:collapse;width:100%}}
 th,td{{border-bottom:1px solid var(--border);padding:6px 10px;white-space:nowrap}}
 th{{background:var(--panel);position:sticky;top:0;text-align:center;color:var(--text-3);
  font-weight:510;font-size:11px;text-transform:uppercase;letter-spacing:.03em}}
 td{{color:var(--text-2)}}
 td:nth-child(2){{color:var(--text);font-weight:510}}
 td:nth-child(11),td:nth-child(14){{white-space:normal;min-width:200px;color:var(--text-3)}}
 tr:hover td{{background:var(--hover)}}
 .badge{{display:inline-block;padding:1px 8px;border-radius:6px;font-size:11px;font-weight:590;
  color:var(--h);background:color-mix(in srgb,var(--h) 16%,transparent);
  border:1px solid color-mix(in srgb,var(--h) 32%,transparent)}}
</style></head><body>
<h1>Tracker · {date} <span class="count">({len(rows)} logros)</span></h1>
<p class="sub">Vista en vivo · se refresca sola cada 5s · para anotar deci&iacute;melo por consola · actualizado {now}</p>
<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>
</body></html>"""
    os.makedirs(TRACKER_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)


def build(date=None):
    date = date or datetime.date.today().isoformat()
    csv_path = os.path.join(TRACKER_DIR, f"{date}.csv")
    rows = _merge(_model_rows(date), _read_existing(csv_path))
    _write_csv(csv_path, rows)
    _render_html(HTML_PATH, rows, date)
    return csv_path, rows


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    csv_path, rows = build(d)
    print(f"  CSV  -> {csv_path}  ({len(rows)} logros)")
    print(f"  HTML -> {HTML_PATH}  (abrilo en el navegador; se refresca solo)")
