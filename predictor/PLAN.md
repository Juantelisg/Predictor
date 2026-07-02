# PLAN — Supra-modelo de decisión de apuestas

> **Rumbo fijado 2026-06-21.** Este documento es el plan canónico. `roadmap.txt` es el
> quick-ref; este archivo manda. Correr siempre con el Python real:
> `C:/Users/Juant/AppData/Local/Python/bin/python.exe`.

## North star

No es "dar picks". Es un **motor de decisión de apuestas** que (1) **predice** con
probabilidades calibradas, (2) **detecta valor** real contra el mercado, y (3) **decide
cuánto arriesgar** (Kelly/portafolio) — cerrando en un **loop que aprende de la plata real**,
no de un número abstracto. Éxito = **crecimiento de bankroll con drawdown controlado**.

## El reencuadre que ordena todo

El pivote a "calibración pura" (jun-13) **no fue alejarse del supra-modelo: fue construirle
los cimientos que la versión EV+ original nunca tuvo** (encontraba edges falsos = su propia
sobreconfianza). Ahora **mergeamos**: la ambición EV+/Kelly/bankroll del `CLAUDE.md` original,
montada sobre el motor calibrado de ahora. La calibración no es una alternativa a ganar
plata — es **la condición que hace que el staking no reviente el bankroll**.

## Arquitectura: 3 cerebros + 1 loop

| Cerebro | Qué hace | Estado hoy |
|---|---|---|
| **1 · Predice** | P calibrada **+ confianza** por mercado (1X2, totales, BTTS, córners, tarjetas, combos vía Monte Carlo) | Base sólida; córners/tarjetas sobreconfiados |
| **2 · Valora** | P calibrada vs cuota de-vigeada → edge real, por mercado | Por construir |
| **3 · Decide cuánto** | (edge × confianza) → stake: fuerte / moderado / bajo / pasar | Por construir |
| **Loop de PnL** | predice → resultado → ROI realizado vs edge, por tier/mercado → reajusta | Loop de calibración listo; falta capa PnL |

**Rol de cada mercado (NO confundir):**
- **1X2 / DC / goles** (selecciones grandes) = **ancla calibrada** del ticket + columna del
  motor (sin marcador no se simulan córners/tarjetas). Mejor calibrados (Brier ~0.16). Bajo
  edge (mercado eficiente) → no forzamos value ahí.
- **Córners / tarjetas / props / ligas chicas** = **donde vive el edge** (book vago), y
  casualmente lo que el usuario juega. Hoy mal calibrados → **Fase 1 los arregla**.

## Guardrails no-negociables (para no repetir el fracaso EV+)

1. **Calibración es prerequisito de edge.** Un mercado NO entra a la capa de valor hasta
   estar calibrado (reliability plana + Brier OK). Si no, el "edge" es el error del modelo.
2. **Edge siempre POST de-vig.** La cuota cruda trae el margen de la casa adentro.
3. **Forward-test antes de confiar.** Nunca backtest sobre la misma data que tuneó.
4. **Kelly fraccional, nunca full.** Kelly con P inflada revienta el bankroll.
5. **Combos con correlación (Monte Carlo), nunca producto de marginales.**
6. **Las cuotas son benchmark/insumo de valor — NUNCA feature del modelo.** Si entran al
   motor, el modelo predice al mercado (circular) y se contamina la calibración.
7. **Disciplina que se mantiene** (de la etapa calibración): logging versionado por
   `model_version`, sin fuga temporal, se evalúa TODO (no solo lo jugado).

---

## FASE 1 — Clavar el motor donde vive el edge  *(en curso)*

Objetivo: **P calibrada + confianza por mercado**, sobre todo córners/tarjetas/combos.
Sin esto, nada de Fase 2-3 es confiable.

| # | Tarea | Dónde | Criterio de éxito (gate) |
|---|---|---|---|
| 1.1 | **Recalibración por familia de mercado** | `calib.py` | Hoy poolea todo en `soccer-v3`. Separar recalibrador por familia (1x2/over/btts/corners/cards). Córners/tarjetas Brier baja de ~0.33; reliability por familia plana. |
| 1.2 | **Tuning walk-forward de hiperparámetros** | nuevo `tune.py` | Grid/Optuna sobre `ELO_W, HALFLIFE_DAYS, SINCE_YEARS, FRIENDLY_W, ALPHA, RHO` vs log loss OOS. Baja log loss 1X2/totales sin overfit (walk-forward). |
| 1.3 | **Monte Carlo de partido (combos)** | nuevo `simulate.py` | Simula N marcadores del Poisson; condiciona córners/tarjetas a la dominancia (gap de goles); devuelve **taxonomía de escenarios** + **P de combo correcta**. Valida combo simulado ≠ producto de marginales contra resultados reales. |
| 1.4 | **Mejores métricas de calibración** | `feedback.py` (report) | Reliability diagram (export) + ECE + sharpness **por familia**. Tablero por familia, no 1 número global. |
| 1.5 | **Señal nueva: XI/lesiones + data fresca de córners** | investigar fuente | El modelo condiciona en disponibilidad. (El más caro: depende de fuente; Linemate injuries da vacío para selecciones → replantear.) |

## FASE 2 — Capa de mercado (termómetro → edge)

Objetivo: medir dónde le ganamos al mercado de-vigeado, **descubrir el nicho**, forward-testear.

| # | Tarea | Dónde | Criterio de éxito |
|---|---|---|---|
| 2.1 | **Ingesta de cuotas (read-only)** | nuevo `odds.py` | Traer cuotas + de-vig. Empezar por mercados finos + 1X2/totales de ligas chicas. Solo lectura. |
| 2.2 | **Cálculo de edge** | nuevo `edge.py` | `edge = P_calibrada − P_devig` por mercado. Solo cuenta si el mercado pasó el gate de calibración (Fase 1) y supera umbral. |
| 2.3 | **Forward-test del edge** | `feedback.py` + `predictions/` | Loguear edge + cuota; evaluar **ROI realizado vs edge predicho** por mercado/situación al cierre. → tabla que revela el nicho. |
| 2.4 | **Detección de errores de cuota** | `edge.py` | Flag de discrepancias grandes, con escepticismo + corroboración (¿edge o agujero del modelo?). |

## FASE 3 — Staking (cómo apostar)

Objetivo: traducir (edge × confianza) en **cuánto** va en cada ticket.

| # | Tarea | Dónde | Criterio de éxito |
|---|---|---|---|
| 3.1 | **Kelly fraccional × confianza → tiers** | nuevo `stake.py` | Fuerte (~half-Kelly, cap) / Moderado (~quarter) / Bajo (~eighth/mínimo) / Pasar (0). Tier sale de (edge, confianza, liquidez). |
| 3.2 | **Staking correlación-aware de combos** | `stake.py` + `simulate.py` | El tamaño del combo sale del Monte Carlo (1.3), no de multiplicar piernas. |
| 3.3 | **Controles de riesgo** | `stake.py` | Caps por ticket/día, stop-loss diario/semanal, límite de exposición. |

## FASE 4 — Portafolio + loop de PnL

Objetivo: el slate como cartera; optimizar por **crecimiento de bankroll real**.

| # | Tarea | Dónde | Criterio de éxito |
|---|---|---|---|
| 4.1 | **Vista de portafolio** | nuevo `portfolio.py` | Exposición total, varianza del día, correlación entre tickets. |
| 4.2 | **Loop de PnL** | `feedback.py` + `evaluations/` | ROI realizado, drawdown, growth por tier/mercado/situación → reajuste. |
| 4.3 | **Dashboard del supra-modelo** | `app.py` + `dashboard.html` | Cada card: pick + edge + tier + monto sugerido. |

## Infra transversal (cuando duela, no antes)

- **Tests (pytest):** anti-fuga temporal, consistencia 1X2, regresión de Brier/ROI. (Cero hoy.)
- **Persistir SQLite** (hoy `:memory:` en `core.py`).
- **Scheduler del loop:** automatizar log → eval → report → calibrate (hoy `retro_tonight.bat` a mano).

---

## Orden de construcción (no se saltea)

```
FASE 1 (motor calibrado + confianza + combos)   <- estamos acá
   └─> FASE 2 (edge medido y forward-testeado)
          └─> FASE 3 (staking Kelly por tier)
                 └─> FASE 4 (portafolio + loop de PnL)
```
No se puede stakear bien sin edge, ni medir edge sin calibración. Cada fase desbloquea la
siguiente; saltar es la receta del EV+ viejo.

## Dónde estamos parados (2026-06-22)

**Spine lógico del supra-modelo: CONSTRUIDO Y TESTEADO end-to-end** (sin cuotas en vivo todavía).

- ✅ **F1.1** Recalibración **por familia** (`calib.py`): Brier 0.213→0.206, ECE 0.082→0.061. 1x2 estira / over comprime (opuestos que el pool anulaba).
- ✅ **F1.4** Métricas por familia + ECE en `feedback.report` (gap por familia: cards +27% sobreconfiado, etc.).
- ✅ **F1.3** Monte Carlo `simulate.py`: combos correlación-aware (joint ≠ producto, lift medido) + taxonomía de escenarios. 1X2 reponderado al blend.
- ✅ **F1.2** Tuning `tune.py`: el modelo ya está bien tuneado a mano (sin free lunch); ALPHA→0.001 ayuda totales pero no se aplicó (riesgo overfit).
- ✅ **F3** Staking `stake.py`: Kelly fraccional × confianza → tiers fuerte/moderado/bajo/pasar; combos correlación-aware.
- ✅ **F2 (core lógico)** `edge.py`: de-vig + edge + **GATE de calibración** (córners/tarjetas = NO-APTO hasta calibrar → no se apuesta el propio error).

- ✅ **F2 ingesta + edge:** `odds.py` trae cuotas 1X2 de **ESPN (DraftKings), GRATIS** (no hace falta API-Football, que en free no da 2026). Cadena viva: modelo → de-vig → edge → stake. Guardrails: shrink del recalibrador (`SHRINK_K`) + `MAX_EDGE` (edge enorme = SOSPECHOSO, no se apuesta).
- ✅ **F1.5:** XI confirmado de **ESPN rosters** (`lineups.py`) como contexto en `analizar`/dashboard (el modelo es team-level → XI = contexto, no feature).
- ✅ **F4 forward-test:** `pnl.py` (log → eval → report). 1er resultado on-thesis: **SOSPECHOSO ROI flat −52% → el guardrail salvó plata** (n chico = no veredicto, el loop acumula solo).

**TODO el spine del supra-modelo: CONSTRUIDO, CABLEADO Y TESTEADO end-to-end, gratis.**

📌 **Pendiente de validar (no de construir):**
- Recalibración por familia + shrink = **in-sample**; el forward-test (`pnl.py`) la valida con volumen.
- El modelo crudo viene un toque alcista en favoritos vs el book → lo dirá `pnl.py` con muestra.
- Polish: render del XI en el dashboard.html (la data ya llega al API); MLB/NBA a la capa de edge; persistir SQLite.

## Dónde estamos parados (2026-07-01) — audit Fable ejecutado

Auditoría completa (`docs/AUDIT_FABLE_2026-07-01.md`) + ejecución de sus tickets. **Veredicto del
forward-test del edge (el juez): edge-v1 daba ROI −43% flat** — no era varianza, eran 3 causas raíz
(de-vig proporcional inflando longshots, modelo ciego al régimen de empate, winner's curse). Ejecutado:

- **T1-T3** (calib/edge/stake): clamp de pendiente (mató el bug de inversión ml|mid), n por partidos,
  gate OOS del calibrador, 1X2 per-outcome + renormalización (mató el edge fantasma), power de-vig +
  gates (empate>33%=NO-APTO, longshot>4.0=NO-APTO) + `p_bet` shrunk. Replay: −43% → +1% (solo longshot)
  → +29% (favoritos). `edge_version="edge-v2"`.
- **T4** CLV con cadencia real (tarea programada cada 2h → cierre ≠ apertura).
- **T5** factor de nivel de cards/córners del torneo (empirical-Bayes walk-forward): cards gap +28%→+4.5%.
- **T6** factor de nivel de GOLES del torneo: sesgo −0.39→−0.14, over ll 0.686→0.675, **1X2 intacto**.
- **T7** máquina +EV multi-book de props (Linemate books): fuente de ROI #1. Verificada en MLB.
- **T8** bug `*0` del acople de simulate corregido (acople medido ~0 con n=24, se mantiene independencia).
- **T9** la calibración manda en el producto (picks/cartera/ticket usan prob calibrada por familia).
- **T10** curva del empate (|elo_diff|): REFUTADA por el sweep (no mejora OOS), documentada.
- **Pendiente**: resolver de props (falta fuente per-fixture de stats de jugador), acumular ≥30
  candidatas edge-v2 para el veredicto de plata, MLB/NBA a la capa de edge.
- **Estado**: 119 tests verdes, motor base (1X2/over holdout) intacto todo el camino.
