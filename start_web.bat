@echo off
rem Запуск сайта Feri shop (каталог + документы).
cd /d "%~dp0"
echo Запускаю сайт: http://127.0.0.1:8000
".venv\Scripts\python.exe" -m uvicorn website.app:app --host 127.0.0.1 --port 8000
pause