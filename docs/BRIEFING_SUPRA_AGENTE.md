# BRIEFING — De predictor a **supra-agente GOAT de predicciones**

> **Para:** un agente superior en conocimiento y capacidad.
> **De:** el agente que construyó el estado actual (Claude, sesiones jun–jul 2026).
> **Objetivo:** que tengas el panorama COMPLETO y REAL de esta plataforma para llevarla a
> nivel de las mejores casas de apuestas y los mejores modelos — a nivel **modelo**,
> **estrategia** y **UX/UI** — SIN romper la disciplina que la hace confiable.
>
> Este documento es honesto: marca lo que está sólido, lo que está flojo y lo que es humo.
> No te fíes de la nostalgia del código; verificá contra los archivos que cito.

---

## 0. Cómo usar este documento

**Leé en este orden antes de tocar nada:**
1. Este briefing (panorama).
2. `predictor/PLAN.md` — **plan canónico fasado** (manda sobre todo lo demás).
3. `loops/` — **los loops de trabajo** (`loops.txt` = loop de mantenimiento/QA; `supra-loop-retro.txt` = loop de backtest/calibración con guardrails). **Revisalos: definen CÓMO se itera acá sin romper la calibración.**
4. `docs/arquitectura_pivote_sports_analytics_v2.md` — blueprint UX/UI+arquitectura inspirado en Outlier / Props.cash / OddsJam / Rithmm.
5. `docs/señal_smart_money_polymarket.md` — ángulo de smart-money (seguir wallets sharp).
6. `CLAUDE.md` — identidad del supra-agente + toolbox + anti-patrones.

**Regla de oro de este repo:** correr Python con el intérprete real
`C:/Users/Juant/AppData/Local/Python/bin/python.exe` (el `python` del PATH es el alias del Store y falla).

**Estado del rumbo:** la app empezó como "EV+ con cuotas" (falló: encontraba edges falsos por
sobreconfianza), pivoteó a "calibración pura sin cuotas" (jun-13) para construir los cimientos,
y desde jun-21 **mergea ambos**: motor calibrado + capa de valor/staking/bankroll encima. Hoy el
spine lógico completo está construido y cableado; falta **validarlo con volumen real**.

---

## 1. Qué es esto (north star)

**No es "dar picks". Es un motor de decisión de apuestas** que:
1. **Predice** con probabilidades **calibradas** + **confianza** por mercado.
2. **Detecta valor** real contra el mercado de-vigeado (edge por mercado).
3. **Decide cuánto arriesgar** (Kelly fraccional por tier).
4. Cierra en un **loop que aprende de la plata real** (PnL/CLV), no de un número abstracto.

**Éxito = crecimiento de bankroll con drawdown controlado.** `PASAR` es una salida válida y frecuente.

Dominio principal hoy: **Mundial 2026 (selecciones)**. Verticales secundarias: MLB (moneyline), NBA (esqueleto).

---

## 2. Filosofía y guardrails NO-negociables

Estos guardrails son la razón por la que el modelo no revienta el bankroll. **No los rompas
para "mejorar" métricas — romperlos es exactamente cómo falló la versión vieja.**

1. **Calibración es prerequisito de edge.** Un mercado no entra a la capa de valor hasta estar
   calibrado (reliability plana + Brier OK). Si no, el "edge" es el error del modelo disfrazado.
2. **Edge SIEMPRE post de-vig.** La cuota cruda trae el margen de la casa adentro (-110/-110 = 52.4%/lado).
3. **Forward-test antes de confiar.** Nunca backtest sobre la misma data que tuneó. Walk-forward, sin fuga temporal.
4. **Kelly fraccional, nunca full.** Kelly con P inflada revienta el bankroll.
5. **Combos con correlación (Monte Carlo), NUNCA producto de marginales.**
6. **Las cuotas son insumo de VALOR, JAMÁS feature del modelo.** Si entran al motor, el modelo
   aprende a predecir al mercado (circular) y se contamina la calibración.
7. **Se evalúa TODO** (los PASAR también), versionado por `model_version`, sin cherry-picking.
8. **Brutal honestidad calibracional.** Si pierde plata, el reporte lo dice. `variance_win`/`variance_loss` son tags honestos.

---

## 3. Arquitectura: 3 cerebros + 1 loop (estado REAL)

| Cerebro | Qué hace | Estado hoy |
|---|---|---|
| **1 · Predice** | P calibrada + confianza por mercado (1X2, DC, totales, BTTS, valla, córners, tarjetas, combos) | Sólido en 1X2/totales; **córners/tarjetas/ml sobreconfiados** |
| **2 · Valora** | P calibrada vs cuota de-vigeada → edge por mercado, con gate de calibración | Construido (`edge.py`, `odds.py`); cuotas de ESPN/DraftKings gratis |
| **3 · Decide cuánto** | (edge × confianza) → tier fuerte/moderado/bajo/pasar (Kelly fraccional) | Construido (`stake.py`); combos correlación-aware |
| **Loop de PnL** | predice → resultado → ROI realizado vs edge por tier/mercado → reajusta | Loop de calibración corriendo; capa PnL (`pnl.py`) existe, **falta volumen para veredicto** |

**Rol de cada mercado (crítico, no confundir):**
- **1X2 / DC / goles de selecciones grandes** = ancla **calibrada** (Brier ~0.14 en 1X2). Mercado
  eficiente → **poco edge**, no forzar valor ahí.
- **Córners / tarjetas / props / ligas chicas** = **donde vive el edge** (book vago) y lo que el
  usuario juega. Hoy **mal calibrados** → es la frontera a clavar.

---

## 4. El motor por dentro (el núcleo que querés potenciar)

Todo en `predictor/*.py`. Docstrings reales:

**Predicción (cerebro 1):**
- `soccer.py` — motor de selecciones. **Blend Elo + Poisson Dixon-Coles.** Elo rodante da el 1X2
  base; un Poisson bivariado (con corrección Dixon-Coles `RHO` para marcadores bajos, decaimiento
  temporal `HALFLIFE_DAYS`, peso de amistosos `FRIENDLY_W`) da goles → over/under, BTTS, valla
  invicta. `ELO_W` mezcla ambos 1X2. `VERSION="soccer-v3"`. Team-level (no jugador). Data: CSV
  martj42 de resultados internacionales.
- `elo.py` — rating Elo rodante estilo World Football Elo desde el CSV.
- `statsbomb_data.py` — xG y **córners/tarjetas** desde StatsBomb Open Data (agregados por equipo,
  NO per-partido). Cobertura despareja: buenas ligas/torneos sí, selecciones menores no.
- `simulate.py` — **Monte Carlo de partido para combos correlacionados**: simula N marcadores del
  Poisson (joint ≠ producto de marginales, lift medido) + taxonomía de escenarios. El acople
  córners/tarjetas↔dominancia es un parámetro (`corner_k`/`card_k`); medido ~0 con n=24 en el WC
  (2026-07-01, T8) → hoy córners/tarjetas van independientes del marcador, con evidencia.
- `soccer_players.py` — **props de jugador desde game-logs reales de API-Football** (tiros, tiros
  al arco, goles, asistencias, gol+asist), hit-rates propios L5/L10. Cubre lo que Linemate no trae.
  Cobertura despareja por nación (England: 113 candidatos con Kane; Congo DR: 0).

**Calibración + confianza:**
- `calib.py` — **recalibrador Platt POR FAMILIA de mercado** (1x2/over/btts/corners/cards/cs/dc/ml),
  fiteado sobre `evaluations/`. La brecha crudo↔calibrado es señal de fiabilidad.
- `uncertainty.py` — **confianza por n EFECTIVA**: un 70% de 5 partidos no vale lo que uno de 50.

**Valor + staking (cerebros 2 y 3):**
- `odds.py` — ingesta de cuotas 1X2 de ESPN (pickcenter/DraftKings), GRATIS. Cuotas = benchmark, NO feature.
- `edge.py` — capa de valor: P calibrada vs cuota de-vig → edge, con **gate de calibración**
  (córners/tarjetas = `NO-APTO` hasta calibrar) + `MAX_EDGE` (edge enorme = `SOSPECHOSO`, no se apuesta).
- `stake.py` — Kelly fraccional × confianza → tiers; combos correlación-aware.
- `bankroll.py` — ledger de equity, drawdown, stop-loss diario/semanal.
- `clv.py` — Closing Line Value (¿le ganamos al cierre?).

**Loop + persistencia:**
- `feedback.py` — Loop A: calibrar el modelo (log → eval → report). Métricas por familia + ECE.
- `pnl.py` — forward-test del EDGE (Fase 4): loguea apuestas-candidato, las resuelve, ROI vs edge.
- `db.py` — persistencia durable SQLite (sync idempotente).
- `backtest_wc.py` — **loop retro calibrado** del Mundial (ver §8).
- `tune.py` — tuning walk-forward de hiperparámetros (grid) — hoy ya está bien tuneado a mano.
- `core.py` — pipeline sport-agnóstico.

**Producto / orquestación:**
- `app.py` — backend FastAPI (sirve el build de React + endpoints JSON).
- `analizar.py` — arma el cuadro de análisis combinado por partido (lo consume el dashboard).
- `cartera.py` — arma TICKETS del día con los picks confiables y reparte el "sobre" del usuario ∝ prob conjunta.
- `ticket.py` — el INVERSO: audita un ticket que arma el usuario (edge por pierna + flag de correlación + lectura).
- `lecturas.py` — paquete para redactar el contexto en vivo (bajas/XI/forma) vía WebSearch on-launch.
- `linemate.py`, `slate.py`, `mlb.py`, `mvp_nba.py`, `lineups.py`, `history.py`, `track.py`, `cache.py`, `budget.py`.

**Tests:** `predictor/tests/` (pytest) — anti-fuga temporal, consistencia 1X2, devig/edge, stake, resolvers, db, cartera, ticket.

---

## 5. Calibración REAL hoy (números, no promesas)

> **Actualización 2026-07-01:** los números de abajo son del snapshot n≈314. Al 2026-07-01 la muestra
> es **n=788 evaluaciones**; el audit `docs/AUDIT_FABLE_2026-07-01.md` y sus tickets (ver §13) cambiaron
> varias familias. Números frescos: correr `feedback.py report` (incluye ahora desglose 1X2 por outcome
> + validación calibración OUT-OF-SAMPLE por familia). Cards y goles tienen ahora **factor de nivel de
> torneo** (`regime.py`); el 1X2 se calibra **por outcome + renormalizado**. Lo de abajo queda histórico.

Del backtest retro del Mundial (`retro_last.txt`, n≈314 acumulado):

| Métrica | Cruda | **Calibrada** |
|---|---|---|
| Brier | 0.198 | **0.193** |
| Log loss | 0.580 | **0.568** |
| ECE | 0.068 | **0.049** |

**Por familia de mercado** (gap = pred − real; `+` = sobreconfiado):

| Familia | n | Brier_cal | gap | Lectura |
|---|---|---|---|---|
| **1x2** | 69 | 0.140 | ~0% | Excelente, calibrado |
| **dc** | 69 | 0.140 | +0% | Excelente |
| **cs** (valla) | 34 | 0.161 | +9.6% | Ligeramente sobreconfiado |
| **over** | 69 | 0.227 | −15% | Subconfiado tras calibrar |
| **corners** | 18 | 0.281 | −4% | Ruidoso, poca muestra |
| **btts** | 23 | 0.252 | −13.5% | Subconfiado |
| **ml** (MLB) | 14 | 0.272 | **+20.7%** | Sobreconfiado, poca muestra |
| **cards** | 18 | 0.309 | **+25.1%** | **El peor: sobreestima tarjetas** |

**Traducción:** el 1X2 es de nivel profesional. **Córners y tarjetas — donde vive el edge — son
el eslabón débil** (poca muestra + sesgo). Ahí está el mayor upside y el mayor riesgo.

---

## 6. Datos y fuentes (con sus límites)

| Fuente | Uso | Límite |
|---|---|---|
| CSV martj42 (resultados internacionales) | motor de selecciones, forma, backtest | histórico, sin xG/tiros |
| ESPN pickcenter (DraftKings) | cuotas 1X2 de-vig (benchmark de valor) | 1X2 nomás, un book |
| StatsBomb Open Data | xG, córners, tarjetas | agregados, cobertura despareja, no per-partido de selecciones |
| **API-Football** (`budget.py`, key en `predictor/.env`) | game-logs de jugador (props) | **FREE: 100 req/día + throttle ~6s; sin `last` (usar season); cobertura despareja por nación** |
| Linemate API | trends de props (curado, ~6-8/partido) | no trae el board completo (falta Kane etc.) |
| Polymarket | ancla de prediction-market (de-vig por construcción) | liquidez despareja; NUNCA feature |
| MLB Stats API | vertical MLB | — |

**Quota escasa = API-Football.** Todo lo caro se cachea agresivo (stats por partido = inmutables,
30 días) y se protege con `budget.guard()`.

---

## 7. Frontend / UX-UI actual

- **Stack:** React 19 + Vite + Tailwind + Zustand + TanStack Query + Recharts. Código en `frontend/src/`.
  El build (`frontend/dist/`) se **commitea** para el deploy en Render (server sin Node.js).
- **Navegación 3 niveles:** deporte → MatchPicker → MatchWorkspace (tabs).
- **Tab "Equipo":** tabla de picks **agrupada por mercado** (Picks confiables / 1X2 / Goles / Valla
  / Córners / Tarjetas), columna **"Prob. modelo"**, y **strips ✓/✗ de "ritmo del pick"** por
  L5/L10 (si ESE pick se cumplió en cada uno de los últimos partidos del equipo). Selector de
  **3 vías: General | Equipo1 | Equipo2**.
- **Tab "Jugadores":** props con hit-rate L5/L10 (fracción "4/5" + %), fuente API-Football + Linemate,
  carga no-bloqueante con polling.
- **Otros:** tab "Cartera" (arma tickets y reparte el sobre), tab "Mi Ticket" (audita el ticket del
  usuario), lecturas de contexto en vivo (precomputadas on-launch).
- **Deploy:** Render (`predictor-o295.onrender.com`), `render.yaml` en la raíz. **Auto-Deploy suele
  estar apagado → hoy hay que "Deploy latest commit" a mano.**

> El blueprint UX/UI aspiracional (Outlier/Props.cash/OddsJam/Rithmm: histogramas por juego,
> matriz +EV multi-book en tiempo real vía WebSockets, sliders de inferencia, OLAP) está en
> `docs/arquitectura_pivote_sports_analytics_v2.md`. **Es la visión, no el estado actual.**

---

## 8. Los loops (carpeta `loops/` — revisala)

- `loops/loops.txt` — **loop de mantenimiento/QA**: actualizar docs a la implementación real,
  optimizar y medir cada proceso, encontrar bugs por causa raíz + verificar el fix, probar todas
  las capacidades y repetir hasta cumplir criterios, dejar el repo limpio.
- `loops/supra-loop-retro.txt` — **loop de backtest/calibración con guardrails**: 5 pasos
  (fixture a ciegas → predicción de control sin fuga temporal → revelar resultados → evaluar por
  CALIBRACIÓN, no exactitud → proponer ajuste walk-forward SIN commitear). Corre `backtest_wc.py`.
  **Criterio de parada = reliability plana / sesgo neutralizado, NUNCA "acertar el 2-1".**

Outputs vivos (se generan al abrir `dashboard.bat`): `predictor/loop_last.txt`,
`predictor/backtest_wc_last.txt`, `predictor/retro_last.txt`.

**Idea clave que estos loops protegen:** el motor da PROBABILIDADES, no marcadores. Torcer ~7 pesos
para clavar ~40 resultados es overfitting que destruye la predicción del resto. Éxito = calibración.

---

## 9. Debilidades conocidas / deuda técnica (honesto)

1. **Córners/tarjetas/ml sobreconfiados** con poca muestra (n≈14-18). Es el mercado del edge y el más flojo.
   *(2026-07-01: cards/córners tienen ahora factor de nivel de torneo — T5; ml lo desactivó el gate OOS. Ver §13.)*
2. **Recalibración por familia + shrink es in-sample** — falta validarla con forward-test de volumen.
3. **Modelo team-level:** XI/lesiones son contexto, no features. No condiciona en disponibilidad real.
4. **Sin xG rodante per-match** (StatsBomb es agregado). Se probó xG estático como fuerza y NO mejoró.
5. **Cobertura de datos despareja:** props de jugador solo para naciones grandes; córners/tarjetas idem.
6. **Sin streaming/tiempo real:** todo es pull + cache. No hay WebSockets ni matriz multi-book +EV viva.
7. **Un solo book de cuotas** (ESPN/DraftKings) → no hay line-shopping real ni "sharp vs soft".
8. **Persistencia frágil en Render** (disco efímero; `cache.py` cae a memoria).
9. **Loop de PnL sin volumen** → todavía no hay veredicto de si le gana al mercado con plata.
10. **Un deporte de foco** (WC). MLB/NBA no están en la capa de edge.

---

## 10. EL MANDATO 10x — dónde está la mina de oro

Tu trabajo no es reescribir por reescribir. Es **subir el techo de razonamiento del modelo** y
**convertir el edge latente en producto**, respetando §2. Frentes, por leverage:

### 10.1. Núcleo del modelo (razonamiento y entendimiento) — máxima prioridad
- **Jerárquico/bayesiano:** reemplazar Platt por-familia + shrink ad-hoc con un modelo jerárquico
  que comparta fuerza entre mercados y regrese a priors poblacionales con incertidumbre explícita
  (intervalos, no solo puntos). Ataca directo el problema córners/tarjetas (poca muestra).
- **Ajuste por rival / condicionamiento:** el motor es incondicional; el book pricea al rival. Props
  y totales necesitan ajuste opponent-aware (ritmo, defensa, estilo). Es la causa principal de edges espurios.
- **Combos más profundos:** el Monte Carlo (`simulate.py`) ya condiciona córners a dominancia;
  extenderlo a más mercados y a la estructura de correlación real (goles↔córners↔tarjetas↔tiempo).
- **Meta-aprendizaje del loop de PnL:** cerrar el lazo — que el ROI realizado por tier/mercado
  reajuste pesos y umbrales automáticamente (con walk-forward, sin overfit).
- **Enriquecer señales:** XI/lesiones como feature (no solo contexto), descanso/viaje, xG rodante
  si aparece fuente barata, forma ponderada por calidad de rival.
- **Ensamble:** el blend Elo+Poisson es un ensamble de 2; sumar vistas (mercado como prior bayesiano
  SIN volverlo feature circular — sutil pero clave) y stacking calibrado.

### 10.2. Estrategia de valor / staking
- **Line-shopping real:** más books (The Odds API u otros) → mejor de-vig, "sharp vs soft", detección de RLM.
- **Portafolio del slate:** exposición total, correlación entre tickets, optimización de crecimiento
  (no maximizar EV por ticket aislado). Fase 4 del PLAN.
- **Smart-money de Polymarket:** seguir wallets sharp como señal (ver `docs/señal_smart_money_polymarket.md`) — nunca como feature del motor.

### 10.3. UX/UI (de dashboard a plataforma pro)
- Ejecutar el blueprint de `docs/arquitectura_pivote_sports_analytics_v2.md`: histogramas por juego
  estilo Props.cash, matriz +EV multi-book estilo OddsJam (streaming), sliders de inferencia estilo
  Rithmm, filtros de contexto instantáneos (Last 5/10/20, H2H, local/visita) resueltos client-side.
- Hacer del **veredicto** (edge + tier + monto sugerido + confianza) el héroe de cada card — es lo
  que Linemate NO hace y donde está la diferenciación.

### 10.4. Infra / escala
- OLAP/vistas materializadas para el cómputo multidimensional instantáneo; streaming (WS/SSE) para
  cuotas vivas; persistencia durable (salir del disco efímero de Render). Solo cuando el modelo lo justifique.

---

## 11. Criterios de éxito (cómo sabremos que lo 10x-easte)

1. **Calibración:** reliability plana y Brier bajo **por familia** (córners/tarjetas dejan de estar
   sobreconfiados), validado **forward** (no in-sample). Intervalos de confianza reales, no puntos.
2. **Edge demostrado:** el forward-test de `pnl.py` muestra ROI realizado ≈ edge predicho en el
   nicho identificado, con muestra suficiente. Si no le gana al mercado, el reporte lo dice.
3. **Bankroll:** curva de equity creciente con drawdown controlado bajo staking Kelly fraccional.
4. **Producto:** un usuario abre un partido y en segundos entiende QUÉ apostar, CUÁNTO y POR QUÉ,
   con la evidencia (hit-rate, edge, confianza) a la vista.
5. **Disciplina intacta:** ningún guardrail de §2 roto para conseguir lo anterior.

---

## 12. Constraints operativos (no los aprendas a los golpes)

- **Python real:** `C:/Users/Juant/AppData/Local/Python/bin/python.exe`.
- **Windows / consola cp1252:** evitá `≥ · → ≈` y emojis en `print` (o `sys.stdout.reconfigure(encoding="utf-8")`). Archivos en UTF-8; JSONL de PowerShell traen BOM → leer con `utf-8-sig`.
- **API-Football:** free 100/día + throttle ~6s + `/status` laguea → `budget.guard()` no ve el throttle por minuto. Cachear agresivo.
- **Cuotas jamás feature** (guardrail 6). Repetido a propósito: es el error que mató a la v1.
- **Render:** disco efímero, Auto-Deploy suele estar off (deploy manual del último commit), el
  backend sirve el build de `frontend/dist/` (hay que commitearlo).
- **Docstrings con rutas Windows:** usar `r"""..."""` (el `\U` de `C:\Users` rompe Python).
- **uvicorn no recarga solo** al editar módulos: reiniciar el proceso.

---

## 13. Sesión 2026-07-01 — audit Fable ejecutado (T1-T11)

Auditoría completa en `docs/AUDIT_FABLE_2026-07-01.md` + ejecución de sus tickets. Contexto clave:
el forward-test del edge (`pnl.py`) dio **veredicto negativo sobre edge-v1 (ROI −43% flat)** con 3
causas raíz. Se ejecutó la cirugía completa (motor base 1X2/over **intacto** todo el camino; 119 tests):

- **Detención de la pérdida (T1-T3):** clamp de pendiente del calibrador (mató un bug de inversión
  `ml|mid` a=−0.131), n contado por PARTIDOS no filas, **gate OUT-OF-SAMPLE** del calibrador (desactiva
  familias que degradan forward), **1X2 calibrado por outcome + renormalizado** (mató el "edge fantasma"),
  **power de-vig** + gates (empate fair >33% = NO-APTO por régimen; cuota >4.0 = NO-APTO longshot) +
  `p_bet` shrunk hacia el mercado. Replay de 40 candidatas: −43% → +1% (solo capando longshots) → +29%
  (favoritos). Nuevas candidatas etiquetadas `edge_version="edge-v2"`.
- **T4 CLV real:** tarea programada Windows (`snapshot.bat`, cada 2h) → el cierre deja de ser == apertura.
- **T5/T6 factores de nivel de torneo (`regime.py`, empirical-Bayes walk-forward):** cards gap +28%→+4.5%
  (factor 0.72: el WC da menos amarillas que StatsBomb 2018-24); goles sesgo −0.39→−0.14 (factor 1.12),
  over ll 0.686→0.675. El factor de goles escala SOLO los mercados de goles; el **1X2 queda intacto**.
- **T7 máquina +EV multi-book de props (`prop_value.py`):** la fuente de ROI #1. El JSON de Linemate ya
  traía cuotas de ~14 books por prop (que `flatten()` tiraba); fair = mediana de-vig del consenso, +EV si
  el mejor precio supera la fair ≥4% Y el hit-rate propio (Beta-Binomial) corrobora. Verificada en MLB.
- **T8** bug `*0` del acople de `simulate.py` corregido (medido: acople córners/cards↔dominancia ~0 con
  n=24, se mantiene independencia con evidencia). **T9** la calibración manda en el producto
  (picks/cartera/ticket usan prob calibrada por familia + gate). **T10** curva del empate (|elo_diff|):
  REFUTADA por el sweep (no mejora OOS), documentada en `soccer._fit_elo_model`.
- **Pendiente:** resolver de props (`props_evals` — falta fuente per-fixture de stats de jugador; el
  núcleo está testeado por inyección); acumular ≥30 candidatas edge-v2 para el veredicto de plata.

---

*Este briefing refleja el repo al 2026-07-01. Si algo acá contradice el código, el CÓDIGO manda —
verificá y actualizá este documento (es parte del loop de mantenimiento de `loops/loops.txt`).*
