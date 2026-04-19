@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Нет виртуального окружения .venv
  echo Создайте: py -3.12 -m venv .venv
  echo Затем: .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)
".venv\Scripts\python.exe" arkada.py
