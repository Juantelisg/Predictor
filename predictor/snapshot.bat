@echo off
REM Snapshot de cuotas 1X2 para Closing Line Value (CLV). Pensado para una TAREA PROGRAMADA
REM que corre cada ~2h durante el dia: cada corrida guarda las cuotas del momento con su
REM timestamp -> el ULTIMO snapshot antes del kickoff es el "cierre" y el CLV deja de ser 0.
REM
REM Registrar la tarea (una vez, en una consola normal):
REM   schtasks /create /tn "bets-clv-snapshot" /tr "C:\bets\predictor\snapshot.bat" ^
REM     /sc hourly /mo 2 /st 10:00 /du 0010:00 /f
REM Borrarla:   schtasks /delete /tn "bets-clv-snapshot" /f
REM Correr ya:  schtasks /run /tn "bets-clv-snapshot"
cd /d "%~dp0\.."
set "PY=C:\Users\Juant\AppData\Local\Python\bin\python.exe"
"%PY%" predictor\clv.py snapshot >> predictor\clv_snapshot_last.txt 2>&1
