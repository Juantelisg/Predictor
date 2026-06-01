"""evaluate.py — resuelve predicciones contra el resultado real y escribe evaluations/.

Lee predictions/<date>.jsonl, busca el score final (skill del sport), determina won/lost
de la selección moneyline, calcula pnl + calibration_error, y escribe una línea por
predicción en evaluations/<hoy>.jsonl (schema en evaluations/SCHEMA.md).

MVP: moneyline (MLB/NBA). Otros bet_type se saltan con aviso. No re-evalúa lo ya evaluado.

Uso: python evaluate.py <date-de-la-prediccion>     # ej: python evaluate.py 2026-05-31
"""
import sys, os, json, datetime
from sports_skills import mlb, nba

ROOT = os.path.dirname(os.path.abspath(__file__))
SPORT_SKILL = {"mlb": mlb, "nba": nba}


def american_to_decimal(a):
    a = float(a)
    return 1 + (a / 100.0 if a > 0 else 100.0 / abs(a))


def final_scores(sport, date):
    """event_id -> (status, {team_name: score_int}) para los partidos finalizados de la fecha."""
    skill = SPORT_SKILL.get(sport.split("_")[0])
    if not skill:
        return {}
    try:
        events = skill.get_scoreboard(date=date)["data"]["events"]
    except Exception:
        return {}
    out = {}
    for e in events:
        sc = {}
        for c in e.get("competitors", []):
            try:
                sc[c["team"]["name"]] = int(c.get("score") or 0)
            except Exception:
                sc[c["team"]["name"]] = 0
        out[e["id"]] = (e.get("status", ""), sc)
    return out


def already_evaluated(today):
    path = os.path.join(ROOT, "evaluations", f"{today}.jsonl")
    if not os.path.exists(path):
        return set()
    return {json.loads(l)["prediction_id"] for l in open(path, encoding="utf-8-sig") if l.strip()}


def evaluate(pred_date):
    preds_path = os.path.join(ROOT, "predictions", f"{pred_date}.jsonl")
    if not os.path.exists(preds_path):
        print(f"  No hay predicciones en {pred_date}.")
        return []
    preds = [json.loads(l) for l in open(preds_path, encoding="utf-8-sig") if l.strip()]
    today = datetime.date.today().isoformat()
    done = already_evaluated(today)
    scores_cache = {}
    results = []

    for p in preds:
        if p.get("action") != "APOSTAR":
            continue
        if p.get("bet_type") != "moneyline":
            print(f"  skip {p['id']}: bet_type={p.get('bet_type')} (MVP solo moneyline)")
            continue
        if p["id"] in done:
            continue
        sport = p["sport"]
        if sport not in scores_cache:
            scores_cache[sport] = final_scores(sport, pred_date)
        status, sc = scores_cache[sport].get(p.get("event_id"), ("", {}))
        if not sc or any(v == 0 for v in sc.values()) and "final" not in (status or "").lower() \
           and status != "STATUS_FINAL":
            print(f"  skip {p['id']}: sin score final (status={status})")
            continue

        sel_team = p["selection"].replace(" ML", "").strip()
        winner = max(sc, key=sc.get)
        won = sel_team.lower() in winner.lower() or winner.lower() in sel_team.lower()
        stake = p.get("stake_pct", 0)
        dec = american_to_decimal(p["book_odds_american"])
        pnl_units = stake * (dec - 1) if won else -stake
        outcome = 1 if won else 0
        model_prob = p.get("model_prob")
        calib = abs(model_prob - outcome) if model_prob is not None else None

        results.append({
            "prediction_id": p["id"],
            "evaluated_at_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "resolution": "won" if won else "lost",
            "actual_score": " — ".join(f"{k} {v}" for k, v in sc.items()),
            "outcome_binary": outcome,
            "stake_pct": round(stake, 4),
            "pnl_units": round(pnl_units, 4),
            "pnl_amount": round(pnl_units * 1000, 2),
            "edge_realized": None,
            "calibration_error": round(calib, 4) if calib is not None else None,
            "notes": p.get("reasoning_summary", "")[:120],
            "tags": ["moneyline"] + (["thesis_held"] if won else ["thesis_failed"]),
        })

    if results:
        os.makedirs(os.path.join(ROOT, "evaluations"), exist_ok=True)
        out = os.path.join(ROOT, "evaluations", f"{today}.jsonl")
        with open(out, "a", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return results


def main():
    if len(sys.argv) < 2:
        print("uso: python evaluate.py <fecha-de-la-prediccion>"); sys.exit(1)
    res = evaluate(sys.argv[1])
    print(f"\n  EVALUACIÓN -- predicciones del {sys.argv[1]} -- {len(res)} resueltas\n")
    for r in res:
        print(f"  {r['resolution'].upper():<5} {r['prediction_id']:<40} "
              f"pnl {r['pnl_units']:+.4f}u  calib_err {r['calibration_error']}")
    print()


if __name__ == "__main__":
    main()
