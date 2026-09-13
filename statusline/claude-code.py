#!/usr/bin/env python3
"""Statusline do Claude Code: o contexto em uso em destaque, mais modelo, pasta e branch.

O Claude Code manda um JSON pela entrada padrão a cada atualização (campos documentados: model,
workspace, context_window, transcript_path...) e mostra a linha que este script imprimir. Nunca
levanta erro: campo faltando ou estranho só empobrece a linha, nunca a apaga.

Instalar, no settings.json do Claude Code (o do usuário, ~/.claude/settings.json, ou o do projeto):
  "statusLine": {"type": "command", "command": "python3 /caminho/da/estacao/statusline/claude-code.py"}
No Windows, `python` ou `py` no lugar de `python3`, conforme a instalação.

Único processo que abre: `git branch --show-current`, com 1 s de limite, para mostrar a branch.
"""
import json
import os
import subprocess
import sys

REPOR = "\033[0m"
NEGRITO = "\033[1m"
APAGADO = "\033[2m"
VERDE = "\033[32m"
AMARELO = "\033[33m"
VERMELHO = "\033[31m"
CIANO = "\033[36m"


def seguro(padrao):
    def decorador(funcao):
        def envelope(*args, **kwargs):
            try:
                return funcao(*args, **kwargs)
            except Exception:
                return padrao
        return envelope
    return decorador


@seguro({})
def ler_entrada():
    bruto = sys.stdin.buffer.read().decode("utf-8", "replace")  # não depende da página de código do sistema
    return json.loads(bruto) if bruto.strip() else {}


@seguro(None)
def branch_git(pasta):
    if not pasta or not os.path.isdir(pasta):
        return None
    resultado = subprocess.run(
        ["git", "--no-optional-locks", "-C", pasta, "branch", "--show-current"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1,
    )
    return (resultado.stdout or "").strip() or None


@seguro(None)
def estimar_pelo_transcript(caminho):
    """Quando o JSON não traz o contexto: soma os tokens do último bloco `usage` que o Claude Code
    gravou no transcript, como aproximação do contexto em uso."""
    if not caminho or not os.path.isfile(caminho):
        return None
    ultimo = None
    with open(caminho, "r", encoding="utf-8", errors="replace") as arquivo:
        for linha in arquivo:
            linha = linha.strip()
            if not linha:
                continue
            try:
                entrada = json.loads(linha)
            except ValueError:
                continue
            mensagem = entrada.get("message") if isinstance(entrada, dict) else None
            uso = mensagem.get("usage") if isinstance(mensagem, dict) else None
            if isinstance(uso, dict):
                ultimo = uso
    if not ultimo:
        return None
    return sum(ultimo.get(chave) or 0 for chave in
               ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))


def fmt_tokens(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "?"
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


@seguro("Claude Code")
def montar_linha():
    dados = ler_entrada()

    modelo = dados.get("model") or {}
    nome_modelo = modelo.get("display_name") or modelo.get("id") or "?"

    area = dados.get("workspace") or {}
    pasta = area.get("current_dir") or dados.get("cwd") or os.getcwd()
    base = os.path.basename(str(pasta).rstrip("/\\")) or str(pasta)
    branch = branch_git(pasta)

    ctx = dados.get("context_window") or {}
    janela = ctx.get("context_window_size")
    usados = ctx.get("total_input_tokens")
    pct = ctx.get("used_percentage")
    aproximado = False

    if pct is None and usados is None:
        estimado = estimar_pelo_transcript(dados.get("transcript_path"))
        if estimado is not None:
            usados, aproximado = estimado, True

    if pct is None and usados is not None and janela:
        try:
            pct = round(usados / janela * 100, 1)
        except (TypeError, ZeroDivisionError):
            pct = None

    # o selo do contexto: a parte mais visível da linha
    if pct is not None:
        largura = 10
        cheio = min(largura, max(0, round(pct / 100 * largura)))
        rotulo = f"[{'#' * cheio}{'-' * (largura - cheio)}] {'~' if aproximado else ''}{pct:.0f}% ctx"
        if usados is not None and janela:
            rotulo += f" ({fmt_tokens(usados)}/{fmt_tokens(janela)})"
        cor = VERMELHO if pct >= 80 else (AMARELO if pct >= 50 else VERDE)
    elif usados is not None:
        rotulo, cor = f"~{fmt_tokens(usados)} tok ctx", CIANO
    else:
        rotulo, cor = "ctx ?", CIANO

    resto = [nome_modelo, base] + ([f"({branch})"] if branch else [])
    return f"{NEGRITO}{cor}{rotulo}{REPOR} {APAGADO}|{REPOR} {APAGADO}{' · '.join(resto)}{REPOR}"


def main():
    linha = montar_linha()
    try:
        sys.stdout.buffer.write((linha + "\n").encode("utf-8"))  # "·" e acento sem depender do sistema
        sys.stdout.flush()
    except (AttributeError, OSError):
        print(linha)


if __name__ == "__main__":
    main()
