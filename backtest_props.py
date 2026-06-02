"""backtest_props.py - calibracion del modelo de props MLB contra resultados reales.

No usa cuotas (cero quota de The Odds API). Para un conjunto de bateadores baja su
game log de la temporada y camina hacia adelante: en cada juego estima model_prob con
SOLO los juegos previos (igual que produccion) y lo compara contra el resultado real
de ese juego. Mide calibracion para responder la pregunta del veredicto:

    cuando el modelo dice 80%, .cuantas veces pega de verdad?

Si dice 80% y pega 65% -> sobre-confiado en ese bucket (lo que vimos en el demo).

Uso:
    python backtest_props.py [YYYY-MM-DD] [K]      # K = fuerza del shrink (default 10)
"""
import sys, datetime, statistics
from concurrent.futures import ThreadPoolExecutor
import player_props as pp

MIN_PRIOR = 15      # minimo de juegos previos para arriesgar una prediccion
LAST_N = 10         # ventana reciente (L10), igual que produccion


def _over(row, label, line):
    return 1 if pp._value(row, label) > line else 0


def model_prob(recent_rows, prior_rows, label, line, k):
    """Produccion: over-rate del L10 regresado hacia la tasa de temporada (prior) con fuerza k."""
    over_recent = sum(_over(r, label, line) for r in recent_rows)
    n_recent = len(recent_rows)
    season_rate = sum(_over(r, label, line) for r in prior_rows) / len(prior_rows)
    return (over_recent + k * season_rate) / (n_recent + k)


def pairs_for_player(rows, k):
    """(label, model_prob, outcome) por cada juego >= MIN_PRIOR, para cada prop. Walk-forward."""
    out = []
    for i in range(MIN_PRIOR, len(rows)):
        prior = rows[:i]
        recent = rows[max(0, i - LAST_N):i]
        for label, line, _ in pp.PROPS:
            p = model_prob(recent, prior, label, line, k)
            out.append((label, p, _over(rows[i], label, line)))
    return out


def population_baseline(logs):
    """Media de la liga por (label, line) = blanco de la regresion poblacional."""
    num, den = {}, {}
    for rows in logs:
        for r in rows:
            for label, line, _ in pp.PROPS:
                key = (label, line)
                num[key] = num.get(key, 0) + _over(r, label, line)
                den[key] = den.get(key, 0) + 1
    return {k: num[k] / den[k] for k in num}


def model_prob_pop(prior_rows, label, line, mu, k):
    """Regresion a la media POBLACIONAL: toda la muestra previa del jugador hacia mu (Beta-Binomial)."""
    overs = sum(_over(r, label, line) for r in prior_rows)
    return (overs + k * mu) / (len(prior_rows) + k)


def pairs_pop(rows, baseline, k):
    out = []
    for i in range(MIN_PRIOR, len(rows)):
        prior = rows[:i]
        for label, line, _ in pp.PROPS:
            mu = baseline[(label, line)]
            p = model_prob_pop(prior, label, line, mu, k)
            out.append((label, p, _over(rows[i], label, line)))
    return out


def _player_set(date, cap=140):
    seen, players = set(), []
    for g in pp._schedule(date):
        for pid, *_ in pp._batters_for_game(g):
            if pid in seen:
                continue
            seen.add(pid); players.append(pid)
            if len(players) >= cap:
                return players
    return players


def reliability(pairs, nbuckets=10):
    buckets = {i: [] for i in range(nbuckets)}
    for _, p, out in pairs:
        buckets[min(int(p * nbuckets), nbuckets - 1)].append((p, out))
    brier = statistics.mean((p - out) ** 2 for _, p, out in pairs)
    rows = []
    for b in range(nbuckets):
        v = buckets[b]
        if not v:
            continue
        rows.append((b * 10, (b + 1) * 10, len(v),
                     statistics.mean(p for p, _ in v), statistics.mean(o for _, o in v)))
    return rows, brier


def run(date, k):
    season = pp._season(date)
    pids = _player_set(date)
    with ThreadPoolExecutor(max_workers=10) as ex:
        logs = list(ex.map(lambda pid: (lambda: pp.gamelog(pid, season))(), pids))
    pairs = []
    for rows in logs:
        if len(rows) > MIN_PRIOR:
            pairs.extend(pairs_for_player(rows, k))
    return pairs, reliability(pairs)


def _hi_gap(pairs):
    hi = [(p, o) for _, p, o in pairs if p >= 0.70]
    if not hi:
        return None
    return statistics.mean(p for p, _ in hi), statistics.mean(o for _, o in hi), len(hi)


def sweep(date):
    """Compara modelo actual (L10->temporada) vs poblacional, barriendo K. Cero quota."""
    season = pp._season(date)
    pids = _player_set(date)
    with ThreadPoolExecutor(max_workers=10) as ex:
        logs = [l for l in ex.map(lambda pid: pp.gamelog(pid, season), pids) if len(l) > MIN_PRIOR]
    base = population_baseline(logs)
    print(f"\n  SWEEP -- temporada {season} -- {len(logs)} bateadores\n")
    print(f"  {'modelo':<26} {'K':>4} {'Brier':>8} {'zona>=70% pred':>16} {'real':>7} {'gap':>7}")
    print("  " + "-" * 74)
    # baseline: modelo actual L10->temporada
    for k in (10, 20):
        pairs = []
        for rows in logs:
            pairs.extend(pairs_for_player(rows, k))
        _, brier = reliability(pairs)
        g = _hi_gap(pairs)
        gp = f"{g[0]*100:.1f}% (n={g[2]})" if g else "-"
        print(f"  {'L10->temporada':<26} {k:>4} {brier:>8.4f} {gp:>16} {g[1]*100:>6.1f}% {(g[0]-g[1])*100:>+6.1f}")
    # candidato: regresion poblacional
    for k in (5, 10, 20, 30, 50):
        pairs = []
        for rows in logs:
            pairs.extend(pairs_pop(rows, base, k))
        _, brier = reliability(pairs)
        g = _hi_gap(pairs)
        gp = f"{g[0]*100:.1f}% (n={g[2]})" if g else "-"
        print(f"  {'poblacional (Beta-Bin)':<26} {k:>4} {brier:>8.4f} {gp:>16} {g[1]*100:>6.1f}% {(g[0]-g[1])*100:>+6.1f}")
    print("\n  menor Brier + gap chico en zona>=70% = mejor calibrado\n")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "sweep":
        sweep(sys.argv[2] if len(sys.argv) > 2 else datetime.date.today().isoformat())
        sys.exit(0)
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    k = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
    pairs, (rows, brier) = run(date, k)
    print(f"\n  CALIBRACION modelo props MLB -- temporada {pp._season(date)} -- K={k}")
    print(f"  {len(pairs)} predicciones walk-forward | Brier={brier:.4f}\n")
    print(f"  {'bucket':<10} {'n':>7} {'predicho':>10} {'real':>8} {'gap':>8}")
    print("  " + "-" * 46)
    for lo, hi, n, pred, act in rows:
        print(f"  {lo:>2}-{hi:<6}% {n:>7} {pred*100:>9.1f}% {act*100:>7.1f}% {(pred-act)*100:>+7.1f}")
    # resumen del bucket donde apostamos (>=70%)
    hi_pairs = [(p, o) for _, p, o in pairs if p >= 0.70]
    if hi_pairs:
        pp_pred = statistics.mean(p for p, _ in hi_pairs)
        pp_act = statistics.mean(o for _, o in hi_pairs)
        print(f"\n  >>> ZONA DE APUESTA (modelo >=70%): predice {pp_pred*100:.1f}%, pega {pp_act*100:.1f}%"
              f"  -> sobre-confianza {(pp_pred-pp_act)*100:+.1f} pts ({len(hi_pairs)} preds)")
    print()
