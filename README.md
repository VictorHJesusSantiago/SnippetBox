# SnippetBox

Gerenciador pessoal de **snippets de código, comandos de terminal e scripts**, com
busca rápida. Resolve o clássico *"onde foi que eu guardei aquele comando docker?"*.

Funciona de dois jeitos, compartilhando o mesmo banco de dados:

- **Interface gráfica** (Tkinter) — busca incremental, editor com realce de
  sintaxe, filtro por tags, tema claro/escuro, copiar com um clique.
- **Terminal** (CLI) — `add`, `list`, `search`, `show`, `copy`, `cat`, `run`,
  `edit`, `rm`, `pin`/`unpin`, `history`, `tags`, `export`, `import`, `complete`.

Sem dependências externas: só Python 3.10+ (com Tkinter, que já vem no Python
oficial). O realce de sintaxe usa `pygments` se estiver instalado, mas tem um
realce nativo embutido como fallback.

## Funcionalidades

- **Busca avançada** — por campo (`--in title`), filtro combinado
  (`--tag` + `--lang`), operadores na query (`tag:docker lang:bash in:title up`)
  e busca tolerante a erros (`--fuzzy`).
- **Organização** — snippets fixados (`pin`), contador de uso e ordenação
  (`--sort recent|used|created|title|relevance`), recentes (`list --recent N`).
- **Placeholders** — `docker run {{image}}` preenchido na hora do `copy`/`run`
  (interativo ou via `--var image=nginx`).
- **Descrição** separada do conteúdo, **histórico de versões** com restauração
  (`history <id> --restore N`) e **detecção automática de linguagem** (`--detect`).
- **Pipeline** — `cat <id>` joga o conteúdo no stdout, `run <id>` executa o
  comando (com confirmação), `--json` em `list`/`search`/`show`, `export`/`import`
  (JSON e Markdown/cookbook).
- **Robustez** — aviso de duplicado ao adicionar, lock de arquivo entre CLI e
  GUI, e migração de schema versionada no JSON.

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

### Busca, organização e pipeline

```bash
# busca por campo, filtro combinado, operadores e fuzzy
python snippetbox.py search "git" --in title
python snippetbox.py search "subir" --tag docker --lang bash
python snippetbox.py search "tag:docker lang:bash in:title up"
python snippetbox.py search "dcoker" --fuzzy

# fixar, recentes, mais usados, JSON
python snippetbox.py pin <id>
python snippetbox.py list --recent 10 --sort used
python snippetbox.py list --json

# placeholders, stdout e execução
python snippetbox.py copy <id> --var image=nginx
python snippetbox.py cat <id> | bash
python snippetbox.py run <id>            # pede confirmação

# histórico, export/import, autocompletar
python snippetbox.py history <id>
python snippetbox.py history <id> --restore 0
python snippetbox.py export --format md -o cookbook.md
python snippetbox.py import backup.json
python snippetbox.py complete bash >> ~/.bashrc
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
