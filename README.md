# SnippetBox

Gerenciador pessoal de **snippets de código, comandos de terminal e scripts**, com
busca rápida. Resolve o clássico *"onde foi que eu guardei aquele comando docker?"*.

Funciona de dois jeitos, compartilhando o mesmo banco de dados:

- **Interface gráfica** (Tkinter) — busca incremental, editor, copiar com um clique.
- **Terminal** (CLI) — `add`, `list`, `search`, `copy`, `show`, `edit`, `rm`, `tags`.

Sem dependências externas: só Python 3.10+ (com Tkinter, que já vem no Python oficial).

## Armazenamento

Tudo fica em um único JSON: `~/.snippetbox/snippets.json`
(ou defina `SNIPPETBOX_HOME` para outro diretório, ou use `--store caminho.json`).

## Uso pelo terminal

```bash
# adicionar (titulo automatico a partir da 1a linha se omitido)
python snippetbox.py add -t "Subir stack" -l bash -g docker,ci "docker compose up -d"

# adicionar lendo de arquivo ou de um pipe
python snippetbox.py add -t "Deploy" -f ./deploy.sh
cat trecho.py | python snippetbox.py add -t "Parser" -l python -    # '-' = ler de stdin

# listar / buscar
python snippetbox.py list
python snippetbox.py list --tag docker
python snippetbox.py search docker

# ver, copiar para a area de transferencia, editar, remover
python snippetbox.py show <id>
python snippetbox.py copy <id>
python snippetbox.py edit <id> -t "Novo titulo"
python snippetbox.py rm <id> -y

# todas as tags
python snippetbox.py tags
```

O `<id>` pode ser o id completo ou um prefixo único.

## Interface gráfica

```bash
python snippetbox.py gui      # ou apenas: python snippetbox.py
```

Atalhos: `Ctrl+N` novo, `Ctrl+S` salvar. A caixa de busca filtra enquanto você digita.

## Instalação (opcional)

```bash
pip install -e .
snippetbox list        # vira um comando direto
```

## Testes

```bash
python -m pytest        # ou: python -m unittest (testes usam tmp_path do pytest)
```

## Por que esse design

- **Núcleo único** (`core.py`) usado por CLI e GUI — uma só lógica de busca/persistência.
- **Gravação atômica** (escreve `.tmp` e renomeia) para não corromper o JSON.
- **Busca pontuada**: match no título pesa mais que no corpo, então o resultado certo
  tende a vir primeiro.
- **Plugável ao fluxo de trabalho**: a CLI lê de stdin/arquivo, então dá para alimentar
  o SnippetBox a partir de qualquer pipeline.
