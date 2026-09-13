# Estação de Comando

Transforma o terminal em posto de trabalho: a sua assistente de IA de um lado, um painel do outro.
No Windows Terminal, a tela se divide sozinha (assistente à esquerda, painel à direita); em Linux e
macOS, o painel roda num `tmux` ou em qualquer terminal.

## O que tem

- **Foco:** bloco de 3 horas (três ciclos de 50 minutos com 10 de pausa), com o tempo em dígitos
  grandes, aviso ao virar a fase e as tarefas de hoje, que se marcam e se criam ali mesmo.
- **Máquina:** CPU (uso, núcleos e histórico), placa de vídeo NVIDIA (uso, VRAM, temperatura,
  energia, ventoinha e clock), memória, disco, rede e os processos que mais consomem.
- **Assistente:** dentro de um escritório [Mnemosine](https://mnemosine.ia.br), a última sessão, as
  pendências, as frentes e a caixa de entrada da sua assistente.
- **Statusline do Claude Code:** o contexto em uso em destaque, com modelo, pasta e branch.

## Instalar

Precisa de Python 3.10 ou mais novo.

```
git clone https://github.com/BGR-Solucoes-Corporativas/estacao-de-comando
cd estacao-de-comando
python3 -m pip install --user --require-hashes -r requirements.lock
```

No Windows, use `py` ou `python` no lugar de `python3`, conforme a sua instalação. As dependências
diretas (`textual`, `psutil` e `nvidia-ml-py`) estão no `requirements.txt`; o `requirements.lock`
fixa a árvore inteira com o hash de cada arquivo, e o `--require-hashes` faz o pip recusar qualquer
pacote que não bata. Sem placa NVIDIA, o `nvidia-ml-py` instala igual e a aba Máquina só avisa que
não há leitura da placa.

## Usar

- **Windows, tela dividida:** `estacao.cmd`. Abre a primeira assistente que encontrar entre
  `claude`, `gemini`, `codex` e `agy`; para escolher, `estacao.cmd gemini`, ou a variável de
  usuário `ESTACAO_ASSISTENTE` com a linha de comando da sua preferência.
- **Só o painel:** `cockpit.cmd` no Windows, `sh cockpit.sh` no Linux e no macOS.
- **Linux e macOS, lado a lado:**
  `tmux new-session claude \; split-window -h -l 35% "sh /caminho/da/estacao/cockpit.sh"`
- **Teclas:** `p` inicia e pausa o foco · `r` zera · `a` relê · `1` `2` `3` trocam de aba · `q`
  sai. Com o cursor no campo de tarefa nova, as letras vão para o texto; `Tab` sai dele.

## Onde ficam as tarefas

Sozinha, a Estação guarda as tarefas de cada dia em `~/.estacao-de-comando/tarefas/AAAA-MM-DD.md`,
um arquivo de texto comum que você pode abrir e editar (para trocar a pasta, defina a variável
`ESTACAO_PASTA`). Instalada dentro de um escritório Mnemosine, em `modulos/estacao-de-comando/`, ela
usa o diário do escritório, e a aba da assistente acende.

## Statusline do Claude Code

No `settings.json` do Claude Code (o seu, em `~/.claude/settings.json`, ou o do projeto):

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 /caminho/da/estacao/statusline/claude-code.py"
  }
}
```

No Windows, troque `python3` por `python` ou `py` e use barras normais no caminho
(`C:/Users/voce/estacao-de-comando/statusline/claude-code.py`).

## O que ela não faz, de propósito

- Não desliga trava de permissão da assistente e não mexe na política de execução do Windows: a
  assistente abre exatamente como abriria sozinha. Se você quiser alguma opção da sua CLI, ela vai
  na linha de comando ou na `ESTACAO_ASSISTENTE`, e é decisão sua.
- O painel não fala com a rede e não abre processo: lê arquivos e os contadores da máquina (pelo
  `psutil` e, na placa NVIDIA, pelo driver). A statusline abre um único processo, o `git`, para
  mostrar a branch.
- A temperatura da CPU aparece no Linux. O Windows só a entrega com um driver de sensor à parte, e
  o painel diz isso em vez de inventar número.

## Testes

```
python3 testes/test_estacao.py
python3 testes/smoke_app.py
```

O primeiro usa só a biblioteca padrão; o segundo abre o painel sem tela e confere, no arquivo, o
que ele gravou. Os dois saem com erro se algo falhar.

## Licença

MIT, © 2026 mnemosine.ia.br. Da mesma casa da [Mnemosine](https://mnemosine.ia.br), a assistente
pessoal que não te substitui: te torna insuperável.
