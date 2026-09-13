"""Telemetria da máquina: CPU, GPU, memória, disco, rede e processos. Só leitura.

O psutil lê os contadores do sistema; a placa NVIDIA vem do nvidia-ml-py, a biblioteca da própria
NVIDIA, que conversa com o driver dentro deste processo. Nenhum dos dois fala com a rede nem abre
processo. Sem a biblioteca, ou sem placa NVIDIA, a aba diz isso e segue: telemetria nunca derruba
o painel.
"""
from __future__ import annotations

import platform
import sys
import time
from collections import deque
from pathlib import Path

GB = 1024 ** 3
MB = 1024 ** 2
HISTORICO = 120  # amostras guardadas para o gráfico: uma a cada 2 s, quatro minutos
TOP = 5
SWAP_VALIDADE = 30.0  # no Windows o swap vem de um contador de desempenho que custa ~0,35 s por leitura
BLOCOS = "▁▂▃▄▅▆▇█"
SEM_BIBLIOTECA = "sem leitura da placa: instale o nvidia-ml-py (está no requirements.txt), só NVIDIA"
SEM_TEMP_CPU = ("o Windows não expõe (exige driver de sensor)" if sys.platform == "win32"
                else "sem sensor legível")
_AUTO = object()


def bloco(pct: float) -> str:
    """Um caractere de altura proporcional à porcentagem, na escala fixa de 0 a 100."""
    return BLOCOS[max(0, min(len(BLOCOS) - 1, int(pct * len(BLOCOS) / 100)))]


def nome_cpu() -> str:
    """Nome comercial do processador, sem abrir processo. Na falta, o que a plataforma disser."""
    try:
        if sys.platform == "win32":
            import winreg
            chave = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, chave) as aberta:
                return " ".join(str(winreg.QueryValueEx(aberta, "ProcessorNameString")[0]).split())
        if sys.platform.startswith("linux"):
            for linha in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace").splitlines():
                if linha.lower().startswith("model name"):
                    return " ".join(linha.split(":", 1)[1].split())
    except (OSError, IndexError):
        pass
    return platform.processor() or platform.machine() or "processador"


def _temperatura_cpu(ps) -> float | None:
    leitor = getattr(ps, "sensors_temperatures", None)  # só Linux e FreeBSD têm
    if leitor is None:
        return None
    try:
        sensores = leitor() or {}
    except (OSError, RuntimeError):
        return None
    for nome in ("k10temp", "coretemp", "zenpower", "cpu_thermal", "acpitz"):
        if sensores.get(nome):
            return float(sensores[nome][0].current)
    return None


def _texto(valor) -> str:
    if valor is None:
        return ""
    return valor.decode("utf-8", "replace") if isinstance(valor, bytes) else str(valor)


class Gpu:
    """A primeira placa NVIDIA, pelo NVML. Cada leitura falha sozinha: placa sem ventoinha não apaga a
    temperatura."""

    def __init__(self, nvml=_AUTO):
        self.nome = self.driver = self.aviso = ""
        self.extras = 0
        self._h = None
        if nvml is _AUTO:
            try:
                import pynvml as nvml
            except ImportError:
                nvml = None
        self._nvml = nvml
        if nvml is None:
            self.aviso = SEM_BIBLIOTECA
            return
        self._erro = getattr(nvml, "NVMLError", OSError)
        try:
            nvml.nvmlInit()
            quantas = nvml.nvmlDeviceGetCount()
            if quantas < 1:
                self.aviso = "nenhuma placa NVIDIA nesta máquina"
                return
            self._h = nvml.nvmlDeviceGetHandleByIndex(0)
        except (self._erro, OSError) as erro:  # sem driver, sem placa ou sem a DLL do NVML
            self.aviso = f"sem leitura da placa NVIDIA ({erro})"
            return
        self.nome = _texto(self._chama("nvmlDeviceGetName", self._h)) or "NVIDIA"
        self.driver = _texto(self._chama("nvmlSystemGetDriverVersion"))
        self.extras = quantas - 1

    @property
    def nome_completo(self) -> str:
        return f"{self.nome} (+{self.extras})" if self.nome and self.extras else self.nome

    def _chama(self, funcao: str, *args):
        try:
            return getattr(self._nvml, funcao)(*args)
        except (self._erro, AttributeError, OSError):  # leitura que esta placa ou driver não tem
            return None

    def ler(self) -> dict | None:
        if self._h is None:
            return None
        n, h = self._nvml, self._h
        uso = self._chama("nvmlDeviceGetUtilizationRates", h)
        memoria = self._chama("nvmlDeviceGetMemoryInfo", h)
        potencia = self._chama("nvmlDeviceGetPowerUsage", h)
        limite = self._chama("nvmlDeviceGetEnforcedPowerLimit", h)
        leitura = {
            "uso": uso.gpu if uso is not None else None,
            "vram_usada": memoria.used / GB if memoria is not None else None,
            "vram_total": memoria.total / GB if memoria is not None else None,
            "temp": self._chama("nvmlDeviceGetTemperature", h, getattr(n, "NVML_TEMPERATURE_GPU", 0)),
            "potencia": potencia / 1000 if potencia is not None else None,  # o NVML fala em mW
            "limite": limite / 1000 if limite else None,
            "ventoinha": self._chama("nvmlDeviceGetFanSpeed", h),
            "clock": self._chama("nvmlDeviceGetClockInfo", h, getattr(n, "NVML_CLOCK_GRAPHICS", 0)),
        }
        if all(valor is None for valor in leitura.values()):
            self.aviso = "a placa NVIDIA parou de responder"
            return None
        self.aviso = ""
        return leitura


class Coletor:
    """Lê a máquina a cada chamada. Guarda a amostra anterior, para transformar contador em taxa
    (MB/s), e o histórico dos gráficos.

    O caro é a varredura de processos (~1 ms por processo no Windows, ~0,4 s numa máquina comum) e o
    swap: quem chama decide quando varrer (`ler(processos=...)`), e o swap tem validade própria.
    """

    def __init__(self, raiz: Path, ps=None, nvml=_AUTO, agora=time.monotonic):
        if ps is None:
            import psutil as ps  # só esta aba precisa dele
        self._ps, self._agora = ps, agora
        self._erro = getattr(ps, "Error", OSError)
        self.unidade = Path(raiz).resolve().anchor or "/"
        self.cpu_nome = nome_cpu()
        self.gpu = Gpu(nvml)
        self.hist_cpu: deque[float] = deque(maxlen=HISTORICO)
        self.hist_gpu: deque[float] = deque(maxlen=HISTORICO)
        self._anterior = None
        self._procs: dict = {}
        self._top: list[tuple[str, float, float]] = []
        self._swap, self._swap_em = None, None
        ps.cpu_percent(percpu=True)  # a 1a leitura só arma a régua; a próxima já compara

    def _tenta(self, funcao, *args, **kwargs):
        try:
            return funcao(*args, **kwargs)
        except (self._erro, OSError, RuntimeError):  # contador que o sistema não entrega vira "sem dado"
            return None

    def _taxas(self, agora: float, disco, rede) -> dict:
        anterior, self._anterior = self._anterior, (agora, disco, rede)
        campos = {"disco_ler": (1, "read_bytes"), "disco_gravar": (1, "write_bytes"),
                  "rede_baixa": (2, "bytes_recv"), "rede_sobe": (2, "bytes_sent")}
        if anterior is None:
            return dict.fromkeys(campos)
        intervalo = agora - anterior[0]
        taxas = {}
        for chave, (i, campo) in campos.items():
            antes, depois = anterior[i], (disco, rede)[i - 1]
            delta = None if antes is None or depois is None else getattr(depois, campo) - getattr(antes, campo)
            # contador que voltou (adaptador reiniciado, disco removido): pula a amostra, não inventa
            taxas[chave] = delta / intervalo / MB if delta is not None and delta >= 0 and intervalo > 0 else None
        return taxas

    def _varrer(self, pids: list[int], logicos: int) -> list[tuple[str, float, float]]:
        """Os que mais usam CPU desde a varredura anterior. Processo novo só arma a régua e entra no
        ranking na próxima, então a 1a varredura devolve lista vazia em vez de zeros inventados."""
        ps, vivos, medidos = self._ps, {}, []
        for pid in pids:
            if pid == 0:  # o "System Idle Process" do Windows é o ocioso, não um consumidor
                continue
            proc = self._procs.get(pid)
            try:
                if proc is None:
                    proc = ps.Process(pid)
                    proc.cpu_percent(None)
                else:
                    # % de um núcleo vira % da máquina; PID que o sistema reutilizou pode medir negativo
                    medidos.append((max(0.0, proc.cpu_percent(None)) / logicos, proc))
            except self._erro:  # acabou ou é protegido: fica fora da lista
                continue
            vivos[pid] = proc
        self._procs = vivos
        medidos.sort(key=lambda par: par[0], reverse=True)
        top = []
        for uso, proc in medidos:
            nome, memoria = self._tenta(proc.name), self._tenta(proc.memory_info)  # só dos que aparecem
            if nome:
                top.append((nome, uso, memoria.rss / GB if memoria is not None else 0.0))
            if len(top) == TOP:
                break
        return top

    def ler(self, processos: bool = True) -> dict:
        ps = self._ps
        agora = self._agora()
        nucleos = list(ps.cpu_percent(percpu=True)) or [0.0]
        cpu = sum(nucleos) / len(nucleos)
        memoria = ps.virtual_memory()
        if self._swap is None or agora - self._swap_em >= SWAP_VALIDADE:
            self._swap = self._tenta(ps.swap_memory) or self._swap
            self._swap_em = agora
        troca = self._swap
        disco = ps.disk_usage(self.unidade)
        taxas = self._taxas(agora, self._tenta(ps.disk_io_counters), self._tenta(ps.net_io_counters))
        gpu = self.gpu.ler()
        pids = self._tenta(ps.pids) or []
        if processos:
            self._top = self._varrer(pids, len(nucleos))
        top = self._top
        self.hist_cpu.append(cpu)
        if gpu and gpu["uso"] is not None:
            self.hist_gpu.append(gpu["uso"])
        return {
            "cpu": cpu, "nucleos": nucleos, "cpu_nome": self.cpu_nome,
            "fisicos": self._tenta(ps.cpu_count, logical=False) or 0,
            "temp_cpu": _temperatura_cpu(ps), "temp_cpu_aviso": SEM_TEMP_CPU,
            "ram": memoria.percent, "ram_usada": memoria.used / GB, "ram_total": memoria.total / GB,
            "swap": troca.percent if troca else 0.0, "swap_usada": troca.used / GB if troca else 0.0,
            "swap_total": troca.total / GB if troca else 0.0,
            "unidade": self.unidade.rstrip("\\/") or "/",
            "disco": disco.percent, "disco_livre": disco.free / GB, "disco_total": disco.total / GB,
            **taxas,
            "gpu": gpu, "gpu_nome": self.gpu.nome_completo, "gpu_driver": self.gpu.driver,
            "gpu_aviso": self.gpu.aviso,
            "hist_cpu": list(self.hist_cpu), "hist_gpu": list(self.hist_gpu),
            "top": top, "processos": len(pids),
            "ligado": max(0.0, time.time() - ps.boot_time()),
            "sistema": f"{platform.system()} {platform.release()}", "python": platform.python_version(),
        }
