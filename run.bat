@echo off
cd /d "%~dp0"
where uv >nul 2>nul
if %errorlevel%==0 (
  uv run --with "PySide6>=6.7" app.py
) else (
  py -m pip install -q "PySide6>=6.7"
  py app.py
)
