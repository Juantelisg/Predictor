# Bets — Supra-agente de análisis deportivo

Sistema cuantitativo de análisis de apuestas deportivas operado desde la consola con Claude Code. Combina el motor de Claude con una toolbox de skills especializadas para detectar value bets (EV+) en mercados deportivos.

> **Disclaimer**: análisis con fines educativos / entretenimiento. Apostar implica riesgo de pérdida total. No es asesoría financiera.

## Arquitectura

```
┌─────────────────────────────────────────────────────┐
│  SUPRA-AGENTE (CLAUDE.md — orchestrator + persona)  │
└──────────────────────┬──────────────────────────────┘
                       │
        ┌──────────────┴──────────────┬──────────────────────┐
        ▼                              ▼                       ▼
   FETCH layer                    MATH layer            ANALYSIS layer
   ───────────                    ──────────            ──────────────
   • nba-data                     • betting             • sports-betting-
   • mlb-data                       (devig, edge,         analyzer
   • football-data                  Kelly, arb,         (synthesis →
   • polymarket                     parlay)              pick canónico)
   • markets                                              │
   • The Odds API                                         │
                                                          ▼
                                                   PERSISTENCIA
                                                   ────────────
                                                   • predictions/*.jsonl
                                                   • evaluations/*.jsonl
                                                   • reports/{daily,weekly}/
```

## Estructura del repo

```
bets/
├── CLAUDE.md                      ← Sistema-prompt del supra-agente (lectura obligatoria de Claude)
├── IDEA.txt                       ← Vision original (preservada)
├── SKILL.txt                      ← Draft original del skill (preservado)
├── README.md                      ← Este archivo
├── skills-lock.json               ← Tracking de skills instaladas
├── .gitignore
│
├── .agents/skills/                ← Skills (toolbox del supra-agente)
│   ├── betting/                   ← Math: devig, edge, Kelly, arb, parlay
│   ├── football-data/             ← Soccer (13 ligas)
│   ├── markets/                   ← ESPN+Polymarket+Kalshi unified
│   ├── mlb-data/                  ← MLB
│   ├── nba-data/                  ← NBA
│   ├── polymarket/                ← Prediction market
│   └── sports-betting-analyzer/   ← LOCAL: synthesis layer (pick canónico)
│
├── config/
│   ├── settings.json              ← Bankroll, edge tiers, Kelly, stop-loss
│   ├── .env.example               ← Template de API keys
│   └── the-odds-api.md            ← Guía de The Odds API
│
├── data/                          ← Cache de odds y stats (NO committed)
│   ├── odds/
│   └── stats/
│
├── predictions/                   ← JSONL de cada pick / pase
│   └── SCHEMA.md
│
├── evaluations/                   ← JSONL de resultados resueltos
│   └── SCHEMA.md
│
└── reports/                       ← Síntesis de calibración y PnL
    └── README.md
```

## Quick start

### 1. Instalar dependencias de skills (una sola vez)

```bash
pip install sports-skills
# o desde GitHub:
pip install git+https://github.com/machina-sports/sports-skills.git
```

Requiere Python 3.10+.

### 2. Configurar API keys (opcional pero recomendado)

```bash
cp config/.env.example config/.env
# Editar config/.env y rellenar THE_ODDS_API_KEY
```

The Odds API: <https://the-odds-api.com/> (free tier 500 req/mes).

### 3. Ajustar bankroll y thresholds

Editar `config/settings.json` con tu bankroll real y preferencias de risk.

### 4. Operar desde la consola

Abrir Claude Code en `c:/bets/` y pedirle análisis al supra-agente:

```
> ¿Hay valor en Lakers ML hoy?
> Scan NBA hoy buscando edges >3%.
> Evaluá las predicciones de ayer.
> ¿Cómo viene la calibración del último mes?
```

CLAUDE.md instruye al modelo cómo orquestar las skills, generar el output canónico, y persistir en `predictions/` + `evaluations/`.

## Pipeline de decisión (resumen)

Cada análisis ejecuta 5 pasos (detalle en `CLAUDE.md`):

1. **Recolección**: odds (sportsbook + prediction market) + stats + lesiones + line movement.
2. **Modelado**: tres anclajes de probabilidad (de-vigged book, prediction market, modelo propio).
3. **Detección de value**: `EDGE = model_prob - market_prob`. Tiers strong/moderate/pass.
4. **Validación cruzada**: ≥2 señales independientes para `APOSTAR`.
5. **Output**: bloque markdown canónico + línea JSONL en `predictions/`.

## Meta-agente — auto-mejora

Cada predicción se loguea (incluyendo `PASAR`). Cada resolución se evalúa. Reportes periódicos miden:
- **Calibración**: ¿cuando digo 60% gano efectivamente ~60% del tiempo?
- **Edge realized vs predicted**: ¿el edge teórico se materializa?
- **Cohortes**: por tag (sharp moves, home favorites, ...) — ¿qué patrones rinden?
- **Patrones de fallo**: dónde el modelo sistemáticamente se equivoca.

Brutal honestidad: si el modelo pierde, el reporte lo dice. `variance_win` / `variance_loss` separan suerte de skill.

## Tech / contexto

- **Plataforma**: Claude Code (CLI)
- **Motor**: Claude (modelo configurable — default project: Sonnet 4.6)
- **OS**: Windows 11 (PowerShell 5.1 / Bash via Git for Windows)
- **Skills**: 7 instaladas — 6 de [machina-sports/sports-skills](https://github.com/machina-sports/sports-skills) + 1 local (`sports-betting-analyzer`)

## Reglas operativas (no negociables)

1. Quant, no tipster.
2. PASAR es output válido — y frecuente.
3. Devig siempre antes de calcular edge.
4. Quarter-Kelly default, nunca full.
5. Loguear cada predicción y cada evaluación.
6. Disclaimer en cada output.
7. Stop-loss diario/semanal respetado.

Detalle completo en `CLAUDE.md`.
