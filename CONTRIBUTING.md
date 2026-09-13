# Como contribuir

Obrigado pelo interesse na Estação de Comando. Ela é mantida pela equipe da Mnemosine, e este
repositório é a face pública do código: a cada versão, ele é gerado de novo a partir da nossa fonte.

## Issues são bem-vindas

Bug, ideia ou dúvida: abra uma issue. Para bug, conte:

- o sistema operacional e a versão do Python;
- o terminal (Windows Terminal, o terminal do macOS, um `tmux` no Linux…);
- o que você fez, o que esperava e o que aconteceu;
- a mensagem de erro inteira, como apareceu.

## Pull requests entram como proposta

Pode abrir, e toda proposta é lida. Mas nenhum pull request é mesclado direto aqui: como o repositório
é regerado a cada versão, um commit feito direto nele sumiria na publicação seguinte. Quando uma
proposta é aceita, a mudança é refeita na fonte, passa pela nossa auditoria e pelos testes, e sai na
próxima versão, com o seu nome no `CHANGELOG.md`.

Antes de propor código:

- rode os testes, que têm de passar: `python3 testes/test_estacao.py` e `python3 testes/smoke_app.py`;
- dependência nova, só depois de conversar numa issue: cada uma entra fixada com hash no
  `requirements.lock`;
- o painel não fala com a rede e não abre processo, de propósito. Proposta que mude isso precisa de um
  bom motivo, discutido antes.

## Licença das contribuições

Ao contribuir, você concorda que a sua contribuição sai sob a mesma licença do projeto, a MIT. É a
regra padrão dos Termos de Serviço do GitHub para repositórios com licença (seção D.6).

## Segurança

Vulnerabilidade não vai em issue pública: veja o [SECURITY.md](SECURITY.md).
