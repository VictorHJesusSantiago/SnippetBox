import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from snippetbox.core import Snippet, Store, parse_tags


def make_store(tmp_path) -> Store:
    return Store(tmp_path / "snippets.json")


def test_add_and_load(tmp_path):
    store = make_store(tmp_path)
    store.add(Snippet(title="docker up", content="docker compose up -d", language="bash"))
    # nova instancia le do disco
    store2 = make_store(tmp_path)
    items = store2.all()
    assert len(items) == 1
    assert items[0].title == "docker up"


def test_search_scoring(tmp_path):
    store = make_store(tmp_path)
    store.add(Snippet(title="git reset", content="git reset --hard", tags=["git"]))
    store.add(Snippet(title="limpar", content="git clean -fd", tags=["docker"]))
    hits = store.search("git")
    assert hits[0].title == "git reset"  # match no titulo pontua mais
    assert len(hits) == 2


def test_get_by_prefix(tmp_path):
    store = make_store(tmp_path)
    s = store.add(Snippet(title="x", content="y"))
    assert store.get(s.id[:4]) is not None
    assert store.get(s.id) is not None


def test_update_and_delete(tmp_path):
    store = make_store(tmp_path)
    s = store.add(Snippet(title="a", content="b"))
    s.title = "novo"
    store.update(s)
    assert store.get(s.id).title == "novo"
    assert store.delete(s.id) is True
    assert store.get(s.id) is None
    assert store.delete("inexistente") is False


def test_parse_tags():
    assert parse_tags("git, docker ;ci") == ["ci", "docker", "git"]
    assert parse_tags("") == []
    assert parse_tags(["b", "a", "a"]) == ["a", "b"]


def test_all_tags(tmp_path):
    store = make_store(tmp_path)
    store.add(Snippet(title="a", content="x", tags=["git", "ci"]))
    store.add(Snippet(title="b", content="y", tags=["docker", "ci"]))
    assert store.all_tags() == ["ci", "docker", "git"]
