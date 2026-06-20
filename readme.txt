==============================================================================
  LEEME PRIMERO  -  Proyecto "bets"  (orientacion para Claude en cowork)
  Ultima actualizacion: 2026-06-19
==============================================================================

Hola Claude. Si te pidieron leer este archivo, leelo ENTERO antes de tocar nada.
Te pone en contexto en 2 minutos y te dice como comportarte en este proyecto.


------------------------------------------------------------------------------
0) QUE ES ESTO (y que NO es)
------------------------------------------------------------------------------
Es un PREDICTOR DE PROBABILIDADES DEPORTIVAS, puramente estadistico.

REGLA DE ORO (no negociable):
  - CERO cuotas. CERO "edges". CERO "ganarle a la casa". CERO value betting.
  - La vara de exito es la CALIBRACION: cuando el modelo dice 70%, ¿pega 70%?
    NO es el ROI, NO es acertar picks, NO es vencer a la casa.
  - Si te encontras pensando en "valor esperado" o "edge contra el book", parate:
    eso es la direccion VIEJA del proyecto y esta descartada.

Por que importa: el dueño es claro en esto. Mezclar cuotas/edges le rompe el
proyecto. Hablale de PROBABILIDADES y de que tan bien calibradas estan.


------------------------------------------------------------------------------
1) DONDE ESTA EL CODIGO VIVO  (y que ignorar)
------------------------------------------------------------------------------
TODO lo vigente vive en la carpeta:   predictor/

IGNORAR (es historico, direccion vieja EV+/cuotas, NO usar como guia):
  - La mayor parte de CLAUDE.md (describe el "supra-agente de value betting" viejo).
    Solo vale el bloque de arriba de CLAUDE.md que marca el PIVOTE.
  - Archivos sueltos en la raiz: prop_value.py, scan.py, totals.py, analyze.py,
    promote.py, backtest_props.py, player_props.py, soccer_odds.py, evaluate.py...
    todo eso es del enfoque viejo (cuotas). No te apoyes en ello.

Para el detalle de arquitectura del predictor, leer:  predictor/README.md


------------------------------------------------------------------------------
2) CAPACIDAD CLAVE Y NUEVA:  LINEMATE  (predictor/linemate.py)
------------------------------------------------------------------------------
Linemate.io es un sitio de analitica deportiva (picks/trends por mercado, con
filtros por forma / localia / vs-rival). Antes el dueño copiaba esos datos A MANO.

Descubrimiento (2026-06-19): Linemate es una SPA que se alimenta de una API JSON
PUBLICA, SIN AUTENTICACION. O sea: se puede leer todo con requests, sin token,
sin navegador headless. Esto es importante para el proyecto.

Base de la API:   https://api.linemate.io/api/{liga}/...
Endpoints utiles (todos GET, sin auth; mandar headers de navegador):
  /v1/trends/straights            -> picks del dia (jugador + equipo) con hit-rates
  /v1/trends/straights/trending   -> trends agrupados (Most bet on / por-partido / Most searched)
  /v3/games/current               -> cartelera del dia (slate completo)
  /v3/games/{gameId}              -> detalle de un partido (odds, win%, venue)
  /v3/teams                       -> tabla de equipos + hit records
  /v3/teams/injuries              -> lesiones
  /v3/players/search?searchTerm=  -> buscar jugador
  /v3/players/{SRID}              -> stats del jugador (averageStats/cumulativeStats)

Slugs de liga: fifa-world-cup, epl, laliga, seriea, bundesliga, mls,
               nba, mlb, nfl, nhl, wnba, ncaab, ncaaf.

Cada "trend" trae hit-rates con los MISMOS splits que la web:
  LAST_5 / LAST_10 / LAST_20 / LAST_30 / SEASON / MATCHUP (vs ese rival) / STARTER
  cada uno como {games, hits, hitRate, average}.

Cliente listo:  predictor/linemate.py
  python predictor/linemate.py --leagues          # lista de ligas
  python predictor/linemate.py wc                  # picks del Mundial
  python predictor/linemate.py wc --game=BRA       # filtrar un partido (substring del gameId)
  python predictor/linemate.py mlb --min=70        # solo SEASON hit-rate >= 70%
  python predictor/linemate.py mlb --market=hits   # filtrar por mercado

OJO honesto:
  - La PROFUNDIDAD de Linemate escala con partidos jugados. En torneos cortos
    (Mundial recien arrancado) los hit-rates son sobre 1-2 juegos = muestras chicas
    (veras 100%/0%). En ligas en plena temporada (MLB/NBA) los splits vienen ricos.
  - Es la API INTERNA de ellos, no oficial. Si cambian rutas hay que reajustar el
    slug/version (esta todo centralizado en linemate.py).
  - Linemate trae cuotas en el JSON crudo. NO las uses para "edge". Sirven solo como
    contexto de mercado. El core que usamos es el HIT-RATE.


------------------------------------------------------------------------------
3) MODULOS DEL PREDICTOR  (resumen; detalle en predictor/README.md)
------------------------------------------------------------------------------
  soccer.py + elo.py   Selecciones (Mundial): Elo rodante + Poisson/Dixon-Coles.
                       Da 1X2 + totales (Over/Under) + BTTS + valla invicta, coherentes.
  corners.py           Corners. Clubes (football-data.co.uk) o selecciones (--intl, StatsBomb).
  cards.py             Tarjetas amarillas (CLUBES). Selecciones via statsbomb_data.predict_cards.
  statsbomb_data.py    xG / corners / tarjetas de selecciones (StatsBomb Open Data, libre).
  linemate.py          Cliente de la API de Linemate (ver seccion 2).
  mlb.py               MLB moneyline con datos reales (MLB Stats API).
  mvp_nba.py           NBA POC (datos sinteticos, placeholder).
  core.py              Pipeline binario compartido (SQLite -> features sin fuga -> logistica).
  feedback.py          Loop de calibracion: log -> eval (vs ESPN) -> report (Brier por bucket).
  slate.py             Partidos de hoy desde fuentes gratis.
  cache.py             Cache JSON con TTL por volatilidad del dato.
  budget.py            Guardia de quota de API-Football (100/dia; unica API escasa).
  app.py + dashboard.html   Backend FastAPI + UI del dashboard.

Carpetas de estado (memoria del proyecto):
  predictor/predictions/<fecha>.jsonl   predicciones logueadas
  predictor/evaluations/<fecha>.jsonl   resultados (won/lost, calib_error) al cierre
  predictor/data/cache/                 cache local


------------------------------------------------------------------------------
4) COMO CORRER
------------------------------------------------------------------------------
En la maquina local del dueño (Windows) el Python real es:
  C:/Users/Juant/AppData/Local/Python/bin/python.exe
  (el "python" del PATH es el alias del Store y NO sirve).

En cowork / sandbox usa el python3 disponible en el entorno. Necesitas internet
para las APIs (Linemate, MLB Stats API, ESPN, StatsBomb, dataset intl en GitHub).

Ejemplos (desde la raiz del repo):
  python predictor/soccer.py "Brazil" "Haiti"      # un partido de selecciones
  python predictor/linemate.py wc --game=BRA        # trends de Linemate de ese partido
  python predictor/corners.py --intl "United States" "Australia"
  python predictor/feedback.py report               # tabla de calibracion

Dashboard (UI):
  python -m uvicorn app:app --port 8900 --app-dir predictor   -> http://localhost:8900
  (uvicorn no recarga solo: al editar, matar el puerto y relanzar)


------------------------------------------------------------------------------
5) COMO TE TENES QUE COMPORTAR EN ESTE PROYECTO
------------------------------------------------------------------------------
A) Formato estandar de analisis de un partido (4 partes, en este orden):
   1. CUADRO PROFUNDO: todos los mercados del modelo (1X2, totales, BTTS, valla,
      corners, tarjetas) con su probabilidad y un nivel de confianza por mercado.
   2. LECTURA + CONTEXTO PROFUNDO: interpretacion cuantitativa + contexto en vivo
      (lesiones, XI, localia, sede). Para selecciones (Mundial) los lineups/bajas
      NO salen de las skills: buscarlos en internet (WebSearch).
   3. PICKS CONFIABLES: los de mayor conviccion, con su probabilidad por pierna.
   4. SELECCION DEL DIA: el/los pick(s) de maxima conviccion.

B) Combos / multi-mercado: dar la probabilidad POR PIERNA. NUNCA vender el combo
   entero como "valor". Mostrar TODOS los mercados del modelo, no solo el 1X2.

C) Mercados objetivo del dueño: 1X2 y totales funcionan bien. Corners/tarjetas son
   mas ruidosos -> tratarlos con humildad. Track record propio: el modelo tiende a
   SOBREESTIMAR tarjetas amarillas -> no apoyarse fuerte en Over de tarjetas.

D) Sesgo conocido del modelo de selecciones: subcalibrado en favoritos moderados
   (los deja cortos). Tenerlo en cuenta al leer 1X2 de un favorito claro.

E) Localia: en el Mundial casi todo es cancha NEUTRAL, PERO si juega el anfitrion
   (USA 2026) corrolo como LOCAL (neutral=False), no neutral. Cambia mucho el 1X2.

F) Honestidad calibracional: no reescribir el pasado, no inventar tasas base, no
   forzar un pick. "PASAR" es una respuesta valida. Si un fetch falla, decirlo y
   bajar confianza; no fabricar datos.

G) Despues de CADA implementacion, cerrar con un reporte corto en criollo:
   que se hizo / que hace / como funciona / como se usa / estado (con limites honestos).

H) No leer config ni SKILL.md al inicio. No inventar comandos/endpoints que no
   esten verificados. Cambios quirurgicos: tocar solo lo necesario.


------------------------------------------------------------------------------
6) FUENTES DE DATOS
------------------------------------------------------------------------------
  Sin key (workhorse): MLB Stats API, dataset intl (martj42/international_results),
                       ESPN, StatsBomb Open Data, football-data.co.uk, Linemate API.
  Con key (escasa):    API-Football (predictor/.env, gitignoreado). 100/dia.
                       Protegida por budget.py. Desbloquea corners/tarjetas/props
                       de selecciones a futuro.
  NO se usa:           The Odds API ni ninguna fuente de cuotas (contra la regla de oro).


------------------------------------------------------------------------------
7) ESTADO ACTUAL  (jun 2026)
------------------------------------------------------------------------------
  Listo:  soccer selecciones (1X2/totales/BTTS/valla), corners/tarjetas intl via
          StatsBomb, MLB moneyline, loop de calibracion, dashboard, cliente Linemate.
  Validacion: soccer 1X2 log loss ~0.86 vs 1.05 baseline, acc ~60%.
              loop con ~60 evaluaciones (Brier ~0.22); n todavia chico para ajustar.
  Proximo paso sugerido: conectar Linemate (trends por-partido + odds de contexto)
          DENTRO del formato de analisis, para que un partido salga con el modelo
          estadistico AL LADO de los trends de Linemate, en un solo cuadro.

==============================================================================
  Fin. Resumen de 1 linea: predictor de PROBABILIDADES, sin cuotas, vara =
  calibracion; codigo vivo en predictor/; Linemate via API publica en linemate.py.
==============================================================================
