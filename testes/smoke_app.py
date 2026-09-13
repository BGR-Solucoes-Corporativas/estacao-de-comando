"""Smoke do painel com o piloto do Textual (precisa de textual e psutil instalados).

Duas rodadas encadeadas: a 1a abre o painel, troca de aba, liga o relógio, cria e marca tarefas; a
2a abre um painel NOVO sobre o diário que a 1a deixou e confere que ele mostra esse estado. A prova
é no destino, o arquivo do diário. Sai com código diferente de zero se qualquer conferência falhar.

Rodar: python3 modulos/estacao-de-comando/testes/smoke_app.py
"""
import asyncio
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

MODULO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(MODULO), str(MODULO / "testes")]

from estacao.app import EstacaoApp, _cartao_proc  # noqa: E402
from textual.content import Content  # noqa: E402
from test_estacao import montar  # noqa: E402
from textual.widgets import Button, Checkbox, Digits, Footer, Input, TabbedContent  # noqa: E402

falhas = []


def confere(condicao, mensagem):
    print(("ok     " if condicao else "FALHA  ") + mensagem)
    if not condicao:
        falhas.append(mensagem)


async def espera(pilot, condicao, segundos=8.0):
    """A leitura da máquina roda numa thread: espera o resultado chegar à tela, sem dormir às cegas."""
    for _ in range(int(segundos / 0.1)):
        if condicao():
            return True
        await pilot.pause(0.1)
    return condicao()


async def rodada_1(raiz, diario):
    app = EstacaoApp(raiz)
    async with app.run_test(size=(90, 40)) as pilot:
        await pilot.pause()
        confere(app.title.startswith("Clio"), f"título com o nome da assistente: {app.title!r}")
        confere([c.value for c in app.query(Checkbox)] == [False, True],
                "as tarefas do diário aparecem com o estado do arquivo")
        confere("Ciclo 1/3" in app._texto_relogio and "pronto" in app._texto_relogio, "relógio parado no ciclo 1")
        confere(app.query_one(Digits).value == "50:00", "dígitos grandes mostram o que falta da fase")

        # layout: o relógio ocupa a largura, e botões e campo de tarefa têm uma linha só
        confere(app.query_one("#barra-bloco").size.width >= 90 * 0.8,
                f"barra do bloco usa a largura toda ({app.query_one('#barra-bloco').size.width} de 90)")
        confere(app.query_one("#nova-tarefa", Input).size.height == 1, "campo de tarefa com uma linha")
        confere(app.query_one("#b-alternar", Button).size.height == 1, "botões com uma linha")
        confere(not app.query_one(Footer).show_command_palette, "rodapé sem o atalho da paleta")

        await pilot.press("p")
        confere(app.relogio.rodando and "rodando" in app._texto_relogio, "p inicia o foco")
        confere(str(app.query_one("#b-alternar", Button).label) == "Pausar", "rodando, o botão vira Pausar")
        await pilot.press("p")
        confere(not app.relogio.rodando and "pausado" in app._texto_relogio, "p de novo pausa")

        for tecla, aba in (("2", "aba-radar"), ("3", "aba-maquina"), ("1", "aba-foco")):
            await pilot.press(tecla)
            await pilot.pause()
            confere(app.query_one(TabbedContent).active == aba, f"tecla {tecla} abre {aba}")
        confere("#7" in app._texto_radar and "revisar o fluxo de caixa" in app._texto_radar,
                "radar mostra a última sessão e as pendências")
        confere("Loja" in app._texto_radar and "pagar boleto" in app._texto_radar
                and "coisa de outra seção" not in app._texto_radar, "radar mostra frentes e só os abertos da caixa")
        await espera(pilot, lambda: "CPU" in app._texto_maquina)
        confere("CPU" in app._texto_maquina and "indisponível" not in app._texto_maquina,
                "máquina lê CPU, memória e disco")
        confere(all(t in app._texto_maquina for t in ("GPU", "Processos", "rede", "histórico")),
                "máquina mostra GPU (ou o aviso dela), rede, histórico e processos")
        # abrir a aba varre os processos na hora (a 1a leitura, na abertura do painel, armou a régua)
        app.action_aba("aba-foco")
        await pilot.pause()
        app.action_aba("aba-maquina")
        confere(await espera(pilot, lambda: "varrendo os processos" not in app._texto_maquina
                             and not app._lendo), "ao abrir a aba Máquina a lista de processos chega")
        inicio = time.perf_counter()
        app._atualizar_maquina(varrer=True)
        gasto = time.perf_counter() - inicio
        confere(gasto < 0.05, f"a leitura não segura a tela: agendar custou {gasto * 1000:.1f} ms")
        confere(await espera(pilot, lambda: not app._lendo), "a leitura agendada volta da thread")

        entrada = app.query_one("#nova-tarefa", Input)
        entrada.focus()
        entrada.value = "ligar pra Ana"
        await pilot.press("enter")
        await pilot.pause()
        confere("- [ ] ligar pra Ana" in diario.read_text(encoding="utf-8"),
                "Enter grava a tarefa nova NO DIÁRIO (destino)")

        primeira = list(app.query(Checkbox))[0]
        primeira.focus()
        await pilot.press("space")
        await pilot.pause()
        confere("- [x] comprar pão" in diario.read_text(encoding="utf-8"),
                "marcar a caixa grava [x] NO DIÁRIO (destino)")


async def rodada_2(raiz):
    app = EstacaoApp(raiz)
    async with app.run_test(size=(90, 40)) as pilot:
        await pilot.pause()
        confere([(t.texto, t.feita) for t in app._tarefas]
                == [("comprar pão", True), ("regar plantas", True), ("ligar pra Ana", False)],
                "2a rodada: painel novo lê o estado que a 1a deixou no diário")
        confere([c.value for c in app.query(Checkbox)] == [True, True, False],
                "2a rodada: as caixas refletem o arquivo")


async def rodada_avulsa(pasta):
    """Sem escritório: título genérico, aba da assistente com o convite, tarefas na pasta avulsa. Dois
    painéis encadeados: o 2o lê o que o 1o gravou."""
    arquivo = pasta / "tarefas" / f"{date.today().isoformat()}.md"
    app = EstacaoApp(None, pasta_avulsa=pasta)
    async with app.run_test(size=(90, 40)) as pilot:
        await pilot.pause()
        confere(app.title == "Estação de Comando", f"avulso: título sem escritório: {app.title!r}")
        confere("mnemosine.ia.br" in app._texto_radar, "avulso: a aba da assistente mostra o convite")
        entrada = app.query_one("#nova-tarefa", Input)
        confere(not entrada.disabled, "avulso: o campo de tarefa está ativo")
        entrada.focus()
        entrada.value = "primeira tarefa avulsa"
        await pilot.press("enter")
        await pilot.pause()
        confere(arquivo.is_file() and "- [ ] primeira tarefa avulsa" in arquivo.read_text(encoding="utf-8"),
                "avulso: Enter grava a tarefa NO ARQUIVO da pasta avulsa (destino)")
        await espera(pilot, lambda: "CPU" in app._texto_maquina)
        confere("indisponível" not in app._texto_maquina and "CPU" in app._texto_maquina,
                "avulso: a aba Máquina funciona")
    app = EstacaoApp(None, pasta_avulsa=pasta)
    async with app.run_test(size=(90, 40)) as pilot:
        await pilot.pause()
        confere([t.texto for t in app._tarefas] == ["primeira tarefa avulsa"],
                "avulso, 2a rodada: painel novo lê a tarefa que o 1o deixou")


async def rodada_caminho_frio(base):
    """O que só roda quando algo dá errado, forçado de verdade e conferido no destino (a tela)."""
    bloqueio = base / "arquivo-no-caminho"
    bloqueio.write_text("x", encoding="utf-8")
    app = EstacaoApp(None, pasta_avulsa=bloqueio / "sub")  # o pai é arquivo: criar a pasta tem de falhar
    async with app.run_test(size=(90, 40)) as pilot:
        await pilot.pause()
        avisos = [str(n.message) for n in app._notifications]
        confere(any("Não consegui criar o arquivo de tarefas" in a for a in avisos),
                "caminho frio: pasta avulsa impossível vira aviso, e o painel segue de pé")
    texto = _cartao_proc({"top": [("[b]proc[/b]", 1.0, 0.1)]}, 60)
    confere("[b]proc[/b]" in Content.from_markup(texto).plain,
            "nome de processo com colchete aparece como texto, não vira marcação")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        hoje = date.today()
        raiz = montar(Path(tmp) / "escritorio", hoje)
        diario = next((raiz / "agenda" / "diario").rglob(f"{hoje.isoformat()}.md"))
        asyncio.run(rodada_1(raiz, diario))
        asyncio.run(rodada_2(raiz))
        asyncio.run(rodada_avulsa(Path(tmp) / "avulsa"))
        asyncio.run(rodada_caminho_frio(Path(tmp)))
    if falhas:
        sys.exit(f"SMOKE FALHOU: {len(falhas)} conferência(s)")
    print("SMOKE OK")


if __name__ == "__main__":
    main()
