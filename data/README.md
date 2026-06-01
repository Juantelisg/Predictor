# Data — caching layer

Cache local de odds y stats fetcheados desde APIs / skills, para no consumir quota innecesario.

## Estructura

```
data/
├── odds/
│   └── YYYY-MM-DD/
│       ├── nba/
│       │   ├── {event_id}.json
│       │   └── ...
│       └── mlb/
│           └── ...
└── stats/
    └── {sport}/
        ├── {team_id}_team_stats.json
        ├── {player_id}_player_stats.json
        └── ...
```

## Política de caché

- **Odds**: TTL 15 min (configurable en `config/settings.json`). Líneas se mueven; cachear más es peligroso.
- **Stats de temporada**: TTL 24h. No cambian intra-día salvo por nuevos juegos.
- **Stats de partido (game summary)**: una vez completo, **nunca expira** — son históricos.
- **Schedules**: TTL 6h.

## Reglas

- **No comitear** este directorio (está en `.gitignore`). Es ephemeral.
- Si una predicción usó datos cacheados, el `raw_inputs` de la predicción referencia el path del archivo cacheado para auditoría.
- Si el cache TTL expiró, el supra-agente debe re-fetchear antes de tomar decisión nueva.
