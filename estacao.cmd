@echo off
rem Estacao de Comando (Windows): abre o Windows Terminal maximizado e dividido,
rem a assistente a esquerda (65%%) e o painel a direita (35%%).
rem O modulo nao desliga trava nenhuma nem mexe na politica de execucao: a
rem assistente abre como abriria sozinha.
rem
rem Qual assistente, e com quais opcoes: a linha de comando (estacao.cmd gemini,
rem ou estacao.cmd claude --uma-opcao); senao a variavel ESTACAO_ASSISTENTE, que
rem pode trazer a CLI com opcoes e vale tambem para os dois cliques; senao a
rem primeira CLI instalada entre claude, gemini, codex e agy, sem opcao nenhuma.
rem
rem Onde a assistente abre: instalada dentro de um escritorio
rem (modulos\estacao-de-comando\), na raiz dele; fora, na pasta de onde a
rem estacao foi chamada, e o painel roda avulso.
setlocal
for %%I in ("%~dp0..\..") do set "RAIZ=%%~fI"
if not exist "%RAIZ%\CLAUDE.md" set "RAIZ=%CD%"
rem chamada da raiz de uma unidade, o %CD% termina em barra invertida, e ela escaparia a aspa no wt
if "%RAIZ:~-1%"=="\" set "RAIZ=%RAIZ%."

set "CLI=%*"
if not defined CLI set "CLI=%ESTACAO_ASSISTENTE%"
if not defined CLI for %%C in (claude gemini codex agy) do if not defined CLI (
  where %%C >nul 2>nul && set "CLI=%%C"
)
if not defined CLI (
  echo Nenhuma CLI de assistente encontrada: claude, gemini, codex ou agy.
  echo Diga qual usar: estacao.cmd nome-da-cli
  exit /b 1
)
for /f "tokens=1" %%T in ("%CLI%") do set "TITULO=%%T"

where wt >nul 2>nul
if errorlevel 1 (
  echo Windows Terminal nao encontrado. Para abrir so o painel: cockpit.cmd
  exit /b 1
)

wt -M -d "%RAIZ%" --title "%TITULO%" %CLI% ; split-pane -V -s 0.35 -d "%RAIZ%" --title "Painel" cmd /k "%~dp0cockpit.cmd"
