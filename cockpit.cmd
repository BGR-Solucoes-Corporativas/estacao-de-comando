@echo off
rem Estacao de Comando: so o painel, em qualquer terminal do Windows.
rem Usa o primeiro Python que ja tem textual e psutil (python3, py, python).
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PY="
for %%P in (python3 py python) do if not defined PY (
  %%P -c "import textual, psutil" >nul 2>nul && set "PY=%%P"
)
if not defined PY (
  echo Nenhum Python com textual e psutil instalados. Instale as dependencias:
  echo   python -m pip install --user --require-hashes -r "%~dp0requirements.lock"
  echo Num escritorio Mnemosine, pelo catalogo ferramentas\README.md, com a sua aprovacao.
  exit /b 1
)
%PY% "%~dp0cockpit.py" %*
