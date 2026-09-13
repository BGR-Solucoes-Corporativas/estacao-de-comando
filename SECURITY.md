# Segurança

## Como relatar uma vulnerabilidade

**Não abra issue pública.** Use o relato privado do GitHub: na aba **Security** deste repositório,
botão **Report a vulnerability**. Só a equipe que mantém o projeto vê o relato, e a conversa segue por
ali até a correção sair.

Ajuda muito contar: o que é, como reproduzir, o que um atacante conseguiria e em qual versão você viu.

## Versões com correção

Só a versão mais recente recebe correção de segurança. As dependências são fixadas com hash no
`requirements.lock` e acompanhadas pelos alertas do GitHub.

## O que está no escopo

O painel lê arquivos locais e só escreve o arquivo de tarefas do dia; não fala com a rede e não abre
processo. A statusline abre um único processo, o `git`, para mostrar a branch. Qualquer caminho que
quebre uma dessas garantias é vulnerabilidade, e queremos saber.
