# Evaluations — schema y convenciones

Cada predicción resuelta se loguea como **una línea JSONL** en `evaluations/YYYY-MM-DD.jsonl`. La fecha del archivo es la fecha de **resolución** (no la fecha de la predicción).

## Por qué este archivo existe

Sin esto el meta-agente no puede aprender. La calibración (¿cuando digo 60% gano efectivamente ~60% del tiempo?) y el realized edge (¿el edge teórico se materializa en PnL?) viven acá.

## Schema

```jsonc
{
  "prediction_id": "pred_2026-05-05_lakers-celtics_ml_lakers",
  "evaluated_at_utc": "2026-05-06T03:15:00Z",
  "resolution": "won",                          // won | lost | push | void
  "actual_score": "Lakers 118 — Celtics 110",
  "outcome_binary": 1,                           // 1 si la selección ganó (para calibración), 0 si perdió, null si push/void
  "stake_pct": 0.039,
  "pnl_units": 0.026,                            // ganancia/pérdida en fracción del bankroll
  "pnl_amount": 26.0,
  "edge_realized": null,                         // se calcula por cohortes en reportes, no acá
  "calibration_error": 0.405,                    // |model_prob - outcome_binary|; menor es mejor
  "notes": "Cumplió: home advantage + rest. AD jugó 32 min sin issues.",
  "tags": ["home_favorite", "rest_advantage", "sharp_line_move"]
}
```

## Cómo evaluar

Cuando un partido cierra:

1. Releer la predicción del archivo `predictions/YYYY-MM-DD.jsonl`.
2. Confirmar el resultado real (via `nba-data get_game_summary`, `mlb-data get_game_summary`, etc.).
3. Calcular:
   - `outcome_binary` = 1 si la selección ganó, 0 si perdió, null si push.
   - `pnl_units`:
     - Si `won`: `stake_pct * (decimal_odds - 1)` (de `book_odds`).
     - Si `lost`: `-stake_pct`.
     - Si `push` o `void`: `0`.
   - `calibration_error`: `abs(model_prob - outcome_binary)`.
4. Agregar `notes` cortas (qué cumplió / qué falló respecto a la tesis original).
5. Agregar `tags` consistentes para análisis por cohorte (ver lista canónica abajo).

## Tags canónicos

Mantener este set chico y consistente. Se usan para slicing en reportes.

**Situacionales**: `home_favorite`, `road_underdog`, `back_to_back`, `rest_advantage`, `divisional_game`, `revenge_spot`, `playoff_implications`, `lookahead_spot`.

**Datos / mercado**: `sharp_line_move`, `reverse_line_move`, `public_heavy`, `low_liquidity_pred_market`, `polymarket_disagreed`, `injury_news_late`.

**Tipo de bet**: `moneyline`, `spread`, `total_over`, `total_under`, `player_prop`, `team_prop`, `parlay`.

**Resultado vs tesis**: `thesis_held`, `thesis_partial`, `thesis_failed`, `variance_loss` (perdió por variancia, no por error de modelo), `variance_win` (ganó pese a tesis débil).

## Reglas

- **No editar predicciones** al evaluarlas — se preserva el registro original.
- **No reportar PnL acumulado en este archivo** — eso vive en `reports/`.
- **`variance_win` / `variance_loss`** son honestos: marcarlos para no felicitarse por suerte ni castigarse por mala suerte.
