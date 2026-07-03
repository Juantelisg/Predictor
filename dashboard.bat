@echo off
REM Lanzador del dashboard del predictor. Doble clic para abrirlo.
REM Antes de levantar el server genera las lecturas de contexto en vivo de HOY
REM (solo la 1ra vez del dia; si ya estan, arranca al instante).
REM Cerra esta ventana (o Ctrl+C) para apagar el server.
cd /d "%~dp0"
set "PY=C:\Users\Juant\AppData\Local\Python\bin\python.exe"

REM retro en segundo plano (no bloquea el dashboard): loguea los WC de hoy AUN no jugados
REM (pre-partido, anti-leakage), resuelve lo ya jugado y actualiza la calibracion -> loop_last.txt (UTF-8)
echo.
echo   Loop completo (calibracion + edge + bankroll + CLV + persistencia) -^> predictor\loop_last.txt  +  backtest Mundial -^> predictor\backtest_wc_last.txt
start "" /b powershell -NoProfile -Command "$p='%PY%'; & $p predictor\loop.py 2>&1 | Out-File -Encoding utf8 predictor\loop_last.txt; & $p predictor\backtest_wc.py 2>&1 | Out-File -Encoding utf8 predictor\backtest_wc_last.txt"

echo.
echo   Preparando analisis del dia...
"%PY%" predictor\lecturas.py missing
if errorlevel 1 (
  echo   Faltan lecturas -^> generando con Claude ^(solo la 1ra vez del dia, puede tardar 1-2 min^)...
  claude -p "Genera las lecturas de contexto en vivo del Mundial 2026 para hoy. Paso 1: ejecuta C:/Users/Juant/AppData/Local/Python/bin/python.exe predictor/lecturas.py packet y fijate que partidos dicen FALTA lectura; los que dicen OK ya estan, no los toques. Paso 2: para cada partido con FALTA, usa la herramienta WebSearch para conseguir bajas, XI probable, forma reciente y situacion de grupo, y redacta en espanol una lectura con cuatro campos: summary (una linea con el veredicto), context (6 vinetas: sede y hora ART, grupo y forma, bajas, XI probable, una senal cuantitativa, y la lectura del modelo integrando los numeros del packet), sources (3 enlaces reales) y disponibilidad (objeto JSON {home:{bajas:[{jugador,pos,impacto}],motivacion},away:{...}} orientado a local/visita del partido; impacto en clave|titular|duda|suplente; motivacion en must-win|dead-rubber|normal; usa bajas=[] si no hay). Usa exactamente el mismo formato y estilo que el archivo predictor/data/lecturas/2026-06-20.json, agregando el campo disponibilidad. Paso 3: guarda o mergea todo en predictor/data/lecturas/AAAA-MM-DD.json usando la fecha de hoy, con cada partido keyed por su gid de Linemate. Si todos los partidos ya dicen OK, no hagas nada." --permission-mode bypassPermissions
  echo   Enriqueciendo bajas con valor de mercado ^(Transfermarkt, local^)...
  "%PY%" predictor\transfermarkt.py enrich
) else (
  echo   Lecturas del dia ya listas.
)

echo.
echo   Dashboard del predictor  -^>  http://localhost:8900
echo   ^(cerra esta ventana para apagarlo^)
echo.
REM espera a que el server este arriba, precalienta el cache (cuadro+picks) y abre el navegador con todo listo
start "" /b powershell -NoProfile -Command "Start-Sleep 3; try { Invoke-WebRequest -UseBasicParsing 'http://localhost:8900/api/wc/today' | Out-Null } catch {}; Start-Process 'http://localhost:8900'"
"%PY%" -m uvicorn app:app --port 8900 --app-dir predictor
