---
name: sports-betting-analyzer
description: |
  Narrative + situational layer for sports-betting analysis — spreads, totals (over/unders), prop bets, historical trends, situational stats, and value-bet identification with reasoning. Synthesizes outputs from `betting` (math), `markets` (cross-platform odds), and sport-specific data skills (`nba-data`, `mlb-data`, `football-data`, `polymarket`) into a structured pick or pass with confidence and risk flags. For entertainment / educational analysis only.

  Use when: user asks for a full bet analysis (spread / total / prop / moneyline) and wants reasoning, not just numbers; user wants prop-bet value identification; user wants a situational read (rest, travel, injuries, motivation, weather, line movement); user wants the final structured pick with stake recommendation and risk callouts; user asks "should I bet X?" or "is there value on Y?".
  Don't use when: user only wants raw odds math (use `betting`), live scores (use the sport skill), or prediction-market quotes (use `polymarket` / `markets`). Don't use as a fetcher — it consumes other skills' outputs.
license: MIT
metadata:
  author: bets-supra-agent
  version: "0.1.0"
---

# Sports Betting Analyzer

Synthesis layer that turns raw odds, stats, and prediction-market prices into a structured value-bet evaluation. **This skill does not fetch data.** It composes the outputs of `betting`, `markets`, and the sport-specific skills.

## Position in the pipeline

```
[fetch]   nba-data / mlb-data / football-data / polymarket / markets
   │
   ▼
[math]    betting   (devig, edge, Kelly, parlay, line_movement)
   │
   ▼
[analysis]  sports-betting-analyzer   ← THIS SKILL
            (situational read, prop bets, narrative,
             cross-validation, final pick / pass)
```

## CRITICAL: Before producing any analysis

CRITICAL — verify before you write a pick:

- **Odds are de-vigged.** Sportsbook quotes (American odds) MUST pass through `betting devig` before any edge math. Never compare raw -110/-110 prices directly to a market probability.
- **At least two independent signals agree.** A pick needs (a) a probability source (model, prediction market, or de-vigged odds) AND (b) a corroborating signal (recent form, advanced stat, line movement, injury context). One signal is a hunch, not a pick.
- **Edge tier is computed, not asserted.** Use the canonical thresholds:
  - `EDGE > 5%` → strong value
  - `EDGE 2-5%` → moderate value
  - `EDGE < 2%` → pass (do not recommend)
- **Stake comes from Kelly, not gut.** Use `betting kelly_criterion` and apply quarter-Kelly by default for conservative sizing.
- **Disclaimer is included.** Every output ends with the responsible-gambling note.

## Inputs the analysis consumes

| Source | Provided by | What it yields |
|---|---|---|
| ESPN moneyline / spread / total | `nba-data` `get_scoreboard`, `mlb-data` `get_scoreboard`, `football-data` `get_event_*`, or `markets get_todays_markets` | Sportsbook odds (American) |
| Prediction-market price | `polymarket search_markets` / `markets compare_odds` | 0–1 probability |
| Advanced stats | `nba-data get_team_stats`, `mlb-data get_team_stats`, `football-data get_event_xg`, `get_event_statistics` | xG, pace, ORtg, ERA/WHIP, etc. |
| Injuries / availability | `nba-data get_injuries`, `mlb-data get_injuries`, `football-data get_missing_players` | Roster gaps |
| Line movement | `markets compare_odds` (open vs current) or manual open/close odds | Sharp action signal |
| Edge / Kelly | `betting evaluate_bet`, `betting kelly_criterion` | EV%, Kelly fraction |

## Workflow

1. **Identify the bet type**: moneyline, spread, total, prop (player/team), parlay, futures.
2. **Fetch real data** via the appropriate skill — never assume odds or stats.
3. **Compute fair probability**:
   - From prediction market (`polymarket` price) — already de-vigged.
   - OR from de-vigged sportsbook odds (`betting devig`).
   - OR from a custom heuristic (stat-based) if neither market is reliable.
4. **Compute edge**: `betting find_edge` or `betting evaluate_bet`.
5. **Situational cross-validation**: form, injuries, rest, travel, motivation, weather (outdoor sports), referee tendencies, line movement.
6. **Classify edge tier** (strong / moderate / pass).
7. **Compute stake**: quarter-Kelly default, capped at 2% of bankroll for moderate-edge picks and 4% for strong-edge picks.
8. **Write the structured output** (template below).
9. **Log the prediction** to `predictions/` so the meta-agent can score it later.

## Output Format (canonical)

Every analysis ends in this structure. Markdown only — no extra prose around it.

```markdown
# Pick — {match} — {market} — {selection}
**Generated**: {YYYY-MM-DD HH:mm} | **Sport**: {nba|mlb|epl|...} | **Bet type**: {moneyline|spread|total|prop|parlay}

## Datos objetivos
- **Odds (sportsbook)**: {american odds} ({book})
- **Probabilidad implícita (de-vigged)**: {x.x%}
- **Probabilidad de mercado (prediction market)**: {x.x%} ({polymarket|kalshi})
- **Stats clave**:
  - {metric 1}: {value}
  - {metric 2}: {value}

## Inferencia (modelo)
- **Probabilidad estimada**: {x.x%}
- **Justificación**:
  - {one-line reason 1, tied to a stat}
  - {one-line reason 2, tied to a stat}
- **Edge**: {x.x%}  → tier: {strong|moderate|pass}
- **EV por unidad**: {+x.x%}

## Validación cruzada
- {signal 1: ✅ alineado | ⚠️ mixto | ❌ contrario} — {one-line explanation}
- {signal 2: ...}
- {signal 3: ...}

## Riesgos
- {top risk 1}
- {top risk 2}

## Decisión
- **Confianza**: {Alta | Media | Baja}
- **Stake sugerido**: {x.x}% del bankroll (quarter-Kelly{; capped at 2%/4%})
- **Acción**: {APOSTAR | PASAR}

---
*Análisis con fines educativos / de entretenimiento. Apostar implica riesgo de pérdida total. Solo arriesgar capital cuya pérdida sea aceptable. Si el juego deja de ser entretenimiento, busca ayuda.*
```

## Examples

**Example 1 — NBA moneyline value check**
User: "¿Hay valor en Lakers ML hoy?"
Actions:
1. `nba-data get_scoreboard` → find Lakers game, ESPN odds Lakers `-150` / opponent `+130`.
2. `polymarket search_markets sport=nba query=Lakers sports_market_types=moneyline` → Lakers price `0.52`.
3. `betting evaluate_bet book_odds=-150,+130 market_prob=0.52` → fair home `0.579`, edge `5.9%`, Kelly `0.123`.
4. `nba-data get_injuries` filter Lakers → check status.
5. `nba-data get_team_stats` Lakers + opponent → ORtg, DRtg, pace.
6. Cross-validate: form (last 5), home/road splits, rest days.
7. Classify edge as **strong** (>5%), confianza **Alta** if all signals align.
8. Stake: quarter-Kelly = `0.123 / 4 = 3.1%` → capped at 4% (strong tier) → **stake 3.1%**.
9. Write the canonical output block.

**Example 2 — MLB total (over/under)**
User: "¿Over 8.5 en el Yankees-Red Sox?"
Actions:
1. `mlb-data get_scoreboard` → find game, total line `8.5`, over `-115` / under `-105`.
2. `betting devig odds=-115,-105` → fair over `0.535`.
3. `mlb-data get_team_stats` both teams → recent runs scored / allowed, OPS, ERA.
4. `mlb-data get_injuries` → check starting pitchers' status.
5. Weather (if outdoor) — wind direction matters for totals at certain parks (note as a manual lookup if the skill doesn't expose it).
6. Compute model probability from offensive metrics + park factor.
7. Compare to fair `0.535`, classify edge.
8. Output canonical block.

**Example 3 — Prop bet (player points)**
User: "LeBron over 24.5 puntos, ¿vale?"
Actions:
1. `nba-data get_player_stats` LeBron season + last 10 games.
2. ESPN prop line + odds (manual — props vary by book).
3. `nba-data get_team_stats` opponent → DRtg, defensive rating vs position.
4. Check usage rate, rest, recent minutes trend.
5. Build empirical distribution from last 10–20 games, compute P(>24.5).
6. De-vig prop and compute edge.
7. Output canonical block; flag as **prop bet — higher variance**.

**Example 4 — Pass (no edge)**
User: "¿Apuesto el Madrid?"
Actions:
1. Fetch all the inputs above.
2. Edge ends up `1.4%` — below 2% threshold.
3. Output: **Acción: PASAR**, with edge tier `pass` and brief explanation. Do not invent a justification to force a pick.

## Commands that DO NOT exist — never call these

This skill has no CLI — it is an analysis pattern. If you need:
- Math → call `betting` commands.
- Odds → call `markets` / `polymarket` / sport-specific skills.
- Live scores → call sport-specific skills.

Do not invent commands like `analyze_bet`, `evaluate`, or `recommend`.

## Best Practices

1. **Quant, not tipster.** Numbers drive the pick. Narrative explains the numbers — it does not replace them.
2. **Pass is a valid output.** Most games have no edge. Forcing picks is the failure mode.
3. **Separate facts from inferences from decisions** in the output, exactly as the template demands.
4. **Always log the prediction** with a timestamp, market state, and your estimated probability — the meta-agent needs this to score you later.
5. **Use quarter-Kelly by default.** Half-Kelly only when the edge has been validated multiple times historically. Never full Kelly.
6. **Disclaimer is mandatory.** Every output.

## Troubleshooting

- *Edge looks impossibly large (>15%)*: re-check that the sportsbook odds were de-vigged and that fair_prob and market_prob were not swapped.
- *Polymarket and de-vigged ESPN disagree heavily (>10pp)*: trust neither in isolation — investigate (stale data on one side, low liquidity, late-breaking news). Likely **pass**.
- *Prop bet variance is huge*: drop one Kelly tier and lower stake cap to 1% of bankroll.
- *No prediction-market price available*: use de-vigged sportsbook as fair probability and only flag as moderate edge max — without a second probability anchor, confidence cannot be high.
