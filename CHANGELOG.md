# Changelog: estacao-de-comando

## 0.2.0 (2026-09-12)
- **Modo avulso:** roda sem escritório Mnemosine. As tarefas de cada dia moram em
  `~/.estacao-de-comando/tarefas/` (ou na pasta da variável `ESTACAO_PASTA`), e a aba da assistente
  explica o que mostraria. Os lançadores deixam de exigir o escritório.
- **Statusline do Claude Code** no pacote (`statusline/claude-code.py`): contexto em uso em
  destaque, com modelo, pasta e branch, sem depender da página de código do sistema.
- **Máquina sem travar a tela:** a leitura roda numa thread; os processos só são varridos com a aba
  à vista (a cada 10 s e ao abri-la), e o swap, que no Windows custa ~0,35 s, a cada 30 s. Medido:
  704 ms por leitura antes, ~5 ms depois (varredura, quando há: ~0,3 s, fora da tela).
- **Foco redesenhado:** relógio em cartão na largura toda, com dígitos
  grandes na cor da fase (apagados quando pausado), a barra do bloco esticada até a borda e com as
  três pausas no lugar delas, um botão só para iniciar, pausar e retomar, e botões e campo de tarefa
  com uma linha de altura. O campo mora no cartão das tarefas, e o placar virou o título do cartão.
- **Rodapé enxuto:** só `p r a q`; os números das abas já aparecem nas próprias abas, e o atalho da
  paleta saiu da vista (continua no `Ctrl+P`).
- **Máquina ampliada:** CPU com núcleos e histórico de 4 minutos na escala fixa de 0 a 100, placa
  NVIDIA pelo NVML (uso, VRAM, temperatura, energia, ventoinha, clock, driver), swap, taxa de
  leitura e escrita do disco, rede, tempo ligado e os 5 processos que mais consomem. Dependência
  nova: `nvidia-ml-py` (NVIDIA).
- **Código aberto (MIT)**, com `requirements.lock`: a árvore inteira de dependências fixada com o
  sha256 de cada arquivo (`pip install --require-hashes`), conferida contra a base de
  vulnerabilidades OSV. Aviso do Dependabot para versões novas.
- Cabeçalho sem travessão: título, assistente e dono numa linha só.
- Corrigido: PID que o sistema reutiliza não aparece com uso negativo; avisos de erro mostram o
  texto do sistema como veio (sem virar marcação); a estação chamada da raiz de uma unidade abre.
- Corrigido: iniciar e pausar no mesmo segundo mostrava "pronto" e "Iniciar" em vez de "pausado" e
  "Retomar".

## 0.1.0 (2026-09-12)
- Primeira versão. Tela dividida no Windows Terminal (assistente 65%, painel 35%) e painel com três
  abas: **Foco** (bloco de 3 horas e tarefas de hoje gravadas no diário), **Radar** da assistente
  (última sessão, pendências, frentes, caixa de entrada) e **Máquina** (CPU, memória, disco).
- Lançadores sem desligar trava de permissão e sem mexer na política de execução; nenhum caminho
  fixo; a CLI da assistente é escolhida por argumento, variável ou detecção, e aceita opções
  (argumentos ou `ESTACAO_ASSISTENTE`), que são do dono: o módulo não traz nenhuma.
- Estado: **piloto**. Linux e macOS: `cockpit.sh` escrito, ainda não exercitado.
