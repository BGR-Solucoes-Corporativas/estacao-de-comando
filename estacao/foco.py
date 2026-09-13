"""Relógio do bloco de foco: 3 ciclos de 50 minutos de foco e 10 de pausa (3 horas).

Conta pelo relógio monotônico do sistema, não por tique da tela: se a interface engasgar, o
tempo não atrasa.
"""
from __future__ import annotations

import time

FOCO = 50 * 60
PAUSA = 10 * 60
CICLOS = 3
TOTAL = (FOCO + PAUSA) * CICLOS


def fase(segundos: int) -> tuple[str, int, int]:
    """(fase, ciclo de 1 a 3, segundos que faltam nesta fase). Passado o bloco: ("fim", 3, 0)."""
    if segundos >= TOTAL:
        return "fim", CICLOS, 0
    ciclo, dentro = divmod(int(segundos), FOCO + PAUSA)
    if dentro < FOCO:
        return "foco", ciclo + 1, FOCO - dentro
    return "pausa", ciclo + 1, FOCO + PAUSA - dentro


def faixas(segundos: int, largura: int) -> list[tuple[str, bool, int]]:
    """A barra do bloco em faixas (fase, já vivida?, colunas), da esquerda para a direita.

    Cada coluna vale um trecho igual das 3 horas, então as pausas aparecem no lugar delas dentro de
    cada ciclo. As colunas somam exatamente a largura pedida.
    """
    lista: list[tuple[str, bool, int]] = []
    for i in range(max(0, largura)):
        meio = (i + 0.5) * TOTAL / largura
        chave = (fase(meio)[0], meio < segundos)
        if lista and lista[-1][:2] == chave:
            lista[-1] = (*chave, lista[-1][2] + 1)
        else:
            lista.append((*chave, 1))
    return lista


def relogio_texto(segundos: int) -> str:
    horas, resto = divmod(max(0, int(segundos)), 3600)
    minutos, segs = divmod(resto, 60)
    return f"{horas}:{minutos:02d}:{segs:02d}" if horas else f"{minutos:02d}:{segs:02d}"


class Relogio:
    def __init__(self, agora=time.monotonic):
        self._agora = agora
        self._acumulado = 0.0
        self._desde = None

    @property
    def rodando(self) -> bool:
        return self._desde is not None

    @property
    def iniciado(self) -> bool:
        """Já saiu do zero, mesmo que por menos de um segundo (aí o decorrido ainda mostra 0)."""
        return self.rodando or self._acumulado > 0

    def iniciar(self) -> None:
        if not self.rodando:
            self._desde = self._agora()

    def pausar(self) -> None:
        if self.rodando:
            self._acumulado += self._agora() - self._desde
            self._desde = None

    def alternar(self) -> None:
        self.pausar() if self.rodando else self.iniciar()

    def zerar(self) -> None:
        self._acumulado, self._desde = 0.0, None

    def decorrido(self) -> int:
        total = self._acumulado + (self._agora() - self._desde if self.rodando else 0)
        return min(int(total), TOTAL)
