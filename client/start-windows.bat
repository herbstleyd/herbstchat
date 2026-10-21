@echo off
REM Herbstchat starten (Windows)
cd /d "%~dp0"
if not exist .venv (
  echo Erster Start: richte Python-Umgebung ein ...
  py -3 -m venv .venv || python -m venv .venv
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\pip install -r requirements.txt
)
start "" .venv\Scripts\pythonw.exe herbstchat.py
