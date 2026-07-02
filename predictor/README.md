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
$PY predictor/analizar.py "Belgium" "Iran" --lm=BEL,IRN   # cuadro combinado + Linemate + calibrado
$PY predictor/mlb.py today                    # cartelera MLB de hoy (no jugados)
$PY predictor/mlb.py 2025                      # backtest de una temporada
$PY predictor/slate.py                         # partidos de hoy (fuentes gratis)

# Loop de aprendizaje
$PY predictor/feedback.py log "Brazil" "Morocco"   # registra predicciones de selecciones
$PY predictor/feedback.py log-mlb                    # registra el moneyline MLB de hoy
$PY predictor/feedback.py eval                       # resuelve contra resultado real (ESPN/statsapi)
$PY predictor/feedback.py report                     # tabla de calibración (Brier + log loss)
$PY predictor/feedback.py calibrate                  # fitea el recalibrador (Platt) desde evaluations/

# Presupuesto de la API escasa
$PY predictor/budget.py

# Closing Line Value (CLV) - snapshot de cuotas
$PY predictor/clv.py snapshot   # guarda las cuotas 1X2 del momento (con timestamp)
$PY predictor/clv.py report     # CLV por apuesta: solo cuentan las de >=2 snapshots a distinto ts
```

## Closing Line Value (CLV)

El CLV mide si el precio que tomamos le gana al **cierre** del mercado — el indicador de edge de
**menor varianza** (converge antes que el ROI). Requiere **cadencia**: snapshotear las cuotas varias
veces al día, así el último snapshot antes del kickoff es el cierre (con un solo snapshot, cierre ==
apertura y el CLV es 0 por construcción). La cadencia la da una **tarea programada de Windows**
(`predictor/snapshot.bat`, cada 2h):

```
schtasks /create /tn "bets-clv-snapshot" /tr "C:\bets\predictor\snapshot.bat" /sc hourly /mo 2 /st 10:00 /f
schtasks /run    /tn "bets-clv-snapshot"    REM correr ya   |   /delete ... /f  REM quitarla
```

> El CLV **no es retroactivo** (ESPN free no da cuotas históricas): se acumula desde que la tarea
> empieza a correr. Es **métrica de validación**, nunca feature del modelo.

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
| `soccer.py` + `elo.py` | **Selecciones**: Elo rodante + Poisson/Dixon-Coles. La supremacía la pone el Elo, el total el Poisson → 1X2 + totales + BTTS coherentes. Modelo `soccer-v3`. Los modelos se fitean **una vez** (`fit_today`) y se reusan entre partidos. |
| `analizar.py` | Cuadro de análisis combinado: junta el predictor (1X2/totales/valla + córners/tarjetas) con los trends de Linemate (validación cruzada) y aplica el recalibrador → prob cruda y calibrada. Lo consume el CLI y el dashboard. |
| `statsbomb_data.py` | **Córners + tarjetas de selecciones** (perfiles StatsBomb). `predict_corners` / `predict_cards`. *Ojo: el modelo SOBREESTIMA tarjetas y córners en partidos desbalanceados* (confirmado en retro). |
| `linemate.py` | Cliente de la API pública de Linemate: cartelera del Mundial + trends de jugador/equipo (hit-rates por split). Solo **contexto**, nunca edge. |
| `calib.py` | Recalibrador (Platt) fiteado sobre `evaluations/` por `model_version`. Corrige la compresión de favoritos. Identidad si n < 40. |
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
- **Loop**: 272 evaluaciones reales acumuladas (ESPN), soccer + MLB. **Brier crudo ~0.213 / calibrado ~0.212**. 1X2 y doble oportunidad son los mercados mejor calibrados (Brier ~0.156); **córners y tarjetas los peores** (Brier ~0.33, sesgo al alza confirmado).
- **Recalibrador (Platt)**: fiteado para `soccer-v3` (a≈1.01, b≈+0.21 → estira, corrige la compresión de favoritos). Córners/tarjetas/MLB quedan en identidad hasta tener n ≥ 40 por familia.

## Estado y próximos pasos (retomar acá)

**Listo:** soccer selecciones (`soccer-v3`), MLB moneyline + su loop, córners/tarjetas de selecciones (StatsBomb), integración Linemate (contexto), recalibrador Platt, dashboard Mundial (`/api/wc/today`), loop de aprendizaje (log → eval vs ESPN → report → calibrate), infra de quota.

**Falta (orden recomendado):**
1. **Recalibrar córners/tarjetas aparte** — el modelo los sobreestima sistemáticamente (Brier ~0.33). Bajarles confianza o fitear su propio recalibrador cuando haya n ≥ 40.
2. **Totales de carreras MLB** — para que MLB tenga varios logros en el dashboard.
3. **NBA datos reales** (nba_api) · **NFL** (nfl_data_py).
4. **Corrección de calibración** (isotónica) — cuando haya volumen por familia de mercado.
5. Persistir la SQLite (hoy `:memory:`).

**Watch (no accionar aún):** córners y tarjetas tiran alto en partidos desbalanceados (confirmado en retro de selecciones); ya excluidos de los "picks confiables" en `analizar._picks`.
