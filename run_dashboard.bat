@echo off

REM Faqat loyiha ildizidan ishga tushiring. `.venv` mavjud bo'lsa, Streamlit shu Python bilan yuradi.

REM Agar "Unable to import numpy" chiqsa: `.venv\Scripts\python.exe -m pip install --upgrade numpy pandas`

cd /d "%~dp0"

set "PY="

if exist ".venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"

if not defined PY (

  echo [.venv topilmadi — tizim python ishlatiladi. Tavsiya:] python -m venv .venv

  set "PY=python"

)



"%PY%" -c "from pathlib import Path; import sys; r=Path('.').resolve(); sys.path.insert(0, str(r)); from agents.bootstrap_env import ensure_env_file; ensure_env_file(r)"

echo Starting: Streamlit ( %PY% )

"%PY%" -m streamlit run dashboard.py
