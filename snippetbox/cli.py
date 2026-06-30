"""Interface de terminal do SnippetBox.

Uso rapido:
    snippetbox add -t "Subir stack" -l bash -g docker "docker compose up -d"
    snippetbox list
    snippetbox search docker
    snippetbox copy <id>
    snippetbox show <id>
    snippetbox rm <id>
    snippetbox gui
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime

from .clipboard import copy as clip_copy
from .core import Snippet, Store, parse_tags


def _fmt_time(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def _read_content(args) -> str:
    """Resolve o conteudo do snippet: argumento posicional, --file ou stdin.

    Stdin so e lido quando o usuario pede explicitamente passando '-' como
    conteudo (evita travar lendo stdin quando nenhum conteudo foi informado).
    """
    if getattr(args, "file", None):
        with open(args.file, "r", encoding="utf-8") as fh:
            return fh.read().rstrip("\n")
    if args.content == ["-"]:
        return sys.stdin.read().rstrip("\n")
    if args.content:
        return " ".join(args.content)
    return ""


# ---- comandos ---------------------------------------------------------
def cmd_add(store: Store, args) -> int:
    content = _read_content(args)
    if not content:
        print("erro: conteudo vazio (passe texto, --file ou via stdin)", file=sys.stderr)
        return 2
    snip = Snippet(
        title=args.title or content.splitlines()[0][:60],
        content=content,
        language=args.language or "",
        tags=parse_tags(args.tags),
    )
    store.add(snip)
    print(f"adicionado {snip.id}: {snip.title}")
    return 0


def _print_row(s: Snippet) -> None:
    tags = ("#" + " #".join(s.tags)) if s.tags else ""
    lang = f"[{s.language}]" if s.language else ""
    print(f"  {s.id}  {s.title[:48]:<48} {lang:<10} {tags}")


def cmd_list(store: Store, args) -> int:
    items = store.search("")
    if args.tag:
        items = [s for s in items if args.tag in s.tags]
    if not items:
        print("nenhum snippet ainda. use 'snippetbox add' para criar.")
        return 0
    print(f"{len(items)} snippet(s):")
    for s in items:
        _print_row(s)
    return 0


def cmd_search(store: Store, args) -> int:
    items = store.search(args.query)
    if not items:
        print(f"nenhum resultado para '{args.query}'.")
        return 1
    print(f"{len(items)} resultado(s) para '{args.query}':")
    for s in items:
        _print_row(s)
    return 0


def cmd_show(store: Store, args) -> int:
    s = store.get(args.id)
    if not s:
        print(f"snippet '{args.id}' nao encontrado.", file=sys.stderr)
        return 1
    tags = ", ".join(s.tags) if s.tags else "-"
    print(f"id:        {s.id}")
    print(f"titulo:    {s.title}")
    print(f"linguagem: {s.language or '-'}")
    print(f"tags:      {tags}")
    print(f"criado:    {_fmt_time(s.created_at)}")
    print(f"alterado:  {_fmt_time(s.updated_at)}")
    print("-" * 50)
    print(s.content)
    return 0


def cmd_copy(store: Store, args) -> int:
    s = store.get(args.id)
    if not s:
        print(f"snippet '{args.id}' nao encontrado.", file=sys.stderr)
        return 1
    if clip_copy(s.content):
        print(f"copiado para a area de transferencia: {s.title}")
        return 0
    print("nao foi possivel acessar a area de transferencia.", file=sys.stderr)
    print(s.content)
    return 1


def cmd_rm(store: Store, args) -> int:
    s = store.get(args.id)
    if not s:
        print(f"snippet '{args.id}' nao encontrado.", file=sys.stderr)
        return 1
    if not args.yes:
        resp = input(f"remover '{s.title}' ({s.id})? [s/N] ").strip().lower()
        if resp not in ("s", "sim", "y", "yes"):
            print("cancelado.")
            return 0
    store.delete(s.id)
    print(f"removido {s.id}.")
    return 0


def cmd_edit(store: Store, args) -> int:
    s = store.get(args.id)
    if not s:
        print(f"snippet '{args.id}' nao encontrado.", file=sys.stderr)
        return 1
    if args.title is not None:
        s.title = args.title
    if args.language is not None:
        s.language = args.language
    if args.tags is not None:
        s.tags = parse_tags(args.tags)
    new_content = _read_content(args)
    if new_content:
        s.content = new_content
    store.update(s)
    print(f"atualizado {s.id}.")
    return 0


def cmd_tags(store: Store, args) -> int:
    tags = store.all_tags()
    if not tags:
        print("nenhuma tag ainda.")
        return 0
    print(" ".join("#" + t for t in tags))
    return 0


def cmd_gui(store: Store, args) -> int:
    from . import gui

    gui.run(store)
    return 0


# ---- parser -----------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="snippetbox",
        description="Gerenciador pessoal de snippets, comandos e scripts.",
    )
    p.add_argument("--store", help="caminho do arquivo de dados JSON")
    sub = p.add_subparsers(dest="command")

    pa = sub.add_parser("add", help="adicionar snippet")
    pa.add_argument("content", nargs="*", help="conteudo (ou use --file / stdin)")
    pa.add_argument("-t", "--title", help="titulo")
    pa.add_argument("-l", "--language", help="linguagem (bash, python, ...)")
    pa.add_argument("-g", "--tags", help="tags separadas por virgula")
    pa.add_argument("-f", "--file", help="ler conteudo de um arquivo")
    pa.set_defaults(func=cmd_add)

    pl = sub.add_parser("list", help="listar snippets")
    pl.add_argument("--tag", help="filtrar por tag")
    pl.set_defaults(func=cmd_list)

    ps = sub.add_parser("search", help="buscar snippets")
    ps.add_argument("query", help="termo de busca")
    ps.set_defaults(func=cmd_search)

    psh = sub.add_parser("show", help="mostrar um snippet")
    psh.add_argument("id")
    psh.set_defaults(func=cmd_show)

    pc = sub.add_parser("copy", help="copiar conteudo para a area de transferencia")
    pc.add_argument("id")
    pc.set_defaults(func=cmd_copy)

    pr = sub.add_parser("rm", help="remover snippet")
    pr.add_argument("id")
    pr.add_argument("-y", "--yes", action="store_true", help="nao perguntar")
    pr.set_defaults(func=cmd_rm)

    pe = sub.add_parser("edit", help="editar snippet")
    pe.add_argument("id")
    pe.add_argument("content", nargs="*", help="novo conteudo (opcional)")
    pe.add_argument("-t", "--title")
    pe.add_argument("-l", "--language")
    pe.add_argument("-g", "--tags")
    pe.add_argument("-f", "--file")
    pe.set_defaults(func=cmd_edit)

    pt = sub.add_parser("tags", help="listar todas as tags")
    pt.set_defaults(func=cmd_tags)

    pg = sub.add_parser("gui", help="abrir a interface grafica")
    pg.set_defaults(func=cmd_gui)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        # sem subcomando: abre a GUI por padrao
        args.func = cmd_gui
    store = Store(args.store)
    return args.func(store, args)


if __name__ == "__main__":
    raise SystemExit(main())
