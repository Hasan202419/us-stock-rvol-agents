@echo off

setlocal

cd /d "%~dp0.."

if exist ".venv\Scripts\python.exe" (

  ".venv\Scripts\python.exe" scripts\trigger_render_deploy.py %*

) else (

  python scripts\trigger_render_deploy.py %*

)

exit /b %ERRORLEVEL%

