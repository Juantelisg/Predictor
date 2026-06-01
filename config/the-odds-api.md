# The Odds API — guía de uso

The Odds API es una API HTTP simple que devuelve odds en tiempo real de múltiples sportsbooks. **No hay skill instalada**: se consume con `curl` o `Invoke-RestMethod`.

## Setup

1. Registrarse en <https://the-odds-api.com/> y obtener API key.
2. Copiar `.env.example` a `.env` y rellenar `THE_ODDS_API_KEY`.
3. **No comitear `.env`** — el archivo está en `.gitignore`.

## Endpoints clave

| Endpoint | Para qué |
|---|---|
| `GET /v4/sports` | Lista de sports disponibles (claves: `basketball_nba`, `baseball_mlb`, `soccer_epl`, ...) |
| `GET /v4/sports/{sport}/odds` | Odds activas para todos los partidos del sport |
| `GET /v4/sports/{sport}/scores` | Scores y status |
| `GET /v4/sports/{sport}/events/{event_id}/odds` | Odds de un partido específico (incluye props) |

Parámetros usuales:
- `regions=us,us2,eu,uk` — qué casas devolver
- `markets=h2h,spreads,totals` — moneyline / spread / total
- `oddsFormat=american` — `american` o `decimal`
- `bookmakers=draftkings,fanduel,pinnacle` — filtrar por casa

## Quick check (PowerShell)

```powershell
$apiKey = (Get-Content c:\bets\config\.env | Select-String "^THE_ODDS_API_KEY=").ToString().Split("=")[1]
$url = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds?apiKey=$apiKey&regions=us&markets=h2h&oddsFormat=american"
Invoke-RestMethod -Uri $url | ConvertTo-Json -Depth 6
```

## Quick check (bash)

```bash
source c:/bets/config/.env
curl -s "https://api.the-odds-api.com/v4/sports/basketball_nba/odds?apiKey=$THE_ODDS_API_KEY&regions=us&markets=h2h&oddsFormat=american" | jq
```

## Cuotas

- Cada llamada cuenta contra el quota mensual.
- Header `x-requests-remaining` indica cuántas llamadas quedan.
- **Cachear**: ver `data/odds/` (TTL 15 min por defecto en `settings.json`).

## Cuándo usar The Odds API vs skills

- **The Odds API** → odds multi-book con un solo request, ideal para *line shopping* y detectar la mejor cuota disponible.
- **`markets` skill** → cuando querés combinar ESPN + Polymarket + Kalshi en un dashboard.
- **`polymarket` skill** → solo prediction markets.
- **`nba-data` / `mlb-data` / `football-data`** → para stats y contexto, **no** para odds line-shopping.
