"""O que o painel sabe do escritório onde está instalado.

Tudo aqui é leitura de arquivo do próprio escritório, com uma exceção: a seção `## Tarefas` do
diário de hoje, que o painel marca e acrescenta quando o dono pede. Sem escritório (modo avulso),
as tarefas moram num arquivo por dia na pasta avulsa, criado pelo próprio painel. Só biblioteca
padrão; nada fala com a rede nem roda processo.
"""
from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

VAZIO = "[A PREENCHER"


@dataclass
class Sessao:
    id: str
    quando: str
    titulo: str
    pendencias: list[str] = field(default_factory=list)


@dataclass
class Tarefa:
    texto: str
    feita: bool
    linha: int  # índice da linha no arquivo do diário


def achar_raiz(inicio: Path) -> Path | None:
    """Sobe as pastas a partir de `inicio` até achar o escritório (CLAUDE.md com assistente-pessoal/ ao lado)."""
    atual = Path(inicio).resolve()
    for pasta in (atual, *atual.parents):
        if (pasta / "CLAUDE.md").is_file() and (pasta / "assistente-pessoal").is_dir():
            return pasta
    return None


def _ler(caminho: Path) -> str:
    try:
        return caminho.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _campo(padrao: str, texto: str) -> str | None:
    m = re.search(padrao, texto)
    if not m:
        return None
    valor = m.group(1).strip()
    return None if not valor or VAZIO in valor else valor


def _limpo(texto: str) -> str:
    """Tira a marcação de negrito e de código, que no painel só atrapalha a leitura."""
    return texto.replace("**", "").replace("`", "").strip()


def identidade(raiz: Path) -> dict:
    """Nome do dono (CLAUDE.md) e da assistente (COMPORTAMENTO.md). Campo em branco não vira nome inventado."""
    claude = _ler(raiz / "CLAUDE.md")
    comportamento = _ler(raiz / "assistente-pessoal" / "COMPORTAMENTO.md")
    dono = _campo(r"\*\*Nome do dono:\*\*[ \t]*([^\r\n]+)", claude)
    assistente = (_campo(r"\*\*Essência\.\*\*\s*É (?:a|o) \*\*([^*]+)\*\*", comportamento)
                  or _campo(r"\*\*Nome padrão:\*\*\s*\*\*([^*]+)\*\*", comportamento))
    return {"dono": dono or "o dono", "assistente": assistente or "Assistente"}


_SESSAO = re.compile(r"^### Sessão #(\d+) · ([^\r\n]+)\r?\n\*\*(.+?)\*\*([^\r\n]*)", re.M)


def ultima_sessao(raiz: Path) -> tuple[Sessao | None, str | None]:
    """A sessão mais recente da Janela de Contexto do COMPORTAMENTO.md, e o próximo ID."""
    texto = _ler(raiz / "assistente-pessoal" / "COMPORTAMENTO.md")
    proximo = _campo(r"\*\*Próximo ID de sessão:\*\*\s*(\d+)", texto)
    m = _SESSAO.search(texto)
    if not m:
        return None, proximo
    pendencias = []
    p = re.search(r"\*\*Pendências:\*\*\s*(.+)", m.group(4))
    if p:
        pendencias = [_limpo(x).rstrip(".") for x in p.group(1).split(";") if _limpo(x)]
    return Sessao(m.group(1), m.group(2).strip(), _limpo(m.group(3)), pendencias), proximo


def _tabela(texto: str, secao: str | None = None) -> list[dict]:
    """Linhas da primeira tabela markdown do texto (ou da seção `## secao`), como dicionários pelo cabeçalho."""
    if secao is not None:
        m = re.search(r"^## %s[ \t]*\r?$(.*?)(?=^## |\Z)" % re.escape(secao), texto, re.M | re.S)
        texto = m.group(1) if m else ""
    cabecalho, linhas = None, []
    for bruta in texto.splitlines():
        s = bruta.strip()
        if not s.startswith("|"):
            if cabecalho:
                break
            continue
        celulas = [c.strip() for c in s.strip("|").split("|")]
        if cabecalho is None:
            cabecalho = celulas
        elif all(set(c) <= set("-: ") for c in celulas):
            continue  # separador do cabeçalho, ou linha toda em branco
        else:
            linhas.append(dict(zip(cabecalho, celulas)))
    return linhas


def _coluna(linha: dict, prefixo: str) -> str:
    for chave, valor in linha.items():
        if chave.lower().startswith(prefixo):
            return valor
    return ""


def frentes(raiz: Path) -> list[dict]:
    """As frentes do `frentes.md` (módulo produtividade): nome, estado e próximo passo."""
    saida = []
    for linha in _tabela(_ler(raiz / "frentes.md")):
        nome = _limpo(next(iter(linha.values()), ""))
        if nome:
            saida.append({"frente": nome, "estado": _coluna(linha, "estado"),
                          "proximo": _limpo(_coluna(linha, "próximo"))})
    return saida


def caixa_de_entrada(raiz: Path) -> list[dict]:
    """Itens da seção `## Abertos` da caixa de entrada que ainda não foram feitos."""
    saida = []
    for linha in _tabela(_ler(raiz / "caixa-de-entrada.md"), "Abertos"):
        o_que = _limpo(_coluna(linha, "o que"))
        if o_que and _coluna(linha, "status").lower() != "feito":
            saida.append({"o_que": o_que, "frente": _coluna(linha, "frente"), "prazo": _coluna(linha, "prazo")})
    return saida


# ---------------------------------------------------------------- tarefas do dia (diário)

def caminho_diario(raiz: Path, dia: date) -> Path | None:
    """O arquivo do diário do dia (`agenda/diario/AAAA/<mês>/<decêndio>/AAAA-MM-DD.md`), se já existe."""
    achados = sorted((raiz / "agenda" / "diario" / f"{dia:%Y}").glob(f"*/*/{dia.isoformat()}.md"))
    return achados[0] if achados else None


def pasta_avulsa() -> Path:
    """Onde o modo avulso guarda as tarefas: a variável `ESTACAO_PASTA`, ou `.estacao-de-comando` na
    pasta do usuário."""
    return Path(os.environ.get("ESTACAO_PASTA") or Path.home() / ".estacao-de-comando")


def diario_avulso(pasta: Path, dia: date) -> Path:
    """O arquivo de tarefas do dia no modo avulso (`<pasta>/tarefas/AAAA-MM-DD.md`), criado na
    primeira vez e nunca sobrescrito depois."""
    caminho = Path(pasta) / "tarefas" / f"{dia.isoformat()}.md"
    if not caminho.exists():
        caminho.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(caminho, "x", encoding="utf-8", newline="") as f:
                f.write(f"# Tarefas de {dia:%d/%m/%Y}\n\n## Tarefas\n\n")
        except FileExistsError:  # outro painel criou no mesmo instante: vale o dele
            pass
    return caminho


_TAREFA = re.compile(r"\s*- \[([ xX])\]\s+(.*\S)")


def _linhas(caminho: Path) -> list[str]:
    # newline="" preserva o fim de linha do arquivo (LF ou CRLF) na volta
    with open(caminho, encoding="utf-8", newline="") as f:
        return f.read().splitlines(keepends=True)


def _secao_tarefas(linhas: list[str]) -> tuple[int, int] | None:
    inicio = next((i for i, l in enumerate(linhas) if l.strip() == "## Tarefas"), None)
    if inicio is None:
        return None
    fim = next((j for j in range(inicio + 1, len(linhas)) if re.match(r"#{1,2} ", linhas[j])), len(linhas))
    return inicio, fim


def _tarefas(linhas: list[str]) -> list[Tarefa]:
    faixa = _secao_tarefas(linhas)
    if faixa is None:
        return []
    saida = []
    for i in range(faixa[0] + 1, faixa[1]):
        m = _TAREFA.match(linhas[i])
        if m:
            saida.append(Tarefa(m.group(2), m.group(1) != " ", i))
    return saida


def tarefas_do_dia(caminho: Path) -> list[Tarefa]:
    return _tarefas(_linhas(caminho))


def _gravar(caminho: Path, linhas: list[str]) -> None:
    """Grava inteiro num temporário ao lado e troca de uma vez: fica o arquivo novo ou o antigo, nunca metade."""
    fd, temporario = tempfile.mkstemp(dir=caminho.parent, prefix=".estacao-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write("".join(linhas))
        os.replace(temporario, caminho)
    except BaseException:
        try:
            os.unlink(temporario)
        except OSError:
            pass
        raise


def definir_tarefa(caminho: Path, indice: int, texto: str, feita: bool) -> list[Tarefa]:
    """Marca ou desmarca uma tarefa, relendo o arquivo antes: se ela mudou lá, recusa em vez de gravar por cima."""
    linhas = _linhas(caminho)
    tarefas = _tarefas(linhas)
    alvo = tarefas[indice] if indice < len(tarefas) and tarefas[indice].texto == texto else None
    if alvo is None:
        alvo = next((t for t in tarefas if t.texto == texto), None)
    if alvo is None:
        raise ValueError("a tarefa mudou no diário desde a última leitura; tecle a para reler")
    if alvo.feita != feita:
        linhas[alvo.linha] = re.sub(r"\[[ xX]\]", "[x]" if feita else "[ ]", linhas[alvo.linha], count=1)
        _gravar(caminho, linhas)
    return _tarefas(linhas)


def adicionar_tarefa(caminho: Path, texto: str) -> list[Tarefa]:
    """Acrescenta `- [ ] texto` no fim da seção `## Tarefas` do diário."""
    texto = " ".join(texto.split())
    if not texto:
        raise ValueError("tarefa vazia")
    linhas = _linhas(caminho)
    faixa = _secao_tarefas(linhas)
    if faixa is None:
        raise ValueError("o diário de hoje não tem a seção ## Tarefas")
    inicio, fim = faixa
    fim_de_linha = "\r\n" if linhas[inicio].endswith("\r\n") else "\n"
    ocupadas = [j for j in range(inicio + 1, fim) if linhas[j].strip()]
    if ocupadas:
        pos, novas = ocupadas[-1] + 1, [f"- [ ] {texto}{fim_de_linha}"]
    else:
        pos, novas = inicio + 1, [fim_de_linha, f"- [ ] {texto}{fim_de_linha}"]
    if not linhas[pos - 1].endswith(("\n", "\r")):
        linhas[pos - 1] += fim_de_linha
    linhas[pos:pos] = novas
    _gravar(caminho, linhas)
    return _tarefas(linhas)
