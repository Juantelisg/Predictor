@echo off
REM Lanzador del dashboard del predictor. Doble clic para abrirlo.
REM Cerra esta ventana (o Ctrl+C) para apagar el server.
cd /d "%~dp0"
echo.
echo   Dashboard del predictor  ->  http://localhost:8900
echo   (cerra esta ventana para apagarlo)
echo.
REM abre el navegador unos segundos despues, cuando el server ya esta arriba
start "" /b powershell -NoProfile -Command "Start-Sleep 3; Start-Process 'http://localhost:8900'"
"C:\Users\Juant\AppData\Local\Python\bin\python.exe" -m uvicorn app:app --port 8900 --app-dir predictor
