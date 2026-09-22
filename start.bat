@echo off
rem Запуск Feris Shop в консоли (видны логи/ошибки).
rem Выход из бота: Ctrl+C.
cd /d "%~dp0"
.venv\Scripts\python.exe bot.py
echo.
echo БОТ ОСТАНОВЛЕН. Ошибка выше? Нажми любую клавишу...
pause >nul