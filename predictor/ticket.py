"""ticket.py - analizador de un ticket que ARMA EL USUARIO (el inverso de cartera.py).

En cartera.py el modelo arma los tickets; aca el usuario carga SU ticket y el modelo lo audita.
El usuario ingresa: tipo (combinada | simples) + piernas, cada pierna = {match, market, pick, cuota}.
Este modulo, por pierna:
  1. resuelve la prob CALIBRADA del modelo (via analizar.analyze),
  2. trae la implicita de la cuota (1/cuota; CRUDA, con margen de la casa),
  3. compara -> edge + veredicto cuantitativo,
y para la combinada arma la prob conjunta (producto si los partidos son distintos; FLAG de
correlacion si hay piernas del mismo partido) + cuota total + edge del combo. Ademas emite un
PAQUETE estructurado (numeros + opciones del modelo por partido) que es el material con el que
Claude redacta la LECTURA en vivo (stats + contexto + WebSearch).

Filosofia (del usuario): la cuota de la casa habla mejor que cualquier modelo. Por eso la cuota
es el ANCLA; el modelo es segunda opinion. Un edge enorme vs una cuota liquida NO es valor: es
probable error del modelo -> se marca REVISAR (mismo criterio que edge.MAX_EDGE). El motor de
prediccion sigue SIN ver cuotas (no circular): la cuota entra solo en esta capa de lectura/valor.

Uso:
  python ticket.py --fecha=2026-06-27   # demo: corre un ticket de ejemplo end-to-end
"""
import sys, datetime
sys.stdout.reconfigure(encoding="utf-8")

import edge   # devig, MIN_EDGE, MAX_EDGE, QUALIFIED (capa de valor, ya testeada)

# selecciones soportadas por mercado (claves normalizadas que produce el form web / el parser)
PICKS = {
    "1x2": ("home", "draw", "away"),
    "dc": ("1x", "x2", "12"),
    "over": ("over1.5", "under1.5", "over2.5", "under2.5", "over3.5", "under3.5"),
    "btts": ("yes", "no"),
    "cs": ("home", "away"),
    "corners": ("o8.5",),
}


def implied(cuota):
    """Implicita CRUDA de una cuota decimal (1/cuota). Incluye el margen de la casa, asi que
    SOBREESTIMA la prob real -> el edge medido contra ella es CONSERVADOR (el real es >=)."""
    return 1.0 / cuota


def _cal(an):
    """(home, draw, away) calibradas del 1X2 del cuadro `an` de analizar.analyze."""
    r = an["resultado"]                     # orden fijo: [Gana local, Empate, Gana visita]
    return r[0]["cal"], r[1]["cal"], r[2]["cal"]


def model_prob(an, market, pick):
    """Prob calibrada del modelo para (market, pick). (None, family) si el modelo no lo cubre.
    La doble oportunidad se deriva del 1X2 CALIBRADO (no del dict crudo). El under = 1 - over."""
    m, p = market.lower(), (pick or "").lower()
    if not an or an.get("error"):
        return None, m
    ch, cd, ca = _cal(an)
    if m == "1x2":
        return {"home": ch, "draw": cd, "away": ca}.get(p), "1x2"
    if m == "dc":
        return {"1x": ch + cd, "x2": cd + ca, "12": ch + ca}.get(p), "dc"
    if m == "over":
        g = an["goles"]
        return {"over1.5": g["over15"], "under1.5": 1 - g["over15"],
                "over2.5": g["over25"], "under2.5": 1 - g["over25"],
                "over3.5": g["over35"], "under3.5": 1 - g["over35"]}.get(p), "over"
    if m == "btts":
        b = an["goles"]["btts"]
        return {"yes": b, "no": 1 - b}.get(p), "btts"
    if m == "cs":
        v = an["valla"]
        return {"home": v["home"], "away": v["away"]}.get(p), "cs"
    if m == "corners":
        c = an.get("corners")
        return (c["o85"] if c else None), "corners"
    return None, m


def _verdict(mp, imp, family):
    """Veredicto cuantitativo HUMILDE (la cuota es sharp; el modelo es segunda opinion).
    Edge = modelo - implicita CRUDA -> conservador. Tiers:
      SIN-MODELO  el modelo no cubre el mercado -> decidir por cuota + contexto
      CONTEXTO    familia no calibrada para edge -> el numero es referencia, no valor medido
      REVISAR     modelo MUY por encima de la cuota -> probable error del modelo, no valor
      CUOTA CARA  modelo por debajo -> la cuota paga poco para lo que vale (mal valor)
      VALOR       edge a favor aun vs la implicita cruda -> candidato real
      JUSTA       modelo ~ cuota -> precio justo, decision por contexto."""
    if mp is None:
        return {"tier": "SIN-MODELO", "edge": None,
                "note": "el modelo no cubre este mercado; decidir por la cuota y el contexto en vivo"}
    e = mp - imp
    if family not in edge.QUALIFIED:
        return {"tier": "CONTEXTO", "edge": round(e, 4),
                "note": f"familia '{family}' sin calibracion suficiente para medir valor; "
                        "el numero del modelo es referencia, no edge confiable"}
    if e > edge.MAX_EDGE:
        return {"tier": "REVISAR", "edge": round(e, 4),
                "note": f"el modelo da {e*100:+.0f} pts mas que la cuota -> probable error del modelo, "
                        "NO valor (el mercado es sharp). Confiar en la cuota salvo dato fuerte de contexto"}
    if e < -edge.MIN_EDGE:
        return {"tier": "CUOTA CARA", "edge": round(e, 4),
                "note": "la cuota paga menos de lo que el modelo cree probable -> mal valor salvo razon de contexto"}
    if e >= edge.MIN_EDGE:
        return {"tier": "VALOR", "edge": round(e, 4),
                "note": f"edge {e*100:+.0f} pts a favor incluso vs la implicita cruda (con margen) -> candidato real"}
    return {"tier": "JUSTA", "edge": round(e, 4),
            "note": "modelo y cuota coinciden -> cuota justa, la decision la define el contexto"}


def analyze_leg(leg, an):
    """Audita una pierna contra el cuadro `an` de su partido. Devuelve numeros + veredicto."""
    mp, family = model_prob(an, leg["market"], leg["pick"])
    imp = implied(leg["cuota"])
    out = {"match": leg.get("match"), "market": leg["market"], "pick": leg["pick"],
           "label": leg.get("label") or f'{leg["market"]} {leg["pick"]}',
           "cuota": leg["cuota"], "implied": round(imp, 4),
           "model_prob": round(mp, 4) if mp is not None else None, "family": family,
           "ev": round(mp * leg["cuota"] - 1, 4) if mp is not None else None}
    out.update(_verdict(mp, imp, family))
    return out


def combo(legs):
    """Combinada a partir de piernas YA auditadas. Prob conjunta = producto (solo honesto si los
    partidos son distintos -> independientes). FLAG same_game si se repite un partido: ahi las
    piernas estan correlacionadas y el producto NO vale (la combinada same-game paga distinto)."""
    matches = [l.get("match") for l in legs]
    same_game = len([m for m in matches if m]) != len(set(m for m in matches if m))
    cuota_total = 1.0
    for l in legs:
        cuota_total *= l["cuota"]
    have_all = all(l["model_prob"] is not None for l in legs)
    jp = None
    if have_all:
        jp = 1.0
        for l in legs:
            jp *= l["model_prob"]
    imp = 1.0 / cuota_total
    return {"n": len(legs), "cuota_total": round(cuota_total, 3), "implied": round(imp, 4),
            "joint_prob": round(jp, 4) if jp is not None else None,
            "edge": round(jp - imp, 4) if jp is not None else None,
            "ev": round(jp * cuota_total - 1, 4) if jp is not None else None,
            "same_game": same_game,
            "note": ("OJO: hay piernas del mismo partido -> correlacionadas; la prob conjunta NO es el "
                     "producto (la combinada same-game paga distinto). Tratar el numero como aproximacion gruesa."
                     if same_game else
                     "piernas de partidos distintos -> independientes; prob conjunta = producto (honesto).")}


def analyze_ticket(legs, kind="combinada", an_by_match=None):
    """legs = piernas estructuradas; kind = 'combinada' | 'simples'.
    an_by_match = {match: cuadro de analizar.analyze} ya computados por el caller (web reusa el cache)."""
    an_by_match = an_by_match or {}
    analyzed = [analyze_leg(l, an_by_match.get(l.get("match"))) for l in legs]
    out = {"kind": kind, "n": len(analyzed), "legs": analyzed}
    if kind == "combinada" and len(analyzed) >= 2:
        out["combo"] = combo(analyzed)
    return out


# ---------- material para la LECTURA en vivo (lo que redacta Claude) ----------

def _opciones(an):
    """Opciones del modelo para ese partido (los picks confiables ya calculados) = candidatos
    alternativos a sugerir. [] si el modelo fallo."""
    return (an or {}).get("picks", []) if an and not an.get("error") else []


def packet(ticket, an_by_match):
    """Imprime el ticket auditado + las opciones del modelo por partido. Es el material con el
    que Claude redacta la lectura (veredicto final + posibles opciones a jugar), agregando el
    contexto en vivo (bajas/XI/forma/situacion) que el script no puede traer."""
    data = analyze_ticket(ticket["legs"], ticket.get("kind", "combinada"), an_by_match)
    pct = lambda x: f"{x*100:.0f}%" if x is not None else "s/d"
    print(f"  TICKET ({data['kind']}, {data['n']} piernas)\n" + "=" * 72)
    for l in data["legs"]:
        print(f"  - {(l['match'] or '?'):<26} {l['label']}")
        print(f"      cuota {l['cuota']}  | implicita {pct(l['implied'])}  | modelo {pct(l['model_prob'])}"
              f"  | {l['tier']}")
        print(f"      {l['note']}")
    if "combo" in data:
        c = data["combo"]
        print("-" * 72)
        print(f"  COMBO: cuota total {c['cuota_total']}  | implicita {pct(c['implied'])}  | "
              f"modelo conjunto {pct(c['joint_prob'])}  | edge {pct(c['edge']) if c['edge'] is not None else 's/d'}")
        print(f"  {c['note']}")
    print("=" * 72)
    print("\n  OPCIONES DEL MODELO por partido (candidatos confiables, sin cuota):")
    for m in dict.fromkeys(l.get("match") for l in data["legs"]):
        ops = _opciones(an_by_match.get(m))
        line = "  ".join(f"{o['pick']} {pct(o['prob'])}" for o in ops) if ops else "(sin picks confiables)"
        print(f"   {(m or '?'):<26} {line}")
    print("\n  Redactar: veredicto final por pierna (cuota=ancla, modelo=2da opinion, contexto en vivo) + "
          "posibles opciones a jugar.")
    return data


# ---------- prosa de la lectura (la redacta claude -p; fallback determinista si falla) ----------

def _pct(x):
    return f"{x*100:.0f}%" if x is not None else "s/d"


def _ctx_line(lect):
    """Una linea de contexto del partido desde su lectura ya generada hoy (summary). '' si no hay."""
    return (lect or {}).get("summary", "") if isinstance(lect, dict) else ""


def prompt_for(data, lect_by_match=None):
    """Construye el prompt para que claude -p redacte la lectura del ticket. Incluye el ticket ya
    auditado (numeros + veredicto por pierna), el contexto en vivo YA generado hoy por partido
    (lecturas) y las opciones del modelo. Devuelve un string (puro y testeable)."""
    lect_by_match = lect_by_match or {}
    lines = []
    lines.append("Sos un analista cuant de apuestas. Te paso un TICKET que arma el usuario "
                 "(piernas + cuotas) ya auditado por el modelo. Redacta una LECTURA profesional en "
                 "espanol rioplatense, sobria (sin jerga tipo 'lock'/'dulce'). FILOSOFIA: la cuota de "
                 "la casa es el ancla sharp (habla mejor que cualquier modelo); el modelo es 2da "
                 "opinion; un edge enorme = probable error del modelo, NO valor.\n")
    lines.append(f"TICKET ({data['kind']}, {data['n']} piernas):")
    for l in data["legs"]:
        ctx = _ctx_line(lect_by_match.get(l.get("match")))
        lines.append(f"- {l['label']}  [{l.get('match','?')}]  cuota {l['cuota']} "
                     f"(implica {_pct(l['implied'])}) · modelo {_pct(l['model_prob'])} · {l['tier']}: {l['note']}")
        if ctx:
            lines.append(f"    contexto del partido: {ctx}")
    if "combo" in data:
        c = data["combo"]
        lines.append(f"COMBO: cuota total {c['cuota_total']} (implica {_pct(c['implied'])}) · "
                     f"modelo conjunto {_pct(c['joint_prob'])} · edge {_pct(c['edge'])}. {c['note']}")
    lines.append("\nIMPORTANTE: el 'contexto del partido' de arriba YA es investigacion en vivo de hoy. "
                 "Apoyate en eso y en los numeros; usa WebSearch SOLO para un dato puntual que falte "
                 "(maximo 1-2 busquedas). Se concreto y breve, NO exhaustivo.")
    lines.append("\nDevuelve, en este orden y en prosa clara:")
    lines.append("1) VEREDICTO FINAL del ticket (jugarlo como esta / ajustarlo / pasar), justificado.")
    lines.append("2) Por cada pierna: que dice la cuota, que dice el modelo, el contexto, y tu veredicto.")
    lines.append("3) POSIBLES OPCIONES A JUGAR: que piernas sostener, cuales soltar, y alternativas "
                 "concretas (mercado + lado) si las ves mejores. Cerra con un disclaimer de juego responsable.")
    return "\n".join(lines)


def fallback_lectura(data, lect_by_match=None):
    """Lectura DETERMINISTA (sin Claude): arma una prosa util desde los numeros + el contexto ya
    generado hoy por partido. Es el backstop para que el boton 'Analizar' siempre devuelva algo."""
    lect_by_match = lect_by_match or {}
    out = [f"Lectura del ticket ({data['kind']}, {data['n']} piernas) — la cuota es el ancla; "
           "el modelo, segunda opinion.\n"]
    for l in data["legs"]:
        out.append(f"• {l['label']} ({l.get('match','?')}) @ {l['cuota']} — "
                   f"la cuota implica {_pct(l['implied'])}; el modelo ve {_pct(l['model_prob'])}. "
                   f"{l['tier']}: {l['note']}")
        ctx = _ctx_line(lect_by_match.get(l.get("match")))
        if ctx:
            out.append(f"   Contexto: {ctx}")
    if "combo" in data:
        c = data["combo"]
        out.append(f"\nCombinada: cuota total {c['cuota_total']} (implica {_pct(c['implied'])}); "
                   f"modelo conjunto {_pct(c['joint_prob'])}; edge {_pct(c['edge'])}. {c['note']}")
    # recomendacion simple por tiers
    keep = [l["label"] for l in data["legs"] if l["tier"] in ("VALOR", "JUSTA")]
    drop = [l["label"] for l in data["legs"] if l["tier"] in ("CUOTA CARA", "REVISAR")]
    out.append("\nPosibles opciones a jugar:")
    if keep:
        out.append(f"  Sostener: {', '.join(keep)}.")
    if drop:
        out.append(f"  Revisar/soltar: {', '.join(drop)} (la cuota no acompana o el edge es sospechoso).")
    if not keep and not drop:
        out.append("  Sin veredicto fuerte: decidir por contexto en vivo.")
    out.append("\n(Lectura automatica sin investigacion en vivo. Apostar es entretenimiento, "
               "riesgo de perdida total; la varianza es real.)")
    return "\n".join(out)


# ---------- helper de red para el CLI / consola (el web reusa el cache de tarjetas) ----------

def an_for_matches(matches, date=None, ctx=None):
    """Corre analizar.analyze para cada partido 'Home vs Away'. Para el CLI/consola; el dashboard
    reusa las tarjetas ya computadas. Devuelve {match: cuadro}."""
    import analizar
    ctx = ctx or analizar.load_ctx()
    out = {}
    for m in dict.fromkeys(matches):
        if not m or " vs " not in m:
            out[m] = {"error": "match debe ser 'Local vs Visita'"}
            continue
        home, away = [s.strip() for s in m.split(" vs ", 1)]
        out[m] = analizar.analyze(home, away, neutral=True, league="wc", ctx=ctx, date=date)
    return out


def _demo_ticket():
    """Ticket de ejemplo (combinada de 3 partidos distintos de la slate del Mundial)."""
    return {"kind": "combinada", "legs": [
        {"match": "Jordan vs Argentina", "market": "dc", "pick": "x2", "cuota": 1.05,
         "label": "Argentina o empate"},
        {"match": "Panama vs England", "market": "1x2", "pick": "away", "cuota": 1.45,
         "label": "Gana England"},
        {"match": "Croatia vs Ghana", "market": "over", "pick": "over1.5", "cuota": 1.40,
         "label": "Over 1.5"},
    ]}


def main():
    g = lambda k, d: next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith(f"--{k}=")), d)
    date = g("fecha", datetime.date.today().isoformat())
    tk = _demo_ticket()
    an_by_match = an_for_matches([l["match"] for l in tk["legs"]], date=date)
    print("=" * 72)
    print(f"  ARMADOR DE TICKETS  ·  demo  ·  {date}")
    print("=" * 72)
    packet(tk, an_by_match)


if __name__ == "__main__":
    main()
