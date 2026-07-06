# AUDIT FABLE — 2026-07-04 (ciclo 2)

> **De:** Fable (auditor/arquitecto). **Para:** Opus (ejecutor) y el usuario.
> **Base:** medición HOY contra las baselines congeladas del audit anterior
> (`docs/AUDIT_FABLE_2026-07-01.md` §11): retro re-corrido (n=85), `feedback.report` (n=916),
> `regime.py` walk-forward, `pnl.py gates`, `clv.py report`, `prop_value.py report`, 138 tests.
> Donde una claim de PLAN.md contradice la medición de hoy, manda la medición (ver §2-T5).
> **Objetivo pedido por el usuario:** que el modelo siga en camino a **acertar más de lo que
> pierde** — acá está traducido a métricas norte (§4) y tickets ejecutables (§5).

---

## 0. Veredicto ejecutivo

1. **Los fixes del ciclo 1 funcionaron donde se los midió.** El sesgo de goles quedó arreglado
   (−0.39 → **−0.13** por partido, objetivo <0.15 ✓); over pasó de −8.2pt a **−2.5pt**; el ancla
   1X2 MEJORÓ (log loss 0.881 → **0.857**, accuracy 64.7%); la ECE calibrada volvió a ser mejor
   que la cruda (0.0380 vs 0.0383, era 0.0556 vs 0.0378 ✗); el bug de inversión del calibrador
   murió; el 1X2 renormaliza; 138 tests verdes (eran 80).

2. **El hallazgo #1 de este ciclo NO es de modelo, es de CADENCIA: el loop estuvo PARADO
   del 02 al 03 de julio.** `dashboard.bat` no se abre desde el 29-jun (el producto vivo migró a
   Render, que solo sirve la API — no corre `loop.py`). Resultado: los partidos de octavos del
   07-02 y 07-03 **no tienen predicciones forward, ni candidatas de edge, ni flags de props, ni
   shadow del sensor** — muestra perdida para siempre en el torneo que es nuestra ventana de
   validación (termina ~19-jul). Ningún forward-test llega a n si el loop depende de un doble-click
   humano. **Esta auditoría lo re-corrió hoy** (51 predicciones 07-04, 18 evals resueltas), pero
   la solución es automatizarlo (R1). Todo lo demás de este plan está gated por R1.

3. **El sesgo dominante que queda es NUEVO y es accionable: subconfianza en favoritos en
   eliminatorias.** Favoritos: predigo 59.1%, ganan 64.7% (−5.6pt, empeoró desde −3.0); bucket
   40-60%: observado 65.8% vs predicho 49.4%. El régimen de la 3ª fecha de grupos (empates en
   cadena) ya no existe: en eliminatorias el favorito aprieta y el empate a los 90' vale menos.
   El modelo, ciego a la fase, sigue repartiendo ~25% al empate. Mismo molde de fix que el factor
   de goles: capa WC walk-forward, motor intacto (R3). **Esto es exactamente donde juega el
   usuario** (su tracker del 07-03 = favoritos, doble oportunidad, over 1.5): arreglarlo sube el
   % de aciertos de los picks que efectivamente se juegan.

4. **La fuente de ROI #1 (props multi-book) sigue sin resolver el WC — y el desbloqueo ya está
   escrito.** `prop_value._resolve_one` declara "no hay fuente per-fixture gratis de props WC"…
   pero `espn_players.py` (construido un día DESPUÉS) trae exactamente eso: SOT/goles/asistencias
   por jugador por partido, verificado idéntico a API-Football. Cablearlo (R2) convierte una
   máquina que loguea flags sin veredicto en un forward-test real.

5. **La capa de valor 1X2 quedó tan estricta que no acumula veredicto.** Con `W_BET=0.5`,
   `MIN_EDGE=0.03` se evalúa sobre `p_bet` → el corte efectivo es ~6% de edge crudo, y
   `MAX_EDGE=0.10` marca SOSPECHOSO arriba del 10%: la ventana apostable real es [6%, 10%] crudo.
   Candidatas edge-v2 truly-forward en 3 días: **2** (ambas PASAR). El CLV confirma la tesis
   (0/16 le gana al cierre, medio −0.19pt): en el 1X2 líquido NO está nuestra plata — pero el
   forward-test necesita caudal para ser un veredicto y no una anécdota (R4).

---

## 1. Medición contra las baselines congeladas del 07-01

| Métrica | Baseline 07-01 | HOY 07-04 | Veredicto |
|---|---|---|---|
| Retro WC: ll 1X2 / ECE | 0.881 / 0.053 (n=79) | **0.857** / 0.063 (n=85) | ll MEJOR ✓ · ECE levemente peor (favoritos, §0.3) |
| Retro: sesgo de goles | −0.39/partido | **−0.13** | **T6 CUMPLIDO** (objetivo <0.15) |
| Retro: Over 2.5 | −8.2pt bajista | **−2.5pt** (ll 0.679 < 0.686) | T6 ✓ |
| Retro: empates | −3.7pt | −1.7pt | mejoró |
| Retro: favoritos | −3.0pt subconf. | **−5.6pt** · bucket 40-60: obs 65.8% vs 49.4% | **EMPEORÓ → R3** |
| ECE calibrada vs cruda | 0.0556 vs 0.0378 (peor!) | **0.0380 vs 0.0383** | **T1 CUMPLIDO** |
| Cards walk-forward (regime v2) | 0.284 crudo / +28.2pt | Brier **0.2405** / gap **+11.3pt** (n=75) | Mejoró mucho, **NO cumple T5** (<0.22 / <8pt) → R5 |
| Corners (regime v2) | 0.207 / +3.3pt | gap **+0.6pt**, pero Brier v2 0.2548 > v1 0.2483 | gap excelente; factor≈0.987 (no hacía falta) → R8 |
| Forward edge ROI flat | −40.7% (n=26) | v1 cerrado: −34.1% (n=42) · **v2: n=2** (sin veredicto) | v2 INANICIÓN → R1+R4 |
| CLV | 0/28, cierre=apertura (no medía) | **16/29 con cierre real (55%)** ✓ T4 · CLV medio −0.19pt, 0/16 | La métrica ya mide; lo que mide es "no hay edge 1X2" |
| Props +EV | no existía | Flags corren (38 el 07-01) · **resueltos: 0** (resolver=solo MLB) | **BLOQUEADO → R2** |
| Tests | 80 verdes | **138 verdes** | ✓ |
| Cadencia del loop | manual (dashboard.bat) | **paró 07-02/07-03**; reactivado hoy a mano | **ROTO → R1** |

Estado del recalibrador por familia hoy (`feedback.report`, n=916): 1x2/dc ~0% gap ✓ · corners
+1.0% ✓ · cs +7.1% · ml +6.9% (OOS dice que calibrar DEGRADA → queda en identidad, correcto) ·
cards +24.2% crudo (la v2 de regime lo baja a +11.3 walk-forward) · over −11.7% y btts −14.6%
**PERO** esas filas mezclan la era pre-factor-de-goles con la nueva bajo la misma `model_version`
→ el gap vigente real del over es ~−2.5pt (retro). Separar eras es R6.

---

## 2. Estado real de los tickets del ciclo 1 (verificado, no según PLAN.md)

- **T1 (higiene calibrador):** ✓ cumplido y medido (ECE cal ≤ cruda; ml en identidad por gate OOS).
- **T2 (1X2 por outcome + renorm):** ✓ en producción; el report separa draw (+3.9%) / home (−8.8%) /
  away (+4.9%) — la señal de R3 sale de acá.
- **T3 (cirugía de valor):** ✓ código en producción (power de-vig, gates, p_bet). Gate-replay:
  −34.1% → +1.0% (cap longshot) → +1.3% (sin empates). **Pendiente el veredicto truly-forward** (n=2).
- **T4 (CLV):** ✓ cumplido (55% con cierre real ≥ objetivo 50%). schtasks corre aunque con huecos
  (4 snapshots en 3 días: la PC no siempre está prendida — R1 lo mitiga con más horarios).
- **T5 (cards/corners v2):** ⚠️ **NO cumplido**: cards Brier 0.2405 (objetivo <0.22), gap +11.3pt
  (objetivo <8). OJO: la claim de PLAN.md "cards +28%→+4.5%" era del día del fit; el walk-forward
  de HOY da +11.3 — corregir el doc (R9). Corners: el gap quedó excelente pero el Brier v2 empeora
  marginalmente (el factor ≈1 no corrige nada y la reconstrucción mete ruido).
- **T6 (factor de goles):** ✓ **cumplido y vivo** (goals_factor=1.116 en el log de hoy; sesgo −0.13).
- **T7 (props multi-book):** ⚠️ mitad: flags y fair de consenso corren; **resolver solo MLB** → 0
  resueltos, n=0/50. El desbloqueo WC existe y es gratis (espn_players) — R2.
- **T8 (bug `*0` + acople):** ✓ bug muerto; acople medido ~0 con n=24 → se mantiene independencia
  documentada (decisión correcta: medido > inventado).
- **T9 (calibración manda en el producto):** ✓ picks/cartera/ticket usan prob calibrada por familia.
- **T10 (curva del empate):** ✓ REFUTADA por el sweep y documentada en soccer.py (regla de honestidad).
- **T11 (docs):** ✓ parcial — quedó vieja la claim de T5 en PLAN.md y `retro_last.txt` sigue siendo
  el del 23-jun (el retro nuevo escribe `backtest_wc_last.txt` solo vía dashboard.bat, que no corre).

**Sin commitear en el working tree** (verificado hoy): `tracker.py` + `data/tracker/` (la planilla
viva), `app.py` (warm-cache al arranque + tarjetas en paralelo + single-flight de cache — mejoras
reales de Render), `cache.py`, `App.jsx` + dist. Commitearlas es parte de R9.

---

## 3. El hallazgo estructural: la cadencia depende de un humano

Cadena verificada: `loop.py` (log pre-partido → eval → re-fit → candidatas edge → flags props →
resolver → sync DB → CLV) solo corre cuando el usuario abre `dashboard.bat`. Última corrida real:
**06-29** (loop_last.txt). El 07-01 corrió a mano por la ejecución de los tickets. Después, nada
hasta hoy. Mientras tanto los octavos de final pasaron de largo: cero forward-rows de Spain-Austria,
Portugal-Croatia, Brazil-Japan, France-Sweden…, cero candidatas edge-v2 nuevas, cero shadow del
sensor (1 solo partido logueado, y solo porque el endpoint lazy se abrió a mano una vez).

Lo único que sí corrió solo fue `snapshot.bat` (schtasks de T4) — la prueba de que schtasks es el
mecanismo correcto en esta máquina.

**Consecuencia estratégica:** el Mundial termina ~19-jul. Quedan ~2 semanas de la mejor ventana de
validación forward que este proyecto va a tener en meses. Cada día sin loop = un día menos de n
para edge-v2 (necesita ≥30), props (necesita ≥50) y el shadow del sensor. R1 es el ticket #1 por
leverage, no por elegancia.

---

## 4. "Acertar más de lo que pierde" — traducción de cuant, sin humo

El % de aciertos del usuario NO sube haciendo el modelo más agresivo; sube por cuatro vías medibles:

1. **Que el pick prometido de 75% pegue ≥75%.** Hoy los picks ALTA están SUBvaluados (favoritos
   −5.6pt): el usuario ya cobra más de lo que el número promete. Arreglar R3 alinea el número y
   además destapa picks que hoy quedan bajo el umbral de confianza por modestia del modelo.
2. **Jugar solo donde el modelo está calibrado.** El gate por familia (T9) ya lo impone en el
   producto. Cards sigue fuera (gap +11.3 aún tras v2). Corners está calibrado (+0.6pt) → puede
   entrar a picks del producto (R8) — más superficie de picks buenos = más aciertos.
3. **Que el valor venga de donde hay valor estructural**: props multi-book (books blandos que
   discrepan entre sí), no del 1X2 de DraftKings (CLV 0/16 lo confirma). R2 es el camino.
4. **Medir el hit-rate REAL del usuario**, no el teórico: el tracker ya captura qué juega
   (Decision=JUGAR); falta cerrarle el loop con Resultado/PnL automático (R7). Sin esto, "% de
   aciertos" es una sensación, no un número.

Métricas norte del ciclo 2 (en este orden):
- **N1:** cero días sin loop (proxy: predictions/ tiene archivo todos los días con partidos).
- **N2:** hit-rate de picks ALTA ≥ su prob prometida (bucket a bucket, tracker + feedback).
- **N3:** props: ≥50 flags resueltos y ROI flat por mercado reportado (veredicto, sea cual sea).
- **N4:** edge-v2: n≥30 resueltas → ROI flat > −5% y CLV ≥ 0 (heredado del ciclo 1).
- **N5:** retro: ll 1X2 ≤ 0.857, ECE ≤ 0.055, |sesgo goles| < 0.15, favoritos |gap| < 3pt.

---

## 5. TICKETS PARA OPUS (ciclo 2 — ejecutar en este orden)

> Reglas comunes heredadas del audit 07-01 §10 (Python real, tests verdes, cp1252 en prints,
> utf-8-sig al leer JSONL, cuotas jamás al motor/fit, versionado + walk-forward). Nuevas de este
> ciclo: (a) toda claim de mejora que entre a un doc lleva el número WALK-FORWARD del día, no el
> del fit; (b) ningún ticket de modelo se da por cerrado sin re-correr el retro y pegar el bloque
> de sesgos en el reporte del ticket.

### R1 — Cadencia autónoma (el ticket #1; gatea todos los demás)
**Archivos:** tarea programada nueva (schtasks, molde de `snapshot.bat`), `loop.py`, `sensor.py`,
`dashboard.bat`, README.
**Cambios:** (1) `loop.bat` + schtasks cada 2-3h entre 10:00 y 23:00 (el loop es idempotente —
verificado: re-corrió hoy sin duplicar nada; los pasos ya son tolerantes a fallo). Redirect con
`-Encoding utf8`. (2) Paso nuevo en loop.py: `sensor.log_shadow` para TODOS los partidos del día
(hoy es lazy: solo loguea si alguien abre el endpoint → 1 partido en 2 días). (3) Paso nuevo:
`tracker.build(date)` (refresca la planilla del usuario sin pisar sus columnas — ya es merge-safe).
(4) `backtest_wc.py` semanal (no por corrida: tarda minutos) → `backtest_wc_last.txt` UTF-8.
**Aceptación:** 3 días corridos SIN intervención manual con: `predictions/`, `bets/`,
`props_flags/`, `data/shadow/` y `data/tracker/` del día poblados; `loop_last.txt` legible como
UTF-8; CLV report con ≥60% de bets nuevas con cierre real.

### R2 — Resolver de props WC vía ESPN (desbloquea la fuente de ROI #1)
**Archivos:** `prop_value.py` (`_resolve_one`), `espn_players.py` (reutilizar `_summary`/rosters),
`tests/test_prop_value.py`.
**Cambios:** enrutar flags de soccer/WC a un resolver que saque el stat real del jugador del
boxscore ESPN del partido (`shotsOnTarget`, `totalGoals`, `goalAssists`, y `_ga` derivado).
**`SHOTS` (tiros totales) NO se resuelve con ESPN** (definición distinta al book, POC 07-02):
queda `unresolved:definition` explícito o se resuelve vía API-Football con `budget.guard`.
Matching jugador↔roster por nombre normalizado (mismo molde que ya usa espn_players).
**Aceptación:** los flags WC del 07-01 (SOT/GOALS/ASSISTS) quedan resueltos contra los boxscores
reales; `prop_value.py report` imprime n resueltos > 0 y ROI flat por mercado; el resolver corre
dentro de loop.py; cero requests nuevos a API-Football sin budget; pytest verde con test del
matching y del caso `unresolved`.

### R3 — Régimen de FASE: favoritos/empate en eliminatorias (el sesgo dominante)
**Archivos:** `regime.py` (nuevo `stage_factor` o similar), `feedback.py`/`analizar.py` (aplicación
capa WC), `backtest_wc.py` (validación), `tests/`.
**Cambios:** (1) PRIMERO medir: partir el retro por fase (fecha 1-2 de grupos / fecha 3 / KO) y
reportar gap de favorito y de empate por fase — el diagnóstico va al reporte del ticket ANTES del
fix. (2) Si el patrón es real (esperado: empate sobrestimado y favorito subestimado en KO), factor
de fase sobre la prob de empate del 1X2 (redistribuir hacia el lado más probable, renormalizar),
estimado walk-forward con shrink (K≈10 partidos KO), aplicado SOLO a partidos WC de eliminatoria.
Motor intacto (mismo patrón que goals_factor). El empate en KO se define resultado a los 90'
(así se apuesta y así lo loguea feedback — verificar y testear).
**Aceptación (retro, walk-forward):** favoritos |gap| < 3pt (hoy −5.6) y bucket 40-60 |gap| < 8pt
(hoy 16.4) SIN degradar: ll 1X2 ≤ 0.857, ECE ≤ 0.063 (objetivo ≤ 0.055), empates |gap| < 3pt.
Si la medición del paso 1 NO muestra patrón por fase → documentar y cerrar sin fix (honestidad).

### R4 — Caudal para el veredicto edge-v2 (sin aflojar guardrails)
**Archivos:** `odds.py`, `pnl.py`, `edge.py` (solo docstring/constante documentada), `tests/`.
**Cambios:** (1) ingesta de cuota de TOTALES desde ESPN pickcenter (`overUnder` viene en el mismo
payload que ya fetcheamos; hoy odds.py solo saca moneyline) → la familia `over` (QUALIFIED y ahora
calibrada post-T6) empieza a generar candidatas. (2) Documentar en edge.py la ventana efectiva:
con W_BET=0.5, MIN_EDGE=0.03 sobre p_bet ≡ ~6% de edge crudo; DECISIÓN EXPLÍCITA (no silenciosa):
mantener el umbral pero loguear TODAS las candidatas con edge crudo ≥3% con su tier contrafactual
(`tier_if_bet`), para que el forward-test acumule veredicto de la política Y de sus alternativas.
(3) `pnl.report` desglosa por familia además de tier/version.
**Aceptación:** con el slate de un día real, bets/ registra candidatas de over cuando hay cuota;
promedio ≥4 candidatas/día (WC+MLB) logueadas (incl. PASAR contrafactual); replay: el reporte
del ticket documenta cuántas candidatas históricas habrían existido con totales. pytest verde.

### R5 — Cards v2 no alcanzó: iterar el régimen (sigue FUERA de la capa de valor)
**Archivos:** `regime.py`, `tests/test_regime.py`.
**Cambios:** hipótesis a probar EN ORDEN con walk-forward (parar en la primera que cumpla):
(1) partir el factor por fase (KO trae eliminación + prórroga → más amarillas que grupos: medir);
(2) K más chico (6→3) — el costo es varianza al arranque, medible; (3) base por confederación del
árbitro SOLO si el dato ya está gratis en los boxscores que cosechamos (no agregar fuente nueva).
**Aceptación:** la MISMA de T5: cards Brier walk-forward < 0.22 y |gap| < 8pt (hoy 0.2405/+11.3);
corners no empeora (v2 Brier ≤ v1 0.2483 — hoy 0.2548, arreglarlo o dejar corners en v1
documentado); cards sigue excluida de QUALIFIED y de picks hasta cumplir. pytest verde.

### R6 — Separar eras del modelo en el feedback (que los fixes se VEAN en el forward)
**Archivos:** `feedback.py`, `tests/`.
**Cambios:** las predicciones post-factor-de-goles conviven con las viejas bajo `soccer-v3` → el
gap de over/btts/cs del report mezcla eras y esconde la mejora. Fix mínimo: `feedback.report`
agrega bloque "modelo vigente" filtrando `date >= 2026-07-01` (o mejor: log nuevo lleva
`model_version="soccer-v3.1"` y el report agrupa por versión — preferido, es el patrón de la casa).
**Aceptación:** el report muestra n y gap por era; la era vigente de over muestra gap ≈ el del
retro (−2.5pt), no el −11.7% mezclado; pytest verde.

### R7 — Cierre automático del tracker + hit-rate real del usuario (la métrica pedida)
**Archivos:** `tracker.py`, `loop.py`, `tests/`.
**Cambios:** (1) `tracker.py resolve [fecha]`: completa Resultado/PnL de las filas con
Decision anotada, usando los resultados ESPN ya cosechados (feedback los tiene; mapear mercado
de la fila → outcome real: 1X2/DC/over/BTTS ya se resuelven en feedback.evaluate — reutilizar esa
lógica, no duplicarla). PnL solo si hay Cuota y Stake; si no, marca WON/LOST igual (el hit-rate
no necesita plata). NUNCA pisar una celda ya escrita a mano (regla existente del merge). (2) En
loop.py, después del eval. (3) Mini-reporte `tracker.py stats`: hit-rate por bucket de prob de
las filas JUGADAS vs prob prometida + PnL acumulado.
**Aceptación:** las filas del 07-03 (Argentina, etc.) quedan resueltas; una fila con Resultado
manual NO se pisa (test); `tracker.py stats` imprime hit-rate real vs prometido; pytest verde.

### R8 — Corners entra al PRODUCTO (no a la plata)
**Archivos:** `analizar.py` (gate de familias de picks), doc.
**Cambios:** corners está calibrado (+0.6pt walk-forward, +1.0% en feedback) → habilitarlo en
picks confiables/cartera CON prob calibrada (el gate general de T9 ya existe: es agregar la
familia a la lista de calificadas DE PRODUCTO). Sigue SIN cuota (Linemate WC no trae córners,
ESPN tampoco) → no entra a la capa de valor; etiqueta clara en el producto.
**Aceptación:** picks de córners aparecen con prob calibrada y por encima del umbral de
confianza; cards sigue excluida; test del gate actualizado; pytest verde.

### R9 — Higiene y verdad documental
**Archivos:** working tree, `PLAN.md`, `predictor/README.md`.
**Cambios:** (1) commitear lo pendiente: `tracker.py` + `data/tracker/`, `app.py` (warm-cache +
paralelo + single-flight), `cache.py`, `App.jsx` — con `npm run build` + `git add -f` de los
assets nuevos de dist (gotcha de deploy conocido: si no, pantalla blanca en Render). (2) PLAN.md:
corregir la claim de cards ("+28→+4.5" era in-sample del día; el walk-forward de hoy da +11.3) y
actualizar "dónde estamos" con este audit. (3) borrar/regenerar `retro_last.txt` viejo (23-jun,
UTF-16) — ya nada debería escribirlo sin `-Encoding utf8`.
**Aceptación:** `git status` limpio; prod sirve el bundle nuevo; cero claims desactualizadas de
la tabla §2; los .txt de reportes legibles como UTF-8.

### R10 — Cuota argentina estimada (agregado 2026-07-04 a pedido del usuario)
> Contexto: el usuario juega en casas argentinas (cuota decimal ~1.30-1.60 por pierna). Nuestra
> referencia DK ya ES decimal (odds.py convierte); lo que difiere es el MARGEN de las casas AR
> (overround más alto). No hay API pública de bplay/Betano.ar/bet365 y scrapear viola ToS.
**Archivos:** módulo nuevo `cuotas_ar.py` (o dentro de odds.py), `tracker.py`, `ticket.py`, tests.
**Cambios:** (1) Cuota AR estimada = fair del consenso (DK para 1X2/totales, mediana Linemate para
props) RE-vigeada con el margen típico AR por familia. (2) El margen se APRENDE de los pares
(cuota_real_usuario, cuota_ref) que ya entran por el tab Mi Ticket y la columna Cuota del tracker:
ratio robusto por familia, activo con ≥20 pares; hasta entonces default conservador (+3pp de
overround sobre DK). (3) El tracker y los picks muestran "cuota AR est." etiquetada como estimación.
**Aceptación:** con ≥20 pares reales, error mediano |est−real|/real < 5% (reportado, sea cual sea);
columna visible en tracker; test del estimador con pares sintéticos; cero scraping.

### R11 — Combos same-match INTELIGENTES: la prob conjunta manda (agregado 2026-07-04)
> Contexto: el usuario arma tickets de 2-3 piernas y su duda es CUÁLES conviven. simulate.py ya
> computa la prob conjunta EXACTA de piernas de goles del mismo partido (matriz de marcadores),
> pero ticket.py/cartera.py usan producto de marginales (ticket solo FLAGuea la correlación).
> Verificado hoy en Argentina-Cabo Verde: home+under2.5 lift 0.88x (piernas que se pelean),
> home+over2.5 lift 1.14x (misma historia). El "instinto de ventana" del usuario, en número.
**Archivos:** `ticket.py`, `cartera.py`, `simulate.py`, `analizar.py`, tests.
**Cambios:** (1) ticket.py: piernas del MISMO partido → prob conjunta vía simulate (reemplaza el
producto+nota); el edge del combo sale de la conjunta. (2) cartera.py: habilitar combos same-match
SOLO con lift ≥ 1.0; prohibido armar (y flag rojo al auditar) lift < 0.9 = piernas contradictorias
(el caso U2.5 + gol de jugador). (3) Acople de props de goleador: P(jugador anota | equipo anota g)
≈ 1−(1−s)^g con s = share del jugador en los goles del equipo (game-logs ESPN ya en mano) →
condicionar el prop al marcador simulado; P(Messi gol | U2.5) << P(Messi gol) queda medido, no
intuido. (4) Salida por combo: prob conjunta + lift + "historia" (cerrado/abierto) + cuota mínima
jugable (1/p_conjunta = umbral de valor de referencia).
**Aceptación:** tests: mismatch home+under da lift<1 y home+over >1; prop de jugador condicionado
baja bajo under (número del test, no hardcode); cartera nunca emite lift<0.9; el tab Mi Ticket
muestra conjunta+lift+historia para same-match; pytest verde.

---

## 6. Baselines congeladas de ESTE audit (contra qué se mide el ciclo 3)

| Métrica | Valor 2026-07-04 | Objetivo del ciclo 2 |
|---|---|---|
| Retro WC (n=85): ll 1X2 / ECE / acc | 0.857 / 0.063 / 64.7% | ≤0.857 / ≤0.055 / (acc no es objetivo) |
| Retro: sesgo goles / over / favoritos | −0.13 / −2.5pt / **−5.6pt** | mantener / mantener / **|gap|<3pt (R3)** |
| Bucket 40-60% | obs 65.8 vs pred 49.4 (16.4pt) | |gap| < 8pt (R3) |
| Cards regime-v2 walk-forward | Brier 0.2405 / gap +11.3pt | <0.22 / <8pt (R5) |
| Corners regime-v2 | gap +0.6pt / Brier 0.2548 (v1 0.2483) | v2 ≤ v1 o quedarse en v1 (R5); producto ON (R8) |
| ECE global cal vs cruda | 0.0380 vs 0.0383 ✓ | cal ≤ cruda (mantener) |
| Edge-v2 truly-forward | n=2 (inanición) | n≥30 → ROI flat >−5% y CLV ≥0 (R1+R4) |
| CLV | 55% con cierre real; medio −0.19pt; 0/16 | ≥60% cierre real; CLV por familia reportado |
| Props resueltos | 0 (resolver solo MLB) | n≥50 resueltos + ROI por mercado (R2) — veredicto honesto |
| Hit-rate usuario (tracker) | no se mide | medido y reportado vs prometido (R7) |
| Días sin loop | 07-02 y 07-03 perdidos | **CERO** (R1) |
| Tests | 138 verdes | 138 + nuevos, verdes |

**Regla de cierre del ciclo (heredada, sigue vigente):** re-correr retro + feedback.report +
pnl.report + prop_value.report + tracker stats contra ESTA tabla. Éxito = calibración plana,
favoritos alineados, props con veredicto y CERO días sin datos — nunca "acertar más marcadores
puntuales". El Mundial termina ~19-jul: si un ticket no puede dar fruto antes (necesita n que no
va a existir), decirlo en el reporte y priorizar los que sí. Nota de continuidad post-WC: el loop
y la infra son agnósticos (MLB ya corre); el plan de retarget a ligas de clubes es del ciclo 3,
NO de este.

---

*Audit al 2026-07-04, ~01:00 ART. Medido hoy: backtest_wc.py (n=85), regime.py walk-forward,
feedback.report (n=916), pnl.py gates (v1 n=42 / v2 n=2), clv.report (16/29 cierre real),
prop_value.report (0 resueltos), 138 tests verdes, loop.py re-corrido (51 predicciones 07-04,
goals_factor=1.116 vivo). Working tree con tracker.py/app.py/cache.py sin commitear.*
