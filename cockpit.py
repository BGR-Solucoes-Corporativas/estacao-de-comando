"""Estação de Comando: abre o painel. Roda de qualquer pasta: python3 cockpit.py"""
import sys
from pathlib import Path

for fluxo in (sys.stdout, sys.stderr):
    try:
        fluxo.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

PASTA = Path(__file__).resolve().parent
sys.path.insert(0, str(PASTA))

try:
    from estacao.app import main
except ModuleNotFoundError as erro:
    if erro.name in ("textual", "rich"):
        sys.exit(f"Falta a dependência '{erro.name}'. Instale: python3 -m pip install --user "
                 f"--require-hashes -r \"{PASTA / 'requirements.lock'}\" (num escritório Mnemosine, pelo catálogo "
                 "ferramentas/README.md, com a sua aprovação).")
    raise

if __name__ == "__main__":
    main()
