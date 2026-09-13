#!/bin/sh
# Estação de Comando: só o painel, em Linux e macOS.
# Lado a lado com a assistente, com tmux (troque claude pela sua CLI e ajuste o caminho do cockpit.sh):
#   tmux new-session claude \; split-window -h -l 35% "sh /caminho/da/estacao/cockpit.sh"
set -e
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
exec python3 "$(dirname "$0")/cockpit.py" "$@"
