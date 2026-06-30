"""Interface de terminal do SnippetBox.

Uso rapido:
    snippetbox add -t "Subir stack" -l bash -g docker "docker compose up -d"
    snippetbox list
    snippetbox search "tag:docker subir" --fuzzy
    snippetbox copy <id> --var image=nginx
    snippetbox run <id>
    snippetbox export --format md -o cookbook.md
    snippetbox gui
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict
from datetime import datetime

from . import completion, exporters, placeholders
from .clipboard import copy as clip_copy
from .core import SEARCH_FIELDS, Snippet, Store, detect_language, parse_tags
from .highlight import highlight, supported as color_supported


def _fmt_time(ts: float) -> str:
    if not ts:
        return "-"
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


def _snippet_dict(s: Snippet) -> dict:
    return asdict(s)


# ---- comandos ---------------------------------------------------------
def cmd_add(store: Store, args) -> int:
    content = _read_content(args)
    if not content:
        print("erro: conteudo vazio (passe texto, --file ou via stdin)", file=sys.stderr)
        return 2

    dup = store.find_duplicate(content)
    if dup and not args.force:
        print(
            f"aviso: conteudo identico ja existe em {dup.id} ({dup.title}). "
            "use --force para adicionar mesmo assim.",
            file=sys.stderr,
        )
        return 3

    language = args.language or ""
    if not language and args.detect:
        language = detect_language(content)

    snip = Snippet(
        title=args.title or content.splitlines()[0][:60],
        content=content,
        language=language,
        tags=parse_tags(args.tags),
        description=args.description or "",
        pinned=bool(args.pin),
    )
    store.add(snip)
    detected = " (linguagem detectada)" if args.detect and language and not args.language else ""
    print(f"adicionado {snip.id}: {snip.title}{detected}")
    return 0


def _print_row(s: Snippet) -> None:
    pin = "*" if s.pinned else " "
    tags = ("#" + " #".join(s.tags)) if s.tags else ""
    lang = f"[{s.language}]" if s.language else ""
    uses = f"({s.use_count}x)" if s.use_count else ""
    print(f" {pin}{s.id}  {s.title[:46]:<46} {lang:<10} {uses:<6} {tags}")


def _output_list(store: Store, items, args, header_word="snippet") -> int:
    if getattr(args, "json", False):
        print(json.dumps([_snippet_dict(s) for s in items], ensure_ascii=False, indent=2))
        return 0 if items else 1
    if not items:
        print(f"nenhum {header_word} encontrado.")
        return 1
    print(f"{len(items)} {header_word}(s):")
    for s in items:
        _print_row(s)
    return 0


def cmd_list(store: Store, args) -> int:
    items = store.search(
        "",
        tag=args.tag,
        language=args.lang,
        sort=args.sort,
        limit=args.recent,
    )
    if args.pinned:
        items = [s for s in items if s.pinned]
    return _output_list(store, items, args, "snippet")


def cmd_search(store: Store, args) -> int:
    items = store.search(
        args.query,
        tag=args.tag,
        language=args.lang,
        fields=args.in_fields,
        fuzzy=args.fuzzy,
        sort=args.sort,
        limit=args.limit,
    )
    if getattr(args, "json", False):
        print(json.dumps([_snippet_dict(s) for s in items], ensure_ascii=False, indent=2))
        return 0 if items else 1
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
    if getattr(args, "json", False):
        print(json.dumps(_snippet_dict(s), ensure_ascii=False, indent=2))
        return 0
    tags = ", ".join(s.tags) if s.tags else "-"
    vars_found = placeholders.extract(s.content)
    print(f"id:        {s.id}")
    print(f"titulo:    {s.title}")
    print(f"linguagem: {s.language or '-'}")
    print(f"tags:      {tags}")
    if s.description:
        print(f"descricao: {s.description}")
    if s.pinned:
        print("fixado:    sim")
    if vars_found:
        print(f"variaveis: {', '.join('{{' + v + '}}' for v in vars_found)}")
    print(f"usos:      {s.use_count} (ultimo: {_fmt_time(s.last_used)})")
    print(f"criado:    {_fmt_time(s.created_at)}")
    print(f"alterado:  {_fmt_time(s.updated_at)}")
    print("-" * 50)
    body = s.content
    use_color = not args.no_color and color_supported(sys.stdout)
    print(highlight(body, s.language) if use_color else body)
    if not args.no_count:
        store.touch(s.id)
    return 0


def _resolve_content_with_vars(s: Snippet, args) -> str | None:
    """Aplica placeholders. Retorna None se o usuario abortar."""
    names = placeholders.extract(s.content)
    if not names:
        return s.content
    values = placeholders.parse_assignments(getattr(args, "var", None))
    missing = [n for n in names if n not in values]
    if missing:
        if getattr(args, "no_prompt", False) or not sys.stdin.isatty():
            # sem como perguntar: deixa os faltantes como estao
            return placeholders.fill(s.content, values)
        for name in missing:
            try:
                values[name] = input(f"{name} = ")
            except (EOFError, KeyboardInterrupt):
                print("\ncancelado.", file=sys.stderr)
                return None
    return placeholders.fill(s.content, values)


def cmd_copy(store: Store, args) -> int:
    s = store.get(args.id)
    if not s:
        print(f"snippet '{args.id}' nao encontrado.", file=sys.stderr)
        return 1
    content = _resolve_content_with_vars(s, args)
    if content is None:
        return 1
    if clip_copy(content):
        print(f"copiado para a area de transferencia: {s.title}")
        store.touch(s.id)
        return 0
    print("nao foi possivel acessar a area de transferencia.", file=sys.stderr)
    print(content)
    return 1


def cmd_cat(store: Store, args) -> int:
    """Imprime o conteudo cru no stdout (para pipes/scripts)."""
    s = store.get(args.id)
    if not s:
        print(f"snippet '{args.id}' nao encontrado.", file=sys.stderr)
        return 1
    content = _resolve_content_with_vars(s, args)
    if content is None:
        return 1
    sys.stdout.write(content + ("\n" if not content.endswith("\n") else ""))
    if not args.no_count:
        store.touch(s.id)
    return 0


def cmd_run(store: Store, args) -> int:
    """Executa o conteudo como comando de shell (com confirmacao)."""
    s = store.get(args.id)
    if not s:
        print(f"snippet '{args.id}' nao encontrado.", file=sys.stderr)
        return 1
    content = _resolve_content_with_vars(s, args)
    if content is None:
        return 1
    print(f"$ {content}")
    if not args.yes:
        try:
            resp = input("executar? [s/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\ncancelado.")
            return 0
        if resp not in ("s", "sim", "y", "yes"):
            print("cancelado.")
            return 0
    store.touch(s.id)
    completed = subprocess.run(content, shell=True)
    return completed.returncode


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


def _open_in_editor(initial: str) -> str:
    """Abre $EDITOR (ou um padrao do SO) e devolve o texto editado."""
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        editor = "notepad" if sys.platform == "win32" else "vi"
    with tempfile.NamedTemporaryFile(
        "w", suffix=".snippet", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(initial)
        tmp = fh.name
    try:
        subprocess.run(f'{editor} "{tmp}"', shell=True, check=False)
        with open(tmp, "r", encoding="utf-8") as fh:
            return fh.read().rstrip("\n")
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


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
    if args.description is not None:
        s.description = args.description
    if args.pin:
        s.pinned = True
    if args.no_pin:
        s.pinned = False

    if args.editor:
        s.content = _open_in_editor(s.content)
    else:
        new_content = _read_content(args)
        if new_content:
            s.content = new_content
    store.update(s)
    print(f"atualizado {s.id}.")
    return 0


def cmd_pin(store: Store, args) -> int:
    s = store.set_pinned(args.id, True)
    if not s:
        print(f"snippet '{args.id}' nao encontrado.", file=sys.stderr)
        return 1
    print(f"fixado {s.id}: {s.title}")
    return 0


def cmd_unpin(store: Store, args) -> int:
    s = store.set_pinned(args.id, False)
    if not s:
        print(f"snippet '{args.id}' nao encontrado.", file=sys.stderr)
        return 1
    print(f"desfixado {s.id}: {s.title}")
    return 0


def cmd_history(store: Store, args) -> int:
    s = store.get(args.id)
    if not s:
        print(f"snippet '{args.id}' nao encontrado.", file=sys.stderr)
        return 1
    if args.restore is not None:
        restored = store.restore_version(s.id, args.restore)
        if not restored:
            print(f"versao {args.restore} invalida.", file=sys.stderr)
            return 1
        print(f"restaurada versao {args.restore} de {s.id}.")
        return 0
    if not s.history:
        print("sem historico para este snippet.")
        return 0
    print(f"{len(s.history)} versao(es) anterior(es) de {s.id}:")
    for i, ver in enumerate(s.history):
        when = _fmt_time(ver.get("saved_at", 0))
        first = (ver.get("content", "").splitlines() or [""])[0][:50]
        print(f"  [{i}] {when}  {ver.get('title', ''):<24} {first}")
    return 0


def cmd_tags(store: Store, args) -> int:
    tags = store.all_tags()
    if not tags:
        print("nenhuma tag ainda.")
        return 0
    print(" ".join("#" + t for t in tags))
    return 0


def cmd_export(store: Store, args) -> int:
    items = store.search("", tag=args.tag, sort="title")
    out = exporters.export(items, fmt=args.format, title=args.title)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"exportados {len(items)} snippet(s) para {args.output}")
    else:
        sys.stdout.write(out if out.endswith("\n") else out + "\n")
    return 0


def cmd_import(store: Store, args) -> int:
    if args.file == "-":
        data = sys.stdin.read()
    else:
        with open(args.file, "r", encoding="utf-8") as fh:
            data = fh.read()
    added = exporters.import_json(store, data, replace_ids=args.new_ids)
    print(f"importados {added} snippet(s).")
    return 0


def cmd_complete(store: Store, args) -> int:
    print(completion.script(args.shell))
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

    # add
    pa = sub.add_parser("add", help="adicionar snippet")
    pa.add_argument("content", nargs="*", help="conteudo (ou use --file / stdin)")
    pa.add_argument("-t", "--title", help="titulo")
    pa.add_argument("-l", "--language", help="linguagem (bash, python, ...)")
    pa.add_argument("-g", "--tags", help="tags separadas por virgula")
    pa.add_argument("-d", "--description", help="descricao / nota")
    pa.add_argument("-f", "--file", help="ler conteudo de um arquivo")
    pa.add_argument("--pin", action="store_true", help="ja criar fixado")
    pa.add_argument("--detect", action="store_true", help="detectar a linguagem")
    pa.add_argument("--force", action="store_true", help="adicionar mesmo se duplicado")
    pa.set_defaults(func=cmd_add)

    # list
    pl = sub.add_parser("list", help="listar snippets")
    pl.add_argument("--tag", help="filtrar por tag")
    pl.add_argument("--lang", help="filtrar por linguagem")
    pl.add_argument("--pinned", action="store_true", help="apenas fixados")
    pl.add_argument("--recent", type=int, metavar="N", help="apenas os N mais recentes")
    pl.add_argument(
        "--sort",
        choices=["relevance", "recent", "created", "used", "title"],
        default="recent",
        help="ordenacao",
    )
    pl.add_argument("--json", action="store_true", help="saida em JSON")
    pl.set_defaults(func=cmd_list)

    # search
    ps = sub.add_parser("search", help="buscar snippets")
    ps.add_argument("query", help="termo (aceita tag:x lang:y in:campo)")
    ps.add_argument("--tag", help="filtrar tambem por tag")
    ps.add_argument("--lang", help="filtrar tambem por linguagem")
    ps.add_argument(
        "--in",
        dest="in_fields",
        nargs="+",
        choices=list(SEARCH_FIELDS),
        help="restringir aos campos (title tags language content description)",
    )
    ps.add_argument("--fuzzy", action="store_true", help="tolerar erros de digitacao")
    ps.add_argument("--limit", type=int, help="limitar quantidade de resultados")
    ps.add_argument(
        "--sort",
        choices=["relevance", "recent", "created", "used", "title"],
        default="relevance",
        help="ordenacao",
    )
    ps.add_argument("--json", action="store_true", help="saida em JSON")
    ps.set_defaults(func=cmd_search)

    # show
    psh = sub.add_parser("show", help="mostrar um snippet")
    psh.add_argument("id")
    psh.add_argument("--json", action="store_true", help="saida em JSON")
    psh.add_argument("--no-color", action="store_true", help="sem realce de sintaxe")
    psh.add_argument("--no-count", action="store_true", help="nao contar como uso")
    psh.set_defaults(func=cmd_show)

    # copy
    pc = sub.add_parser("copy", help="copiar conteudo para a area de transferencia")
    pc.add_argument("id")
    pc.add_argument("--var", action="append", metavar="K=V", help="valor de placeholder")
    pc.add_argument("--no-prompt", action="store_true", help="nao perguntar placeholders")
    pc.set_defaults(func=cmd_copy)

    # cat
    pcat = sub.add_parser("cat", help="imprimir conteudo no stdout (para pipes)")
    pcat.add_argument("id")
    pcat.add_argument("--var", action="append", metavar="K=V")
    pcat.add_argument("--no-prompt", action="store_true")
    pcat.add_argument("--no-count", action="store_true")
    pcat.set_defaults(func=cmd_cat)

    # run
    prun = sub.add_parser("run", help="executar o snippet como comando de shell")
    prun.add_argument("id")
    prun.add_argument("--var", action="append", metavar="K=V")
    prun.add_argument("--no-prompt", action="store_true")
    prun.add_argument("-y", "--yes", action="store_true", help="nao confirmar")
    prun.set_defaults(func=cmd_run)

    # rm
    pr = sub.add_parser("rm", help="remover snippet")
    pr.add_argument("id")
    pr.add_argument("-y", "--yes", action="store_true", help="nao perguntar")
    pr.set_defaults(func=cmd_rm)

    # edit
    pe = sub.add_parser("edit", help="editar snippet")
    pe.add_argument("id")
    pe.add_argument("content", nargs="*", help="novo conteudo (opcional)")
    pe.add_argument("-t", "--title")
    pe.add_argument("-l", "--language")
    pe.add_argument("-g", "--tags")
    pe.add_argument("-d", "--description")
    pe.add_argument("-f", "--file")
    pe.add_argument("-e", "--editor", action="store_true", help="abrir no $EDITOR")
    pe.add_argument("--pin", action="store_true", help="fixar")
    pe.add_argument("--no-pin", action="store_true", help="desfixar")
    pe.set_defaults(func=cmd_edit)

    # pin / unpin
    pp = sub.add_parser("pin", help="fixar snippet")
    pp.add_argument("id")
    pp.set_defaults(func=cmd_pin)
    pu = sub.add_parser("unpin", help="desfixar snippet")
    pu.add_argument("id")
    pu.set_defaults(func=cmd_unpin)

    # history
    ph = sub.add_parser("history", help="ver/restaurar versoes anteriores")
    ph.add_argument("id")
    ph.add_argument("--restore", type=int, metavar="N", help="restaurar versao N")
    ph.set_defaults(func=cmd_history)

    # tags
    pt = sub.add_parser("tags", help="listar todas as tags")
    pt.set_defaults(func=cmd_tags)

    # export
    pex = sub.add_parser("export", help="exportar snippets (json/markdown)")
    pex.add_argument("--format", choices=["json", "md", "markdown"], default="json")
    pex.add_argument("-o", "--output", help="arquivo de saida (padrao: stdout)")
    pex.add_argument("--tag", help="exportar apenas uma tag")
    pex.add_argument("--title", help="titulo do cookbook (markdown)")
    pex.set_defaults(func=cmd_export)

    # import
    pim = sub.add_parser("import", help="importar snippets de um JSON")
    pim.add_argument("file", help="arquivo JSON (ou '-' para stdin)")
    pim.add_argument("--new-ids", action="store_true", help="gerar novos ids sempre")
    pim.set_defaults(func=cmd_import)

    # complete
    pco = sub.add_parser("complete", help="gerar script de autocompletar")
    pco.add_argument("shell", choices=["bash", "zsh", "powershell", "pwsh"])
    pco.set_defaults(func=cmd_complete)

    # gui
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
