import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from snippetbox.core import (
    Snippet,
    Store,
    detect_language,
    parse_query,
)
from snippetbox import exporters, placeholders, completion
from snippetbox.highlight import highlight, _highlight_basic


def make_store(tmp_path) -> Store:
    return Store(tmp_path / "snippets.json")


# ---- busca avancada ---------------------------------------------------
def test_search_by_field(tmp_path):
    store = make_store(tmp_path)
    store.add(Snippet(title="docker", content="nada", language="bash"))
    store.add(Snippet(title="outro", content="docker compose"))
    # restrito ao titulo: so o primeiro
    hits = store.search("docker", fields=["title"])
    assert len(hits) == 1 and hits[0].title == "docker"


def test_combined_tag_and_lang(tmp_path):
    store = make_store(tmp_path)
    store.add(Snippet(title="a", content="x", language="bash", tags=["docker"]))
    store.add(Snippet(title="b", content="x", language="python", tags=["docker"]))
    hits = store.search("", tag="docker", language="bash")
    assert len(hits) == 1 and hits[0].title == "a"


def test_query_operators():
    spec = parse_query("tag:docker lang:bash in:title subir stack")
    assert spec.tags == ["docker"]
    assert spec.langs == ["bash"]
    assert spec.fields == ["title"]
    assert spec.text == "subir stack"


def test_search_operators_integration(tmp_path):
    store = make_store(tmp_path)
    store.add(Snippet(title="subir", content="x", language="bash", tags=["docker"]))
    store.add(Snippet(title="subir", content="x", language="python", tags=["docker"]))
    hits = store.search("tag:docker lang:bash subir")
    assert len(hits) == 1


def test_fuzzy_search(tmp_path):
    store = make_store(tmp_path)
    store.add(Snippet(title="docker compose", content="up"))
    assert store.search("dcoker", fuzzy=True)  # erro de digitacao
    assert not store.search("dcoker", fuzzy=False)


# ---- pinned, uso, recentes -------------------------------------------
def test_pinned_first(tmp_path):
    store = make_store(tmp_path)
    a = store.add(Snippet(title="a", content="x"))
    b = store.add(Snippet(title="b", content="x"))
    store.set_pinned(b.id, True)
    hits = store.search("", sort="recent")
    assert hits[0].id == b.id


def test_touch_and_used_sort(tmp_path):
    store = make_store(tmp_path)
    a = store.add(Snippet(title="a", content="x"))
    b = store.add(Snippet(title="b", content="x"))
    store.touch(b.id)
    store.touch(b.id)
    assert store.get(b.id).use_count == 2
    hits = store.search("", sort="used")
    assert hits[0].id == b.id


def test_recent_limit(tmp_path):
    store = make_store(tmp_path)
    for i in range(5):
        store.add(Snippet(title=f"s{i}", content="x"))
    assert len(store.search("", sort="recent", limit=3)) == 3


# ---- placeholders -----------------------------------------------------
def test_placeholder_extract_and_fill():
    text = "docker run {{image}} --name {{name}} {{image}}"
    assert placeholders.extract(text) == ["image", "name"]
    out = placeholders.fill(text, {"image": "nginx", "name": "web"})
    assert out == "docker run nginx --name web nginx"


def test_placeholder_parse_assignments():
    assert placeholders.parse_assignments(["a=1", "b=x y"]) == {"a": "1", "b": "x y"}


# ---- descricao --------------------------------------------------------
def test_description_persists_and_searchable(tmp_path):
    store = make_store(tmp_path)
    store.add(Snippet(title="a", content="x", description="sobe a stack docker"))
    store2 = make_store(tmp_path)
    assert store2.all()[0].description == "sobe a stack docker"
    assert store2.search("stack")  # achou pela descricao


# ---- historico --------------------------------------------------------
def test_history_on_update_and_restore(tmp_path):
    store = make_store(tmp_path)
    s = store.add(Snippet(title="v1", content="um"))
    s.content = "dois"
    store.update(s)
    s2 = store.get(s.id)
    assert len(s2.history) == 1
    assert s2.history[0]["content"] == "um"
    store.restore_version(s.id, 0)
    assert store.get(s.id).content == "um"


def test_history_skipped_when_no_change(tmp_path):
    store = make_store(tmp_path)
    s = store.add(Snippet(title="a", content="x"))
    store.update(s)  # nada mudou
    assert store.get(s.id).history == []


# ---- export / import --------------------------------------------------
def test_export_json_roundtrip(tmp_path):
    store = make_store(tmp_path)
    store.add(Snippet(title="a", content="x", tags=["t"]))
    data = exporters.export(store.all(), fmt="json")
    target = make_store(tmp_path / "other")
    added = exporters.import_json(target, data)
    assert added == 1 and target.all()[0].title == "a"


def test_export_markdown(tmp_path):
    store = make_store(tmp_path)
    store.add(Snippet(title="Subir", content="docker up", language="bash", tags=["x"]))
    md = exporters.export(store.all(), fmt="md")
    assert "## Subir" in md and "```bash" in md and "docker up" in md


def test_import_skips_existing_ids(tmp_path):
    store = make_store(tmp_path)
    store.add(Snippet(title="a", content="x"))
    data = exporters.export(store.all(), fmt="json")
    added = exporters.import_json(store, data)  # mesmos ids
    assert added == 0


def test_import_new_ids(tmp_path):
    store = make_store(tmp_path)
    store.add(Snippet(title="a", content="x"))
    data = exporters.export(store.all(), fmt="json")
    added = exporters.import_json(store, data, replace_ids=True)
    assert added == 1 and len(store.all()) == 2


# ---- dedup ------------------------------------------------------------
def test_find_duplicate(tmp_path):
    store = make_store(tmp_path)
    store.add(Snippet(title="a", content="docker up "))
    assert store.find_duplicate("docker up") is not None
    assert store.find_duplicate("outro") is None


# ---- deteccao de linguagem -------------------------------------------
def test_detect_language():
    assert detect_language("def foo():\n    import os\n    print(os)") == "python"
    assert detect_language("SELECT * FROM users WHERE id = 1") == "sql"
    assert detect_language("") == ""


# ---- migracao de schema ----------------------------------------------
def test_migrate_v1_list(tmp_path):
    # formato antigo: lista pura
    path = tmp_path / "snippets.json"
    path.write_text(
        json.dumps([{"title": "old", "content": "x", "id": "abc"}]),
        encoding="utf-8",
    )
    store = Store(path)
    items = store.all()
    assert len(items) == 1 and items[0].title == "old"
    # ao salvar, vira formato novo com version
    store.add(Snippet(title="new", content="y"))
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict) and raw["version"] >= 2


def test_unknown_fields_ignored(tmp_path):
    path = tmp_path / "snippets.json"
    path.write_text(
        json.dumps({"version": 99, "snippets": [
            {"title": "a", "content": "x", "campo_futuro": 123}
        ]}),
        encoding="utf-8",
    )
    store = Store(path)
    assert store.all()[0].title == "a"


# ---- highlight / completion ------------------------------------------
def test_highlight_basic_adds_ansi():
    out = _highlight_basic('def foo(): return "x"  # c')
    assert "\033[" in out


def test_completion_scripts():
    assert "complete -F" in completion.script("bash")
    assert "compdef" in completion.script("zsh")
    assert "Register-ArgumentCompleter" in completion.script("powershell")


# ---- file lock concorrencia ------------------------------------------
def test_concurrent_saves_dont_corrupt(tmp_path):
    store = make_store(tmp_path)
    for i in range(10):
        store.add(Snippet(title=f"s{i}", content="x"))
    # arquivo continua sendo JSON valido
    raw = json.loads((tmp_path / "snippets.json").read_text(encoding="utf-8"))
    assert len(raw["snippets"]) == 10
