@echo off
REM Planilla viva (tracker) - doble clic para abrirla.
REM Genera/refresca la planilla de HOY, la abre en el navegador y la sigue refrescando
REM cada 5 minutos mientras esta ventana quede abierta (el HTML se re-lee solo cada 5s).
REM El refresh NUNCA pisa lo anotado a mano (Decision/Stake/Notas/Cumplio/Resultado/PnL).
cd /d "%~dp0"
set "PY=C:\Users\Juant\AppData\Local\Python\bin\python.exe"

echo   Generando la planilla de hoy...
"%PY%" predictor\tracker.py
if errorlevel 1 (
  echo   FALLO tracker.py - revisar arriba el error.
  pause
  exit /b 1
)

start "" "%~dp0predictor\data\tracker\tracker.html"
echo.
echo   Planilla abierta en el navegador (se re-lee sola cada 5s).
echo   Esta ventana la refresca con los numeros del modelo cada 5 min.
echo   Cerra esta ventana cuando termines (la planilla queda, solo deja de refrescarse).
echo.

:loop
timeout /t 300 /nobreak >nul
"%PY%" predictor\tracker.py
goto loop
