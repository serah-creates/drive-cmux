# tests/test_tree.py
import json, os
from dcx.tree import parse_tree, find_workspace, find_surface, first_surface_ref

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "tree_snapshot.json")

def load():
    with open(FIX) as f:
        return parse_tree(json.load(f))

def test_parses_workspaces_with_refs():
    wss = load()
    assert wss, "snapshot should have workspaces"
    assert all(w.ref.startswith("workspace:") for w in wss)
    # refs are distinct from index
    assert any(str(w.index) != w.ref.split(":")[1] for w in wss)

def test_find_workspace_and_surface_roundtrip():
    wss = load()
    w = wss[0]
    assert find_workspace(wss, w.ref) is w
    sref = first_surface_ref(w)
    if sref:
        parent, surf = find_surface(wss, sref)
        assert parent.ref == w.ref and surf.ref == sref

def test_find_missing_returns_none():
    wss = load()
    assert find_workspace(wss, "workspace:999999") is None
    assert find_surface(wss, "surface:999999") is None
