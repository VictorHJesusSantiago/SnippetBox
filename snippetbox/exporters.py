"""Exportacao e importacao de snippets (backup, compartilhamento e cookbook).

Formatos: JSON (fiel, ida e volta) e Markdown (legivel, vira documentacao).
Conecta-se a ideia de "gerador de documentacao a partir de codigo".
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime

from .core import Snippet, Store, _coerce_snippet


def to_json(snippets: list[Snippet]) -> str:
    return json.dumps(
        [asdict(s) for s in snippets], ensure_ascii=False, indent=2
    )


def to_markdown(snippets: list[Snippet], title: str = "SnippetBox Cookbook") -> str:
    """Gera um documento Markdown com todos os snippets agrupados por tag."""
    lines: list[str] = [f"# {title}", ""]
    lines.append(f"_{len(snippets)} snippet(s) — gerado em "
                 f"{datetime.now().strftime('%Y-%m-%d %H:%M')}_")
    lines.append("")

    for s in snippets:
        header = s.title or "(sem titulo)"
        lines.append(f"## {header}")
        if s.pinned:
            lines.append("> **[fixado]**")
        if s.description:
            lines.append("")
            lines.append(s.description)
        meta = []
        if s.language:
            meta.append(f"linguagem: `{s.language}`")
        if s.tags:
            meta.append("tags: " + " ".join(f"`{t}`" for t in s.tags))
        if s.use_count:
            meta.append(f"usos: {s.use_count}")
        if meta:
            lines.append("")
            lines.append(" · ".join(meta))
        lines.append("")
        fence_lang = s.language or ""
        lines.append(f"```{fence_lang}")
        lines.append(s.content)
        lines.append("```")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def export(snippets: list[Snippet], fmt: str = "json", title: str | None = None) -> str:
    fmt = fmt.lower()
    if fmt == "json":
        return to_json(snippets)
    if fmt in ("md", "markdown"):
        return to_markdown(snippets, title or "SnippetBox Cookbook")
    raise ValueError(f"formato desconhecido: {fmt}")


def import_json(store: Store, data: str, replace_ids: bool = False) -> int:
    """Importa snippets de um JSON exportado. Pula ids ja existentes (a menos
    que replace_ids gere novos). Retorna quantos foram adicionados."""
    raw = json.loads(data)
    if isinstance(raw, dict):
        raw = raw.get("snippets", [])
    existing = {s.id for s in store.all()}
    added = 0
    for item in raw:
        snip = _coerce_snippet(item)
        if replace_ids:
            snip.id = Snippet(title="", content="").id  # novo id sempre
        if snip.id in existing:
            continue  # ja existe: pula (use --new-ids para duplicar)
        store.add(snip)
        existing.add(snip.id)
        added += 1
    return added
