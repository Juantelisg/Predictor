# Documento de Arquitectura de Software: Blueprint Conceptual para Plataforma Unificada de Analítica y Mercados Deportivos (v2)

## 1. Introducción y Marco Estratégico

### 1.1. Objetivo Técnico
El presente documento establece las directrices de arquitectura conceptual, patrones de diseño y requerimientos no funcionales necesarios para guiar el **pivote estratégico** de nuestro ecosistema actual. El objetivo es consolidar una plataforma de analítica predictiva y mercados de apuestas cruzadas, inspirada en las ventajas competitivas de cuatro referentes de la industria: **Outlier, Props.cash, OddsJam y Rithmm**.

### 1.2. Filosofía de Diseño: Flexibilidad Tecnológica
Este plano está diseñado desde una perspectiva **agnóstica respecto al stack tecnológico final**. Entendiendo que el equipo de arquitectura evaluará las herramientas específicas según las competencias internas y la infraestructura existente, este documento define los **roles de componentes, patrones de interacción, modelos de datos abstractos y flujos de información** requeridos.

---

## 2. Deconstrucción de la Experiencia de Usuario (UX/UI) y sus Implicaciones de Arquitectura

La interfaz de usuario (UI) en este tipo de plataformas no es un mero consumidor de datos plano; es un motor dinámico que requiere una arquitectura de backend altamente optimizada para responder de forma fluida.

```
+------------------------------------------------------------------------------------------+
|                                    DASHBOARD CENTRAL                                     |
|  +-----------------------------------+  +---------------------------------------------+  |
|  | PANEL DE CONTROL DE TENDENCIAS    |  | SELECCIÓN DE FILTROS TEMPORALES             |  |
|  | [Jugador/Equipo] [Línea del Book] |  | [Last 5] [Last 10] [Last 20] [Temporada]     |  |
|  +-----------------------------------+  +---------------------------------------------+  |
|  +------------------------------------------------------------------------------------+  |
|  | MATRIZ DE HISTOGRAMAS Y BARRAS DE STATS (Props.cash Style)                         |  |
|  |                                                                                    |  |
|  |  Valor Stat                                                                        |  |
|  |   30 |      _            _            _            _                               |  |
|  |   25 | ----|_|----------|_|----------|_|----------|_|------- [Línea de Apuesta]    |  |
|  |   20 |     |_|    _     |_|    _     |_|    _     |_|                               |  |
|  |      +-----+----+-----+----+-----+----+-----+----+-----+                           |  |
|  |           G1    G2    G3    G4    G5    G6    G7    G8                           |  |
|  +------------------------------------------------------------------------------------+  |
|  +-----------------------------------+  +---------------------------------------------+  |
|  | PANEL DE MATRIZ +EV (OddsJam Style)|  | SLIDERS DE INFERENCIA CUSTOM (Rithmm Style) |  |
|  | [Casa A] [Casa B] [Edge %] [Alerta] |  | Def: [---o---] Off: [-----o-] Pace: [-o----] |  |
|  +-----------------------------------+  +---------------------------------------------+  |
+------------------------------------------------------------------------------------------+
```

### 2.1. El Dashboard de Tendencias e Ingesta Cruzada (Estilo Outlier)
* **Comportamiento UX:** El usuario busca un jugador (ej. *LeBron James*) y el mercado de *Player Props* (ej. *Más/Menos de 24.5 Puntos*). De inmediato, la pantalla debe pintar el "Hit Rate": el porcentaje de veces que el jugador superó esa línea exacta bajo condiciones específicas.
* **Implicación de Arquitectura:**
    * **Cómputo Multidimensional Instantáneo:** El backend no puede realizar escaneos completos (`Table Scans`) de tablas históricas en bases de datos relacionales tradicionales cada vez que un usuario cambia de pestaña. 
    * **Requerimiento Arquitectónico:** Se requiere una capa de **Almacenamiento Analítico Orientado a Columnas (OLAP)** o el uso intensivo de **Vistas Materializadas Continuas**. Los datos de partidos jugados deben indexarse de forma compuesta por `[Player_ID, Market_Type, Date]`.

### 2.2. Filtros Dinámicos de Contexto (Last 5, Last 10, Last 20, Versus Opponent)
* **Comportamiento UX:** Botones de alternancia rápida que recalculan los gráficos y los porcentajes de éxito en milisegundos cuando el usuario cambia entre los últimos 5 partidos, los últimos 10, toda la temporada actual, o partidos específicos en condición de Local/Visitante.
* **Implicación de Arquitectura:**
    * **Estrategia de Ventanas de Tiempo (Time-Windowing):** El motor de API debe estar optimizado para inyectar cláusulas de acotamiento de registros (`LIMIT` o filtros por rango de fechas precalculados).
    * **Requerimiento Arquitectónico:** Implementar un patrón de **Agregación en Memoria (In-Memory Pre-Aggregation)**. Al cargar el perfil del jugador, se descarga un payload compacto con el histórico ordenado de la temporada en un estado global del Frontend (State Management eficiente), permitiendo que los cortes de *Last 5/10/20* se ejecuten directamente en el cliente en 0 milisegundos, liberando de carga al servidor.

### 2.3. Barras de Estadísticas y Gráficos de Dispersión de Densidad Densa (Estilo Props.cash)
* **Comportamiento UX:** Gráficos de barras que muestran cada partido del jugador en orden cronológico. Una línea horizontal estática interseca las barras para denotar el valor actual ofrecido por la casa de apuestas, pintando de color verde las barras que superan la línea y de rojo las que quedan por debajo.
* **Implicación de Arquitectura:**
    * **Normalización y Serialización de Datos:** El backend debe proveer estructuras de datos JSON altamente estandarizadas y livianas que incluyan no solo el valor absoluto de la estadística, sino metadatos del juego (ID del rival, condición local/visitante, minutos jugados).
    * **Requerimiento Arquitectónico:** Diseñar endpoints de lectura que utilicen protocolos de serialización rápidos. Evitar payloads anidados complejos. La UI requiere arrays planos de objetos para mapear directamente sobre componentes de renderizado de alto rendimiento (ej. librerías basadas en Canvas o SVG optimizado).

### 2.4. Matriz de Cuotas en Tiempo Real y Feed +EV (Estilo OddsJam)
* **Comportamiento UX:** Una grilla masiva que parpadea en verde o rojo cuando las cuotas de 20 o más casas de apuestas cambian en tiempo real. Resalta las oportunidades de Valor Esperado Positivo (+EV) calculando desviaciones contra una "Línea Base" del mercado (Sharp Books).
* **Implicación de Arquitectura:**
    * **Arquitectura de Empuje (Push Architecture) vs. Pull:** El polling HTTP tradicional destruirá la escalabilidad del sistema y ofrecerá datos obsoletos.
    * **Requerimiento Arquitectónico:** Implementación obligatoria de una **Capa de Transmisión en Tiempo Real (Real-Time Streaming)** basada en WebSockets o Server-Sent Events (SSE). El backend debe contar con un **Motor de Comparación en Memoria (In-Memory Rules Engine)** que procese el diferencial de cuotas en milisegundos y despache eventos de cambio únicamente a los clientes suscritos a ese mercado.

### 2.5. Simulador Predictivo Basado en Sliders de Parámetros (Estilo Rithmm)
* **Comportamiento UX:** El usuario ajusta controles deslizantes (*sliders*) para alterar los pesos de un modelo de predicción (ej. darle 50% de importancia a la defensa del oponente, 20% al ritmo de juego del equipo y 30% al rendimiento histórico reciente del jugador). La plataforma calcula al vuelo una nueva proyección de puntos esperados.
* **Implicación de Arquitectura:**
    * **Desacoplamiento del Cómputo Analítico (Decoupled Ingestion/Inference):** Calcular modelos predictivos complejos bajo demanda por cada interacción del slider puede congelar la infraestructura.
    * **Requerimiento Arquitectónico:** El backend distribuye los vectores de características precalculados (ej. métricas puras de defensas y ritmos). Cuando el usuario manipula la UI, la ecuación polinomial o de inferencia ligera se resuelve mediante una de estas dos estrategias elegidas por los arquitectos:
        1.  **Client-Side Execution (Edge):** Si los datos son livianos, la fórmula matemática se ejecuta directamente en Javascript o WebAssembly (Wasm) en el navegador del usuario.
        2.  **Serverless Micro-Workers:** Una arquitectura de funciones de cómputo rápido (Serverless o microservicios dedicados de baja latencia) que toma los coeficientes, ejecuta el producto punto y retorna el escalar en milisegundos.

---

## 3. Arquitectura Conceptual de Referencia (Agnóstica)

Para estructurar este giro sin comprometer la estabilidad operativa, se propone un diseño basado en **Capas de Responsabilidad Desacopladas mediante Eventos**.

```
+---------------------------------------------------------------------------------------+
| 1. CAPA DE PRESENTACIÓN (UI COMPONENT ARCHITECTURE)                                   |
|    - Renderizador de Gráficos de Alta Densidad (Canvas/SVG Core)                      |
|    - Conector de Estado de Flujo Continuo (WebSocket/SSE Client)                      |
+---------------------------------------------------------------------------------------+
                                           ^
                                           | (Protocolo de Red de Baja Latencia)
                                           v
+---------------------------------------------------------------------------------------+
| 2. CAPA DE ENTRADA Y ORQUESTACIÓN (API GATEWAY & GATEWAY ROUTING)                     |
|    - Autenticación, Rate Limiting perimetral, Enrutamiento de Consultas / Comandos    |
+---------------------------------------------------------------------------------------+
                                           |
                    +----------------------+----------------------+
                    | (Queries Analíticas)                        | (Streams en Tiempo Real)
                    v                                             v
+---------------------------------------+   +-------------------------------------------+
| 3. SERVICIO DE CONSULTA AGREGADA     |   | 4. MOTOR DE PROCESAMIENTO EN TIEMPO REAL  |
|    - Orquestador de lecturas de       |   |    - Filtro de Cuotas (Odds Matcher)      |
|      estadísticas históricas.         |   |    - Evaluador de Reglas Matemáticas (+EV) |
+---------------------------------------+   +-------------------------------------------+
                    |                                             |
                    v (Lecturas de Alta Velocidad)                v (Lectura/Escritura In-Memory)
+---------------------------------------+   +-------------------------------------------+
| 5. CAPA DE DATOS ANALÍTICOS (OLAP)    |   | 6. CAPA DE ALTA VELOCIDAD (CACHE/SPEED)   |
|    - Store de Series Temporales e     |   |    - Almacenamiento de líneas vigentes    |
|      históricos de estadísticas.      |      de múltiples casas de apuestas.          |
+---------------------------------------+   +-------------------------------------------+
                                           ^
                                           | (Event Log Consumidor)
+---------------------------------------------------------------------------------------+
| 7. BUS DE EVENTOS DISTRIBUIDO (MESSAGE BROKER)                                        |
|    - Tópicos Core: `sports-data-raw`, `market-odds-stream`, `user-predictions`         |
+---------------------------------------------------------------------------------------+
                                           ^
                                           | (Ingesta Asincrónica)
+---------------------------------------------------------------------------------------+
| 8. TRABAJADORES DE INGESTA Y MODELADO (INGESTION WORKERS & ML SERVING)                |
|    - Conectores de Feeds Externos (Sportradar, Stats Perform, APIs de Terceros)        |
|    - Engine de Inferencia Predictiva (Modelos de Machine Learning en lote)            |
+---------------------------------------------------------------------------------------+
```

### 3.1. Definición de Responsabilidades por Capa

1.  **Capa de Presentación:** Diseñada bajo el principio de componentes reactivos puros. Debe separar el hilo principal de renderizado de la lógica de procesamiento de mensajes provenientes de la red.
2.  **Capa de Entrada (API Gateway):** Punto único de entrada. Abstrae la complejidad de los microservicios subyacentes. Maneja la persistencia de conexiones WebSocket del cliente.
3.  **Servicio de Consulta Agregada:** Microservicio encargado de resolver consultas complejas de UI (Filtros Last 5, Historiales, Head-to-Head). No toca la base de datos transaccional del sistema.
4.  **Motor de Procesamiento en Tiempo Real (Real-Time Odds Engine):** Servicio crítico de baja latencia encargado de ingerir las cuotas crudas que cambian constantemente, calcular la línea media del mercado y encontrar ineficiencias de cuotas (+EV y Arbitraje).
5.  **Capa de Datos Analíticos (OLAP Store):** El motor de persistencia optimizado para lecturas masivas agregadas. Almacena filas inmutables de estadísticas históricas de juego.
6.  **Capa de Alta Velocidad (Speed Layer):** Almacenamiento en memoria con expiración por tiempo (TTL). Guarda el estado "vivo" de las líneas de apuestas en los mercados actuales de las próximas 24-48 horas.
7.  **Bus de Eventos Distribuido:** El tejido conectivo del sistema. Garantiza que la ingesta de datos de proveedores externos no bloquee los servicios de cara al usuario y permite propagar los datos en paralelo a la capa analítica y a la capa en memoria.
8.  **Trabajadores de Ingesta y Modelado:** Procesos en segundo plano encargados de traducir los formatos heterogéneos de los proveedores de datos a eventos estandarizados dentro de nuestro sistema.

---

## 4. Estrategia de Mapeo de Datos y Abstracción del Modelo

Para dar el giro al proyecto utilizando la estructura de datos que el equipo ya maneja, debemos implementar una separación conceptual entre el **Modelo Transaccional (OLTP)** y el **Modelo Analítico (OLAP)**. 

### 4.1. Abstracción del Modelo de Datos de Propiedades Deportivas (*Player Props*)

Cualquier métrica analítica de las plataformas de referencia se puede descomponer en el siguiente modelo de hechos y dimensiones abstracto:

```
                  +-----------------------+
                  |  DIM_PLAYER (Atleta)  |
                  |  - Player_ID          |
                  |  - Name, Position     |
                  +-----------------------+
                              | (1)
                              |
                              v (N)
+---------------------------------------------------------------------+
| FACT_PLAYER_GAME_STAT (Hecho Histórico de Rendimiento)             |
+---------------------------------------------------------------------+
| - Game_ID (FK)                                                      |
| - Player_ID (FK)                                                    |
| - Team_ID / Opponent_Team_ID                                        |
| - Metric_Type (Enum: POINTS, REBOUNDS, ASSISTS, PASSING_YARDS, etc.)|
| - Stat_Value (Float - El resultado real logrado por el jugador)     |
| - Is_Home_Game (Boolean)                                            |
| - Days_of_Rest (Integer)                                            |
| - Game_Timestamp (DateTime)                                         |
+---------------------------------------------------------------------+
                              ^ (N)
                              |
                              | (1)
                  +-----------------------+
                  |  DIM_GAME (Partido)   |
                  |  - Game_ID            |
                  |  - Season, Week/Date  |
                  +-----------------------+
```

### 4.2. Abstracción del Modelo de Datos de Mercado de Apuestas (*Odds & Lines*)

Para soportar las capacidades analíticas de fluctuación de líneas (estilo OddsJam), el estado vivo y el histórico de cuotas se abstrae de la siguiente manera:

```
+---------------------------------------------------------------------+
| FACT_MARKET_ODDS (Historial y Estado Vivo de Cuotas)                |
+---------------------------------------------------------------------+
| - Market_ID (UUID único por mercado, ej: Player_LeBron_Points_24.5) |
| - Game_ID (FK)                                                      |
| - Player_ID (FK, opcional para props de equipo)                     |
| - Bookmaker_ID (Identificador de la casa de apuestas)               |
| - Line_Value (Float - Ej: 24.5)                                     |
| - Over_Price (Decimal/Americano - Cuota para la alta)               |
| - Under_Price (Decimal/Americano - Cuota para la baja)              |
| - Implied_Probability (Calculada al vuelo por el backend)           |
| - Timestamp (Momento exacto del cambio de cuota)                    |
+---------------------------------------------------------------------+
```

### 4.3. Lógica del Cálculo Matemático en el Backend (+EV)
El motor de tiempo real debe aplicar de forma continua la lógica de **Valor Esperado (+EV)** sobre los flujos de la tabla abstracta de cuotas (`FACT_MARKET_ODDS`). El algoritmo abstracto es:

1.  Determinar la **Probabilidad Pura ($P_{fair}$)** eliminando la comisión (*Vig*) de las casas de apuestas más eficientes del mundo (*Sharp Books*):
    $$P_{fair} = rac{	ext{Probabilidad Implícita}_{sharp}}{	ext{Probabilidad Implícita}_{sharp\_over} + 	ext{Probabilidad Implícita}_{sharp\_under}}$$
2.  Comparar contra la cuota ofrecida por una casa de apuestas comercial (*Soft Book*), convirtiendo su cuota decimal a una probabilidad de pago ($P_{soft}$).
3.  Calcular el **Valor Esperado (EV)**:
    $$	ext{EV} = (P_{fair} 	imes 	ext{Ganancia Potencial}_{soft}) - ((1 - P_{fair}) 	imes 	ext{Estaca})$$
4.  Si $	ext{EV} > 0.0$, el registro es catalogado inmediatamente como un evento prioritario y empujado hacia la UI mediante la capa de mensajería en tiempo real.

---

## 5. Estrategia de Sincronización y Gestión de Estados en la UX

Un gran desafío que el equipo de arquitectura debe resolver es evitar el conflicto visual de datos en el frontend: las cuotas cambian cada segundo, pero las estadísticas históricas cambian una vez por partido.

### 5.1. Gestión de Estados Dual en el Cliente

Para lograr una UX fluida, se propone separar el estado del cliente en dos ciclos de vida independientes:

1.  **Estado Estático-Analítico (Carga Pesada / Baja Frecuencia):**
    * **Datos:** Perfil del jugador, tendencias de los últimos partidos, logs históricos de la temporada, clasificaciones defensivas de equipos.
    * **Estrategia:** Se solicita vía HTTP REST/GraphQL en la carga inicial de la vista. Se almacena en la memoria caché del cliente con una política de invalidación laxa (ej. expira solo cuando cambia el día o termina un partido en vivo). Los filtros de *Last 5 / Last 10* operan exclusivamente sobre este segmento local de memoria.
2.  **Estado Efímero-Dinámico (Carga Liviana / Alta Frecuencia):**
    * **Datos:** Líneas actuales de las casas de apuestas, cuota actual del *Over/Under*, indicadores de alertas +EV.
    * **Estrategia:** Se abre un canal persistente (WebSocket/SSE). Los mensajes entrantes deben ser payloads atómicos (ej. `{"market_id": "xyz", "book": "B1", "line": 24.5, "over": -110}`). Un motor de estado reactivo en el frontend intercepta este mensaje, localiza la fila en la pantalla por el identificador del mercado y actualiza exclusivamente los nodos del árbol DOM afectados, aplicando animaciones de cambio visual (parpadeo verde/rojo) sin re-renderizar todo el panel analítico.

---

## 6. Plan de Acción Técnico para el Equipo de Arquitectura

El equipo de diseño y desarrollo de arquitectura puede abordar este pivote estratégico dividiendo la implementación en las siguientes etapas conceptuales:

### Fase 1: Capa de Abstracción de Datos e Ingesta Unificada
* **Acción 1:** Definir los contratos de los eventos de ingesta. Crear esquemas estructurados para los tópicos core del Bus de Eventos (`sports-data-raw` y `market-odds-stream`).
* **Acción 2:** Desarrollar los adaptadores periféricos (Workers) para transformar las APIs de los proveedores actuales del proyecto hacia los tópicos del Bus de Eventos.
* **Acción 3:** Configurar la base de datos analítica orientada a columnas (OLAP Store) para consumir de forma asincrónica del bus de eventos, poblando el modelo analítico de rendimiento de jugadores de forma inmutable.

### Fase 2: Motor de Reglas en Tiempo Real y API de Suscripción
* **Acción 1:** Diseñar la Capa de Velocidad en Memoria para mantener las líneas vivas del día actual. Cada evento del bus de cuotas actualiza esta base de datos en memoria con llaves de acceso rápido indexadas por identificador de partido y mercado.
* **Acción 2:** Implementar el microservicio de cálculo matemático para evaluar ineficiencias de cuotas (+EV) procesando los deltas en memoria y publicando las alertas en un tópico secundario de alertas.
* **Acción 3:** Implementar el componente de puerta de enlace (API Gateway / WebSocket Server) para gestionar las conexiones de los usuarios y canalizar los eventos del tópico de alertas directamente a la UI.

### Fase 3: Optimización de Componentes de UI de Alta Densidad
* **Acción 1:** Diseñar las APIs de lectura analítica para entregar arrays planos optimizados para graficar las series temporales de rendimiento de jugadores.
* **Acción 2:** Refactorizar la arquitectura del cliente frontend para adoptar la gestión de estado dual (separando datos estáticos históricos de flujos de cuotas volátiles).
* **Acción 3:** Implementar técnicas de optimización visual del lado del cliente (como virtualización de listas para las tablas masivas de cuotas y aceleración de gráficos) asegurando estabilidad en dispositivos móviles y de escritorio.
