# Predictor estadístico de deportes

> **Regla de oro:** es un predictor de **probabilidades puramente estadístico**.
> **Cero cuotas, cero "edges", cero "ganarle a la casa".** La vara de éxito es la
> **calibración** (cuando dice 70%, ¿pega 70%?), no el ROI.

Predice probabilidades de eventos deportivos (1X2, totales, BTTS, moneyline) a partir de
datos históricos y de rendimiento. Se valida solo contra resultados reales y se mide su
calibración para mejorar con el tiempo.

## Cómo correr

Usar **siempre** el Python real (el `python` del PATH es el alias del Store y no sirve):

```
PY="C:/Users/Juant/AppData/Local/Python/bin/python.exe"

# Dashboard (UI)
$PY -m uvicorn app:app --port 8900 --app-dir predictor   # -> http://localhost:8900

# Análisis por consola
$PY predictor/soccer.py "Brazil" "Morocco"   # un partido de selecciones (Mundial)
$PY predictor/mlb.py today                    # cartelera MLB de hoy (no jugados)
$PY predictor/mlb.py 2025                      # backtest de una temporada
$PY predictor/slate.py                         # partidos de hoy (fuentes gratis)

# Loop de aprendizaje
$PY predictor/feedback.py log "Brazil" "Morocco"   # registra predicciones
$PY predictor/feedback.py eval                       # resuelve contra resultado real (ESPN)
$PY predictor/feedback.py report                     # tabla de calibración

# Presupuesto de la API escasa
$PY predictor/budget.py
```

> uvicorn **no recarga solo**: al editar, matar el puerto y relanzar
> (`Get-NetTCPConnection -LocalPort 8900 | Stop-Process` en PowerShell).

## Arquitectura

```
INGESTA (gratis)            MOTOR (1 por deporte)         SALIDA + LOOP
statsapi / CSV intl / ESPN  →  features → modelo → prob  →  dashboard + calibración
        │ cache.py (TTL)                                        feedback.py
        └ budget.py protege la única API escasa (API-Football)
```

| Archivo | Qué hace |
|---|---|
| `core.py` | Pipeline binario compartido (SQLite formato largo → features sin fuga → logística → validación). `form()`, `fit_model()`, `entrenar_y_evaluar()`. |
| `schema.sql` | Esquema SQLite multi-deporte (núcleo + stats en formato largo). |
| `soccer.py` + `elo.py` | **Selecciones**: Elo rodante + Poisson/Dixon-Coles. La supremacía la pone el Elo, el total el Poisson → 1X2 + totales + BTTS coherentes. |
| `mlb.py` | **MLB moneyline**: forma de equipo + ERA rodante del abridor (sin fuga). Datos reales statsapi. |
| `mvp_nba.py` | NBA POC con datos sintéticos (placeholder hasta cablear nba_api). |
| `feedback.py` | Loop de aprendizaje: `log` → `eval` (resuelve vs ESPN, CSV de respaldo) → `report` (fiabilidad por bucket + Brier). |
| `slate.py` | Arma los partidos de hoy desde fuentes gratis (statsapi/CSV/ESPN). |
| `budget.py` | Guardia de presupuesto de API-Football (100/día). `/status` no consume quota. |
| `cache.py` | Caché JSON con política de TTL por volatilidad. |
| `app.py` + `dashboard.html` | Backend FastAPI + UI minimalista (1 partido = 1 card con varios logros). |

## Fuentes de datos

- **Sin key (workhorse):** MLB Stats API, dataset internacional (martj42/international_results), ESPN, nflverse, nba_api.
- **Con key (escasa):** API-Football — `predictor/.env` (gitignoreado). Free = 100/día + temporadas 2022-2024. Único cuello de botella → protegido por `budget.py`.
- **The Odds API: NO se usa** (cuotas, contra la regla de oro).

## Validación actual

- **Soccer 1X2**: log loss test ~0.86 vs 1.05 baseline · acc ~60%. Compresión de favoritos resuelta con Elo. Totales/BTTS coherentes (descomposición supremacía/total).
- **MLB moneyline**: 57% acc vs 53% baseline (2025) · log loss 0.68. El abridor es el feature dominante.
- **Loop**: corrido con 20 evaluaciones reales (ESPN). Brier 0.20. **n chico = ruido → no se ajusta nada todavía** (hace falta volumen).

## Estado y próximos pasos (retomar acá)

**Listo:** soccer selecciones, MLB moneyline, loop de aprendizaje, dashboard, infra de quota.

**Falta (orden recomendado):**
1. **MLB → loop** — cablear resultados+logging de MLB al `feedback.py` (statsapi). 15 partidos/día = volumen rápido para calibrar. *(lo más alto)*
2. **Decidir tier API-Football** — desbloquea córners/tarjetas/player-props (los mercados que el usuario realmente juega).
3. **Totales de carreras MLB** — para que MLB tenga varios logros en el dashboard.
4. **NBA datos reales** (nba_api) · **NFL** (nfl_data_py).
5. **Corrección de calibración** (isotónica) — cuando haya volumen.
6. Persistir la SQLite (hoy `:memory:`).

**Watch (no accionar aún):** los goles podrían tirar un poco altos (2 partidos low-scoring; sin confirmar).
