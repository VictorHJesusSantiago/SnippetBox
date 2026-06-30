"""Nucleo do SnippetBox: modelo de dados e armazenamento.

Reutilizado tanto pela CLI quanto pela GUI. Sem dependencias externas:
o armazenamento e um unico arquivo JSON no diretorio do usuario.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable


def default_store_path() -> Path:
    """Caminho do arquivo de dados.

    Respeita SNIPPETBOX_HOME se definido (util para testes e portabilidade),
    caso contrario usa ~/.snippetbox/snippets.json.
    """
    base = os.environ.get("SNIPPETBOX_HOME")
    if base:
        return Path(base) / "snippets.json"
    return Path.home() / ".snippetbox" / "snippets.json"


@dataclass
class Snippet:
    title: str
    content: str
    language: str = ""
    tags: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def matches(self, query: str) -> bool:
        """True se a query (case-insensitive) aparece em titulo, conteudo,
        linguagem ou tags."""
        if not query:
            return True
        q = query.lower()
        haystack = " ".join(
            [self.title, self.content, self.language, " ".join(self.tags)]
        ).lower()
        return q in haystack

    def score(self, query: str) -> int:
        """Pontuacao simples de relevancia para ordenar resultados de busca."""
        if not query:
            return 0
        q = query.lower()
        s = 0
        if q in self.title.lower():
            s += 10
        if q in " ".join(self.tags).lower():
            s += 5
        if q == self.language.lower():
            s += 3
        if q in self.content.lower():
            s += 1
        return s


class Store:
    """Camada de persistencia. Carrega tudo em memoria e grava o JSON inteiro
    a cada modificacao (volume pessoal e pequeno, simplicidade vale mais)."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else default_store_path()
        self._snippets: list[Snippet] = []
        self._loaded = False

    # ---- persistencia -------------------------------------------------
    def load(self) -> None:
        self._snippets = []
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8") or "[]")
            for item in raw:
                self._snippets.append(Snippet(**item))
        self._loaded = True

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(s) for s in self._snippets]
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # ---- operacoes ----------------------------------------------------
    def all(self) -> list[Snippet]:
        self._ensure_loaded()
        return list(self._snippets)

    def get(self, snippet_id: str) -> Snippet | None:
        self._ensure_loaded()
        for s in self._snippets:
            if s.id == snippet_id:
                return s
        # tambem aceita prefixo unico do id
        matches = [s for s in self._snippets if s.id.startswith(snippet_id)]
        return matches[0] if len(matches) == 1 else None

    def add(self, snippet: Snippet) -> Snippet:
        self._ensure_loaded()
        self._snippets.append(snippet)
        self.save()
        return snippet

    def update(self, snippet: Snippet) -> None:
        self._ensure_loaded()
        snippet.updated_at = time.time()
        for i, s in enumerate(self._snippets):
            if s.id == snippet.id:
                self._snippets[i] = snippet
                self.save()
                return
        raise KeyError(f"snippet {snippet.id} nao encontrado")

    def delete(self, snippet_id: str) -> bool:
        self._ensure_loaded()
        target = self.get(snippet_id)
        if target is None:
            return False
        self._snippets = [s for s in self._snippets if s.id != target.id]
        self.save()
        return True

    def search(self, query: str) -> list[Snippet]:
        self._ensure_loaded()
        hits = [s for s in self._snippets if s.matches(query)]
        if query:
            hits.sort(key=lambda s: s.score(query), reverse=True)
        else:
            hits.sort(key=lambda s: s.updated_at, reverse=True)
        return hits

    def all_tags(self) -> list[str]:
        self._ensure_loaded()
        tags: set[str] = set()
        for s in self._snippets:
            tags.update(s.tags)
        return sorted(tags)


def parse_tags(value: str | Iterable[str] | None) -> list[str]:
    """Normaliza tags vindas de string 'a,b,c' ou lista."""
    if not value:
        return []
    if isinstance(value, str):
        parts = value.replace(";", ",").split(",")
    else:
        parts = list(value)
    return sorted({p.strip() for p in parts if p.strip()})
