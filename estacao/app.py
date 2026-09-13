"""Estação de Comando: o painel. Três abas: Foco, Radar da assistente e Máquina.

Lê o escritório onde está instalado; a única escrita é a seção `## Tarefas` do diário de hoje,
quando o dono marca ou cria uma tarefa aqui. Sem escritório, roda avulsa: as tarefas moram na pasta
avulsa e a aba da assistente explica o que ela mostraria. Não fala com a rede e não roda processo.
"""
from __future__ import annotations

from datetime import date
from functools import partial
from pathlib import Path

from rich.markup import escape
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Checkbox, Digits, Footer, Header, Input, Static, TabbedContent, TabPane

from . import escritorio, foco, hardware

VERDE, AMARELO, VERMELHO, APAGADO = "#3fb950", "#d29922", "#f85149", "#30363d"
NOME_FASE = {"foco": "FOCO", "pausa": "PAUSA", "fim": "BLOCO CONCLUÍDO"}
COR_FASE = {"foco": VERDE, "pausa": AMARELO, "fim": VERMELHO}
# barra do bloco: o trecho vivido na cor da fase, o que falta apagado (a pausa num tom próprio)
COR_FAIXA = {("foco", True): VERDE, ("pausa", True): AMARELO,
             ("foco", False): APAGADO, ("pausa", False): "#5c4a1e"}
ROTULO, VALOR = 10, 13  # aba Máquina: coluna do rótulo e coluna do valor à direita da barra
VARREDURA = 5  # com a aba Máquina à vista, varre os processos a cada 5 leituras (10 s)
TEXTO_AVULSO = """[b cyan]Aba da assistente[/]

Aqui aparece o que a sua assistente de IA sabe do seu trabalho: a última sessão, as pendências, as
frentes e a caixa de entrada.

Ela lê um escritório [b]Mnemosine[/b], a assistente pessoal que guarda memória, agenda e rotina em
arquivos na sua própria máquina. Conheça em [b]mnemosine.ia.br[/b]. Com a Estação instalada dentro
de um escritório (em [b]modulos/estacao-de-comando/[/b]), esta aba acende sozinha.

As outras abas funcionam sem ela: o Foco guarda as tarefas em
[dim]{pasta}[/dim]
e a Máquina lê o seu computador."""


def _cor(pct: float, amarelo: float = 75, vermelho: float = 90) -> str:
    return VERDE if pct < amarelo else (AMARELO if pct < vermelho else VERMELHO)


def _cor_temp(graus: float) -> str:
    return _cor(graus, 70, 85)


def _barra(pct: float, largura: int, cor: str) -> str:
    cheio = round(max(0.0, min(100.0, pct)) * largura / 100)
    return f"[{cor}]{'█' * cheio}[/][{APAGADO}]{'█' * (largura - cheio)}[/]"


def _linha_barra(rotulo: str, pct: float, valor: str, w: int, cor: str | None = None) -> str:
    largura = max(8, w - ROTULO - VALOR - 1)
    return f"{rotulo:<{ROTULO}}{_barra(pct, largura, cor or _cor(pct))} {valor:>{VALOR}}"


def _blocos(valores, sep: str = "") -> str:
    return sep.join(f"[{_cor(v)}]{hardware.bloco(v)}[/]" for v in valores)


def _historico(valores: list[float], largura: int) -> str:
    amostras = valores[-largura:]
    return " " * (largura - len(amostras)) + _blocos(amostras)


def _taxa(mb: float | None) -> str:
    if mb is None:
        return "medindo"
    return f"{mb * 1024:.0f} KB/s" if mb < 1 else f"{mb:.1f} MB/s"


def _duracao(segundos: float) -> str:
    dias, resto = divmod(int(segundos) // 60, 1440)
    horas, minutos = divmod(resto, 60)
    if dias:
        return f"{dias} d {horas} h"
    return f"{horas} h {minutos:02d} min" if horas else f"{minutos} min"


def _cartao_cpu(m: dict, w: int) -> str:
    nucleos = m["nucleos"]
    contagem = f"{len(nucleos)} lógicos" + (f" · {m['fisicos']} físicos" if m["fisicos"] else "")
    sep = " " if ROTULO + 2 * len(nucleos) + 2 + len(contagem) <= w else ""
    temp = m["temp_cpu"]
    return "\n".join([
        _linha_barra("uso", m["cpu"], f"{m['cpu']:.1f}%", w),
        f"{'núcleos':<{ROTULO}}{_blocos(nucleos, sep)}  [dim]{contagem}[/dim]",
        f"{'temp.':<{ROTULO}}" + (f"[{_cor_temp(temp)}]{temp:.0f} °C[/]" if temp is not None
                                  else f"[dim]{escape(m['temp_cpu_aviso'])}[/dim]"),
        f"{'histórico':<{ROTULO}}{_historico(m['hist_cpu'], w - ROTULO)}",
    ])


def _cartao_gpu(m: dict, w: int) -> str:
    g = m["gpu"]
    if g is None:
        return f"[dim]{escape(m['gpu_aviso'])}[/dim]"
    linhas = []
    if g["uso"] is not None:
        linhas.append(_linha_barra("uso", g["uso"], f"{g['uso']:.0f}%", w))
    if g["vram_total"]:
        linhas.append(_linha_barra("VRAM", 100 * g["vram_usada"] / g["vram_total"],
                                   f"{g['vram_usada']:.1f}/{g['vram_total']:.1f} GB", w))
    termica, energia = [], []
    if g["temp"] is not None:
        termica.append(f"[{_cor_temp(g['temp'])}]{g['temp']:.0f} °C[/]")
    if g["ventoinha"] is not None:
        termica.append(f"ventoinha {g['ventoinha']:.0f}%")
    if g["potencia"] is not None:
        energia.append(f"{g['potencia']:.0f} W" + (f" de {g['limite']:.0f} W" if g["limite"] else ""))
    if g["clock"]:
        energia.append(f"{g['clock']:.0f} MHz")
    if termica:
        linhas.append(f"{'temp.':<{ROTULO}}" + " · ".join(termica))
    if energia:
        linhas.append(f"{'energia':<{ROTULO}}" + " · ".join(energia))
    if m["hist_gpu"]:
        linhas.append(f"{'histórico':<{ROTULO}}{_historico(m['hist_gpu'], w - ROTULO)}")
    return "\n".join(linhas)


def _cartao_mem(m: dict, w: int) -> str:
    linhas = [_linha_barra("memória", m["ram"], f"{m['ram_usada']:.1f}/{m['ram_total']:.0f} GB", w)]
    if m["swap_total"]:
        linhas.append(_linha_barra("swap", m["swap"], f"{m['swap_usada']:.1f}/{m['swap_total']:.0f} GB", w))
    linhas += [
        _linha_barra(f"disco {m['unidade']}", m["disco"], f"{m['disco_livre']:.0f} GB livres", w,
                     _cor(m["disco"], 80)),
        f"{'E/S disco':<{ROTULO}}lê {_taxa(m['disco_ler'])} · grava {_taxa(m['disco_gravar'])}",
        f"{'rede':<{ROTULO}}↓ {_taxa(m['rede_baixa'])} · ↑ {_taxa(m['rede_sobe'])}",
    ]
    return "\n".join(linhas)


def _cartao_proc(m: dict, w: int) -> str:
    if not m["top"]:
        return "[dim]varrendo os processos (a lista chega na próxima varredura)[/dim]"
    largura = max(10, w - 18)
    linhas = [f"[dim]{'processo':<{largura}}{'CPU':>7} {'memória':>9}[/dim]"]
    for nome, uso, rss in m["top"]:
        curto = nome if len(nome) <= largura else nome[:largura - 1] + "…"
        linhas.append(f"{escape(f'{curto:<{largura}}')}[{_cor(uso)}]{uso:>6.1f}%[/] {rss:>6.2f} GB")
    return "\n".join(linhas)


class EstacaoApp(App):
    CSS_PATH = "estilo.tcss"
    BINDINGS = [
        Binding("p", "alternar_foco", "Iniciar/pausar"),
        Binding("r", "zerar_foco", "Zerar"),
        Binding("a", "atualizar", "Reler"),
        Binding("1", "aba('aba-foco')", "Foco", show=False),  # as abas já mostram o número
        Binding("2", "aba('aba-radar')", "Radar", show=False),
        Binding("3", "aba('aba-maquina')", "Máquina", show=False),
        Binding("q", "quit", "Sair"),
    ]

    def __init__(self, raiz: Path | None, pasta_avulsa: Path | None = None, **kwargs):
        super().__init__(**kwargs)
        self.raiz = raiz  # None = modo avulso: sem escritório, as tarefas moram na pasta avulsa
        self.avulso = raiz is None
        self.pasta_avulsa = Path(pasta_avulsa) if pasta_avulsa else escritorio.pasta_avulsa()
        self.ident = self._identidade()
        self.relogio = foco.Relogio()
        self._fase_anterior = None
        self._tarefas: list[escritorio.Tarefa] = []
        self._coletor = None
        self._lendo = self._pedir_processos = False
        self._leituras = 0
        self._texto_relogio = self._texto_radar = self._texto_maquina = ""
        self._titular()

    def _identidade(self) -> dict:
        return {"dono": "", "assistente": "Assistente"} if self.avulso else escritorio.identidade(self.raiz)

    def _titular(self) -> None:
        # tudo no título: com subtítulo, o cabeçalho do Textual põe um travessão no meio
        self.title = ("Estação de Comando" if self.avulso else
                      f"{self.ident['assistente']} · Estação de Comando · escritório de {self.ident['dono']}")

    def _caminho_hoje(self) -> Path | None:
        """O arquivo onde moram as tarefas de hoje: o diário do escritório ou, avulso, o da pasta avulsa."""
        if not self.avulso:
            return escritorio.caminho_diario(self.raiz, date.today())
        try:
            return escritorio.diario_avulso(self.pasta_avulsa, date.today())
        except OSError as erro:
            self.notify(f"Não consegui criar o arquivo de tarefas: {erro}", severity="error", markup=False)
            return None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="aba-foco"):
            with TabPane("1 Foco", id="aba-foco"):
                with Vertical(id="cartao-relogio", classes="cartao"):
                    yield Static(id="fase", classes="centro")
                    yield Digits("50:00", id="digitos")
                    yield Static(id="destino", classes="centro")
                    yield Static(id="barra-bloco")
                    yield Static(id="progresso", classes="centro")
                    with Horizontal(id="botoes"):
                        yield Button("Iniciar", id="b-alternar", variant="success", compact=True)
                        yield Button("Zerar", id="b-zerar", variant="error", compact=True)
                with Vertical(id="cartao-tarefas", classes="cartao"):
                    yield VerticalScroll(id="lista-tarefas")
                    yield Input(placeholder="+ tarefa de hoje (Enter grava no diário)", id="nova-tarefa",
                                compact=True)
            with TabPane(f"2 {self.ident['assistente']}", id="aba-radar"):
                with VerticalScroll():
                    yield Static(id="radar")
            with TabPane("3 Máquina", id="aba-maquina"):
                with VerticalScroll(id="maquina"):
                    for chave in ("cpu", "gpu", "mem", "proc"):
                        yield Static(id=f"maq-{chave}", classes="cartao")
                    yield Static(id="maq-rodape", classes="centro")
        yield Footer(compact=True, show_command_palette=False)

    async def on_mount(self) -> None:
        cartao = self.query_one("#cartao-relogio")
        cartao.border_title = "Bloco de foco"
        cartao.border_subtitle = f"{foco.CICLOS} ciclos · {foco.FOCO // 60} min + {foco.PAUSA // 60} de pausa"
        await self.action_atualizar()
        self._tique()
        self.set_interval(1.0, self._tique)
        self.set_interval(2.0, self._atualizar_maquina)
        self.set_interval(60.0, self._atualizar_radar)

    # ------------------------------------------------------------ ações

    def action_aba(self, aba: str) -> None:
        self.query_one(TabbedContent).active = aba

    def action_alternar_foco(self) -> None:
        self.relogio.alternar()
        self._tique()

    def action_zerar_foco(self) -> None:
        self.relogio.zerar()
        self._fase_anterior = None
        self._tique()

    async def action_atualizar(self) -> None:
        self.ident = self._identidade()
        self._titular()
        await self._carregar_tarefas()
        self._atualizar_radar()
        self._atualizar_maquina()

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if self.query_one(TabbedContent).active == "aba-maquina":
            self._atualizar_maquina(varrer=True)  # quem abre a aba vê os processos já, não daqui a 10 s

    def on_button_pressed(self, event: Button.Pressed) -> None:
        acao = {"b-alternar": self.action_alternar_foco, "b-zerar": self.action_zerar_foco}.get(event.button.id)
        if acao:
            acao()

    # ------------------------------------------------------------ aba 1: foco

    def _tique(self) -> None:
        seg = self.relogio.decorrido()
        nome, ciclo, resta = foco.fase(seg)
        if nome == "fim" and self.relogio.rodando:
            self.relogio.pausar()
        if self._fase_anterior not in (None, (nome, ciclo)):
            self.bell()
            self.notify(f"{NOME_FASE[nome]} · ciclo {ciclo}/{foco.CICLOS}")
        self._fase_anterior = (nome, ciclo)

        rodando, iniciado = self.relogio.rodando, self.relogio.iniciado
        estado = "rodando" if rodando else ("pausado" if iniciado else "pronto")
        if nome == "fim":
            titulo, destino = NOME_FASE[nome], "três ciclos de foco cumpridos"
        else:
            titulo = f"CICLO {ciclo} DE {foco.CICLOS} · {NOME_FASE[nome]}"
            destino = ("para a pausa" if nome == "foco"
                       else "para o próximo foco" if ciclo < foco.CICLOS else "para o fim do bloco")
        self.query_one("#fase", Static).update(f"[b {COR_FASE[nome]}]{titulo}[/] [dim]· {estado}[/dim]")

        digitos = self.query_one("#digitos", Digits)
        digitos.update(foco.relogio_texto(resta))
        classes = {f"fase-{nome}"} | (set() if rodando or nome == "fim" else {"parado"})
        if set(digitos.classes) != classes:
            digitos.set_classes(" ".join(classes))
        self.query_one("#destino", Static).update(f"[dim]{destino}[/dim]")

        barra = self.query_one("#barra-bloco", Static)
        barra.update("".join(f"[{COR_FAIXA[f, cheia]}]{'█' * n}[/]"
                             for f, cheia, n in foco.faixas(seg, barra.content_size.width or 40)))
        self.query_one("#progresso", Static).update(
            f"[dim]{seg * 100 // foco.TOTAL}% do bloco · faltam {foco.relogio_texto(foco.TOTAL - seg)}[/dim]")

        botao = self.query_one("#b-alternar", Button)
        botao.label = "Pausar" if rodando else ("Retomar" if iniciado and seg < foco.TOTAL else "Iniciar")
        botao.variant = "warning" if rodando else "success"
        botao.disabled = nome == "fim"
        self._texto_relogio = (f"Ciclo {ciclo}/{foco.CICLOS} · {NOME_FASE[nome]} · {estado} · "
                               f"{foco.relogio_texto(resta)} {destino}")

    async def _carregar_tarefas(self) -> None:
        lista = self.query_one("#lista-tarefas", VerticalScroll)
        entrada = self.query_one("#nova-tarefa", Input)
        await lista.remove_children()
        caminho = self._caminho_hoje()
        if caminho is None:
            self._tarefas = []
            entrada.disabled = True
            await lista.mount(Static("[dim]O diário de hoje ainda não existe. A assistente cria na abertura; "
                                     "depois tecle a.[/dim]"))
        else:
            self._tarefas = escritorio.tarefas_do_dia(caminho)
            entrada.disabled = False
            caixas = []
            for i, tarefa in enumerate(self._tarefas):
                caixa = Checkbox(Text(tarefa.texto), tarefa.feita)
                caixa.indice_tarefa = i
                caixas.append(caixa)
            if caixas:
                await lista.mount(*caixas)
            else:
                await lista.mount(Static("[dim]Nenhuma tarefa no diário de hoje. Escreva abaixo e tecle Enter.[/dim]"))
        self._atualizar_placar()

    def _atualizar_placar(self) -> None:
        feitas = sum(t.feita for t in self._tarefas)
        self.query_one("#cartao-tarefas").border_title = f"Tarefas de hoje · {feitas}/{len(self._tarefas)} feitas"

    async def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        i = getattr(event.checkbox, "indice_tarefa", None)
        if i is None or i >= len(self._tarefas) or self._tarefas[i].feita == event.value:
            return
        caminho = self._caminho_hoje()
        try:
            if caminho is None:
                raise ValueError("o diário de hoje sumiu (virou o dia?)")
            novas = escritorio.definir_tarefa(caminho, i, self._tarefas[i].texto, event.value)
        except (ValueError, OSError) as erro:
            self.notify(f"Não gravei no diário: {erro}", severity="error", markup=False)
            await self._carregar_tarefas()
            return
        mudou_fora = [t.texto for t in novas] != [t.texto for t in self._tarefas]
        self._tarefas = novas
        if mudou_fora:
            await self._carregar_tarefas()
        else:
            self._atualizar_placar()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        texto = " ".join(event.value.split())
        if not texto:
            return
        caminho = self._caminho_hoje()
        try:
            if caminho is None:
                raise ValueError("o diário de hoje ainda não existe")
            escritorio.adicionar_tarefa(caminho, texto)
        except (ValueError, OSError) as erro:
            self.notify(f"Não gravei no diário: {erro}", severity="error", markup=False)
            return
        event.input.value = ""
        await self._carregar_tarefas()
        event.input.focus()

    # ------------------------------------------------------------ aba 2: radar

    def _atualizar_radar(self) -> None:
        if self.avulso:
            self._texto_radar = TEXTO_AVULSO.format(pasta=escape(str(self.pasta_avulsa / "tarefas")))
            self.query_one("#radar", Static).update(self._texto_radar)
            return
        e = escape
        linhas = [f"[b cyan]{e(self.ident['assistente'])}[/] [dim]· escritório de {e(self.ident['dono'])}[/dim]", ""]

        sessao, proximo = escritorio.ultima_sessao(self.raiz)
        linhas.append("[b]ÚLTIMA SESSÃO[/b]")
        if sessao:
            linhas += [f"#{e(sessao.id)} [dim]· {e(sessao.quando)}[/dim]", e(sessao.titulo)]
            if proximo:
                linhas.append(f"[dim]a próxima é a #{e(proximo)}[/dim]")
            if sessao.pendencias:
                linhas += ["", "[b]PENDÊNCIAS[/b]"] + [f"[yellow]•[/yellow] {e(p)}" for p in sessao.pendencias[:10]]
        else:
            linhas.append("[dim]nenhuma ainda na Janela de Contexto[/dim]")

        linhas += ["", "[b]FRENTES[/b]"]
        lista_frentes = escritorio.frentes(self.raiz)
        for f in lista_frentes:
            estado = f["estado"] or "sem estado"
            linhas.append(f"[green]●[/green] [b]{e(f['frente'])}[/b] [dim]({e(estado)})[/dim] → {e(f['proximo'])}")
        if not lista_frentes:
            linhas.append("[dim]nenhuma frente mapeada[/dim]")

        caixa = escritorio.caixa_de_entrada(self.raiz)
        linhas += ["", f"[b]CAIXA DE ENTRADA[/b] {len(caixa)} aberto(s)"]
        linhas += [f"• {e(i['o_que'])} [dim]{e(i['prazo'])}[/dim]" for i in caixa[:5]]

        self._texto_radar = "\n".join(linhas)
        self.query_one("#radar", Static).update(self._texto_radar)

    # ------------------------------------------------------------ aba 3: máquina

    def _atualizar_maquina(self, varrer: bool = False) -> None:
        """Agenda uma leitura numa thread, porque a varredura de processos custa ~0,4 s no Windows e
        não pode congelar a tela. Processos: na 1a leitura (arma a régua), ao abrir a aba e, com ela
        à vista, a cada 10 s. Fora dela, só o barato (CPU, GPU, memória, disco, rede)."""
        self._pedir_processos |= varrer
        if self._lendo:  # a leitura anterior ainda não voltou: não empilha
            return
        self._lendo = True
        self._leituras += 1
        visivel = self.query_one(TabbedContent).active == "aba-maquina"
        processos = self._leituras == 1 or (visivel and (self._pedir_processos or self._leituras % VARREDURA == 0))
        if processos:
            self._pedir_processos = False
        self.run_worker(partial(self._ler_maquina, processos), thread=True, group="maquina")

    def _ler_maquina(self, processos: bool) -> None:  # roda na thread
        try:
            if self._coletor is None:
                self._coletor = hardware.Coletor(self.raiz or self.pasta_avulsa)
            resultado = self._coletor.ler(processos=processos)
        except Exception as erro:  # telemetria nunca derruba o painel
            resultado = erro
        try:
            self.call_from_thread(self._mostrar_maquina, resultado)
        except RuntimeError:  # o painel fechou no meio da leitura
            pass

    def _mostrar_maquina(self, m: dict | Exception) -> None:
        self._lendo = False
        cartoes = {c: self.query_one(f"#maq-{c}", Static) for c in ("cpu", "gpu", "mem", "proc")}
        if isinstance(m, Exception):
            self._texto_maquina = f"[red]Telemetria indisponível:[/red] {escape(str(m))}"
            cartoes["cpu"].update(self._texto_maquina)
            return
        w = cartoes["cpu"].content_size.width or 60
        titulos = {
            "cpu": (f"CPU · {m['cpu_nome']}", None),
            "gpu": (f"GPU · {m['gpu_nome']}" if m["gpu_nome"] else "GPU",
                    f"driver {m['gpu_driver']}" if m["gpu_driver"] else None),
            "mem": ("Memória · disco · rede", None),
            "proc": (f"Processos · {m['processos']}", f"ligado há {_duracao(m['ligado'])}"),
        }
        textos = {"cpu": _cartao_cpu(m, w), "gpu": _cartao_gpu(m, w),
                  "mem": _cartao_mem(m, w), "proc": _cartao_proc(m, w)}
        for chave, cartao in cartoes.items():
            titulo, subtitulo = titulos[chave]
            cartao.border_title = escape(titulo)
            cartao.border_subtitle = subtitulo
            cartao.update(textos[chave])
        rodape = f"[dim]{escape(m['sistema'])} · Python {m['python']} · atualiza a cada 2 s[/dim]"
        self.query_one("#maq-rodape", Static).update(rodape)
        self._texto_maquina = "\n".join([f"{titulos[k][0]}\n{textos[k]}" for k in textos] + [rodape])


def main() -> None:
    # instalada dentro de um escritório, é ele; senão, o escritório de onde foi chamada; senão, avulsa
    raiz = escritorio.achar_raiz(Path(__file__)) or escritorio.achar_raiz(Path.cwd())
    EstacaoApp(raiz).run()
