"""Interface grafica do SnippetBox (Tkinter).

Layout: busca no topo, lista de snippets a esquerda, detalhe/editor a direita.
Compartilha o mesmo Store da CLI, entao os dados sao os mesmos.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .clipboard import copy as clip_copy
from .core import Snippet, Store, parse_tags


class SnippetApp:
    def __init__(self, root: tk.Tk, store: Store):
        self.root = root
        self.store = store
        self.current: Snippet | None = None
        self._build()
        self.refresh()

    # ---- construcao da UI --------------------------------------------
    def _build(self) -> None:
        self.root.title("SnippetBox")
        self.root.geometry("900x560")
        self.root.minsize(720, 420)

        # barra de busca
        top = ttk.Frame(self.root, padding=(8, 8, 8, 4))
        top.pack(fill="x")
        ttk.Label(top, text="Buscar:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh())
        entry = ttk.Entry(top, textvariable=self.search_var)
        entry.pack(side="left", fill="x", expand=True, padx=6)
        entry.focus_set()
        ttk.Button(top, text="Novo", command=self.new_snippet).pack(side="left")

        # corpo dividido
        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=4)

        # lista
        left = ttk.Frame(body)
        self.listbox = tk.Listbox(left, activestyle="dotbox")
        self.listbox.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(left, orient="vertical", command=self.listbox.yview)
        sb.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=sb.set)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        body.add(left, weight=1)

        # detalhe / editor
        right = ttk.Frame(body)
        body.add(right, weight=2)

        meta = ttk.Frame(right)
        meta.pack(fill="x", pady=(0, 4))
        ttk.Label(meta, text="Titulo").grid(row=0, column=0, sticky="w")
        self.title_var = tk.StringVar()
        ttk.Entry(meta, textvariable=self.title_var).grid(
            row=0, column=1, sticky="ew", padx=4, pady=2
        )
        ttk.Label(meta, text="Linguagem").grid(row=1, column=0, sticky="w")
        self.lang_var = tk.StringVar()
        ttk.Entry(meta, textvariable=self.lang_var).grid(
            row=1, column=1, sticky="ew", padx=4, pady=2
        )
        ttk.Label(meta, text="Tags").grid(row=2, column=0, sticky="w")
        self.tags_var = tk.StringVar()
        ttk.Entry(meta, textvariable=self.tags_var).grid(
            row=2, column=1, sticky="ew", padx=4, pady=2
        )
        meta.columnconfigure(1, weight=1)

        self.text = tk.Text(right, wrap="none", undo=True, font=("Consolas", 10))
        self.text.pack(fill="both", expand=True)

        actions = ttk.Frame(right, padding=(0, 6, 0, 0))
        actions.pack(fill="x")
        ttk.Button(actions, text="Salvar", command=self.save).pack(side="left")
        ttk.Button(actions, text="Copiar", command=self.copy).pack(side="left", padx=4)
        ttk.Button(actions, text="Remover", command=self.delete).pack(side="left")
        self.status = ttk.Label(actions, text="", foreground="#2a7")
        self.status.pack(side="right")

        self.root.bind("<Control-s>", lambda e: self.save())
        self.root.bind("<Control-n>", lambda e: self.new_snippet())

    # ---- dados --------------------------------------------------------
    def refresh(self) -> None:
        query = self.search_var.get()
        self.results = self.store.search(query)
        self.listbox.delete(0, "end")
        for s in self.results:
            lang = f" [{s.language}]" if s.language else ""
            self.listbox.insert("end", f"{s.title}{lang}")
        # mantem selecao do snippet atual, se ainda visivel
        if self.current:
            for i, s in enumerate(self.results):
                if s.id == self.current.id:
                    self.listbox.selection_set(i)
                    break

    def on_select(self, _evt) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        self.load_snippet(self.results[sel[0]])

    def load_snippet(self, s: Snippet) -> None:
        self.current = s
        self.title_var.set(s.title)
        self.lang_var.set(s.language)
        self.tags_var.set(", ".join(s.tags))
        self.text.delete("1.0", "end")
        self.text.insert("1.0", s.content)
        self._flash("")

    def new_snippet(self) -> None:
        self.current = None
        self.title_var.set("")
        self.lang_var.set("")
        self.tags_var.set("")
        self.text.delete("1.0", "end")
        self.listbox.selection_clear(0, "end")
        self.text.focus_set()
        self._flash("novo snippet")

    def _collect(self) -> tuple[str, str, str, list[str]]:
        title = self.title_var.get().strip()
        content = self.text.get("1.0", "end").rstrip("\n")
        lang = self.lang_var.get().strip()
        tags = parse_tags(self.tags_var.get())
        if not title:
            title = content.splitlines()[0][:60] if content else "(sem titulo)"
        return title, content, lang, tags

    def save(self) -> None:
        title, content, lang, tags = self._collect()
        if not content.strip():
            messagebox.showwarning("SnippetBox", "Conteudo vazio.")
            return
        if self.current is None:
            snip = Snippet(title=title, content=content, language=lang, tags=tags)
            self.store.add(snip)
            self.current = snip
            self._flash("criado")
        else:
            self.current.title = title
            self.current.content = content
            self.current.language = lang
            self.current.tags = tags
            self.store.update(self.current)
            self._flash("salvo")
        self.refresh()

    def copy(self) -> None:
        content = self.text.get("1.0", "end").rstrip("\n")
        if not content:
            return
        self._flash("copiado" if clip_copy(content) else "falha ao copiar")

    def delete(self) -> None:
        if self.current is None:
            return
        if not messagebox.askyesno("SnippetBox", f"Remover '{self.current.title}'?"):
            return
        self.store.delete(self.current.id)
        self.new_snippet()
        self.refresh()
        self._flash("removido")

    def _flash(self, msg: str) -> None:
        self.status.config(text=msg)


def run(store: Store | None = None) -> None:
    store = store or Store()
    root = tk.Tk()
    SnippetApp(root, store)
    root.mainloop()


if __name__ == "__main__":
    run()
