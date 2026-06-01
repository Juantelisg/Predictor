# Reporte — Estado del proyecto + primer ciclo de evaluación

**Generado**: 2026-05-29 | **Autor**: supra-agente | **Tipo**: diagnóstico + primer batch de calibración

---

## TL;DR

El "cerebro" del proyecto (arquitectura, schemas, lógica de decisión) está bien diseñado y la **capa de cálculo funciona**. Pero la **capa de datos no funciona en este entorno** (la red bloquea ESPN, NBA, Polymarket y The Odds API) y **el loop de aprendizaje nunca había corrido**: había 2 apuestas reales sin evaluar desde el 06/05.

Este reporte cierra ese loop por primera vez. Resultado del primer batch (el Clásico del 10/05): **+22 USD (+2,2 % del bankroll), ROI sobre lo arriesgado +44 %** — 1 acierto (Barça ML) y 1 fallo (Over 3.5). Con n=2 esto **no significa nada estadísticamente**; es el arranque del registro, no una señal de skill.

---

## 1. Estado del proyecto (diagnóstico)

El proyecto define tres capas. Estado real de cada una hoy:

| Capa | Qué hace | Estado | Detalle |
|---|---|---|---|
| **Ingesta (datos)** | Baja odds/stats/lesiones | 🔴 **No operativa aquí** | `sports-skills` v0.22.0 instala bien, pero la red de este entorno bloquea los endpoints: ESPN, NBA, Polymarket y The Odds API devuelven 403 / sin conexión. Además falta `config/.env` con `THE_ODDS_API_KEY`. |
| **Cálculo (math)** | devig, edge, Kelly, EV | 🟢 **Operativa** | Probado en vivo: devig −150/+130 → fair 58,0 %/42,0 %, vig 3,48 %. Conversión −125 → 1,80 dec. |
| **Razonamiento** | Decide APOSTAR / PASAR | 🟢 Operativa | Es el motor del agente. |
| **Persistencia** | predictions / evaluations / reports | 🟡 **Recién arrancando** | `predictions/`: 1 solo día (06/05). `evaluations/`: vacío hasta hoy → **ahora tiene su primer archivo**. `reports/`: este es el primero. |

Otros hallazgos: el repo **no está bajo git** (los docs asumen que sí, para auditabilidad). Hay **drift de versión**: los SKILL.md documentan una sintaxis de CLI que en v0.22.0 rompe con cuotas separadas por coma (`--odds=-150,+130` falla) — **el SDK de Python sí funciona** y es el camino confiable.

---

## 2. Primer ciclo de evaluación — Clásico Barça–Real Madrid (10/05/2026)

**Resultado real**: Barcelona 2–0 Real Madrid (goles de Rashford 9' y Ferran Torres 18'). Barça campeón (29º título). Mbappé, Courtois y Güler ausentes en el Madrid. Confirmado por ESPN, CNN, Al Jazeera y FOX Sports.

### Volumen del día 06/05
- Predicciones totales: **5** → 2 APOSTAR, 3 PASAR.
- Evaluadas en este ciclo: **2** (las apuestas con stake).
- Pendientes: **3 PASAR** (Bayern–PSG ×2 UCL, NYK–PHI G2 NBA) — falta back-check contrafáctico.

### Apuestas resueltas

| Pick | Cuota | Stake | model_prob | Resultado | PnL | calib_err |
|---|---|---|---|---|---|---|
| Barça ML | −125 (1,80) | 4 % ($40) | 63 % | ✅ **WON** | **+$32** (+0,032 u) | 0,37 |
| Over 3.5 | −150 (1,67) | 1 % ($10) | 61 % | ❌ **LOST** | **−$10** (−0,010 u) | 0,61 |

### PnL del batch
- Arriesgado: **5 % del bankroll ($50)**.
- PnL: **+0,022 u (+$22) → +2,2 % del bankroll**.
- ROI sobre lo arriesgado: **+44 %**.

### Calibración
- Brier (n=2): **0,2545** — ⚠️ **ruido total con 2 datos. No se saca ninguna conclusión.** Se registra para empezar a acumular.
- El acierto fue de tesis sólida (injury-mismatch + motivación), no suerte → no es `variance_win`.

---

## 3. Qué aprendimos / errores

**El fallo del Over 3.5 es accionable, no solo varianza.** El modelo se apoyó en el H2H histórico de alto scoring (≈5 goles/Clásico) pero ignoró que **ambos ataques estaban diezmados** (Yamal OUT por Barça, Mbappé OUT por Madrid). La señal disponible apuntaba a UNDER. Además la cuota −150 ya comprimía el EV.

➡️ **Regla propuesta para el modelo**: cuando los dos equipos tienen su ataque titular mermado, **bajar la proyección de total** en vez de anclarse al H2H histórico. (Confianza baja: 1 solo dato, pero la lógica es robusta.)

---

## 4. Qué descartar

- `excels/Book.xlsx` — placeholder vacío (solo "BAYERN/PSG"). No aporta; borrar o reusar.
- La suposición de que los fetches de datos funcionan **dentro de este entorno** — no es el caso.
- La sintaxis de CLI con cuotas-coma de los SKILL.md — usar el **SDK de Python**.

---

## 5. Roadmap priorizado

| Prio | Acción | Por qué |
|---|---|---|
| **P0** | **Resolver acceso a datos.** Opciones: (a) correr el motor desde la máquina del usuario, donde la red no está restringida; (b) cargar `THE_ODDS_API_KEY` en `config/.env`; (c) workaround: el agente trae odds/stats por búsqueda web y se las pasa al math layer. | Sin datos en vivo no hay pipeline; es el blocker #1. |
| **P1** | **Back-check de los 3 PASAR del 06/05** (Bayern–PSG, NYK–PHI). Evaluar si pasar fue correcto (contrafáctico). | El proyecto exige evaluar cada decisión, también los pases. |
| **P2** | **Inicializar git** en `C:\bets`. | Auditabilidad que los docs ya asumen. |
| **P3** | **Eliminar/reusar** `excels/Book.xlsx`. | Limpieza. |
| **P4** | **Fijar en CLAUDE.md**: el math layer se usa por SDK, no CLI (drift v0.22.0). | Evitar errores futuros. |

---

*Análisis con fines educativos / de entretenimiento. Apostar implica riesgo de pérdida total. Solo arriesgar capital cuya pérdida sea financieramente aceptable. Si el juego deja de ser entretenimiento, buscar ayuda: https://www.gamblersanonymous.org/*
