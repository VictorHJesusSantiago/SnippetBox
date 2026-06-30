"""Nucleo do SnippetBox: modelo de dados e armazenamento.

Reutilizado tanto pela CLI quanto pela GUI. Sem dependencias externas:
o armazenamento e um unico arquivo JSON no diretorio do usuario.
"""

from __future__ import annotations

import difflib
import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict, fields as dataclass_fields
from pathlib import Path
from typing import Iterable

# Versao do formato em disco. Veja Store.load / _migrate.
SCHEMA_VERSION = 2

# Campos pesquisaveis (usados por busca por campo especifico e operadores in:).
SEARCH_FIELDS = ("title", "tags", "language", "content", "description")


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
    description: str = ""
    pinned: bool = False
    use_count: int = 0
    last_used: float = 0.0
    history: list[dict] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # ---- busca --------------------------------------------------------
    def _field_text(self, name: str) -> str:
        if name == "tags":
            return " ".join(self.tags)
        return str(getattr(self, name, "") or "")

    def haystack(self, fields: Iterable[str] | None = None) -> str:
        names = tuple(fields) if fields else SEARCH_FIELDS
        return " ".join(self._field_text(n) for n in names).lower()

    def matches(
        self, query: str, fields: Iterable[str] | None = None, fuzzy: bool = False
    ) -> bool:
        """True se a query (case-insensitive) aparece nos campos pedidos.

        Com fuzzy=True tolera pequenos erros de digitacao via difflib.
        """
        if not query:
            return True
        q = query.lower()
        hay = self.haystack(fields)
        if q in hay:
            return True
        if fuzzy:
            tokens = set(hay.split())
            for word in q.split():
                if difflib.get_close_matches(word, tokens, n=1, cutoff=0.78):
                    return True
        return False

    def score(self, query: str, fields: Iterable[str] | None = None) -> float:
        """Pontuacao de relevancia para ordenar resultados de busca."""
        s = 0.0
        if query:
            q = query.lower()
            names = tuple(fields) if fields else SEARCH_FIELDS
            weights = {
                "title": 10,
                "tags": 5,
                "language": 3,
                "description": 2,
                "content": 1,
            }
            for n in names:
                text = self._field_text(n).lower()
                if not text:
                    continue
                if n == "language":
                    if q == text:
                        s += weights[n]
                elif q in text:
                    s += weights.get(n, 1)
        if self.pinned:
            s += 100  # fixados sempre no topo
        return s


def _coerce_snippet(item: dict) -> Snippet:
    """Constroi um Snippet ignorando chaves desconhecidas (compat. de schema)."""
    known = {f.name for f in dataclass_fields(Snippet)}
    return Snippet(**{k: v for k, v in item.items() if k in known})


class FileLock:
    """Lock entre processos via arquivo .lock (O_EXCL), para CLI e GUI nao
    corromperem o JSON ao gravar ao mesmo tempo. Locks orfaos (processo morto)
    sao considerados velhos apos `stale` segundos."""

    def __init__(self, target: Path, timeout: float = 5.0, stale: float = 30.0):
        self.lock_path = Path(str(target) + ".lock")
        self.timeout = timeout
        self.stale = stale
        self._fd: int | None = None

    def acquire(self) -> None:
        deadline = time.time() + self.timeout
        while True:
            try:
                self._fd = os.open(
                    self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                )
                os.write(self._fd, str(os.getpid()).encode())
                return
            except FileExistsError:
                # lock velho de um processo que morreu? remove e tenta de novo.
                try:
                    age = time.time() - self.lock_path.stat().st_mtime
                    if age > self.stale:
                        self.lock_path.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.time() >= deadline:
                    # nao trava o usuario indefinidamente; segue sem o lock.
                    return
                time.sleep(0.05)

    def release(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        self.lock_path.unlink(missing_ok=True)

    def __enter__(self) -> "FileLock":
        self.acquire()
        return self

    def __exit__(self, *exc) -> None:
        self.release()


class Store:
    """Camada de persistencia. Carrega tudo em memoria e grava o JSON inteiro
    a cada modificacao (volume pessoal e pequeno, simplicidade vale mais)."""

    HISTORY_LIMIT = 20

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else default_store_path()
        self._snippets: list[Snippet] = []
        # snapshot do estado persistido por id, para detectar mudancas no
        # historico mesmo quando o chamador muta o proprio objeto da store.
        self._persisted: dict[str, dict] = {}
        self._loaded = False

    # ---- persistencia -------------------------------------------------
    def load(self) -> None:
        self._snippets = []
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8") or "[]")
            for item in self._migrate(raw):
                self._snippets.append(_coerce_snippet(item))
        self._loaded = True
        self._snapshot()

    def _snapshot(self) -> None:
        self._persisted = {s.id: asdict(s) for s in self._snippets}

    @staticmethod
    def _migrate(raw) -> list[dict]:
        """Aceita o formato antigo (lista pura, v1) e o novo (objeto com
        'version' e 'snippets'). Retorna sempre a lista de dicts de snippets."""
        if isinstance(raw, list):
            return raw  # v1
        if isinstance(raw, dict):
            return raw.get("snippets", [])
        return []

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": SCHEMA_VERSION,
            "snippets": [asdict(s) for s in self._snippets],
        }
        with FileLock(self.path):
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tmp.replace(self.path)
        self._snapshot()

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

    def find_duplicate(self, content: str) -> Snippet | None:
        """Snippet com conteudo identico (ignorando espacos nas pontas)."""
        self._ensure_loaded()
        needle = content.strip()
        for s in self._snippets:
            if s.content.strip() == needle:
                return s
        return None

    def update(self, snippet: Snippet, keep_history: bool = True) -> None:
        self._ensure_loaded()
        for i, s in enumerate(self._snippets):
            if s.id == snippet.id:
                if keep_history:
                    self._push_history(snippet)
                snippet.updated_at = time.time()
                self._snippets[i] = snippet
                self.save()
                return
        raise KeyError(f"snippet {snippet.id} nao encontrado")

    def _push_history(self, snippet: Snippet) -> None:
        """Guarda uma versao anterior se algo relevante mudou, comparando com
        o estado persistido (funciona mesmo se o chamador mutou o objeto)."""
        prev = self._persisted.get(snippet.id)
        if prev is None:
            return
        changed = (
            prev["content"] != snippet.content
            or prev["title"] != snippet.title
            or prev["language"] != snippet.language
            or prev["tags"] != snippet.tags
            or prev.get("description", "") != snippet.description
        )
        if not changed:
            return
        snapshot = {
            "title": prev["title"],
            "content": prev["content"],
            "language": prev["language"],
            "tags": list(prev["tags"]),
            "description": prev.get("description", ""),
            "saved_at": prev["updated_at"],
        }
        snippet.history = (snippet.history or []) + [snapshot]
        if len(snippet.history) > self.HISTORY_LIMIT:
            snippet.history = snippet.history[-self.HISTORY_LIMIT :]

    def restore_version(self, snippet_id: str, index: int) -> Snippet | None:
        """Restaura a versao `index` do historico (0 = mais antiga)."""
        s = self.get(snippet_id)
        if s is None or not s.history:
            return None
        if index < 0 or index >= len(s.history):
            return None
        ver = s.history[index]
        s.title = ver["title"]
        s.content = ver["content"]
        s.language = ver.get("language", "")
        s.tags = list(ver.get("tags", []))
        s.description = ver.get("description", "")
        self.update(s)  # a restauracao tambem entra no historico
        return s

    def touch(self, snippet_id: str) -> None:
        """Registra um uso (copy/show/run): incrementa contador e data."""
        s = self.get(snippet_id)
        if s is None:
            return
        s.use_count += 1
        s.last_used = time.time()
        self.save()

    def set_pinned(self, snippet_id: str, pinned: bool) -> Snippet | None:
        s = self.get(snippet_id)
        if s is None:
            return None
        s.pinned = pinned
        self.save()
        return s

    def delete(self, snippet_id: str) -> bool:
        self._ensure_loaded()
        target = self.get(snippet_id)
        if target is None:
            return False
        self._snippets = [s for s in self._snippets if s.id != target.id]
        self.save()
        return True

    # ---- busca --------------------------------------------------------
    def search(
        self,
        query: str = "",
        *,
        tag: str | Iterable[str] | None = None,
        language: str | None = None,
        fields: Iterable[str] | None = None,
        fuzzy: bool = False,
        sort: str = "relevance",
        limit: int | None = None,
    ) -> list[Snippet]:
        """Busca combinando texto livre, operadores na query, filtro por tag e
        por linguagem.

        - Operadores aceitos na string: ``tag:x``, ``lang:y``, ``in:campo``.
        - `tag`/`language` aplicam filtros adicionais (combinaveis com a query).
        - `fields` restringe os campos pesquisados pelo texto livre.
        - `sort`: relevance | recent | created | used | title.
        """
        self._ensure_loaded()
        spec = parse_query(query)

        want_tags = set(_as_list(tag)) | set(spec.tags)
        want_langs = set(_as_list(language)) | set(spec.langs)
        search_fields = list(fields) if fields else (spec.fields or None)
        text = spec.text

        results: list[Snippet] = []
        for s in self._snippets:
            if want_tags and not want_tags.issubset(set(s.tags)):
                continue
            if want_langs and s.language.lower() not in {l.lower() for l in want_langs}:
                continue
            if not s.matches(text, fields=search_fields, fuzzy=fuzzy):
                continue
            results.append(s)

        self._sort(results, sort, text, search_fields)
        if limit is not None:
            results = results[:limit]
        return results

    def _sort(self, items, sort, text, fields) -> None:
        if sort == "recent":
            items.sort(key=lambda s: (s.pinned, s.updated_at), reverse=True)
        elif sort == "created":
            items.sort(key=lambda s: (s.pinned, s.created_at), reverse=True)
        elif sort == "used":
            items.sort(key=lambda s: (s.pinned, s.use_count, s.last_used), reverse=True)
        elif sort == "title":
            items.sort(key=lambda s: s.title.lower())
            items.sort(key=lambda s: s.pinned, reverse=True)
        else:  # relevance
            if text:
                items.sort(
                    key=lambda s: (s.score(text, fields), s.updated_at), reverse=True
                )
            else:
                items.sort(key=lambda s: (s.pinned, s.updated_at), reverse=True)

    def all_tags(self) -> list[str]:
        self._ensure_loaded()
        tags: set[str] = set()
        for s in self._snippets:
            tags.update(s.tags)
        return sorted(tags)

    def all_languages(self) -> list[str]:
        self._ensure_loaded()
        return sorted({s.language for s in self._snippets if s.language})


# ---- consultas e utilidades ------------------------------------------
@dataclass
class QuerySpec:
    text: str = ""
    tags: list[str] = field(default_factory=list)
    langs: list[str] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)


def parse_query(raw: str) -> QuerySpec:
    """Quebra uma string de busca em texto livre + operadores.

    Ex.: ``tag:docker lang:bash in:title subir`` ->
    text='subir', tags=['docker'], langs=['bash'], fields=['title'].
    """
    spec = QuerySpec()
    if not raw:
        return spec
    text_parts: list[str] = []
    for tok in raw.split():
        low = tok.lower()
        if low.startswith("tag:") and len(tok) > 4:
            spec.tags.append(tok[4:])
        elif low.startswith("lang:") and len(tok) > 5:
            spec.langs.append(tok[5:])
        elif low.startswith("in:") and len(tok) > 3:
            fld = tok[3:].lower()
            if fld in SEARCH_FIELDS and fld not in spec.fields:
                spec.fields.append(fld)
        else:
            text_parts.append(tok)
    spec.text = " ".join(text_parts)
    return spec


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    return [v for v in value if v]


def parse_tags(value: str | Iterable[str] | None) -> list[str]:
    """Normaliza tags vindas de string 'a,b,c' ou lista."""
    if not value:
        return []
    if isinstance(value, str):
        parts = value.replace(";", ",").split(",")
    else:
        parts = list(value)
    return sorted({p.strip() for p in parts if p.strip()})


# ---- deteccao de linguagem -------------------------------------------
# Heuristica simples (sem dependencias): assinaturas comuns por linguagem.
_LANG_SIGNS: list[tuple[str, tuple[str, ...]]] = [
    ("python", ("def ", "import ", "print(", "self.", "elif ", "__name__")),
    ("javascript", ("const ", "let ", "=>", "console.log", "function ", "require(")),
    ("bash", ("#!/bin/bash", "#!/bin/sh", "sudo ", "apt ", "echo $", "grep ", "| awk")),
    ("docker", ("docker ", "docker compose", "dockerfile", "entrypoint", "expose ")),
    ("sql", ("select ", "insert into", "update ", "delete from", "create table")),
    ("json", ('{"', '": ', "[\n  {")),
    ("html", ("<html", "<div", "<span", "<!doctype")),
    ("go", ("package main", "func ", "fmt.", ":= ")),
    ("java", ("public class", "System.out", "void main", "import java.")),
    ("yaml", ("---\n", ":\n  - ", "version:")),
]


def detect_language(content: str) -> str:
    """Tenta adivinhar a linguagem pelo conteudo. '' se incerto."""
    if not content:
        return ""
    text = content.lower()
    best, best_score = "", 0
    for lang, signs in _LANG_SIGNS:
        score = sum(1 for sign in signs if sign.lower() in text)
        if score > best_score:
            best, best_score = lang, score
    return best
