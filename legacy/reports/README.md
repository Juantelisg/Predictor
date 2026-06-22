# Reports

Síntesis periódica del desempeño del supra-agente. Estos reportes los genera el meta-agente leyendo `predictions/` + `evaluations/`.

## Cadencia

| Reporte | Archivo | Cuándo |
|---|---|---|
| Diario | `reports/daily/YYYY-MM-DD.md` | Al final del día deportivo (cuando todas las predicciones del día se evaluaron) |
| Semanal | `reports/weekly/YYYY-Www.md` (ISO week) | Lunes UTC |
| Mensual | `reports/monthly/YYYY-MM.md` | Día 1 de cada mes UTC |

## Qué contiene cada reporte

```markdown
# Report — {período}

## Volumen
- Predicciones totales: X (Y APOSTAR / Z PASAR)
- Por sport: {nba: X, mlb: Y, ...}
- Por bet type: {moneyline: X, total: Y, prop: Z, ...}

## PnL
- Stake total: X.X% del bankroll
- PnL acumulado: +/- X.X% del bankroll
- ROI: +/- X.X%

## Calibración
- Buckets de probabilidad (0-10%, 10-20%, ..., 90-100%):
  - Predicho: 60-70% → real: XX.X% (n=Y)
  - ...
- Brier score: X.XXX
- Log loss: X.XXX

## Edge realized vs predicted
- Edge promedio predicho (solo APOSTAR): X.X%
- Edge promedio realizado: X.X%
- Gap: X.X% (positivo = sub-estimamos; negativo = sobreestimamos)

## Cohortes (por tag)
- `sharp_line_move` (n=X): WR Y%, ROI Z%
- `home_favorite` (n=X): WR Y%, ROI Z%
- `polymarket_disagreed` (n=X): WR Y%, ROI Z%
- ...

## Errores recurrentes
- {patrón 1 detectado, ej. "sub-estimamos under en MLB outdoor con viento <5mph"}
- {patrón 2, ...}

## Ajustes propuestos para el próximo ciclo
- {ajuste 1: ej. "subir peso de rest_advantage en NBA"}
- {ajuste 2: ej. "evitar player props con line < -130 — variancia mata el EV"}
```

## Reglas

- **Honestidad calibracional > narrativa.** Si el modelo pierde dinero, el reporte lo dice claro. No se reescribe el pasado.
- **Sample size matters.** Cohortes con `n < 10` se reportan con un flag `(low n)` y no se sacan conclusiones fuertes.
- **Variance is real.** Brier y calibración son más confiables a corto plazo que ROI. ROI requiere n>50 para significar algo.

## Convenciones

- Reports en markdown, lectura humana.
- Datos derivados: si necesitás raw, parsea los JSONL de `predictions/` + `evaluations/` directamente.
