"""Placeholders em snippets: ``docker run {{image}}``.

Permite guardar comandos com variaveis e preenche-las na hora de copiar/rodar.
Sem dependencias externas.
"""

from __future__ import annotations

import re

PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][\w-]*)\s*\}\}")


def extract(text: str) -> list[str]:
    """Nomes de placeholders na ordem de aparicao, sem repetir."""
    seen: list[str] = []
    for m in PLACEHOLDER_RE.finditer(text or ""):
        name = m.group(1)
        if name not in seen:
            seen.append(name)
    return seen


def fill(text: str, values: dict[str, str]) -> str:
    """Substitui ``{{nome}}`` pelos valores informados. Faltantes ficam como
    estao."""

    def repl(m: re.Match) -> str:
        name = m.group(1)
        return values.get(name, m.group(0))

    return PLACEHOLDER_RE.sub(repl, text or "")


def parse_assignments(pairs) -> dict[str, str]:
    """Converte ['k=v', 'a=b c'] em {'k': 'v', 'a': 'b c'}."""
    out: dict[str, str] = {}
    for item in pairs or []:
        if "=" in item:
            k, v = item.split("=", 1)
            out[k.strip()] = v
    return out
