"""uncertainty.py - confianza por n EFECTIVA: un 70% sacado de 5 partidos no vale lo que uno
de 200. CERO promesas.

El staking (stake.py) ya escala el Kelly por una 'confianza' [0,1]; hasta ahora era fija (0.7).
Aca esa confianza sale de cuanta MUESTRA evaluada respalda esa familia de mercado: con poca
data, la confianza baja -> el Kelly encoge (o PASA). Es la traduccion honesta de "no se lo
suficiente todavia" a "arriesga menos".

band() da una banda de CONFIANZA (no un posterior real): ancho ~ 1/sqrt(n_efectiva), para
mostrar al lado de la prob cuanto pesa la muestra. Etiquetada como tal, sin fingir precision.

Uso:
  python uncertainty.py        # confianza por familia segun la muestra evaluada de hoy
"""
import os, sys, math
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

CONF_MIN, CONF_MAX = 0.40, 0.90    # piso (por debajo de MIN_CONF de stake, PASAR) y techo
K = 25                             # half-saturacion en PARTIDOS: n=K -> a mitad de camino del techo


def effective_n(family, version=None, con=None):
    """Cuantos PARTIDOS UNICOS respaldan esa familia (y version si se da). Antes contaba FILAS
    de evaluations (~3-12 por partido) -> inflaba la muestra. Un partido = una observacion
    independiente; sus mercados estan correlacionados. Proxy honesto de cuanto 'sabemos'."""
    sql = ("SELECT COUNT(DISTINCT date || '|' || home || '|' || away) AS n "
           "FROM evaluations WHERE market LIKE ?")
    params = [f"{family}:%"]
    if version:
        sql += " AND model_version = ?"
        params.append(version)
    return db.query(sql, tuple(params), con=con)[0]["n"]


def confidence(family, version=None, con=None):
    """Confianza [CONF_MIN, CONF_MAX] para el staking, creciente con la muestra evaluada.
    n=0 -> piso (data-starved, el Kelly casi no entra); n grande -> techo."""
    n = effective_n(family, version, con)
    return round(CONF_MIN + (CONF_MAX - CONF_MIN) * n / (n + K), 3)


def band(prob, n_eff):
    """Banda de confianza (NO un intervalo posterior): half-width ~ z*sqrt(p(1-p)/n). Para
    mostrar al lado de la prob cuanto la respalda la muestra. n_eff chica -> banda ancha."""
    if n_eff <= 0:
        return 0.5
    z = 1.0      # ~68% (1 sigma), honesto y legible; no pretende rigor frecuentista sobre un modelo
    return round(min(z * math.sqrt(max(prob * (1 - prob), 1e-4) / n_eff), 0.5), 3)


def main():
    fams = db.query("SELECT substr(market,1,instr(market,':')-1) fam, model_version ver, count(*) n "
                    "FROM evaluations GROUP BY fam, ver ORDER BY n DESC")
    print("=" * 60)
    print("  CONFIANZA POR n EFECTIVA  (alimenta el Kelly del staking)")
    print("=" * 60)
    print(f"  {'familia':<10}{'version':<14}{'n':>5}{'confianza':>11}")
    for r in fams:
        c = confidence(r["fam"], r["ver"])
        print(f"  {r['fam']:<10}{r['ver']:<14}{r['n']:>5}{c:>11.3f}")
    print(f"\n  piso {CONF_MIN} (= PASAR por debajo) · techo {CONF_MAX} · half-sat n={K}")
    print("  data-starved -> confianza baja -> Kelly encoge. Honesto: arriesga segun lo que sabes.")


if __name__ == "__main__":
    main()
