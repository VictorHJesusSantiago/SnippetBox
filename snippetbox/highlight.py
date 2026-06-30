"""Realce de sintaxe leve para o terminal, via codigos ANSI.

Generico (nao e um parser completo): destaca strings, comentarios, numeros e
algumas palavras-chave comuns. Usa pygments se estiver instalado; caso
contrario cai para o realce nativo. Sem dependencias obrigatorias.
"""

from __future__ import annotations

import re

RESET = "\033[0m"
_COLORS = {
    "keyword": "\033[36m",   # ciano
    "string": "\033[32m",    # verde
    "comment": "\033[90m",   # cinza
    "number": "\033[33m",    # amarelo
}

_KEYWORDS = {
    "def", "class", "return", "import", "from", "if", "else", "elif", "for",
    "while", "in", "is", "not", "and", "or", "with", "as", "try", "except",
    "finally", "lambda", "yield", "const", "let", "var", "function", "public",
    "private", "static", "void", "int", "string", "package", "func", "select",
    "insert", "update", "delete", "from", "where", "echo", "sudo", "true",
    "false", "null", "none",
}

_TOKEN_RE = re.compile(
    r"""
    (?P<comment>\#[^\n]*|//[^\n]*)        |
    (?P<string>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')  |
    (?P<number>\b\d+(?:\.\d+)?\b)         |
    (?P<word>[A-Za-z_]\w*)
    """,
    re.VERBOSE,
)


def supported(stream) -> bool:
    """True se vale a pena emitir cores (saida e um terminal)."""
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def highlight(code: str, language: str = "") -> str:
    """Devolve o codigo com cores ANSI. Tenta pygments primeiro."""
    pyg = _highlight_pygments(code, language)
    if pyg is not None:
        return pyg
    return _highlight_basic(code)


def _highlight_basic(code: str) -> str:
    def repl(m: re.Match) -> str:
        kind = m.lastgroup
        val = m.group()
        if kind == "word":
            if val.lower() in _KEYWORDS:
                return f"{_COLORS['keyword']}{val}{RESET}"
            return val
        color = _COLORS.get(kind)
        return f"{color}{val}{RESET}" if color else val

    return _TOKEN_RE.sub(repl, code)


def _highlight_pygments(code: str, language: str):
    try:
        from pygments import highlight as _h
        from pygments.lexers import get_lexer_by_name, guess_lexer
        from pygments.formatters import TerminalFormatter
    except Exception:
        return None
    try:
        lexer = get_lexer_by_name(language) if language else guess_lexer(code)
    except Exception:
        try:
            lexer = guess_lexer(code)
        except Exception:
            return None
    return _h(code, lexer, TerminalFormatter()).rstrip("\n")
