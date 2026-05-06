@echo off
REM Loyiha .env fayliga ish stoli yorlig'i yaratadi (nusxa emas — bitta fayl).
cd /d "%~dp0\.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0add_env_desktop_shortcut.ps1"
if errorlevel 1 pause
