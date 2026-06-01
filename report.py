"""report.py — reporte de calibración desde predictions/ + evaluations/.

Lee todas las predicciones y evaluaciones, las cruza por prediction_id, y computa:
volumen (APOSTAR/PASAR), record W-L, PnL, ROI sobre lo arriesgado, Brier global y
calibración por bucket de probabilidad. Escribe reports/<hoy>_calibration.md.

Honestidad calibracional: con n chico todo es ruido y el reporte lo dice.

Uso: python report.py
"""
import os, sys, json, glob, datetime

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # consola Windows = cp1252
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))


def load_all(subdir, id_key):
    rows = {}
    for path in glob.glob(os.path.join(ROOT, subdir, "*.jsonl")):
        for line in open(path, encoding="utf-8-sig"):   # utf-8-sig: tolera BOM de PowerShell
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                rows[r[id_key]] = r
            except Exception:
                pass
    return rows


def main():
    preds = load_all("predictions", "id")
    evals = load_all("evaluations", "prediction_id")

    bet = [p for p in preds.values() if p.get("action") == "APOSTAR"]
    pasar = [p for p in preds.values() if p.get("action") == "PASAR"]
    resolved = [(preds[pid], ev) for pid, ev in evals.items() if pid in preds]

    won = sum(1 for _, e in resolved if e.get("resolution") == "won")
    lost = sum(1 for _, e in resolved if e.get("resolution") == "lost")
    pnl_u = sum(e.get("pnl_units", 0) or 0 for _, e in resolved)
    staked = sum(e.get("stake_pct", 0) or 0 for _, e in resolved)
    roi = (pnl_u / staked) if staked else 0

    # Brier + calibración por bucket usando model_prob de la predicción y outcome de la eval
    briers, buckets = [], {}
    for p, e in resolved:
        mp, ob = p.get("model_prob"), e.get("outcome_binary")
        if mp is None or ob is None:
            continue
        briers.append((mp - ob) ** 2)
        lo = int(mp * 10) * 10
        buckets.setdefault(lo, []).append(ob)
    brier = sum(briers) / len(briers) if briers else None

    today = datetime.date.today().isoformat()
    L = []
    L.append(f"# Reporte de calibración — {today}\n")
    L.append(f"**Generado**: {today} | **Fuente**: predictions/ + evaluations/ (automático)\n")
    L.append("## Volumen")
    L.append(f"- Predicciones totales: **{len(preds)}** ({len(bet)} APOSTAR, {len(pasar)} PASAR)")
    L.append(f"- Resueltas (con evaluación): **{len(resolved)}**\n")
    L.append("## Resultado de lo apostado")
    L.append(f"- Record: **{won}-{lost}**" + (f" ({won/(won+lost)*100:.0f}% aciertos)" if won + lost else ""))
    L.append(f"- PnL: **{pnl_u:+.4f}u** (~${pnl_u*1000:+.0f} sobre bankroll $1000)")
    L.append(f"- Arriesgado: {staked:.4f}u | **ROI: {roi*100:+.1f}%**\n")
    L.append("## Calibración")
    if brier is not None:
        L.append(f"- Brier score (n={len(briers)}): **{brier:.4f}**" +
                 ("  [!] n muy chico, ruido — no concluir nada." if len(briers) < 20 else ""))
        L.append("- Por bucket de model_prob (dijiste X% → ganó Y%):")
        for lo in sorted(buckets):
            obs = buckets[lo]
            L.append(f"    - {lo}-{lo+10}%: {len(obs)} preds, ganó {sum(obs)/len(obs)*100:.0f}%")
    else:
        L.append("- Sin datos suficientes (faltan model_prob u outcome). Nada que calibrar todavía.")
    L.append("\n---")
    L.append("*Educativo / entretenimiento. Apostar implica riesgo de pérdida total.*\n")

    md = "\n".join(L)
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    out = os.path.join(ROOT, "reports", f"{today}_calibration.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    print(f"\n  -> escrito en {os.path.relpath(out, ROOT)}")


if __name__ == "__main__":
    main()
