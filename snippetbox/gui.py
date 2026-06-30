"""Interface grafica do SnippetBox (Tkinter).

Layout: busca no topo, painel de tags + lista a esquerda, detalhe/editor a
direita. Compartilha o mesmo Store da CLI, entao os dados sao os mesmos.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import exporters, placeholders
from .clipboard import copy as clip_copy
from .core import Snippet, Store, parse_tags

# Paletas de tema (claro / escuro).
THEMES = {
    "claro": {
        "bg": "#f4f4f4", "fg": "#1a1a1a", "field": "#ffffff",
        "select": "#cde4ff", "accent": "#2266cc",
        "comment": "#7a7a7a", "string": "#1a7f37", "keyword": "#0a52c4",
    },
    "escuro": {
        "bg": "#1e1e1e", "fg": "#e6e6e6", "field": "#252526",
        "select": "#264f78", "accent": "#4da6ff",
        "comment": "#6a9955", "string": "#ce9178", "keyword": "#569cd6",
    },
}

_KEYWORDS = {
    "def", "class", "return", "import", "from", "if", "else", "elif", "for",
    "while", "in", "with", "as", "try", "except", "lambda", "const", "let",
    "var", "function", "public", "private", "func", "package", "echo", "sudo",
    "select", "insert", "update", "delete", "where",
}


class SnippetApp:
    def __init__(self, root: tk.Tk, store: Store):
        self.root = root
        self.store = store
        self.current: Snippet | None = None
        self.results: list[Snippet] = []
        self.active_tag: str | None = None
        self.theme_name = "claro"
        self._build()
        self.apply_theme()
        self.refresh()

    # ---- construcao da UI --------------------------------------------
    def _build(self) -> None:
        self.root.title("SnippetBox")
        self.root.geometry("1000x600")
        self.root.minsize(760, 440)

        # barra de busca
        top = ttk.Frame(self.root, padding=(8, 8, 8, 4))
        top.pack(fill="x")
        ttk.Label(top, text="Buscar:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh())
        self.search_entry = ttk.Entry(top, textvariable=self.search_var)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=6)
        self.search_entry.focus_set()
        ttk.Button(top, text="Novo", command=self.new_snippet).pack(side="left")
        self.theme_btn = ttk.Button(top, text="Tema", command=self.toggle_theme)
        self.theme_btn.pack(side="left", padx=4)
        ttk.Button(top, text="Exportar", command=self.export_md).pack(side="left")

        # corpo dividido
        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=4)

        # esquerda: tags + lista
        left = ttk.Frame(body)
        tagbar = ttk.Frame(left)
        tagbar.pack(fill="x", pady=(0, 4))
        ttk.Label(tagbar, text="Tags:").pack(side="left")
        self.tag_combo = ttk.Combobox(tagbar, state="readonly", width=14)
        self.tag_combo.pack(side="left", padx=4)
        self.tag_combo.bind("<<ComboboxSelected>>", self.on_tag_pick)
        ttk.Button(tagbar, text="x", width=2, command=self.clear_tag).pack(side="left")

        self.listbox = tk.Listbox(left, activestyle="dotbox")
        self.listbox.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(left, orient="vertical", command=self.listbox.yview)
        sb.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=sb.set)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        body.add(left, weight=1)

        # direita: detalhe / editor
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
        ttk.Label(meta, text="Descricao").grid(row=3, column=0, sticky="w")
        self.desc_var = tk.StringVar()
        ttk.Entry(meta, textvariable=self.desc_var).grid(
            row=3, column=1, sticky="ew", padx=4, pady=2
        )
        self.pin_var = tk.BooleanVar()
        ttk.Checkbutton(meta, text="Fixado", variable=self.pin_var).grid(
            row=4, column=1, sticky="w", padx=4
        )
        meta.columnconfigure(1, weight=1)

        self.text = tk.Text(
            right, wrap="none", undo=True, font=("Consolas", 10),
            insertbackground="#000000",
        )
        self.text.pack(fill="both", expand=True)
        self.text.bind("<KeyRelease>", lambda e: self._schedule_highlight())

        actions = ttk.Frame(right, padding=(0, 6, 0, 0))
        actions.pack(fill="x")
        ttk.Button(actions, text="Salvar", command=self.save).pack(side="left")
        ttk.Button(actions, text="Copiar", command=self.copy).pack(side="left", padx=4)
        ttk.Button(actions, text="Remover", command=self.delete).pack(side="left")
        self.status = ttk.Label(actions, text="")
        self.status.pack(side="right")

        self.root.bind("<Control-s>", lambda e: self.save())
        self.root.bind("<Control-n>", lambda e: self.new_snippet())
        self.root.bind("<Control-f>", lambda e: self.search_entry.focus_set())
        self._hl_job = None

    # ---- tema ---------------------------------------------------------
    def toggle_theme(self) -> None:
        self.theme_name = "escuro" if self.theme_name == "claro" else "claro"
        self.apply_theme()

    def apply_theme(self) -> None:
        t = THEMES[self.theme_name]
        self.root.configure(bg=t["bg"])
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=t["bg"], foreground=t["fg"])
        style.configure("TFrame", background=t["bg"])
        style.configure("TLabel", background=t["bg"], foreground=t["fg"])
        style.configure("TButton", background=t["field"], foreground=t["fg"])
        style.configure("TCheckbutton", background=t["bg"], foreground=t["fg"])
        style.configure(
            "TEntry", fieldbackground=t["field"], foreground=t["fg"]
        )
        self.listbox.configure(
            bg=t["field"], fg=t["fg"], selectbackground=t["select"],
            highlightbackground=t["bg"],
        )
        self.text.configure(
            bg=t["field"], fg=t["fg"], insertbackground=t["fg"],
            selectbackground=t["select"],
        )
        self.status.configure(foreground=t["accent"])
        self.text.tag_configure("kw", foreground=t["keyword"])
        self.text.tag_configure("str", foreground=t["string"])
        self.text.tag_configure("com", foreground=t["comment"])
        self._highlight()

    # ---- realce -------------------------------------------------------
    def _schedule_highlight(self) -> None:
        if self._hl_job:
            self.root.after_cancel(self._hl_job)
        self._hl_job = self.root.after(250, self._highlight)

    def _highlight(self) -> None:
        self._hl_job = None
        for tag in ("kw", "str", "com"):
            self.text.tag_remove(tag, "1.0", "end")
        content = self.text.get("1.0", "end-1c")
        for i, line in enumerate(content.split("\n"), start=1):
            self._highlight_line(i, line)

    def _highlight_line(self, lineno: int, line: str) -> None:
        import re

        # comentarios
        m = re.search(r"(#|//).*$", line)
        if m:
            self.text.tag_add("com", f"{lineno}.{m.start()}", f"{lineno}.end")
        # strings
        for sm in re.finditer(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'", line):
            self.text.tag_add("str", f"{lineno}.{sm.start()}", f"{lineno}.{sm.end()}")
        # palavras-chave
        for wm in re.finditer(r"[A-Za-z_]\w*", line):
            if wm.group().lower() in _KEYWORDS:
                self.text.tag_add(
                    "kw", f"{lineno}.{wm.start()}", f"{lineno}.{wm.end()}"
                )

    # ---- dados --------------------------------------------------------
    def refresh(self) -> None:
        query = self.search_var.get()
        self.results = self.store.search(query, tag=self.active_tag, sort="recent")
        self.listbox.delete(0, "end")
        for s in self.results:
            pin = "* " if s.pinned else ""
            lang = f" [{s.language}]" if s.language else ""
            self.listbox.insert("end", f"{pin}{s.title}{lang}")
        # atualiza combo de tags
        tags = self.store.all_tags()
        self.tag_combo["values"] = tags
        # mantem selecao do snippet atual, se ainda visivel
        if self.current:
            for i, s in enumerate(self.results):
                if s.id == self.current.id:
                    self.listbox.selection_set(i)
                    break

    def on_tag_pick(self, _evt) -> None:
        self.active_tag = self.tag_combo.get() or None
        self.refresh()

    def clear_tag(self) -> None:
        self.active_tag = None
        self.tag_combo.set("")
        self.refresh()

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
        self.desc_var.set(s.description)
        self.pin_var.set(s.pinned)
        self.text.delete("1.0", "end")
        self.text.insert("1.0", s.content)
        self._highlight()
        self._flash("")

    def new_snippet(self) -> None:
        self.current = None
        self.title_var.set("")
        self.lang_var.set("")
        self.tags_var.set("")
        self.desc_var.set("")
        self.pin_var.set(False)
        self.text.delete("1.0", "end")
        self.listbox.selection_clear(0, "end")
        self.text.focus_set()
        self._flash("novo snippet")

    def _collect(self):
        title = self.title_var.get().strip()
        content = self.text.get("1.0", "end").rstrip("\n")
        lang = self.lang_var.get().strip()
        tags = parse_tags(self.tags_var.get())
        desc = self.desc_var.get().strip()
        if not title:
            title = content.splitlines()[0][:60] if content else "(sem titulo)"
        return title, content, lang, tags, desc

    def save(self) -> None:
        title, content, lang, tags, desc = self._collect()
        if not content.strip():
            messagebox.showwarning("SnippetBox", "Conteudo vazio.")
            return
        if self.current is None:
            snip = Snippet(
                title=title, content=content, language=lang, tags=tags,
                description=desc, pinned=self.pin_var.get(),
            )
            self.store.add(snip)
            self.current = snip
            self._flash("criado")
        else:
            self.current.title = title
            self.current.content = content
            self.current.language = lang
            self.current.tags = tags
            self.current.description = desc
            self.current.pinned = self.pin_var.get()
            self.store.update(self.current)
            self._flash("salvo")
        self.refresh()

    def copy(self) -> None:
        content = self.text.get("1.0", "end").rstrip("\n")
        if not content:
            return
        # preenche placeholders, se houver
        names = placeholders.extract(content)
        if names:
            values = {}
            for name in names:
                val = simpledialog.askstring("Placeholder", f"{name} =", parent=self.root)
                if val is None:
                    self._flash("copia cancelada")
                    return
                values[name] = val
            content = placeholders.fill(content, values)
        ok = clip_copy(content)
        if ok and self.current:
            self.store.touch(self.current.id)
        self._flash("copiado" if ok else "falha ao copiar")

    def delete(self) -> None:
        if self.current is None:
            return
        if not messagebox.askyesno("SnippetBox", f"Remover '{self.current.title}'?"):
            return
        self.store.delete(self.current.id)
        self.new_snippet()
        self.refresh()
        self._flash("removido")

    def export_md(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Exportar cookbook",
            defaultextension=".md",
            filetypes=[("Markdown", "*.md"), ("JSON", "*.json"), ("Todos", "*.*")],
        )
        if not path:
            return
        items = self.store.search("", sort="title")
        fmt = "md" if path.lower().endswith(".md") else "json"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(exporters.export(items, fmt=fmt))
        self._flash(f"exportado: {len(items)} snippet(s)")

    def _flash(self, msg: str) -> None:
        self.status.config(text=msg)


def run(store: Store | None = None) -> None:
    store = store or Store()
    root = tk.Tk()
    SnippetApp(root, store)
    root.mainloop()


if __name__ == "__main__":
    run()
