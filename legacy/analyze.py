"""analyze.py - analiza props CARGADOS por el usuario (no generados por trends()).

El usuario trae el candidato (jugador, mercado, linea, lado) + SU cuota (la casa donde
JUEGA). El modelo calibrado da la prob justa -> cuota justa -> EV a TU precio -> veredicto.

Clave del diseno: la cuota de una foto (casa X) es solo referencia; el edge SIEMPRE se
calcula contra el precio que el usuario puede jugar (su casa Y). El modelo da una prob
agnostica de casa; el EV se computa contra cualquier precio que pongas. Cero quota de
The Odds API. Solo MLB (donde el modelo esta calibrado).
"""
import datetime
import player_props as pp
import prop_value as pv
import cache

# alias libres (excel/foto/manual) -> etiquetas internas de pp.PROPS
MARKET_ALIASES = {
    "hits": "Hits", "h": "Hits", "hit": "Hits",
    "total bases": "Bases totales", "bases totales": "Bases totales", "tb": "Bases totales", "bases": "Bases totales",
    "runs": "Carreras", "carreras": "Carreras", "run": "Carreras",
    "rbi": "Impulsadas", "rbis": "Impulsadas", "impulsadas": "Impulsadas",
    "hr": "Home Run", "home run": "Home Run", "home runs": "Home Run", "jonron": "Home Run", "jonrones": "Home Run",
    "h+r+rbi": "H+R+RBI", "hrr": "H+R+RBI",
    "singles": "Singles", "sencillos": "Singles",
    "doubles": "Dobles", "dobles": "Dobles", "2b": "Dobles",
    "stolen bases": "Bases robadas", "sb": "Bases robadas", "bases robadas": "Bases robadas", "robos": "Bases robadas",
    "strikeouts": "Ponches", "k": "Ponches", "ks": "Ponches", "ponches": "Ponches", "so": "Ponches",
}
SUPPORTED = sorted({(l, ln) for l, ln, _ in pp.PROPS})   # combos (mercado, linea) con baseline


def _market(label):
    return MARKET_ALIASES.get((label or "").strip().lower(), (label or "").strip())


def _num(x):
    return float(str(x).replace("+", "").replace(",", ".").strip())


def american_to_decimal(a):
    a = _num(a)
    return 1 + a / 100 if a > 0 else 1 + 100 / abs(a)


def implied_prob(a):
    return 1 / american_to_decimal(a)


def prob_to_american(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    dec = 1 / p
    return round((dec - 1) * 100) if dec >= 2 else round(-100 / (dec - 1))


def _player_index(date):
    """{nombre_norm: [id, fullName]} de los bateadores del slate del dia. Cacheado 6h."""
    def _f():
        idx = {}
        for g in pp._schedule(date):
            for pid, name, team, opp in pp._batters_for_game(g):
                if name:
                    idx[pv._norm(name)] = [pid, name]
        return idx
    return cache.cached(f"plidx:{date}", 6 * 3600, _f)


def resolve_player(name, idx):
    """name -> [id, fullName] del slate. Exacto, luego contains, luego apellido."""
    n = pv._norm(name)
    if not n:
        return None
    if n in idx:
        return idx[n]
    for k, v in idx.items():
        if n in k or k in n:
            return v
    last = n.split()[-1]
    for k, v in idx.items():
        if k.split() and k.split()[-1] == last:
            return v
    return None


def analyze_one(prop, date, baselines, idx):
    name = prop.get("jugador") or prop.get("player") or ""
    label = _market(prop.get("mercado") or prop.get("market"))
    side_raw = (prop.get("lado") or prop.get("side") or "Over").strip().lower()
    side = "Over" if side_raw.startswith("o") else "Under"
    res = {"jugador": name, "mercado": label, "lado": side, "cuota": prop.get("cuota") or prop.get("odds")}
    try:
        line = _num(prop.get("linea") or prop.get("line"))
    except Exception:
        return {**res, "error": "linea invalida"}
    res["linea"] = line
    if (label, line) not in baselines:
        return {**res, "error": "mercado/linea no soportado"}
    pl = resolve_player(name, idx)
    if not pl:
        return {**res, "error": "jugador no esta en el slate de hoy"}
    pid, full = pl
    res["player"] = full
    season = pp._season(date)
    rows = [r for r in pp.gamelog(pid, season) if not r["date"] or r["date"] < date]
    if len(rows) < pv.MIN_GAMES:
        return {**res, "error": f"muestra insuficiente ({len(rows)} juegos)"}
    model, _ = pv._model_prob(rows, label, line, side, baselines[(label, line)])   # sin pitcher (rival desconocido)
    res.update({"n": len(rows), "model": round(model, 3), "fair_line": prob_to_american(model)})
    odds = prop.get("cuota") or prop.get("odds")
    if odds not in (None, ""):
        try:
            imp = implied_prob(odds)
            edge = model - imp
            ev = model * (american_to_decimal(odds) - 1) - (1 - model)
            tier = "strong" if edge >= pv.STRONG_MIN else "moderate" if edge >= pv.MODERATE_MIN else "pass"
            res.update({"implied": round(imp, 3), "edge": round(edge, 3), "ev": round(ev, 3),
                        "tier": tier, "verdict": "APOSTAR" if tier != "pass" else "PASAR",
                        "suspect": abs(edge) > pv.MAX_EDGE})
        except Exception:
            res["error"] = "cuota invalida"
    return res


def analyze(props, date=None):
    """Lista de props {jugador, mercado, linea, lado, cuota} -> veredictos. Cero quota."""
    date = date or datetime.date.today().isoformat()
    season = pp._season(date)
    baselines = pv._baselines(date, season)
    idx = _player_index(date)
    return [analyze_one(p, date, baselines, idx) for p in props]


if __name__ == "__main__":
    import json, sys
    demo = [
        {"jugador": "Yandy Diaz", "mercado": "hits", "linea": 0.5, "lado": "Over", "cuota": "+150"},
        {"jugador": "Yandy Diaz", "mercado": "hits", "linea": 0.5, "lado": "Over", "cuota": "+120"},
        {"jugador": "Junior Caminero", "mercado": "tb", "linea": 1.5, "lado": "Over", "cuota": "+105"},
    ]
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    for r in analyze(demo, date):
        print(json.dumps(r, ensure_ascii=False))
