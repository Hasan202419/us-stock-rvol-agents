@echo off
title us-stock-rvol-agents — push + deploy (GITHUB_TOKEN .env dan)
cd /d "%~dp0"
python scripts\push_and_deploy_full.py -m "feat: Market Shield SPY QQQ VIX regime gates for long BUY"
if errorlevel 1 goto fail
echo.
echo Tayyor.
pause
exit /b 0
:fail
echo.
echo Xato. .env da GITHUB_TOKEN=ghp_... (repo scope) tekshiring.
echo Token: https://github.com/settings/tokens
pause
exit /b 1
