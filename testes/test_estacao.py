"""Testes da Estação de Comando que não precisam de nada instalado (só biblioteca padrão).

Cobrem a leitura do escritório, a escrita nas tarefas do diário (em duas rodadas encadeadas: a 2a
parte do arquivo que a 1a deixou no disco), o relógio do foco e as travas de segurança do próprio
módulo. Tudo roda duas vezes, com arquivos LF e CRLF. Sai com código diferente de zero se falhar.

Rodar: python3 modulos/estacao-de-comando/testes/test_estacao.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

MODULO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULO))

from estacao import escritorio, foco, hardware  # noqa: E402
from estacao.hardware import GB, MB  # noqa: E402

DIA = date(2026, 9, 12)

CLAUDE = "# Escritório\n\n- **Nome do dono:** Ana\n"

COMPORTAMENTO = """# Comportamento

- **Essência.** É a **Clio**, musa da história.

**Próximo ID de sessão:** 8

### Sessão #7 · 2026-09-10 09:00 → 11:00
**Planilha de custos fechada.** Conferida com o contador. **Pendências:** mandar ao sócio; revisar o **fluxo** de caixa.

### Sessão #6 · 2026-09-09 14:00 → 15:00
**Sessão antiga.** Nada.
"""

FRENTES = """# Mapa das frentes

| Frente | O que é | Estado | Últ. revisão | Próximo passo |
|---|---|---|---|---|
| Loja | Vendas online | girando | 2026-09-01 | subir fotos |
| Casa | Tarefas da vida | | 2026-09-01 | mutirão |
"""

CAIXA = """# Caixa de entrada

## Abertos

| # | Entrada | Origem | O que resolver | Frente | Tipo | Prazo | Status |
|---|---|---|---|---|---|---|---|
| 1 | 09/09 | e-mail | pagar boleto | Casa | reativa | 15/09 | aberto |
| 2 | 09/09 | conversa | ligar pro contador | Loja | reativa | | feito |
| | | | | | | | |

## Histórico (feitos)

| # | Entrada | Origem | O que resolver | Frente | Tipo | Prazo | Status |
|---|---|---|---|---|---|---|---|
| 0 | 01/09 | x | coisa de outra seção | Casa | reativa | | aberto |
"""

DIARIO = """---
type: diario
---

# Diário

## Tarefas

- [ ] comprar pão
- [x] regar plantas

## Compromissos (calendário)

## Linha do tempo

[00:00]
"""


def montar(base: Path, dia: date, diario: str | None = DIARIO, eol: str = "\n") -> Path:
    """Escritório de mentira com as peças que o painel lê. Não planta nada que o código deva produzir."""
    arquivos = {
        "CLAUDE.md": CLAUDE,
        "assistente-pessoal/COMPORTAMENTO.md": COMPORTAMENTO,
        "frentes.md": FRENTES,
        "caixa-de-entrada.md": CAIXA,
    }
    if diario is not None:
        arquivos[f"agenda/diario/{dia:%Y}/{dia:%m}-mes/D1/{dia.isoformat()}.md"] = diario
    for relativo, texto in arquivos.items():
        caminho = base / relativo
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(texto.replace("\n", eol).encode("utf-8"))
    return base


class EscritorioLF(unittest.TestCase):
    EOL = "\n"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.raiz = montar(self.base / "escritorio", DIA, eol=self.EOL)
        self.diario = escritorio.caminho_diario(self.raiz, DIA)

    def tearDown(self):
        self._tmp.cleanup()

    def test_acha_a_raiz_subindo_e_nao_inventa_fora_dela(self):
        funda = self.raiz / "modulos" / "estacao-de-comando" / "estacao"
        funda.mkdir(parents=True)
        self.assertEqual(escritorio.achar_raiz(funda / "app.py"), self.raiz.resolve())
        self.assertIsNone(escritorio.achar_raiz(self.base / "fora" / "x.py"))

    def test_identidade(self):
        self.assertEqual(escritorio.identidade(self.raiz), {"dono": "Ana", "assistente": "Clio"})

    def test_identidade_em_branco_nao_vira_nome_inventado(self):
        (self.raiz / "CLAUDE.md").write_text("- **Nome do dono:** [A PREENCHER]\n", encoding="utf-8")
        (self.raiz / "assistente-pessoal" / "COMPORTAMENTO.md").write_text("sem nome\n", encoding="utf-8")
        self.assertEqual(escritorio.identidade(self.raiz), {"dono": "o dono", "assistente": "Assistente"})

    def test_ultima_sessao_e_pendencias_da_janela(self):
        sessao, proximo = escritorio.ultima_sessao(self.raiz)
        self.assertEqual((sessao.id, sessao.quando, sessao.titulo, proximo),
                         ("7", "2026-09-10 09:00 → 11:00", "Planilha de custos fechada.", "8"))
        self.assertEqual(sessao.pendencias, ["mandar ao sócio", "revisar o fluxo de caixa"])

    def test_frentes(self):
        self.assertEqual([(f["frente"], f["estado"], f["proximo"]) for f in escritorio.frentes(self.raiz)],
                         [("Loja", "girando", "subir fotos"), ("Casa", "", "mutirão")])

    def test_caixa_de_entrada_so_os_abertos_da_secao_abertos(self):
        self.assertEqual([i["o_que"] for i in escritorio.caixa_de_entrada(self.raiz)], ["pagar boleto"])

    def test_le_as_tarefas_do_dia(self):
        self.assertEqual([(t.texto, t.feita) for t in escritorio.tarefas_do_dia(self.diario)],
                         [("comprar pão", False), ("regar plantas", True)])

    def test_estado_encadeado_em_duas_rodadas(self):
        # a 1a rodada marca; a 2a parte do que a 1a deixou no disco (relido, não da memória)
        escritorio.definir_tarefa(self.diario, 0, "comprar pão", True)
        self.assertEqual([t.feita for t in escritorio.tarefas_do_dia(self.diario)], [True, True])
        escritorio.definir_tarefa(self.diario, 1, "regar plantas", False)
        self.assertEqual([t.feita for t in escritorio.tarefas_do_dia(self.diario)], [True, False])

    def test_adicionar_mexe_so_numa_linha_e_respeita_o_fim_de_linha(self):
        eol = self.EOL.encode()
        antes = self.diario.read_bytes()
        escritorio.adicionar_tarefa(self.diario, "ligar pra\n Ana")
        marca = "- [x] regar plantas".encode("utf-8") + eol
        self.assertEqual(self.diario.read_bytes(),
                         antes.replace(marca, marca + "- [ ] ligar pra Ana".encode("utf-8") + eol))

    def test_secao_vazia_ganha_linha_em_branco_depois_do_titulo(self):
        self.diario.write_bytes("# D\n\n## Tarefas\n\n## Compromissos\n".replace("\n", self.EOL).encode())
        escritorio.adicionar_tarefa(self.diario, "x")
        self.assertEqual(self.diario.read_bytes(),
                         "# D\n\n## Tarefas\n\n- [ ] x\n\n## Compromissos\n".replace("\n", self.EOL).encode())

    def test_tarefa_que_mudou_no_arquivo_nao_e_gravada_por_cima(self):
        antes = self.diario.read_bytes()
        with self.assertRaises(ValueError):
            escritorio.definir_tarefa(self.diario, 0, "tarefa que outro apagou", True)
        self.assertEqual(self.diario.read_bytes(), antes)

    def test_sem_secao_tarefas_recusa_em_vez_de_inventar(self):
        self.diario.write_bytes(b"# D\n\n## Linha do tempo\n")
        with self.assertRaises(ValueError):
            escritorio.adicionar_tarefa(self.diario, "x")

    def test_diario_que_nao_existe(self):
        self.assertIsNone(escritorio.caminho_diario(self.raiz, date(2026, 9, 13)))

    def test_nao_deixa_temporario_para_tras(self):
        escritorio.adicionar_tarefa(self.diario, "x")
        self.assertEqual([p.name for p in self.diario.parent.iterdir()], [self.diario.name])


class EscritorioCRLF(EscritorioLF):
    EOL = "\r\n"


class Foco(unittest.TestCase):
    def test_fases_nas_bordas(self):
        casos = {0: ("foco", 1, 3000), 2999: ("foco", 1, 1), 3000: ("pausa", 1, 600),
                 3599: ("pausa", 1, 1), 3600: ("foco", 2, 3000), 10200: ("pausa", 3, 600),
                 10799: ("pausa", 3, 1), 10800: ("fim", 3, 0), 99999: ("fim", 3, 0)}
        for segundos, esperado in casos.items():
            self.assertEqual(foco.fase(segundos), esperado, segundos)

    def test_relogio_so_conta_rodando(self):
        agora = [0.0]
        r = foco.Relogio(agora=lambda: agora[0])
        r.iniciar()
        agora[0] = 100
        r.pausar()
        agora[0] = 150
        self.assertEqual(r.decorrido(), 100)
        r.iniciar()
        agora[0] = 160
        r.iniciar()  # iniciar de novo não zera nem conta em dobro
        agora[0] = 170
        self.assertEqual(r.decorrido(), 120)
        agora[0] = 1e6
        self.assertEqual(r.decorrido(), foco.TOTAL)
        r.zerar()
        self.assertEqual((r.decorrido(), r.rodando, r.iniciado), (0, False, False))

    def test_iniciar_e_pausar_no_mesmo_segundo_ainda_conta_como_iniciado(self):
        agora = [0.0]
        r = foco.Relogio(agora=lambda: agora[0])
        self.assertFalse(r.iniciado)
        r.iniciar()
        agora[0] = 0.2
        r.pausar()
        self.assertEqual((r.decorrido(), r.rodando, r.iniciado), (0, False, True))

    def test_texto_do_relogio(self):
        self.assertEqual([foco.relogio_texto(s) for s in (0, 61, 3600, 10799)],
                         ["00:00", "01:01", "1:00:00", "2:59:59"])

    def test_faixas_da_barra(self):
        for largura in (1, 7, 60, 83):
            for segundos in (0, 1234, 3600, foco.TOTAL):
                self.assertEqual(sum(n for *_, n in foco.faixas(segundos, largura)), largura)
        self.assertFalse(any(cheia for _, cheia, _ in foco.faixas(0, 60)))
        self.assertTrue(all(cheia for _, cheia, _ in foco.faixas(foco.TOTAL, 60)))
        self.assertEqual(sum(n for f, _, n in foco.faixas(0, 60) if f == "pausa"), 9)  # 3 colunas por ciclo
        self.assertEqual(sum(n for _, cheia, n in foco.faixas(3600, 60) if cheia), 20)  # um ciclo = um terço


class FakeProc:
    def __init__(self, ps, pid):
        self._ps, self.pid = ps, pid

    def _dados(self):
        dados = self._ps.procs.get(self.pid)
        if dados is None or dados.get("falha"):
            raise FakePs.Error(self.pid)
        return dados

    def cpu_percent(self, interval=None):
        return self._dados()["cpu"]

    def name(self):
        return self._dados()["nome"]

    def memory_info(self):
        return SimpleNamespace(rss=self._dados()["rss"])


class FakePs:
    """psutil de mentira: só a superfície que o coletor usa."""

    class Error(Exception):
        pass

    def __init__(self):
        self.nucleos = [10.0, 30.0]
        self.disco = SimpleNamespace(read_bytes=0, write_bytes=0)
        self.rede = SimpleNamespace(bytes_recv=0, bytes_sent=0)
        self.procs = {}
        self.leituras_swap = 0

    def cpu_percent(self, interval=None, percpu=False):
        return list(self.nucleos) if percpu else sum(self.nucleos) / len(self.nucleos)

    def cpu_count(self, logical=True):
        return len(self.nucleos) if logical else 1

    def virtual_memory(self):
        return SimpleNamespace(percent=50.0, used=8 * GB, total=16 * GB)

    def swap_memory(self):
        self.leituras_swap += 1
        return SimpleNamespace(percent=0.0, used=0, total=0)

    def disk_usage(self, caminho):
        return SimpleNamespace(percent=40.0, free=60 * GB, total=100 * GB)

    def disk_io_counters(self):
        return self.disco

    def net_io_counters(self):
        return self.rede

    def boot_time(self):
        return time.time() - 7200

    def pids(self):
        return list(self.procs)

    def Process(self, pid):
        if pid not in self.procs:
            raise FakePs.Error(pid)
        return FakeProc(self, pid)


class FakeNvml:
    """NVML de mentira: `sem` lista as leituras que esta placa "não suporta"."""

    class NVMLError(Exception):
        pass

    NVML_TEMPERATURE_GPU = 0
    NVML_CLOCK_GRAPHICS = 0

    def __init__(self, falha_init=False, sem=()):
        self.falha_init, self.sem = falha_init, set(sem)

    def _pode(self, leitura):
        if leitura in self.sem:
            raise self.NVMLError(f"{leitura}: Not Supported")

    def nvmlInit(self):
        if self.falha_init:
            raise self.NVMLError("Driver Not Loaded")

    def nvmlDeviceGetCount(self):
        return 1

    def nvmlDeviceGetHandleByIndex(self, i):
        return "placa-0"

    def nvmlDeviceGetName(self, h):
        return b"GeForce de teste"

    def nvmlSystemGetDriverVersion(self):
        return "591.86"

    def nvmlDeviceGetUtilizationRates(self, h):
        self._pode("uso")
        return SimpleNamespace(gpu=37, memory=10)

    def nvmlDeviceGetMemoryInfo(self, h):
        self._pode("memoria")
        return SimpleNamespace(used=1 * GB, total=4 * GB)

    def nvmlDeviceGetTemperature(self, h, sensor):
        self._pode("temp")
        return 55

    def nvmlDeviceGetPowerUsage(self, h):
        self._pode("potencia")
        return 20000

    def nvmlDeviceGetEnforcedPowerLimit(self, h):
        self._pode("limite")
        return 70000

    def nvmlDeviceGetFanSpeed(self, h):
        self._pode("ventoinha")
        return 30

    def nvmlDeviceGetClockInfo(self, h, tipo):
        self._pode("clock")
        return 1620


class Maquina(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self._tmp.name)
        self.ps, self.t = FakePs(), [0.0]

    def tearDown(self):
        self._tmp.cleanup()

    def coletor(self, nvml=None):
        return hardware.Coletor(self.raiz, ps=self.ps, nvml=nvml, agora=lambda: self.t[0])

    def test_taxa_em_mb_por_segundo_e_contador_que_volta_nao_vira_negativo(self):
        c = self.coletor()
        m = c.ler()
        self.assertEqual((m["rede_baixa"], m["disco_gravar"]), (None, None))  # a 1a amostra só arma
        self.t[0] = 2.0
        self.ps.rede = SimpleNamespace(bytes_recv=4 * MB, bytes_sent=MB)
        self.ps.disco = SimpleNamespace(read_bytes=0, write_bytes=MB)
        m = c.ler()
        self.assertEqual((m["rede_baixa"], m["rede_sobe"], m["disco_ler"], m["disco_gravar"]),
                         (2.0, 0.5, 0.0, 0.5))
        self.t[0] = 4.0
        self.ps.rede = SimpleNamespace(bytes_recv=0, bytes_sent=MB)  # adaptador reiniciou: contador zerou
        m = c.ler()
        self.assertIsNone(m["rede_baixa"])
        self.assertEqual(m["rede_sobe"], 0.0)

    def test_historico_guarda_so_as_ultimas_amostras(self):
        c = self.coletor()
        for _ in range(hardware.HISTORICO + 5):
            m = c.ler()
        self.assertEqual(len(m["hist_cpu"]), hardware.HISTORICO)
        self.assertEqual(m["cpu"], 20.0)

    def test_top_processos(self):
        self.ps.procs = {0: {"nome": "System Idle Process", "cpu": 1500.0, "rss": 0},
                         4: {"nome": "render", "cpu": 100.0, "rss": 2 * GB},
                         8: {"nome": "editor", "cpu": 20.0, "rss": GB},
                         12: {"nome": "protegido", "cpu": 0.0, "rss": 0, "falha": True}}
        c = self.coletor()
        self.assertEqual(c.ler()["top"], [])  # a 1a varredura só arma a régua: nada de zeros inventados
        m = c.ler()
        self.assertEqual(m["top"], [("render", 50.0, 2.0), ("editor", 10.0, 1.0)])  # % da máquina: 2 núcleos
        self.ps.procs[4]["cpu"] = 0.0
        self.assertEqual(c.ler(processos=False)["top"], m["top"])  # sem varrer, repete a última lista
        self.ps.procs[4]["cpu"] = 100.0
        del self.ps.procs[8]  # processo que acabou entre duas varreduras
        m = c.ler()
        self.assertEqual(m["top"], [("render", 50.0, 2.0)])
        self.assertEqual(m["processos"], 3)

    def test_swap_e_relido_so_depois_da_validade(self):
        c = self.coletor()
        for instante in (0.0, 2.0, hardware.SWAP_VALIDADE - 1):
            self.t[0] = instante
            c.ler()
        self.assertEqual(self.ps.leituras_swap, 1)
        self.t[0] = hardware.SWAP_VALIDADE
        c.ler()
        self.assertEqual(self.ps.leituras_swap, 2)

    def test_gpu_sem_biblioteca_avisa_e_nao_derruba(self):
        m = self.coletor(nvml=None).ler()
        self.assertIsNone(m["gpu"])
        self.assertIn("nvidia-ml-py", m["gpu_aviso"])

    def test_gpu_sem_driver(self):
        m = self.coletor(nvml=FakeNvml(falha_init=True)).ler()
        self.assertIsNone(m["gpu"])
        self.assertIn("Driver Not Loaded", m["gpu_aviso"])

    def test_gpu_le_e_cada_leitura_falha_sozinha(self):
        m = self.coletor(nvml=FakeNvml(sem={"ventoinha"})).ler()
        g = m["gpu"]
        self.assertEqual((m["gpu_nome"], m["gpu_driver"]), ("GeForce de teste", "591.86"))
        self.assertEqual((g["uso"], g["temp"], g["vram_usada"], g["vram_total"], g["potencia"], g["limite"],
                          g["clock"]), (37, 55, 1.0, 4.0, 20.0, 70.0, 1620))
        self.assertIsNone(g["ventoinha"])
        self.assertEqual(m["hist_gpu"], [37])

    def test_gpu_que_para_de_responder_avisa_e_volta(self):
        nvml = FakeNvml()
        c = self.coletor(nvml=nvml)
        nvml.sem = {"uso", "memoria", "temp", "potencia", "limite", "ventoinha", "clock"}
        m = c.ler()
        self.assertIsNone(m["gpu"])
        self.assertIn("parou de responder", m["gpu_aviso"])
        nvml.sem = set()
        m = c.ler()  # a 2a leitura parte do aviso que a 1a deixou: ele some quando a placa volta
        self.assertEqual((m["gpu"]["temp"], m["gpu_aviso"]), (55, ""))

    def test_pid_reutilizado_nao_vira_uso_negativo(self):
        self.ps.procs = {4: {"nome": "novo", "cpu": -8.0, "rss": GB}}
        c = self.coletor()
        c.ler()
        self.assertEqual(c.ler()["top"], [("novo", 0.0, 1.0)])

    def test_bloco_na_escala_fixa(self):
        self.assertEqual([hardware.bloco(p) for p in (-5, 0, 12.4, 50, 99.9, 100, 250)],
                         ["▁", "▁", "▁", "▅", "█", "█", "█"])


class Avulso(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self._tmp.name) / "estacao"

    def tearDown(self):
        self._tmp.cleanup()

    def test_cria_na_primeira_vez_e_nunca_sobrescreve(self):
        caminho = escritorio.diario_avulso(self.pasta, DIA)
        self.assertEqual(caminho, self.pasta / "tarefas" / "2026-09-12.md")
        escritorio.adicionar_tarefa(caminho, "ligar pra Ana")
        # 2a rodada: parte do que a 1a deixou no disco, não recria o arquivo por cima
        self.assertEqual(escritorio.diario_avulso(self.pasta, DIA), caminho)
        self.assertEqual([(t.texto, t.feita) for t in escritorio.tarefas_do_dia(caminho)],
                         [("ligar pra Ana", False)])

    def test_pasta_avulsa_respeita_a_variavel(self):
        with mock.patch.dict(os.environ, {"ESTACAO_PASTA": str(self.pasta)}):
            self.assertEqual(escritorio.pasta_avulsa(), self.pasta)
        with mock.patch.dict(os.environ, {"ESTACAO_PASTA": ""}):
            self.assertEqual(escritorio.pasta_avulsa(), Path.home() / ".estacao-de-comando")


class Statusline(unittest.TestCase):
    SCRIPT = MODULO / "statusline" / "claude-code.py"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self._tmp.name) / "projeto-ação"
        self.pasta.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def rodar(self, entrada: str) -> str:
        # sem PYTHONUTF8: a linha tem de sair certa em qualquer Windows, não só numa máquina com UTF-8 ligado
        ambiente = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
        r = subprocess.run([sys.executable, str(self.SCRIPT)], input=entrada.encode("utf-8"),
                           capture_output=True, env=ambiente, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.decode("utf-8")

    def test_contexto_modelo_e_pasta(self):
        saida = self.rodar(json.dumps({
            "model": {"display_name": "Opus"}, "workspace": {"current_dir": str(self.pasta)},
            "context_window": {"used_percentage": 45, "total_input_tokens": 90000,
                               "context_window_size": 200000}}))
        self.assertIn("[####------] 45% ctx (90.0k/200.0k)", saida)
        self.assertIn("Opus · projeto-ação", saida)

    def test_entrada_vazia_nao_quebra(self):
        self.assertIn("ctx ?", self.rodar(""))

    def test_estima_pelo_transcript_em_utf8(self):
        transcript = self.pasta / "t.jsonl"
        linhas = [{"message": {"content": "olá, ação"}},
                  {"message": {"usage": {"input_tokens": 1000, "cache_read_input_tokens": 500}}}]
        transcript.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in linhas), encoding="utf-8")
        saida = self.rodar(json.dumps({"transcript_path": str(transcript), "cwd": str(self.pasta)}))
        self.assertIn("~1.5k tok ctx", saida)


class Seguranca(unittest.TestCase):
    CODIGO = {".py", ".cmd", ".sh", ".tcss", ".txt"}

    def _arquivos(self):
        return [p for p in MODULO.rglob("*") if p.suffix in self.CODIGO and "__pycache__" not in p.parts]

    def test_sem_trava_desligada_nem_caminho_fixo(self):
        # montados por partes para este arquivo não se acusar
        proibidos = ["dangerously" + "-skip-permissions", "Execution" + "Policy", "By" + "pass"]
        # qualquer caminho absoluto de máquina (unidade do Windows, pasta de usuário) é caminho fixo
        caminho_fixo = re.compile(r"\b[A-Za-z]:[\\/]|/home/[A-Za-z]|/Users/[A-Za-z]")
        for arquivo in self._arquivos():
            texto = arquivo.read_text(encoding="utf-8")
            onde = arquivo.relative_to(MODULO)
            for termo in proibidos:
                self.assertNotIn(termo, texto, f"{termo!r} em {onde}")
            self.assertIsNone(caminho_fixo.search(texto), f"caminho fixo em {onde}")

    def test_painel_nao_fala_com_rede_nem_roda_processo(self):
        for arquivo in (MODULO / "estacao").glob("*.py"):
            texto = arquivo.read_text(encoding="utf-8")
            for termo in ("subprocess", "socket", "urllib", "http.client", "requests", "os.system", "os.popen"):
                self.assertNotIn(termo, texto, f"{termo!r} em {arquivo.name}")

    def test_lancadores_do_windows_sao_ascii(self):
        # o cmd.exe lê o .cmd na página de código do console: acento ali vira lixo ou quebra a linha
        lancadores = list(MODULO.glob("*.cmd"))
        self.assertEqual(len(lancadores), 2)
        for arquivo in lancadores:
            arquivo.read_bytes().decode("ascii")


if __name__ == "__main__":
    unittest.main(verbosity=2)
