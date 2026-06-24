# Reporte de viabilidad — Señal "smart money" de Polymarket como input del modelo

> **Para el supra-agente de `C:\bets`.** Este documento te pide que analices la **viabilidad**
> de incorporar, como un input más del pipeline, los **movimientos de los perfiles deportivos más
> exitosos de Polymarket** (los top del leaderboard filtrado por deportes). No te pide que lo
> construyas: te pide que decidas, con la honestidad calibracional de siempre, si vale la pena
> y, si vale, **dónde exactamente encaja** sin romper los guardrails del proyecto.
>
> Toda la funcionalidad descripta **ya existe y corre** en otro proyecto del usuario (`C:\polybot`,
> un bot de copy-trading). Acá está destilado lo reutilizable + los hallazgos empíricos que ya
> se pagaron con tiempo y plata real. Las rutas de archivo apuntan a código verificado al
> 2026-06-24.

---

## 0. TL;DR (veredicto preliminar — confirmalo o refutalo vos)

- **La idea es sólida en concepto, pero el lugar donde la metas decide si suma o contamina.**
- La señal correcta a extraer NO es "copiá su trade" (eso ya se probó y **pierde**: el timing se
  come el edge, 7/7 sims reales perdieron). La señal es **"el dinero inteligente está posicionado
  del lado X en este partido, con qué convicción y desde cuándo"** — un análogo de *sharp money /
  line movement*, que tu CLAUDE.md **ya trata como señal canónica** (paso 4, validación cruzada).
- **Recomendación de encuadre:** entra como **señal corroboratoria del paso 4**, NO como feature
  del motor de `model_prob` (paso 2). Meterla en el motor viola tu guardrail anti-circular
  ("las cuotas/precios son insumo de VALOR, nunca feature del modelo") porque el precio de
  Polymarket **ya está adentro** de tu pipeline como ancla de probabilidad.
- **El bloqueante real para validarla es el backtest:** Polymarket **da de baja los mercados al
  resolverse**, así que no hay histórico reconstruible. Sólo se puede validar **forward** (loguear
  hoy, evaluar al cierre). Eso choca con tu regla "forward-test antes de confiar" — no la rompe,
  pero implica una **pista de despegue de semanas** antes de que puedas pesarla.
- **Costo de entrada técnico: bajo.** Todo es API REST pública (sin auth, sin scraping, sin
  fondos). Las funciones ya están escritas en `C:\polybot` y se portan casi tal cual.
- **La pregunta que tenés que responder está en la §5.** Todo lo de arriba es contexto para
  poder contestarla.

---

# PARTE A — Qué hace la funcionalidad hoy (en Polybot)

## A.1. Qué es

Polybot consulta el **leaderboard de Polymarket filtrado por deportes**, identifica las wallets
top, y lee la **actividad reciente** de cada una para detectar sus operaciones. No scrapea HTML:
**consume las APIs REST oficiales de Polymarket** (Data API + Gamma API), todas públicas y sin
autenticación. El nombre interno "scraper" es engañoso — es un **API client con polling**.

## A.2. Las dos llamadas centrales

### (1) Leaderboard de deportes
```
GET https://data-api.polymarket.com/v1/leaderboard
    ?category=SPORTS      # SPORTS | POLITICS | CRYPTO | OVERALL | ...
    &timePeriod=ALL       # DAY | WEEK | MONTH | ALL
    &orderBy=PNL          # PNL | VOL
    &limit=50             # tope duro del endpoint: 50
```
Devuelve, por wallet:

| Campo crudo | Significado | Ojo |
|---|---|---|
| `proxyWallet` | address (la clave) | — |
| `userName` | alias legible (puede venir vacío) | — |
| `pnl` | PnL acumulado en USD | ordena el ranking |
| `vol` | volumen operado en USD | — |

**No trae** ROI, win-rate, trade-count ni avg-size. Esos se **derivan aparte** (Polybot los
calcula en su capa de scoring — ver A.5).

### (2) Actividad de una wallet
```
GET https://data-api.polymarket.com/activity?user={address}&limit={n}
```
Devuelve una lista de eventos; se filtra `type == "TRADE"`. Por trade:

| Campo crudo | Mapea a | Notas |
|---|---|---|
| `asset` | `token_id` | identifica el outcome (YES/NO de un mercado) |
| `conditionId` | `condition_id` | identifica el mercado |
| `side` | `BUY` / `SELL` | **98% son BUY** (ver A.6) |
| `usdcSize` | tamaño en USD | proxy de convicción |
| `price` | precio de entrada (0–1 = prob implícita) | **= probabilidad** |
| `outcome` | "YES"/"NO" o el equipo | — |
| `title` | pregunta del mercado | ej. "Lakers vs Celtics" |
| `slug` | slug del mercado | usado para clasificar deporte |
| `timestamp` / `createdAt` | momento del trade | clave para "¿entró antes que la línea?" |

### (3) Posiciones abiertas de una wallet (opcional, útil)
```
GET https://data-api.polymarket.com/positions?user={address}&limit=500
```
Da el **estado de cartera** (no el flujo): `asset`, `title`, `slug`, `outcome`, `size`,
`avgPrice`, `curPrice`, `currentValue`, `cashPnl`, `percentPnl`, `endDate`, `redeemable`.
Sirve para preguntar "¿qué tiene puesto **ahora** el dinero inteligente en el partido de hoy?"
sin reconstruirlo desde el flujo de actividad.

## A.3. Metadata de mercado + clasificación de deporte (Gamma API)

Para saber a qué **deporte y partido** corresponde un `token_id`:
```
GET https://gamma-api.polymarket.com/markets?clob_token_ids={token_id}&include_tag=true
GET https://gamma-api.polymarket.com/events?slug={slug}      # respaldo para tags
```
Devuelve `conditionId`, `slug`, `question`, `endDate`, `liquidity`, `lastTradePrice`, y
—lo importante— las **tags del evento padre** (`['Soccer']`, `['NBA']`, …).

**Esto es más fiño de lo que parece y ya costó una reescritura.** En Polybot, clasificar por
slug/título dejaba **~72% de los mercados en `sport=NULL`**. El fix fue clasificar por las **tags
del evento padre** (que Polymarket mantiene confiables), con el slug como último respaldo:

- `_sport_from_tags(tags)` → mapea tags a deporte vía `_TAG_TO_SPORT`
  (`soccer→soccer, nba→NBA, wnba→WNBA, mlb→MLB, nfl→NFL, nhl→NHL`).
- `_event_tags(market)` → lee tags inline (requiere `include_tag=true`).
- `_fetch_event_tags(market)` → respaldo: pide `/events?slug=` cuando las inline vienen vacías
  (pasa con fútbol: el param `include_tag` es inconsistente entre deportes).
- `_sport_from_slug(slug, question)` → último respaldo por prefijos (`nba-`, `mlb-`, …).

Verificado 12/12 en vivo tras el fix. **Si portás esto, traete las 4 funciones, no reinventes
el clasificador.**

## A.4. Resiliencia y límites

- **Retry:** todas las llamadas pasan por un `_get()` con reintento exponencial (0.5s, 1s) ante
  `ConnectionError`/`Timeout`.
- **Rate limit:** Data API = **1000 req / 10s**, y es **throttle, no ban** (doc oficial). Para
  consultar ~10–50 wallets una vez por slate, es trivial.
- **Red:** la **red universitaria del usuario bloquea todas las APIs de Polymarket**. Red
  doméstica / hotspot funciona sin VPN. (Dato operativo, no de código.)
- **Sin auth, sin fondos, sólo lectura.** Nada de esto toca la CLOB API de escritura ni claves
  privadas. (La parte de *ejecución* de Polybot está rota por la migración CLOB V2 de Polymarket
  — **irrelevante para vos**: vos sólo leés.)

## A.5. Cómo se rankean las wallets (capa de scoring de Polybot)

El leaderboard sólo ordena por PnL bruto. Polybot re-rankea las 50 con un score compuesto
(`mvp2_auditor/scorer.py` → `score_wallet(pnl, vol, age)`), y para auditoría más profunda calcula
sobre la actividad histórica: **ROI específico en sports, Brier score (calibración del trader),
max drawdown, win-rate, antigüedad**. El Brier del trader es especialmente relevante para vos:
mide si el tipo tiene **edge real o tuvo suerte** (si compra YES a 0.80 y eso pasa el 80% de las
veces → calibrado; si pasa el 55% → no tiene info). Un trader bien calibrado es una señal de más
calidad que uno con PnL alto pero ruidoso.

## A.6. Hallazgos empíricos ya pagados (críticos para tu análisis)

Estos datos salieron de operar/simular en serio. **Léelos como evidencia, no como opinión:**

1. **Política de los cracks = comprar y aguantar.** Sobre 10 top traders sports / 2699 trades:
   **~98% BUY, ~2% SELL**, esencialmente **hold hasta la resolución**. No tradean los vaivenes del
   partido. → La señal explotable es **la entrada direccional** (de qué lado y con cuánto), no un
   patrón de salida.

2. **Copiar al precio del trader rinde +46% ROI optimista… pero se desarma al desagregar.**
   Backtest sobre 235 BUYs clasificados: **fútbol (94 trades, el grueso del volumen) PIERDE −29%**.
   Los positivos (MLB +162%, WNBA +97%) son **cola de alta varianza en muestras chicas** (un par de
   longshots). No hay edge estable por deporte en esa muestra.

3. **El timing mata el copy-trade, pero NO mata la señal predictiva.** Las 7 sims reales (entrada
   a precio de mercado, ya movido por el trader) perdieron **7/7**. El gap entre el +46% optimista
   y el resultado real perdedor **es el costo de copiar tarde**. → Para *apostar copiando* no sirve.
   **Pero vos no querés ejecutar a su precio**: querés saber **si su posicionamiento predice el
   resultado**. Ese problema de latencia **te es indiferente**.

4. **Backtest histórico = casi imposible.** Polymarket **da de baja los mercados al resolverse**
   (probado: 19/20 mercados de un mes atrás devolvían vacío). No se puede reconstruir un dataset
   histórico de "qué tenían puesto y cómo salió". **Sólo forward-test.** Este es, de lejos, el
   mayor obstáculo para validar la señal con tus estándares.

---

# PARTE B — Qué necesitás para traer esto a `C:\bets`

## B.1. Dependencias

| Recurso | Estado |
|---|---|
| `requests` | **Ya lo tenés.** Es lo único que usa el cliente. |
| Librería de scraping (bs4/selenium/…) | **No hace falta nada.** Es API REST + JSON. |
| Auth / API key / wallet | **Nada.** Data API y Gamma API son públicas. |
| `cache.py` (TTL en `data/cache/`) | **Ya lo tenés.** Reusalo para no martillar la API. |
| Python real | `C:/Users/Juant/AppData/Local/Python/bin/python.exe` (el de siempre). |

## B.2. Código reutilizable (portar desde `C:\polybot\core\polymarket.py`)

Todo esto está escrito, probado y se copia casi tal cual a un módulo nuevo (sugerido:
`predictor/polymarket_signal.py`):

| Función | Qué hace | Línea aprox. |
|---|---|---|
| `_get(base, path, params)` | GET con retry exponencial | `polymarket.py:12` |
| `get_leaderboard(limit, category, time_period, order_by)` | top wallets sports | `:36` |
| `get_wallet_activity(address, limit)` | trades recientes (flujo) | `:114` |
| `get_wallet_activity_audit(address, limit=500)` | versión profunda con timestamp | `:75` |
| `get_user_positions(address, only_open=True)` | cartera actual (estado) | `:266` |
| `get_market_info(token_id)` | metadata + deporte de un mercado | `:142` |
| `_event_tags` / `_fetch_event_tags` / `_sport_from_tags` / `_sport_from_slug` / `_TAG_TO_SPORT` | **clasificador de deporte** (no reinventar) | `:441–503` |

Y de `C:\polybot\mvp2_auditor\scorer.py`: `score_wallet()` y la lógica de **Brier del trader**,
si querés ponderar wallets por calidad en vez de por PnL bruto.

Hay un script de referencia listo para leer, `C:\polybot\_lb.py` (~20 líneas): pide el top 50 y
lo imprime re-rankeado por score. Es el "hello world" de esta señal.

> **Gotchas a corregir al portar** (ya detectados): (a) `_fetch_event_tags` tiene un **typo de
> ruta**: usa `"\events"` (backslash) en vez de `"/events"` — corregilo o el respaldo de tags
> falla silencioso. (b) Consola Windows cp1252: nada de emojis/`≥·→` en `print` (ya lo sabés).
> (c) timestamps de Polymarket vienen en **segundos Unix** → ×1000 para JS / `datetime.utcfromtimestamp` para Python.

## B.3. La pieza que NO existe y tenés que construir: matching mercado ↔ partido

Polybot nunca necesitó cruzar un mercado de Polymarket con "tu" partido del slate — sólo seguía
wallets. Vos sí. El puente es:

```
partido del slate (bets)  ⟷  mercado de Polymarket
  ej. "Lakers @ Celtics"  ⟷  title="Lakers vs Celtics", slug="nba-lal-bos-2026-06-24"
```

Necesitás **normalización de nombres de equipo** (Polymarket usa nombres/slug propios) + match por
**deporte + fecha + equipos**. Tenés precedente directo en el proyecto: ya resolvés colisiones de
matchup en `scan.py` (series multi-día → `commence_time` más cercano) y ya elegís "el mercado de
Polymarket de mayor liquidez" descartando los duplicados muertos (liq ~$50). Esta es la misma clase
de problema. **Es el grueso del trabajo de integración**, no la consulta a la API.

## B.4. Recursos de datos por consulta (presupuesto)

Para un slate típico:
- 1 llamada de leaderboard (50 wallets).
- N llamadas de actividad/posiciones (1 por wallet que decidas seguir; con 10–20 alcanza).
- M llamadas de Gamma para clasificar/ubicar mercados (cacheables 7 días: los mercados no cambian
  de deporte).

Total: **decenas de requests por slate**, muy por debajo del límite (1000/10s). Con `cache.py`
(TTL corto para actividad, largo para metadata de mercado) queda holgado.

---

# PARTE C — Dónde encaja en TU arquitectura (lo más importante)

Tu pipeline tiene 5 pasos. **Dónde inyectes esta señal cambia si suma o si te contamina.**

### Opción 1 — Como feature del motor (`model_prob`, paso 2). ❌ Desaconsejada.
Meter "smart money está en YES a 0.78" como input de tu probabilidad propia. **Rompe el guardrail
anti-circular** de tu CLAUDE.md: el precio de Polymarket ya entra a tu pipeline como **ancla de
probabilidad** (paso 2b) y como **prediction-market en la validación cruzada** (paso 4). Sumar el
posicionamiento del que mueve ese precio es **predecir al mercado con el mercado** → inflás falsa
confianza y rompés la calibración. No lo hagas.

### Opción 2 — Como señal corroboratoria del paso 4 (validación cruzada). ✅ Recomendada.
Tu paso 4 **ya** exige ≥2 señales independientes y **ya** lista como canónicas "line movement /
sharp action" y "prediction market vs sportsbook". El smart money de Polymarket es exactamente eso:
una variante de **sharp action con identidad y track-record**. Se modela como una señal más:

- **✅ alineada** — el dinero inteligente está del lado de tu edge, con tamaño y/o entró **antes**
  de que se moviera la línea del book.
- **⚠️ mixta** — posicionamiento dividido o de baja convicción / liquidez.
- **❌ contraria** — el dinero inteligente está del **otro** lado de tu edge (señal de freno
  potente: puede que sepan algo que tu modelo no).

Esto respeta todos tus guardrails: no toca `model_prob`, no es circular, y aporta justo donde tu
arquitectura ya espera corroboración independiente.

### Opción 3 — Como *meta-feature* del loop de calibración (cohort tag). ✅ Complementaria.
Logueá en cada predicción un tag tipo `smart_money_aligned` / `smart_money_contra` y dejá que tu
`feedback.py` / análisis de cohortes mida **si las predicciones donde el smart money concordaba
calibran mejor o rinden más**. Esto es lo que convierte la corazonada en evidencia, con tu propia
maquinaria. **Cero costo de circularidad** (es post-hoc, no entra al pricing).

> **Qué información NUEVA aporta (más allá del precio que ya ves):** identidad y **calibración del
> trader** (Brier), **convicción** (tamaño relativo a su histórico), y **timing** (¿entró antes que
> el book?). El precio crudo de Polymarket no carga nada de eso. Si la señal agrega valor, va a ser
> por **una de esas tres dimensiones ortogonales al precio**, no por el precio en sí.

---

# PARTE D — Análisis de viabilidad (balance honesto)

### A favor
- **Costo técnico bajo:** API pública, sin auth, sin scraping, código ya escrito y probado.
- **Encaje arquitectónico limpio:** hay un slot natural (paso 4) que no viola guardrails.
- **El defecto fatal del copy-trade (timing) no aplica** a un uso de señal predictiva.
- **Aporta dimensiones ortogonales al precio** (calibración del trader, convicción, timing) —
  *si* resultan informativas.
- **Sports es el nicho donde tu propio proyecto dice que está el edge** (líneas stale, props,
  discrepancias cross-platform). El smart-money posicionado temprano es un candidato a esa familia.

### En contra / riesgos
- **Validación sólo forward.** Sin histórico (mercados delistados al resolver) no podés backtestear.
  Tu cultura es "lo que no se midió no existe" y "forward-test antes de confiar" → **vas a estar
  semanas logueando antes de poder pesarla**. No es un no, es un "lento".
- **Posible redundancia con el precio.** Si su compra ya movió el precio, su info ya está en tu
  ancla de prob. Hay que demostrar que el posicionamiento agrega **algo más** (timing/identidad), no
  re-empaquetarlo.
- **Evidencia de copy-trade negativa en el grueso del volumen.** Fútbol (el deporte con más trades)
  rindió −29% al copiar. Aunque tu uso es distinto, es una bandera amarilla de que **el edge
  direccional crudo de estos traders no es robusto** — al menos no en fútbol, que probablemente sea
  tu mayor volumen de slate.
- **Cobertura despareja:** Polymarket tiene buena liquidez en algunos partidos y mercados muertos
  (~$50) en otros. Para muchos partidos del slate puede no haber un mercado deportivo útil. La señal
  va a ser **intermitente**, no universal.
- **Costo de integración real = el matching** mercado↔partido + normalización de equipos (§B.3), no
  la API.

### Falsos problemas (descartar)
- "Hay que scrapear" → **no**, es API REST.
- "Necesito fondos / la ejecución está rota" → **irrelevante**, sólo lectura.
- "El rate limit me va a frenar" → **no**, estás 2 órdenes de magnitud por debajo.

---

# PARTE E — La pregunta que tenés que responder, y cómo

## §5. Pregunta central de viabilidad

> **¿El posicionamiento del dinero inteligente de Polymarket aporta información PREDICTIVA sobre el
> resultado del partido, por encima de lo que el precio del mercado ya refleja — y en qué deportes?**

Si la respuesta es "sólo replica el precio" → es redundante, descartar. Si es "aporta por
timing/convicción/identidad del trader" → es señal válida para el paso 4.

## Experimento mínimo para decidir (forward-test, sin construir todo)

Diseñado para tu maquinaria existente (`predictions/` → `evaluations/` → calibración):

1. **Snapshot diario, read-only.** Por cada partido del slate que **tenga** mercado en Polymarket:
   guardá `(side, precio, tamaño, timestamp, trader, score/Brier del trader)` del smart money.
   ~Decenas de requests, cacheado. (Reusá el código de Parte B.)
2. **Logueá un tag** en tu predicción del partido: `smart_money_aligned` / `contra` / `none`,
   con la convicción. **No cambies `model_prob`.**
3. **Evaluá al cierre** como ya hacés. Acumulá n.
4. **Medí dos cosas, por deporte:**
   - **Valor incremental:** ¿las predicciones con `smart_money_aligned` calibran mejor / rinden más
     que las `none`? ¿Las `contra` rinden peor? (análisis de cohortes que ya sabés hacer).
   - **Ortogonalidad al precio:** controlando por `market_prob`, ¿el lado/timing del smart money
     todavía explica resultado? Si no explica nada extra → es el precio disfrazado.
5. **Criterio de éxito (falsable, definílo antes):** p. ej. "en ≥X partidos, el cohorte
   `smart_money_aligned` mejora Brier en ≥Δ y la mejora **sobrevive** a controlar por `market_prob`,
   en al menos un deporte". Si no → PASAR, y lo documentás como hipótesis refutada (tan valioso como
   confirmarla).

**Empezá por UN deporte con buena liquidez en Polymarket** (NBA/MLB suelen tener más que fútbol de
ligas chicas) y **un puñado de partidos**, igual que hiciste el demo de `prop_value` con un solo
partido antes de escalar.

---

## Apéndice — referencias de archivo (verificadas 2026-06-24)

**Origen (Polybot, sólo lectura para portar):**
- `C:\polybot\core\polymarket.py` — cliente de las 3 APIs (todo lo de Parte B.2).
- `C:\polybot\core\config.py` — `DATA_BASE`, `GAMMA_BASE`, `CLOB_BASE`, `SPORTS_FILTER`, `TOP_WALLETS_TO_TRACK=50`.
- `C:\polybot\mvp1_observer\scraper.py` — el loop de polling (`scrape_once`, `get_leaderboard` en uso real).
- `C:\polybot\mvp2_auditor\scorer.py` — scoring de wallets + Brier del trader.
- `C:\polybot\_lb.py` — script mínimo de leaderboard rankeado (lectura rápida de referencia).
- `C:\polybot\CLAUDE.md` — log de avances con los hallazgos empíricos de Parte A.6.

**Destino (bets):**
- Módulo nuevo sugerido: `C:\bets\predictor\polymarket_signal.py`.
- Reusar: `C:\bets\predictor\cache.py`, el matching/normalización estilo `scan.py`,
  el loop `predictions/→evaluations/` y `feedback.py` para la cohorte.
- Guardrails a respetar: `C:\bets\CLAUDE.md` (anti-circularidad, paso 4, forward-test, honestidad
  calibracional).

**Endpoints (todos públicos, sin auth):**
- `https://data-api.polymarket.com/v1/leaderboard` · `/activity` · `/positions`
- `https://gamma-api.polymarket.com/markets` · `/events`
