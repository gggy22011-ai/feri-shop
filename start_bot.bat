@echo off
rem Запуск Feri_shop 24/7 без окна консоли (через ватчдог).
rem Используется Windows Task Scheduler.
cd /d "%~dp0"
start "" /b "%~dp0.venv\Scripts\pythonw.exe" "%~dp0watchdog.py"