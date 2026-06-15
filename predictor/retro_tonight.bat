@echo off
REM Retro automatica de las predicciones del 2026-06-14 (soccer). Generado por Claude.
REM Corre eval (baja resultados de ESPN/CSV) + report (calibracion) y guarda la salida.
cd /d C:\bets
set PY="C:\Users\Juant\AppData\Local\Python\bin\python.exe"
set OUT="C:\bets\predictor\retro_2026-06-14.txt"
echo ===== RETRO 2026-06-14 (corrida: %DATE% %TIME%) ===== > %OUT%
echo. >> %OUT%
echo --- feedback eval --- >> %OUT%
%PY% predictor\feedback.py eval >> %OUT% 2>&1
echo. >> %OUT%
echo --- feedback report --- >> %OUT%
%PY% predictor\feedback.py report >> %OUT% 2>&1
