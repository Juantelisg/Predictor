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
            # la confiable y, si es O/U, seguido la SIGUIENTE linea (alt, menos %): 'indicar todo'
            entries = [(p["pick"], p["prob"], p.get("level", ""), False)]
            if p.get("alt"):
                a = p["alt"]
                entries.append((a["pick"], a["prob"], app._lvl(a["prob"]), True))
            for pick_label, prob, level, is_alt in entries:
                team = pick_label.replace("Gana ", "").strip()   # pick 1X2 = "Gana X" -> label edge = "X"
                e = edge_by_label.get(team) or edge_by_label.get(pick_label)
                rows.append({
                    "Hora": c["time"], "Partido": partido, "Ronda": c.get("tag", ""),
                    "Mercado": p["market"] + (" · sig" if is_alt else ""), "Pick": pick_label,
                    "Prob %": round(prob * 100), "Confianza": level,
                    "Cuota": (e or {}).get("odds", ""),
                    "Edge %": round(e["edge"] * 100, 1) if e else "",
                    "Tier": (e or {}).get("tier", ""),
                    "Contexto": summary, "Decision": "", "Stake": "", "Notas": "",
                    "Resultado": "", "PnL": "",
                })
        # props de jugador (SOT / gol+asist / tapadas), gateados por posicion+volumen y contraidos.
        # Van como filas propias marcadas 'Prop' (mayor varianza, sin cuota) -> el usuario los ve en el sheet.
        try:
            import espn_players as ep
            props = ep.match_props(c["home"], c["away"], date)
        except Exception:
            props = []
        for pr in props:
            rows.append({
                "Hora": c["time"], "Partido": partido, "Ronda": c.get("tag", ""),
                "Mercado": f"Prop: {pr['market']}", "Pick": f"{pr['who']} O{pr['line']}",
                "Prob %": round(pr["p"] * 100), "Confianza": app._lvl(pr["p"]),
                "Cuota": "", "Edge %": "", "Tier": "",
                "Contexto": f"L10 {pr['hits_l10']}/{pr['games_l10']} ({pr['l10']}%) · {pr['position']} · varianza alta",
                "Decision": "", "Stake": "", "Notas": "", "Resultado": "", "PnL": "",
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


def _strategy(date):
    """Jugadas recomendadas (estrategia.recommend) sobre las tarjetas del dia. Best-effort:
    corre simulate (Monte Carlo) para los combos correlacionados; nunca rompe el sheet."""
    try:
        import estrategia
        cards = app._compute_wc(date).get("cards", [])
        return estrategia.recommend(cards).get("plays", [])
    except Exception:
        return []


def _strategy_html(plays):
    """Bloque 'Como jugar hoy': ancla + combos con su conjunta y fundamento. '' si no hay."""
    if not plays:
        return ""
    cards = []
    for pl in plays:
        legs = "".join(
            f'<div class="leg"><span class="lm">{html.escape(l["market"])}</span>'
            f'<span class="lp">{html.escape(l["pick"])}</span>'
            f'<span class="lpr">{round(l["prob"] * 100)}%</span></div>'
            for l in pl["legs"])
        cards.append(
            f'<div class="play"><div class="ph"><span class="pt">{html.escape(pl["tipo"])}</span>'
            f'<span class="pj">conjunta {round(pl["joint"] * 100)}%</span></div>'
            f'<div class="legs">{legs}</div>'
            f'<p class="pr">{html.escape(pl["rationale"])}</p></div>')
    return ('<div class="strat"><h2>Cómo jugar hoy</h2>'
            f'<div class="plays">{"".join(cards)}</div></div>')


def _render_html(path, rows, date, plays=None):
    """Vista en vivo: tabla oscura que se auto-refresca cada 5s (meta refresh -> anda con file://)."""
    now = datetime.datetime.now().strftime("%H:%M:%S")
    strat = _strategy_html(plays)

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
    # agrupa por partido: un encabezado por partido y debajo sus logros (orden = primera aparicion,
    # o sea por hora/prob). El CSV queda plano; el agrupado es solo la vista.
    groups = {}
    for r in rows:
        groups.setdefault(r.get("Partido", ""), []).append(r)
    body_parts = []
    for partido, grp in groups.items():
        first = grp[0]
        meta = "  ·  ".join(x for x in (first.get("Hora"), first.get("Ronda")) if x)
        label = html.escape(partido) + (f'<span class="rd">  ·  {html.escape(meta)}</span>' if meta else "")
        body_parts.append(f'<tr class="grp"><td colspan="{len(COLS)}">{label}</td></tr>')
        body_parts += ["<tr>" + "".join(cell(r, c) for c in COLS) + "</tr>" for r in grp]
    body = "".join(body_parts)
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
 .strat{{margin:0 0 20px}}
 .strat h2{{font-size:13px;font-weight:590;color:var(--accent);text-transform:uppercase;
  letter-spacing:.03em;margin:0 0 10px}}
 .plays{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}}
 .play{{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:12px 14px}}
 .ph{{display:flex;justify-content:space-between;align-items:center;margin:0 0 8px}}
 .pt{{font-weight:590;font-size:12px;color:var(--text)}}
 .pj{{font-weight:590;font-size:12px;color:var(--color-green)}}
 .leg{{display:flex;gap:8px;align-items:baseline;padding:2px 0;font-size:12px}}
 .lm{{color:var(--text-3);min-width:96px}}
 .lp{{color:var(--text);flex:1}}
 .lpr{{color:var(--accent);font-weight:590}}
 .pr{{color:var(--text-3);font-size:11.5px;line-height:1.5;margin:8px 0 0}}
 tr.grp td{{background:#141516;color:var(--text);font-weight:590;font-size:12px;
  letter-spacing:-.01em;border-top:2px solid var(--border-2);padding:9px 10px}}
 tr.grp .rd{{color:var(--text-3);font-weight:510}}
</style></head><body>
<h1>Tracker · {date} <span class="count">({len(rows)} logros)</span></h1>
<p class="sub">Vista en vivo · se refresca sola cada 5s · para anotar deci&iacute;melo por consola · actualizado {now}</p>
{strat}
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
    _render_html(HTML_PATH, rows, date, _strategy(date))
    return csv_path, rows


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    csv_path, rows = build(d)
    print(f"  CSV  -> {csv_path}  ({len(rows)} logros)")
    print(f"  HTML -> {HTML_PATH}  (abrilo en el navegador; se refresca solo)")
