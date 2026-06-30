"""Copia texto para a area de transferencia sem dependencias externas.

Tenta tkinter (sempre disponivel aqui) e cai para utilitarios nativos
do SO se preciso.
"""

from __future__ import annotations

import subprocess
import sys


def copy(text: str) -> bool:
    # 1) tkinter funciona em Windows, macOS e Linux com display
    try:
        import tkinter

        r = tkinter.Tk()
        r.withdraw()
        r.clipboard_clear()
        r.clipboard_append(text)
        r.update()  # garante que o clipboard seja preenchido
        r.destroy()
        return True
    except Exception:
        pass

    # 2) utilitarios nativos
    candidates: list[list[str]] = []
    if sys.platform == "win32":
        candidates.append(["clip"])
    elif sys.platform == "darwin":
        candidates.append(["pbcopy"])
    else:
        candidates.append(["xclip", "-selection", "clipboard"])
        candidates.append(["xsel", "--clipboard", "--input"])

    for cmd in candidates:
        try:
            p = subprocess.run(cmd, input=text.encode("utf-8"), check=True)
            if p.returncode == 0:
                return True
        except Exception:
            continue
    return False
