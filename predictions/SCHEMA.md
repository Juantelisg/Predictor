# Predictions — schema y convenciones

Cada predicción se loguea como **una línea JSONL** en `predictions/YYYY-MM-DD.jsonl`. Una línea = una decisión del supra-agente (incluye los `PASAR` — son tan informativos como los `APOSTAR`).

## Por qué loguear todo

El meta-agente solo puede mejorar si tiene un registro completo de decisiones y resultados. Loguear únicamente las apuestas tomadas sesga la evaluación: no se puede saber si los `PASAR` fueron correctos.

## Schema

```jsonc
{
  "id": "pred_2026-05-05_lakers-celtics_ml_lakers",  // {timestamp_date}_{slug-match}_{market}_{selection}
  "timestamp_utc": "2026-05-05T19:32:11Z",
  "sport": "nba",
  "match": "Lakers vs Celtics",
  "event_id": "401234567",                            // ID del sport-skill (ESPN, etc.)
  "kickoff_utc": "2026-05-05T23:30:00Z",
  "bet_type": "moneyline",                            // moneyline | spread | total | prop | parlay | futures
  "selection": "Lakers ML",
  "line": null,                                        // ej. -3.5 para spread, 224.5 para total, 24.5 para prop
  "book_odds": -150,
  "book": "DraftKings",
  "book_format": "american",
  "book_implied_prob": 0.600,
  "fair_prob_devigged": 0.579,                        // tras betting devig
  "market_prob": 0.520,                                // polymarket / kalshi (null si no hay)
  "market_source": "polymarket",
  "model_prob": 0.595,                                 // probabilidad estimada por el supra-agente
  "edge": 0.075,                                       // model_prob - market_prob (o vs implied si no hay market)
  "edge_tier": "strong",                               // strong | moderate | pass
  "ev_per_unit": 0.144,
  "kelly_fraction_full": 0.156,
  "kelly_fraction_applied": 0.039,                     // tras quarter-Kelly + cap
  "stake_pct": 0.039,                                  // fracción del bankroll
  "stake_amount": 39.0,                                // calculado con bankroll de settings.json
  "confidence": "Alta",                                // Alta | Media | Baja
  "action": "APOSTAR",                                 // APOSTAR | PASAR
  "reasoning_summary": "Lakers en casa, oponente con back-to-back, ORtg favorable, prediction market subvalúa.",
  "signals": [
    { "name": "form_l5", "alignment": "✅", "note": "4-1 últimos 5" },
    { "name": "rest_advantage", "alignment": "✅", "note": "2 días vs 0" },
    { "name": "injuries", "alignment": "⚠️", "note": "AD probable, sin titulares clave fuera" },
    { "name": "line_movement", "alignment": "✅", "note": "abrió -135, cerró -150 (sharp money)" }
  ],
  "risks": [
    "Variancia alta en últimos 3 cuartos",
    "Árbitro con tendencia a faltas a Lakers"
  ],
  "raw_inputs": {
    "_comment": "Snapshot crudo de las llamadas a skills, para auditabilidad.",
    "espn_odds": { "...": "..." },
    "polymarket_price": 0.520,
    "team_stats": { "...": "..." }
  },
  "supra_agent_version": "0.1.0",
  "model_used": "claude-sonnet-4-6"
}
```

## Cómo escribir una entrada

Cuando produzcas un análisis con el skill `sports-betting-analyzer`, **además** del bloque markdown legible, agregá la línea JSONL al archivo del día:

```bash
# Bash
echo '<json line>' >> predictions/$(date -u +%Y-%m-%d).jsonl
```

```powershell
# PowerShell
$dateStr = (Get-Date).ToString("yyyy-MM-dd")
Add-Content -Path "c:\bets\predictions\$dateStr.jsonl" -Value '<json line>' -Encoding utf8
```

## Reglas

- **Una línea por decisión**, sin saltos de línea internos.
- **Timestamps siempre UTC** (`Z` sufijo).
- **`action: "PASAR"` también se loguea** — con `edge_tier: "pass"` o `confidence: "Baja"` y razón.
- **`raw_inputs`** debe contener al menos las odds y la market_prob. No es necesario volcar todos los stats; sí los más relevantes que sostuvieron la decisión.
- **Nunca editar líneas viejas.** Si una predicción se invalida (ej. cancelación del partido), agregar una nueva entrada con `bet_type: "void"` y `parent_id` apuntando a la original.
