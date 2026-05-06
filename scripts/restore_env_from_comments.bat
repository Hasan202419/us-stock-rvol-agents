@echo off

setlocal

cd /d "%~dp0.."

if exist ".venv\Scripts\python.exe" (

  ".venv\Scripts\python.exe" scripts\restore_env_from_comments.py %*

) else (

  python scripts\restore_env_from_comments.py %*

)

exit /b %ERRORLEVEL%

