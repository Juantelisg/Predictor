"""promote.py — prepara candidatos de scan.py para Opus y escribe predicciones.

scan.py escribe candidates/. Este módulo:
  (a) enriquece cada candidato con el contexto que Opus necesita (abridores MLB) y lo
      imprime como "packet";
  (b) ofrece append_prediction() para escribir una línea schema-correcta en predictions/
      una vez que Opus asignó model_prob / action / señales.

La aritmética del candidato ya viene de scan.py (determinística). El JUICIO —model_prob,
APOSTAR/PASAR, 2 señales corroboratorias— lo pone Opus. Por eso esto NO decide solo.

Uso:
    python promote.py mlb [YYYY-MM-DD]     # imprime packets para que Opus los analice
"""
import sys, os, json, datetime

ROOT = os.path.dirname(os.path.abspath(__file__))

REQUIRED = ["id", "sport", "match", "bet_type", "selection", "book_odds_american",
            "fair_prob_devigged", "market_prob", "model_prob", "edge", "edge_tier",
            "action", "stake_pct", "reasoning_summary"]


def load_candidates(date, sport):
    p = os.path.join(ROOT, "candidates", f"{date}_{sport}.jsonl")
    return [json.loads(l) for l in open(p, encoding="utf-8-sig") if l.strip()] if os.path.exists(p) else []


def build_packets(date, sport):
    """Cada candidato + disponibilidad de jugadores (sport-aware) para análisis de Opus."""
    cands = load_candidates(date, sport)
    if not cands:
        return []
    import availability
    mlb_av = availability.for_game("mlb", date=date) if sport == "mlb" else None
    packets = []
    for c in cands:
        away, home = (c["match"].split(" @ ") + [None, None])[:2]
        if sport == "mlb":
            ctx = {"type": "mlb",
                   "starters": mlb_av["starters"].get(c["match"]) if mlb_av else None,
                   "lineup": mlb_av["lineups"].get(c["match"]) if mlb_av else None}
        elif sport == "nba":
            ctx = availability.for_game("nba", home=home, away=away)
        else:
            ctx = availability.for_game(sport, event_id=c.get("event_id"))
        packets.append({"candidate": c, "availability": ctx})
    return packets


def append_prediction(pred):
    """Escribe una predicción schema-correcta en predictions/<fecha>.jsonl. La llama Opus."""
    missing = [k for k in REQUIRED if k not in pred]
    if missing:
        raise ValueError(f"faltan campos requeridos: {missing}")
    pred.setdefault("timestamp_utc", datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    pred.setdefault("supra_agent_version", "0.1.0")
    pred.setdefault("model_used", "claude-opus-4-8")
    date = pred["id"].split("_")[1]
    os.makedirs(os.path.join(ROOT, "predictions"), exist_ok=True)
    path = os.path.join(ROOT, "predictions", f"{date}.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(pred, ensure_ascii=False) + "\n")
    return path


def main():
    sport = sys.argv[1].lower() if len(sys.argv) > 1 else "mlb"
    date = sys.argv[2] if len(sys.argv) > 2 else datetime.date.today().isoformat()
    packets = build_packets(date, sport)
    print(f"\n  PACKETS PARA OPUS -- {sport.upper()} -- {date} -- {len(packets)} candidato(s)\n")
    if not packets:
        print("  Sin candidatos (scan.py no encontró divergencia >= umbral). Nada que promover.\n")
        return
    for pk in packets:
        c = pk["candidate"]
        print(f"  - {c['selection']}  | edge {c['edge_provisional']*100:.1f}% | "
              f"fair {c['fair_prob_devigged']:.3f} vs PM {c['market_prob']:.3f} | "
              f"mejor cuota {c['book_odds_american']}@{c['book']}")
        av = pk["availability"]
        if av.get("type") == "mlb" and av.get("starters"):
            s = av["starters"]
            print(f"      SP: {s['away'][0]} (ERA {s['away'][1]}) @ {s['home'][0]} (ERA {s['home'][1]})")
            if av.get("lineup"):
                print(f"      lineup de bateo publicado")
        elif av.get("type") == "nba" and av.get("injuries"):
            for team, inj in av["injuries"].items():
                bad = [i["name"] for i in inj if i.get("status") in ("Out", "Doubtful", "Day-To-Day")]
                if bad:
                    print(f"      {team} (afectados): {', '.join(bad)}")
        elif av.get("type") == "soccer" and av.get("lineups"):
            for team, lu in av["lineups"].items():
                print(f"      {team} XI: {', '.join(lu['starting'][:11])}")
        print(f"      -> Opus: asignar model_prob + 2 señales, decidir APOSTAR/PASAR, append_prediction()\n")


if __name__ == "__main__":
    main()
