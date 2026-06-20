"""analizar.py - cuadro de analisis combinado en una sola corrida. CERO cuotas.

Operativiza el formato de analisis: junta el predictor estadistico (soccer + corners/
tarjetas StatsBomb) con los trends de Linemate (validacion cruzada / contexto). Aplica
el recalibrador (calib.py) al 1X2 -> muestra prob CRUDA y CALIBRADA: la brecha entre
ambas es una senal de fiabilidad ([5] del roadmap; un intervalo formal queda pendiente).

Las odds de Linemate son SOLO contexto de mercado, nunca edge (regla de oro).

Uso:
  python analizar.py "Paraguay" "Turkey" --lm=PAR,TUR
  python analizar.py "United States" "Australia" --home --lm=AUS,USA
  python analizar.py "Brazil" "Haiti"                 # sin Linemate (omitir --lm)
"""
import sys
import soccer, elo, calib

sys.stdout.reconfigure(encoding="utf-8")


def run(local, visita, neutral=True, lm_codes=None, league="wc"):
    df = soccer.load()
    df_elo, rating = elo.compute(df)
    teams = set(df.home_team) | set(df.away_team)
    L, V = soccer.resolve(local, teams), soccer.resolve(visita, teams)
    if not L or not V:
        print(f"  No reconozco: {local if not L else visita!r}")
        return
    r = soccer.predict(df_elo, rating, L, V, neutral=neutral, df_all=df)
    cp = calib.load()
    cal = lambda p: calib.apply(p, soccer.VERSION, cp)
    b = r["blend"]

    print("=" * 72)
    print(f"  ANALISIS  {L} vs {V}   ({'cancha neutral' if neutral else L + ' de local'})")
    print("=" * 72)
    print(f"  1X2 (modelo {soccer.VERSION})        {'cruda':>7} {'calibrada':>10}")
    print(f"    Gana {L:<18} {b[1]*100:>6.1f}% {cal(b[1])*100:>9.1f}%")
    print(f"    Empate{'':<17} {b[0]*100:>6.1f}% {cal(b[0])*100:>9.1f}%")
    print(f"    Gana {V:<18} {b[-1]*100:>6.1f}% {cal(b[-1])*100:>9.1f}%")
    print(f"    Doble:  1X {(b[1]+b[0])*100:.0f}%   X2 {(b[0]+b[-1])*100:.0f}%   12 {(b[1]+b[-1])*100:.0f}%")
    print(f"  Goles:  Over1.5 {r['over15']*100:.0f}%   Over2.5 {r['over']*100:.0f}%   "
          f"Over3.5 {r['over35']*100:.0f}%   BTTS {r['btts']*100:.0f}%")
    print(f"  Valla invicta:  {L} {r['cs_home']*100:.0f}%   {V} {r['cs_away']*100:.0f}%")

    try:
        import statsbomb_data as sb
        c, k = sb.predict_corners(L, V), sb.predict_cards(L, V)
        print(f"  Corners (exp {c['total_exp']}):  O8.5 {c['over85']*100:.0f}%   O9.5 {c['over95']*100:.0f}%")
        print(f"  Tarjetas (exp {k['total_exp']}):  O3.5 {k['over35']*100:.0f}%   O4.5 {k['over45']*100:.0f}%   "
              f"(ojo: el modelo SOBREESTIMA tarjetas)")
    except Exception as e:
        print(f"  Corners/tarjetas: sin datos StatsBomb ({str(e)[:60]})")

    if lm_codes:
        try:
            import linemate as lm
            tr = lm.game_trends(league, *lm_codes)
            print(f"\n  LINEMATE - {len(tr)} trends (validacion cruzada):")
            for t in tr:
                print(f"    {t['who'][:22]:<22} {t['market'][:17]:<17} "
                      f"{t['side'][:1].upper()}{t['line']:<5} L10={t['splits'].get('LAST_10')} "
                      f"SEA={t['splits'].get('SEASON')} sig={t['signal']}")
            g = lm.game_context(league, *lm_codes)
            if g:
                for s in ("homeTeamData", "awayTeamData"):
                    am = (g[s].get("odds") or {}).get("lines", {}).get("american", {})
                    code = g["homeTeamCode"] if s == "homeTeamData" else g["awayTeamCode"]
                    print(f"    [mercado, contexto] {code} ML {am.get('moneyLine')}")
        except Exception as e:
            print(f"  Linemate: error ({str(e)[:60]})")

    print("\n  Cruda = modelo; calibrada = tras recalibrador (calib.py, in-sample; las 3 vias")
    print("  del 1X2 calibradas pueden no sumar 100). Educativo, sin cuotas.\n")


def main():
    args = sys.argv[1:]
    non_flags = [a for a in args if not a.startswith("--")]
    if len(non_flags) < 2:
        print('  Uso: analizar.py "<local>" "<visita>" [--home] [--lm=COD1,COD2] [--league=wc]')
        return
    neutral = "--home" not in args
    lm = next((a.split("=", 1)[1].split(",") for a in args if a.startswith("--lm=")), None)
    league = next((a.split("=", 1)[1] for a in args if a.startswith("--league=")), "wc")
    run(non_flags[0], non_flags[1], neutral=neutral, lm_codes=lm, league=league)


if __name__ == "__main__":
    main()
