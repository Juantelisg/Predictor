# AUDIT FABLE — 2026-07-01

> **De:** Fable (auditor/arquitecto). **Para:** Opus (ejecutor) y el usuario.
> **Base:** briefing + PLAN.md + loops + blueprints leídos en el orden de §0 del briefing;
> después verificación contra el código real de `predictor/*.py` y contra la data viva
> (788 evaluaciones, 40 apuestas-candidato resueltas, retro corrido HOY con n=79).
> Donde el código contradice a los documentos, manda el código — las discrepancias están en §3.
> **Sin código acá:** arquitectura + tickets. Los tickets se ejecutan tal cual, en orden.

---

## 0. Veredicto ejecutivo

1. **El cerebro 1 (predicción calibrada) es real y defendible.** 1X2/DC: log loss 0.881 vs
   baseline 1.072, ECE 0.053 en el retro de hoy (n=79). Nivel serio para un modelo team-level
   con datos gratis. La disciplina anti-fuga es genuina (verificada en código, no solo en docs).

2. **El cerebro 2 (valor) hoy PIERDE plata y tenemos el diagnóstico completo.** El forward-test
   de `pnl.py` da **ROI −40.7% (5/26 aciertos), TODOS los tiers en negativo** (flat −22% a −60%).
   No es solo varianza: hay **tres causas raíz identificadas y accionables** (§5). La versión
   corta: la capa de valor es hoy una fábrica de edges falsos sobre empates y longshots, apostando
   exactamente donde el modelo es más tonto que DraftKings.

3. **La tesis del ROI real** (§7): con datos gratis team-level **no se le gana al 1X2 líquido del
   Mundial** — el forward-test lo acaba de demostrar empíricamente. El 1X2 es el ANCLA, no la mina.
   La plata está en: **(a) line-shopping multi-book de props** (descubrimiento de este audit: el
   JSON crudo de Linemate trae cuotas de ~7 books por prop que `flatten()` descarta — una matriz
   +EV estilo OddsJam gratis, que NO exige que nuestro modelo sepa más que el mercado, solo que
   los books discrepen entre sí); **(b) córners**, la familia más cerca de calificar (gap +3.3%,
   n=63); **(c) tarjetas**, tras arreglar el nivel base del torneo (hoy +28.2% sobreconfiado — el
   fix está diseñado en §8-P2 y la data para hacerlo ya se cosecha sola).

4. **Hay defectos concretos de higiene en producción** que se arreglan barato: un recalibrador con
   pendiente NEGATIVA activo (invierte probabilidades), el 1X2 calibrado que no suma 1 (fabrica
   edge fantasma), n de muestra inflado ~3-12× por filas correlacionadas, un bug literal `* 0` que
   mata el acople de córners en el Monte Carlo, CLV que compara un precio contra sí mismo, y un
   producto (picks/cartera) que bypasea la calibración que el propio sistema ya computa.

---

## 1. Verificación de cierre (corrida HOY, 2026-07-01)

`backtest_wc.py` según `loops/supra-loop-retro.txt` (fixture a ciegas → predicción de control sin
fuga → revelación → evaluación por CALIBRACIÓN):

| Métrica (retro WC, n=79) | Hoy | Baseline briefing §5 (n≈40-314) |
|---|---|---|
| 1X2 log loss | **0.881** vs baseline 1.072 | 0.96 vs 1.06 (jun-23) |
| 1X2 accuracy | 62.0% | — |
| ECE 1X2 | **0.053** | 0.055 |
| O/U 2.5 log loss | 0.686 vs baseline 0.695 | — |
| Marcador exacto | 12.7% (reality-check OK: rango esperado 10-12%) | — |

Sesgos sistemáticos vigentes (los objetivos de los tickets se miden contra ESTO):
- **Goles: −0.39/partido** (espera 2.53, real 2.92); Over 2.5 **−8.2 pt bajista**.
- Empates: −3.7 pt (leve subestimación global — pero ver §5.2: el problema real es la FLATNESS).
- Favoritos: −3.0 pt (subconfiado leve).
- Bucket 40-60%: observado 62.9% vs predicho 49.5% (gap), bucket 80-100%: 71.4% vs 84.0% (n=7).

Y el estado del loop forward (`feedback.report`, n=788 — el briefing cita 314, quedó viejo):

| Familia | n filas | Brier_c | gap crudo | Lectura |
|---|---|---|---|---|
| 1x2 / dc | 144 | 0.140 | ~0% | Calibrado (pero ver §4-C2: empate enmascarado) |
| cs | 84 | 0.179 | +4.2% | OK |
| corners | 63 | **0.207** | **+3.3%** | **Mejoró mucho con muestra — cerca de calificar** |
| cards | 63 | 0.227 | **+28.2%** | **PEOR que el briefing (+25.1). Sesgo estructural confirmado** |
| ml (MLB) | 98 | 0.239 | +6.1% | Mejoró con volumen; pero calibrador `mid` INVERTIDO (§4-C1) |
| over | 144 | 0.226 | −11.6% | Subconfiado sistemático (coherente con retro) |
| btts | 48 | 0.249 | −10.6% | Subconfiado |
| **Global** | 788 | Brier 0.191 / **ECE_c 0.0556 vs cruda 0.0378** | | **La ECE calibrada ya es PEOR que la cruda** → el recalibrador por contexto sobreajusta (§4-C3) |

**Forward-test del edge (`pnl.py`, el juez):** 40 candidatas resueltas, 26 apostables →
**ROI −40.7%**, aciertos 5/26, cuota promedio 5.3, ROI flat por tier: BAJO −60%, FUERTE −57%,
MODERADO −22.2%, SOSPECHOSO (no apostado) −38.1%. **CLV: 0/28 le ganan al cierre** (y casi todos
los "cierres" son idénticos al precio tomado → la métrica no está midiendo nada, §4-E).

Tests: **80/80 pasan** (estado base para los gates de no-regresión).

---

## 2. Qué está sólido (NO tocar, y proteger con gates de no-regresión)

1. **Disciplina anti-fuga**: walk-forward en soccer.evaluate, backtest por fecha, `log-wc` solo
   pre-partido, tests de leakage. Es la ventaja cultural del repo — cada ticket la respeta.
2. **El ancla 1X2/DC** (números arriba). Cualquier ticket que la degrade se revierte.
3. **Los guardrails salvaron plata real**: MAX_EDGE flaggeó 14 candidatas SOSPECHOSAS que
   perdieron −38% flat; el gate de calibración mantuvo córners/tarjetas fuera de la capa de valor.
   El sistema de defensa funciona; el de ataque es el que está mal calibrado.
4. **La cosecha de datos ya corre sola**: boxscores reales de córners/tarjetas de ESPN por partido
   (63 evals por familia y subiendo), game-logs de jugador por API-Football, CSV martj42, todo
   cacheado y con budget. La materia prima de los fixes YA se está acumulando.
5. **Loop idempotente + persistencia** (loop.py, db.py, JSONL como fuente de verdad) + 80 tests.

---

## 3. Discrepancias código vs documentación (el código manda)

| # | Doc dice | El código/data real |
|---|---|---|
| D1 | Briefing §4 y CLAUDE.md: `simulate.py` "condiciona córners/tarjetas a la dominancia" | `dominance_k` default **0** (independencia) y en la línea de córners hay un **`* 0` literal**: el acople de córners es inalcanzable aunque actives el parámetro. Nunca se calibró con datos. |
| D2 | Briefing §5: cifras con n≈314; "córners Y tarjetas mal calibrados" | n=788. Córners **convergió** (+3.3% gap, Brier_c 0.207); tarjetas **empeoró** (+28.2%). Ya no son el mismo problema: cards es sesgo estructural, corners es solo muestra. |
| D3 | PLAN.md: "1er resultado on-thesis: SOSPECHOSO −52% → el guardrail salvó plata" | Hoy TODOS los tiers pierden, incluso los apostables (−22% a −60% flat). El problema no es el cap: es la fábrica de edges. |
| D4 | uncertainty.py docstring: "piso (= MIN_CONF de stake: por debajo, PASAR)" | `CONF_MIN = 0.40 = MIN_CONF` y la condición es estricta (`<`) → el PASAR por confianza **nunca dispara**. |
| D5 | clv.py: "el ÚLTIMO snapshot antes del inicio ≈ cierre" | El loop corre solo al abrir el dashboard → cierre ≡ apertura. 26/28 CLV = 0.0 exacto. La métrica líder no mide. |
| D6 | Regla "archivos en utf-8" | `retro_last.txt` está en UTF-16-LE con BOM (redirect de PowerShell). |
| D7 | analizar/CLAUDE.md: la calibración corrige las probs del producto | Solo "Resultado" usa prob calibrada. Goles/BTTS/valla/córners van CRUDOS a picks confiables, cartera y tickets (§4-F). |

---

## 4. Diagnóstico 10.1 — Núcleo del modelo (prioridad máxima)

### Lo que está mal, con evidencia

**A. Cards: sesgo de NIVEL, no de forma.** `cards-sb-v1` = agregados StatsBomb 2018-2024
(WC22/Euro24/Copa24/AFCON23) → forma multiplicativa ataque×defensa → Poisson. El WC2026 está
dando muchas menos amarillas que esa base histórica, y el modelo **no aprende nada del torneo en
curso** aunque `feedback.evaluate` ya cosecha los conteos reales de cada partido jugado. El Platt
(a=0.768, b=−0.471) comprime pero no puede corregir un nivel base equivocado: gap +28.2% a n=63.
Prueba de que la enfermedad es el nivel y no la forma: **córners, con la MISMA arquitectura,
convergió a +3.3%** — la base de córners de torneos pasados sí generaliza; la de tarjetas no
(régimen arbitral distinto por torneo).

**B. Totales: sesgo bajista sistemático de −0.39 goles/partido** (retro n=79), over −8.2 pt,
familia over −11.6% en el loop forward. El O/U apenas le gana al baseline (0.686 vs 0.695). El
Poisson entrenado con ventana de 10 años + halflife 3 años trae el nivel de gol de OTRA era del
fútbol de selecciones; el WC2026 es más goleador. Como BTTS, valla y marcador modal salen de la
MISMA matriz, este sesgo contamina 4 familias a la vez. Y "over" está formalmente en `QUALIFIED`
para edge con este sesgo (hoy no se apuesta porque odds.py solo ingesta 1X2, pero el gate está
abierto para un mercado torcido).

**C. Higiene del recalibrador (defectos en producción):**
- **C1. Pendiente negativa activa.** `mlb-ml-v1|ml|mid`: a=−0.131, n=47 → para MLB con prob
  45-55%, el calibrador INVIERTE (más prob del modelo → menos prob calibrada). `fit_one` no tiene
  clamp; el shrink no alcanza a impedir el cruce por cero. Ajuste de ruido operando en vivo.
- **C2. El 1X2 se calibra pooleado y sin renormalizar.** Un solo Platt 1-D para home/draw/away →
  (i) la miscalibración específica del EMPATE queda enmascarada por el promedio (gap "~0%" del
  1x2 es un promedio de errores opuestos); (ii) al aplicar el calibrador por outcome, la suma
  calibrada ≠ 1 (medido: hasta ~1.02 en favoritos extremos) → **edge fantasma de hasta +2 pt
  repartido entre los tres lados**, que la capa de valor consume como si fuera señal.
- **C3. Todo in-sample y refiteado a diario sobre lo mismo que después reporta.** La ECE global
  calibrada (0.0556) ya es PEOR que la cruda (0.0378): la capa de contexto fav/dog/mid está
  sobreajustando con buckets chicos (ej: `over|fav` a=2.107 con n=48 filas ≈ 16 partidos).
- **C4. n inflado por correlación.** Cada partido aporta ~12 filas correlacionadas (3×1x2 + 3×dc
  + 3×over + btts + 2×cs). `MIN_N=40` filas ≈ **4 partidos reales**; `uncertainty.effective_n`
  cuenta filas → la confianza del Kelly se cree respaldada por 3-12× más muestra de la que hay.

**D. La probabilidad de empate es demasiado PLANA.** En el retro, el modelo da empate 20-30% en
casi todos los partidos (rango real del mercado: 8% → 47%). El logit multinomial sobre
[elo_diff, localía] no puede afinar la curva del empate (le falta el término de |diferencia| /
total de fuerza). Esta flatness es la máquina que fabrica edges falsos de empate en AMBAS
direcciones: compra empates a cuota 8-12 en mismatches (modelo 12% vs mercado 8%) y compra
local+visita en partidos con incentivo de empate (modelo 28% vs mercado 47%).

**E. Monte Carlo de combos con correlación inventada.** El acople córners/tarjetas↔marcador es
un parámetro nunca calibrado, apagado por default, y con el bug D1 que lo hace inalcanzable para
córners. Hoy "combo correlacionado" = producto de marginales para cualquier pierna de
córners/tarjetas. Con 79+ partidos de WC2026 con boxscore ya cosechados, la correlación real
(goles↔córners↔tarjetas) es MEDIBLE por primera vez — el insumo existe, el código no lo usa.

### Lo que está sólido del núcleo
El blend Elo+Poisson/Dixon-Coles con supremacía del Elo y total del Poisson; la separación
familia/versión; el patrón walk-forward. El sweep de jun-23 ("ningún cambio de peso se justifica")
fue la decisión correcta ENTONCES con n=40; hoy hay el doble de muestra y sesgos direccionales
estables (goles bajista en 3 mediciones independientes) → amerita re-testear con el mismo rigor.

---

## 5. Diagnóstico 10.2 — Valor / staking

### El forward-test es un veredicto, no un accidente

40 candidatas resueltas. Composición: **15/40 empates (2 aciertos), cuota promedio 5.3** — el
"edge" vive en longshots. Tres causas raíz, cada una verificada en la data:

**5.1. De-vig proporcional en mercados de 3 vías con longshots.** El margen del book se concentra
en los longshots (sesgo favorito-longshot, hecho empírico estándar). El de-vig proporcional
(normalizar 1/cuota) lo reparte parejo → deja la fair prob de los longshots INFLADA → el edge
`p_model − p_market` de empates y cuotas altas sale sistemáticamente sobreestimado. Con power
de-vig (o Shin), la fair de una cuota 12.0 baja bastante más que proporcionalmente → mata la
mayoría de los edges falsos de empate de una sola vez.

**5.2. El modelo no ve el régimen del torneo.** Caso medido: Algeria v Austria (3ª fecha de
grupo), fair del empate del mercado = **46.7%** (el book priceaba el incentivo mutuo del empate);
el modelo, ciego al contexto, dio empate 28% y "encontró" edge en AMBOS lados (home +7.6%, away
+9.1%). Resultado: 3-3. El mercado tenía razón. La 3ª fecha de grupos (24-27 jun) concentra las
pérdidas del forward-test: Egypt-Iran 1-1, Cape Verde-Saudi 0-0, Paraguay-Australia 0-0,
Colombia-Portugal 0-0… empates en cadena que el mercado olió y el modelo no. **Cuando la fair del
empate del book es anómalamente alta, ESO ES INFORMACIÓN — el partido debe quedar NO-APTO, no
convertirse en dos apuestas.**

**5.3. Selección adversa (winner's curse del edge).** Se apuesta exactamente donde el modelo más
diverge de un book líquido y eficiente. Divergencia grande vs mercado eficiente es, a priori, más
probablemente error del modelo que edge (Colombia 43% vs book 22% contra Portugal → 0-0). El edge
puntual `p_cal − p_market ≥ 3%` no descuenta la incertidumbre del PROPIO modelo. La decisión de
apuesta necesita una prob "shrunk" hacia el mercado, con peso que solo crece con evidencia
forward de que la familia le gana al book. **Frontera de guardrail explícita:** esto es cerebro 2
(decisión de apostar), NO toca el motor ni el logging — `p_model` se loguea puro, la calibración
sigue sin ver cuotas jamás. El propio briefing §10.1 ya anticipa esta sutileza ("mercado como
prior bayesiano SIN volverlo feature circular").

### CLV sin dientes
El "cierre" es el mismo snapshot de cuando se logueó la apuesta (loop corre al abrir el
dashboard). 26/28 con CLV 0.0 exacto; los 2 únicos movimientos reales fueron EN CONTRA. El
indicador de menor varianza del edge — el que convergería 10× más rápido que el ROI — hoy no mide
nada. Es el fix más barato con mayor retorno informacional del repo.

### Staking
`stake.py` es mecánicamente correcto (Kelly fraccional × confianza, caps) pero: (i) garbage-in —
dimensionó edges falsos; (ii) el PASAR por confianza nunca dispara (D4); (iii) la confianza viene
de un n inflado (C4). Se arregla solo con lo anterior.

---

## 6. Diagnóstico 10.3 / 10.4 — Producto e infra (breve, como manda el orden)

- **F. El producto bypasea la calibración.** `_picks` usa prob calibrada solo para "Resultado";
  goles/BTTS/valla/córners van crudos a picks confiables → cartera → tickets. Un córner
  "confiable" al 62% crudo es ~50% calibrado (a=0.704). Cards se excluye a mano (parche honesto,
  pero el mecanismo correcto es el gate por familia en un solo lugar).
- El blueprint OLAP/WebSockets/multibook (`arquitectura_pivote_v2.md`) sigue siendo la visión,
  no el paso siguiente: **no hay volumen de usuarios ni de mercados vivos que lo justifique aún**
  (criterio del propio briefing §10.4: "solo cuando el modelo lo justifique"). El único pedazo
  que SÍ se adelanta es la matriz multi-book de props — porque la data ya está en mano (Linemate
  books) y es la fuente de ROI #1 (§7).
- Smart-money Polymarket (doc §señal): el encuadre del documento es correcto (señal del paso 4 /
  cohort tag, jamás feature; solo forward). **No es de este ciclo**: primero hay que detener la
  sangría y calificar mercados. Queda en backlog con su experimento mínimo tal como está escrito.

---

## 7. La tesis del ROI (dónde está la plata, honestamente)

El usuario quiere ganancia real, no tickets seguros de cuota mínima. Lectura de cuant sin humo:

1. **1X2 líquido del Mundial (DK): NO hay edge nuestro.** Confirmado forward. Rol: ancla
   calibrada para combos, staking y simulación. Se sigue midiendo (log/eval/CLV) pero con la
   cirugía de §8-P1 la mayoría de las "candidatas" van a morir en los gates — **eso es éxito**,
   no fracaso: dejar de pagar matrícula.
2. **Props con line-shopping multi-book (Linemate books): la única fuente de +EV estructural
   que no exige saber más que el mercado.** Consenso de-vig de ~7 books = fair robusto; un book
   soft descolgado del consenso = +EV aritmético. Es el modelo de negocio de OddsJam, y la data
   ya llega gratis en el payload que hoy tiramos. Nuestro modelo de hit-rates (API-Football,
   shrink Beta-Binomial — el molde que YA corrigió +12.6pt de sobreconfianza en MLB props) actúa
   de segundo voto, no de única fuente. **Guardrails intactos**: cuotas solo en cerebro 2.
3. **Córners: el primer mercado modelo-vs-book con chance real de calificar.** Gap +3.3%,
   Brier_c 0.207, n=63 y subiendo solo. Book vago, mercado blando. Con P2 (nivel de torneo) y
   2-3 semanas más de forward, puede pasar el gate con evidencia y entrar a la capa de valor.
4. **Tarjetas: solo después del fix estructural.** Es el mercado más blando de todos, pero hoy
   nuestro modelo es peor que el book. Calibrar primero (guardrail 1), valor después.
5. **Combos correlacionados como multiplicador del producto** una vez que córners/cards estén
   calibrados y la correlación esté MEDIDA (no inventada): es lo que Linemate no hace y los books
   pricean perezosamente en parlays de mismo partido.

La ganancia "real" (no cuotitas): props +EV multi-book suele vivir en cuotas 1.8-2.5 con edges
de 3-8% — exactamente el perfil que pide crecimiento de bankroll sin volatilidad de longshots.

---

## 8. Propuestas técnicas (arquitectura del cambio + por qué no rompe lo calibrado)

### P1. Cirugía de la capa de valor — `edge.py`, `odds.py`, `pnl.py`
- **Power de-vig** para 1X2 (fair ∝ implícita^k, k resuelto por mercado para que sumen 1; caso
  2-vías puede quedar proporcional). Mata el edge falso de longshots en la raíz matemática.
- **Gates de régimen y sanidad**: (i) fair del empate > ~0.33 → partido NO-APTO 1x2 (mercado
  priceando incentivos/info que el modelo no ve — o data rota; en ambos casos no se apuesta);
  (ii) overround crudo fuera de [1.00, 1.20] → descartar la cuota (dato corrupto);
  (iii) **cap de cuota** (~4.0) hasta que el forward demuestre calibración en zona longshot.
- **Edge con descuento de incertidumbre**: la decisión usa `p_bet = w·p_cal + (1−w)·p_fair`, con
  w por familia que ARRANCA bajo (0.5) y solo sube con evidencia forward (CLV+/ROI≈edge). Se
  loguean AMBAS (p_model puro para calibración, p_bet para la decisión) — frontera de guardrail
  documentada en el docstring: cuota jamás entra al motor ni al fit del calibrador.
- **No rompe nada**: no toca soccer.py ni calib.py; solo hace más estricto qué llega a stake.
- **Riesgo**: volverse tan conservador que no apuesta nunca → se mide tasa de candidatas y se
  reporta; el objetivo del ciclo es ROI_flat ≈ edge predicho y CLV ≥ 0, no volumen.

### P2. Nivel base EN-TORNEO para cards (y córners) — `statsbomb_data.py` + módulo de régimen
Empirical-Bayes de 2 niveles, sin librerías nuevas (el molde POP_K=30 de MLB props, precedente
interno con resultado probado):
- λ_torneo = media observada del WC2026 hasta AYER (boxscores que `feedback` ya cosecha),
  shrunk hacia la base StatsBomb histórica con K≈12 partidos: λ_T = (n·obs + K·hist)/(n+K).
- Los efectos multiplicativos de equipo se conservan, re-centrados a λ_T.
- Walk-forward interno obligatorio (predecir día d solo con partidos < d), versionado
  `cards-sb-v2`/`corners-sb-v2` (v1 intacto para comparación).
- **No rompe nada**: familias separadas del 1X2 por diseño; el gate de edge las mantiene fuera
  de la capa de valor hasta que la v2 pase el criterio.

### P3. Higiene del recalibrador — `calib.py`, `feedback.py`, `uncertainty.py`
- Clamp: pendiente calibrada a < 0.1 → identidad (nunca invertir).
- **1X2 por outcome** (home/draw/away calibrados por separado) + **renormalización a suma 1**
  al aplicar; dc DERIVADO del 1X2 calibrado (misma información, no doble fit).
- n contado por PARTIDOS únicos, no filas; MIN_N y half-saturación de uncertainty en partidos.
- Contexto fav/dog/mid: inactivo hasta ≥30 partidos por bucket (hoy sobreajusta).
- Validación out-of-sample rolling del calibrador (fit hasta t−7d, medir en la última semana);
  si no mejora a la cruda fuera de muestra → identidad. Cierra la deuda #2 del briefing.
- **No rompe nada**: gate duro de no-regresión sobre 1x2/dc (Brier_c ≤ actual) antes de mergear.

### P4. Régimen de goles del torneo — capa de predicción WC (soccer.py intacto)
Factor multiplicativo sobre (λh, λa) SOLO para partidos del WC2026, estimado walk-forward con
shrink (obs 2.92 vs esperado 2.53 → factor ~1.10-1.15 shrunk). Arregla over, BTTS, valla y
marcador modal de un golpe (misma matriz). Gate doble: mejora el retro SIN degradar el holdout
de 2 años (`soccer.evaluate`) — el mismo criterio que el sweep de jun-23 usó para decir "no".

### P4b. Curva del empate — `soccer.py` (única modificación al motor, gated)
Agregar |elo_diff| como feature al logit multinomial del 1X2 (y evaluar en supremacía). Es UNA
feature con justificación estructural (la prob de empate es función en campana de la paridad,
no lineal del signo). Validación: tune.py folds walk-forward + retro + holdout; si no mejora
log loss OOS, se descarta sin discusión (el sweep manda, como siempre).

### P5. Máquina +EV multi-book de props — `linemate.py` + módulo nuevo de valor de props
- Preservar `market.books` en el flatten (hoy se tira); normalizar (book, over/under,
  opening/current, línea).
- Fair = mediana de-vig del consenso (2 vías); flag +EV cuando el mejor precio supera la fair
  por umbral (~4%) Y el modelo propio de hit-rate shrunk apunta al mismo lado (2 señales, regla
  del CLAUDE.md). Descartar cuotas stale (timestamp).
- Forward-test OBLIGATORIO antes de plata: loguear flags en un track separado de pnl, resolver
  contra game-logs (API-Football ya resuelve), ROI flat por familia de prop. n≥50 antes de
  cualquier veredicto.
- **No rompe nada**: módulo nuevo, cero contacto con el motor; cuota = insumo de valor.

### P6. CLV con dientes — `clv.py` + tarea programada de Windows
Snapshots cada 2-3h del slate del día (schtasks; barato: requests ESPN cacheables). El cierre
pasa a ser el último snapshot pre-kickoff real. CLV por familia/tier como métrica PRIMARIA de
los forward-tests (converge mucho antes que el ROI).

### P7. Correlación medida para combos — `simulate.py`
Arreglar el `* 0`; estimar el acople córners/tarjetas ~ (|margen|, total de goles) con los 79+
boxscores del WC2026 (walk-forward); recién entonces habilitar piernas de córners/tarjetas en
combos de cartera. Hoy cualquier estimación medida le gana a la independencia asumida.

### P8. La calibración manda en TODO el producto — `analizar.py`, `cartera.py`, `ticket.py`
Toda prob mostrada/usada = calibrada por familia + banda de confianza; "picks confiables" solo
familias calificadas (córners entra solo cuando pase el gate); el parche manual de cards se
reemplaza por el gate general.

---

## 9. Ranking por leverage real sobre ROI/CLV

| # | Propuesta | Leverage | Por qué |
|---|---|---|---|
| 1 | P1 cirugía de valor | **Detiene pérdida activa hoy** | −40.7% ROI es el incendio; sin esto, todo lo demás alimenta una máquina que quema plata |
| 2 | P3 higiene calibrador | Cimiento de todo | Bug real en producción (pendiente negativa), edge fantasma del 1X2 sin renormalizar, n inflado que infla el Kelly |
| 3 | P6 CLV | Multiplica la velocidad de aprendizaje | Sin CLV real, cada iteración de valor tarda semanas en juzgarse; con CLV, días |
| 4 | P5 props multi-book | **La fuente de +EV nueva** | Única vía que no exige ganarle al mercado en información; data gratis ya en mano |
| 5 | P2 cards/córners v2 | Abre los mercados blandos | El plan de la casa desde el día 1; córners está a semanas de calificar |
| 6 | P4 goles del torneo | 4 familias con un fix | Sesgo confirmado en 3 mediciones independientes |
| 7 | P4b curva del empate | Ataca la mayor fuente de edges falsos | Gated por sweep; si no mejora OOS, muere |
| 8 | P7 combos medidos | Diferenciador de producto | Después de P2; hoy la correlación es inventada |
| 9 | P8 producto calibrado | Integridad | No genera ROI directo; evita que el usuario juegue probs infladas |

---

## 10. TICKETS PARA OPUS (ejecutar en este orden)

> Reglas comunes a TODOS los tickets: correr con el Python real
> (`C:/Users/Juant/AppData/Local/Python/bin/python.exe`); los 80 tests existentes siguen en verde
> + tests nuevos por ticket; sin emojis/`≥→` en prints (cp1252); JSONL con `utf-8-sig` al leer;
> ninguna cuota entra a soccer.py/calib.fit ni a ningún fit del motor; todo cambio de modelo se
> versiona (`*-v2`) y se compara contra el v1 congelado; walk-forward siempre (nada se evalúa
> sobre data que lo tuneó).

### T1 — Higiene del recalibrador (P3, parte 1)
**Archivos:** `calib.py`, `uncertainty.py`, `feedback.py`, `tests/test_calib.py`.
**Cambios:** (1) `fit_one`: si la pendiente post-shrink < 0.1 → devolver identidad. (2) El n de
`fit`/`MIN_N` y `uncertainty.effective_n` cuentan PARTIDOS únicos (date, home, away), no filas;
recalibrar umbrales: MIN_N = 15 partidos, half-sat de uncertainty K = 25 partidos. (3) Los
calibradores de contexto (`|fav`/`|dog`/`|mid`) solo se activan con ≥30 partidos en el bucket.
(4) `stake.MIN_CONF` sube a 0.45 (para que el piso 0.40 de uncertainty pueda gatillar PASAR).
**Aceptación (medible):** `mlb-ml-v1|ml|mid` deja de invertir (a ≥ 0.1 o identidad, verificado en
`data/calibrators.json` re-fiteado); en `feedback.report` con las 788 evals: **ECE calibrada ≤
ECE cruda + 0.003** (hoy 0.0556 vs 0.0378) y Brier_c global ≤ 0.1913; Brier_c de 1x2 ≤ 0.1404
(no-regresión); pytest verde con ≥3 tests nuevos (clamp, n por partidos, activación de contexto).

### T2 — 1X2 calibrado por outcome + renormalización (P3, parte 2)
**Archivos:** `calib.py`, `analizar.py`, `feedback.py`, `tests/`.
**Cambios:** calibradores separados para 1x2:home / 1x2:draw / 1x2:away; al aplicar a un partido,
renormalizar los tres a suma 1; `dc` se DERIVA del 1X2 calibrado (se elimina su calibrador
propio); `feedback.report` muestra el gap del EMPATE como línea separada.
**Aceptación:** test unitario: para cualquier predicción, |Σ p_cal(1x2) − 1| < 1e-9; sobre las
144 evals de 1x2: Brier_c ≤ 0.1404 (no-regresión estricta); el reporte imprime gap de draw por
separado; pytest verde.

### T3 — Cirugía de la capa de valor (P1)
**Archivos:** `edge.py`, `odds.py`, `pnl.py`, `tests/test_devig_edge.py`.
**Cambios:** (1) power de-vig para mercados de 3 vías (proporcional se mantiene para 2 vías).
(2) Gates nuevos en `edge_market`/`verdict_1x2`: overround crudo fuera de [1.00, 1.20] →
descartar cuota; fair del empate > 0.33 → partido NO-APTO para 1x2 (razón: "mercado priceando
régimen que el modelo no ve"); cuota del outcome > 4.0 → NO-APTO zona longshot. (3) La decisión
de apuesta usa `p_bet = 0.5·p_cal + 0.5·p_fair`; el JSONL de bets loguea p_model, p_bet y
p_market; el tier sale de p_bet. (4) Etiquetar las candidatas nuevas con `edge_version: "edge-v2"`.
**Aceptación:** test: con cuotas [1.95, 3.60, 4.50], la fair del outcome a 4.50 con power de-vig
es MENOR que con proporcional (dirección verificada); replay one-off de las 40 candidatas
históricas que REPORTA (sin tunear) cuántas sobreviven a los gates nuevos y cuál habría sido el
ROI flat del subconjunto — el número se documenta en el reporte del ticket, sea cual sea;
`pnl.report` separa por edge_version. **Criterio de éxito del ciclo (no del merge):** tras ≥30
candidatas edge-v2 resueltas, ROI_flat > −5% y CLV medio ≥ 0.

### T4 — CLV con cadencia real (P6)
**Archivos:** `clv.py`, `loop.py`, tarea programada (schtasks) + doc en README del predictor.
**Cambios:** comando ligero `clv.py snapshot` agendado cada 2h entre 10:00 y 20:00 locales;
`clv.report` agrega desglose por familia y por edge_version.
**Aceptación:** tras 2 días de corrida, los partidos nuevos tienen ≥3 snapshots con ts distintos
pre-kickoff; >50% de las bets nuevas tienen cierre ≠ precio tomado; el reporte por familia corre.

### T5 — cards-sb-v2 / corners-sb-v2 con nivel de torneo (P2)
**Archivos:** `statsbomb_data.py` (o módulo nuevo de régimen de torneo), `feedback.py`, `tests/`.
**Cambios:** λ del torneo = shrink (K=12 partidos) entre la media observada del WC2026 (de los
boxscores ya cosechados en evaluations/ + `_espn_soccer_stats`) y la base StatsBomb; efectos de
equipo re-centrados; `feedback.log` loguea con `cards-sb-v2`/`corners-sb-v2`; v1 deja de loguear
(queda su histórico para comparar).
**Aceptación (walk-forward, no in-sample):** reconstrucción día-a-día de las 63 predicciones de
cards con v2 usando solo datos previos a cada partido: **Brier < 0.22 y |gap| < 8 pt** (hoy
0.284 crudo / +28.2); córners v2 no empeora (Brier ≤ 0.21); cero cambio en 1x2/over (archivos del
motor intactos); pytest verde.

### T6 — Factor de goles del torneo (P4)
**Archivos:** capa de predicción WC (`backtest_wc.py`, `feedback.log_wc`/`analizar` para partidos
WC), `tests/test_no_leakage.py` extendido. **soccer.py NO se toca** (el factor vive fuera del
motor base).
**Cambios:** multiplicador de (λh, λa) para partidos WC2026, estimado walk-forward con shrink
(K=20 partidos) de la razón total_real/total_esperado acumulada hasta el día anterior.
**Aceptación:** en el retro completo (n=79): |goles esperados − reales| < 0.15 (hoy 0.39),
ll_over < 0.686, ECE ≤ 0.055, ll_1x2 ≤ 0.885 (sin degradar el ancla); en el holdout de 2 años
(`soccer.evaluate` sin el factor, que solo aplica a WC): sin cambio por construcción — test que
lo prueba; pytest verde.

### T7 — Máquina +EV multi-book de props (P5)
**Archivos:** `linemate.py` (flatten preserva books), módulo nuevo de valor de props, `loop.py`
(paso nuevo), track nuevo de forward-test (análogo a bets/bet_evals), `tests/`.
**Cambios:** extracción de books por prop (book, lado, línea, opening/current, ts); fair =
mediana de-vig del consenso (≥3 books para calificar); flag +EV si mejor precio > fair + 4% Y el
hit-rate shrunk (Beta-Binomial, K=30 — el molde MLB) apunta al mismo lado; log diario de TODOS
los flags (también los PASAR); resolución contra game-logs API-Football; reporte ROI flat por
familia de prop y por book.
**Aceptación:** para un slate real del Mundial: tabla de props con fair de consenso + mejor book
+ edge; ≥95% de los props con ≥3 books matchean (jugador, mercado, línea) sin ambigüedad; el
forward-test corre en loop.py; cero requests nuevos a API-Football fuera del cacheo existente
(budget.guard lo protege); pytest verde. **Sin veredicto de plata hasta n≥50 flags resueltos**
(el criterio es el reporte honesto, no un ROI objetivo).

### T8 — simulate.py: bug + correlación medida (P7)
**Archivos:** `simulate.py`, script/función de estimación del acople, `tests/`.
**Cambios:** eliminar el `* 0` de la línea de córners; estimar coeficientes de acople
córners/tarjetas ~ (|margen|, total de goles) con los boxscores WC2026 (walk-forward, mínimo 60
partidos); `dominance_k` (y su análogo de córners) pasan a ser valores MEDIDOS con fecha de
estimación en el docstring.
**Aceptación:** test: con acople activo, la distribución de córners condicionada a |margen|≥2
difiere de la de |margen|=0 (hoy imposible por el bug); el lift de un combo con pierna de córners
difiere de 1.0 en la dirección del coeficiente medido; doc del briefing/CLAUDE.md actualizado
(la claim de D1 pasa a ser verdadera); pytest verde.

### T9 — La calibración manda en el producto (P8)
**Archivos:** `analizar.py`, `cartera.py`, `ticket.py`, frontend solo si hace falta re-etiquetar,
`tests/test_cartera.py`, `tests/test_ticket.py`.
**Cambios:** `_picks`/cartera/ticket consumen prob CALIBRADA por familia (over/btts/cs incluidos)
con banda de confianza de uncertainty; "picks confiables" solo familias con gate aprobado (la
exclusión manual de cards se reemplaza por el gate general; córners entra solo cuando su familia
califique); `analyze()` expone cruda Y calibrada por mercado.
**Aceptación:** test: un pick cuya prob cruda ≥62% pero calibrada <62% NO aparece en picks
confiables; cartera arma tickets con las calibradas (fixture de regresión); pytest verde.

### T10 — Curva del empate (P4b) — SOLO si T1-T6 están mergeados
**Archivos:** `soccer.py` (única modificación al motor), `tune.py`, `tests/`.
**Cambios:** agregar |elo_diff| como segunda feature del logit multinomial 1X2; re-correr
tune.py (folds walk-forward) y el retro.
**Aceptación (gate estricto, es el ancla):** log loss 1X2 OOS de los folds ≤ actual − 0.005 Y
retro ll_1x2 ≤ 0.881 Y ECE ≤ 0.053 Y el rango de prob de empate del retro se ensancha (p10-p90
más amplio que el actual 18-30%). Si CUALQUIERA falla → descartar el cambio y documentarlo (el
resultado negativo también se reporta, regla de honestidad).

### T11 — Documentación y limpieza (loop de mantenimiento)
**Archivos:** `docs/BRIEFING_SUPRA_AGENTE.md` (§5 con n=788, §4 claim de simulate, §9 estado
cards/corners divergente), `predictor/PLAN.md` ("dónde estamos" + veredicto del forward-test),
`CLAUDE.md` (claim de simulate), `dashboard.bat`/quien escriba `retro_last.txt` (forzar UTF-8).
**Aceptación:** cero claims falsas restantes de la tabla §3 de este audit; `retro_last.txt`
regenerado legible como UTF-8.

---

## 11. Baselines congeladas de este audit (contra qué se mide el próximo ciclo)

| Métrica | Valor 2026-07-01 | Objetivo del ciclo |
|---|---|---|
| Retro WC: ll 1X2 / ECE | 0.881 / 0.053 (n=79) | ≤ 0.881 / ≤ 0.053 (no romper el ancla) |
| Retro WC: sesgo de goles | −0.39/partido | |bias| < 0.15 (T6) |
| Cards: Brier walk-forward / gap | 0.284 crudo (0.227 Platt) / +28.2 pt | < 0.22 / < 8 pt (T5) |
| Corners: Brier_c / gap | 0.207 / +3.3 pt | ≤ 0.21 y calificar para edge con n≥100 partidos |
| ECE global calibrada vs cruda | 0.0556 vs 0.0378 (¡peor!) | calibrada ≤ cruda + 0.003 (T1) |
| Forward edge: ROI flat | −40.7% (n=26) | edge-v2: > −5% con n≥30 y CLV ≥ 0 (T3+T4) |
| CLV medible | 0/28 con cierre real | >50% de bets con cierre ≠ apertura (T4) |
| Props +EV | no existe | pipeline corriendo con n≥50 flags resueltos (T7) |
| Tests | 80 verdes | 80 + nuevos, siempre verdes |

**Regla de cierre del ciclo:** re-correr `backtest_wc.py` + `feedback.report` + `pnl.report
(edge-v2)` y comparar contra ESTA tabla. Éxito = calibración plana y sesgos neutralizados
validados forward — nunca "acertar más marcadores". Si una propuesta empuja a optimizar
resultados puntuales, está mal formulada: parar y reformular (regla del supra-loop).

---

*Audit al 2026-07-01. Código verificado: soccer.py, elo.py, calib.py, statsbomb_data.py,
simulate.py, uncertainty.py, edge.py, stake.py, odds.py, feedback.py, pnl.py, clv.py, loop.py,
db.py, backtest_wc.py, tune.py, analizar.py, cartera.py, linemate.py, soccer_players.py.
Data verificada: 788 evaluations, 40 bet_evals, calibrators.json, retro n=79 corrido hoy,
payload crudo de Linemate con books multi-book confirmado en vivo.*
