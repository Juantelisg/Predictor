"""pnl.py - forward-test del EDGE (Fase 4). Loguea apuestas-candidato, las resuelve contra el
resultado real y mide ROI realizado vs edge predicho. CERO promesas: es el JUEZ del supra-modelo.

El loop de calibracion (feedback.py) dice si las PROBABILIDADES son buenas. Este loop dice si
las EDGES son reales (si cuando el modelo ve +6% de valor, ese valor existe). Sin esto, una
edge es una hipotesis, no plata.

  log    -> registra las candidatas (edge>=MIN_EDGE) del dia, con su tier/cuota/stake Kelly
  eval   -> resuelve las jugadas (resultado ESPN) -> bet_evals/  (won/lost, PnL real y flat)
  report -> ROI realizado por tier + forward-test del edge (predicho vs materializado)

Uso:
  python pnl.py log [fecha]
  python pnl.py eval
  python pnl.py report
"""
import os, sys, json, datetime
import odds, analizar, edge as edgemod, feedback

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.abspath(__file__))
BETS_DIR = os.path.join(ROOT, "bets")
EVAL_DIR = os.path.join(ROOT, "bet_evals")
NOTIONAL = 10.0     # unidad fija para el ROI "flat" (mide el edge sin el ruido del sizing Kelly)


def _append(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _read(d):
    out = []
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".jsonl"):
                with open(os.path.join(d, fn), encoding="utf-8-sig") as f:
                    out += [json.loads(ln) for ln in f if ln.strip()]
    return out


def log_bets(date=None):
    date = date or datetime.date.today().isoformat()
    ctx = analizar.load_ctx()
    done = {(b["date"], b["home"], b["away"], b["side"]) for b in _read(BETS_DIR)}
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    rows = []
    for ev in odds._events(date):
        comp = ev["competitions"][0]
        cs = {c["homeAway"]: c["team"]["displayName"] for c in comp["competitors"]}
        v = odds.verdict_1x2(cs.get("home", ""), cs.get("away", ""), date, ctx)
        if not v:
            continue
        for side, r in zip(("home", "draw", "away"), v["rows"]):
            if r["edge"] < edgemod.MIN_EDGE:                      # solo candidatas con edge positivo
                continue
            if (date, v["home"], v["away"], side) in done:
                continue
            rows.append({"date": date, "home": v["home"], "away": v["away"], "side": side,
                         "p_model": r["p_model"], "p_market": r["p_market"],
                         "p_bet": r.get("p_bet"), "edge": r["edge"],
                         "odds": r["odds"], "tier": r["tier"], "edge_version": "edge-v2",
                         "stake": float(r.get("amount", 0.0)),     # Kelly real (0 si NO-APTO/SOSPECHOSO/PASAR)
                         "played": False, "ts": ts})
    _append(os.path.join(BETS_DIR, f"{date}.jsonl"), rows)
    print(f"  Registradas {len(rows)} candidatas ({date}) -> bets/{date}.jsonl")
    for r in rows:
        print(f"    {r['home']} vs {r['away']}  {r['side']:<5} edge {r['edge']*100:+5.1f}%  {r['tier']:<10} ${r['stake']:.0f}")


def eval_bets():
    bets = _read(BETS_DIR)
    done = {(b["date"], b["home"], b["away"], b["side"]) for b in _read(EVAL_DIR)}
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    rows, pend = [], 0
    for b in bets:
        if (b["date"], b["home"], b["away"], b["side"]) in done:
            continue
        sc = feedback._espn_soccer_score(b["home"], b["away"], b["date"])
        if sc is None:
            pend += 1
            continue
        h, a = sc
        actual = "home" if h > a else "draw" if h == a else "away"
        won = int(b["side"] == actual)
        pnl = b["stake"] * (b["odds"] - 1) if won else -b["stake"]              # ROI real (Kelly)
        pnl_flat = NOTIONAL * (b["odds"] - 1) if won else -NOTIONAL             # ROI flat (mide el edge)
        rows.append({**{k: b[k] for k in ("date", "home", "away", "side", "edge", "odds", "tier", "stake")},
                     "edge_version": b.get("edge_version", "edge-v1"),
                     "result": f"{h}-{a}", "won": won, "pnl": round(pnl, 2),
                     "pnl_flat": round(pnl_flat, 2), "evaluated_at": ts})
    if rows:
        _append(os.path.join(EVAL_DIR, f"{datetime.date.today().isoformat()}.jsonl"), rows)
    print(f"  Resueltas {len(rows)} apuestas. Pendientes (sin resultado aun): {pend}")


def report():
    ev = _read(EVAL_DIR)
    if not ev:
        print("  Sin apuestas resueltas todavia. Corre 'log' y luego 'eval' tras los partidos.")
        return
    real = [e for e in ev if e["stake"] > 0]                # las que realmente apostariamos (Kelly>0)
    st = sum(e["stake"] for e in real); pnl = sum(e["pnl"] for e in real)
    print(f"  FORWARD-TEST DEL EDGE  ({len(ev)} candidatas resueltas)\n")
    ver = {}                                                # ROI flat por version de logica de edge
    for e in ev:
        ver.setdefault(e.get("edge_version", "edge-v1"), []).append(e)
    if len(ver) > 1:
        print("  Por version de edge (ROI flat = calidad del edge sin sizing):")
        for v in sorted(ver):
            es = ver[v]; n = len(es); hit = sum(x["won"] for x in es)
            roi = sum(x["pnl_flat"] for x in es) / (n * NOTIONAL) * 100
            print(f"    {v:<10} {n:>3} candidatas  aciertos {hit}/{n}  ROI flat {roi:+.1f}%")
        print()
    print(f"  REAL (solo tiers apostables, Kelly): {len(real)} apuestas")
    if real:
        hit = sum(e["won"] for e in real)
        print(f"    apostado ${st:.0f}  ->  PnL ${pnl:+.0f}  |  ROI {pnl/st*100:+.1f}%  |  aciertos {hit}/{len(real)}")
    print(f"\n  Por tier (ROI flat ${NOTIONAL:.0f}/unidad = calidad del edge sin sizing):")
    print(f"    {'tier':<11} {'n':>3} {'aciertos':>8} {'edge_prom':>9} {'ROI_flat':>9}")
    by = {}
    for e in ev:
        by.setdefault(e["tier"], []).append(e)
    for t in sorted(by):
        es = by[t]; n = len(es); hit = sum(x["won"] for x in es)
        roi = sum(x["pnl_flat"] for x in es) / (n * NOTIONAL) * 100
        print(f"    {t:<11} {n:>3} {hit:>4}/{n:<3} {sum(x['edge'] for x in es)/n*100:>+7.1f}% {roi:>+8.1f}%")
    susp = by.get("SOSPECHOSO", [])
    if susp:
        roi = sum(x["pnl_flat"] for x in susp) / (len(susp) * NOTIONAL) * 100
        verdict = "el guardrail nos SALVO (ROI flat negativo)" if roi < 0 else "OJO: las SOSPECHOSAS ganaron -> revisar el cap"
        print(f"\n  SOSPECHOSO (flaggeadas, NO apostadas): ROI flat {roi:+.1f}% -> {verdict}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "log":
        log_bets(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "eval":
        eval_bets()
    else:
        report()


if __name__ == "__main__":
    main()
