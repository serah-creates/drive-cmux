# tests/test_fence.py
import json, os, pytest
from dcx.tree import parse_tree, find_workspace, find_surface
from dcx import fence

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "tree_snapshot.json")
def load():
    with open(FIX) as f:
        return parse_tree(json.load(f))

DENY = ["ppv","onlyfans","serah","vault","fan","crm","purchase","gemma","chat-app","orchestrator"]

def test_validate_ref_accepts_qualified_rejects_bare():
    assert fence.validate_ref("workspace:14", "workspace") is True
    assert fence.validate_ref("surface:60", "surface") is True
    for bad in ["14", "4", "workspace:", "surface:x", "workspace:14 ", "ws:14", "workspace:14;rm"]:
        assert fence.validate_ref(bad, "workspace") is False

def test_validate_ref_kind_must_match():
    assert fence.validate_ref("surface:1", "workspace") is False
    assert fence.validate_ref("workspace:1", "surface") is False

def test_denylist_matches_sensitive_titles_from_real_tree():
    wss = load()
    # Every workspace whose title OR any subtree surface title hits a pattern must match.
    hits = [w.title for w in wss if any(fence.denylist_match(t, DENY) for t in fence.subtree_text(w))]
    # The real fleet has these live sessions; assert the denylist catches them.
    joined = " | ".join(hits).lower()
    for must in ["fan crm", "gemma", "ppv"]:
        assert must in joined, f"denylist failed to catch a live session containing {must!r}"

def test_denylist_clean_title_returns_none():
    assert fence.denylist_match("unity-erp build board", DENY) is None
    assert fence.denylist_match("Quotes costing tree", DENY) is None

def test_subtree_text_includes_workspace_and_surface_titles_and_urls():
    wss = load()
    w = wss[0]
    texts = fence.subtree_text(w)
    assert w.title in texts
    for s in w.surfaces:
        assert s.title in texts

def test_is_browser_surface():
    wss = load()
    for w in wss:
        for s in w.surfaces:
            assert fence.is_browser_surface(s) == (s.type == "browser")

def test_real_fixture_has_a_browser_surface_and_is_detected():
    # Non-vacuous: the real snapshot MUST contain at least one browser surface,
    # and is_browser_surface must return True for it (exercise the True branch on real data).
    wss = load()
    browsers = [s for w in wss for s in w.surfaces if s.type == "browser"]
    assert browsers, "fixture should contain at least one browser surface"
    assert all(fence.is_browser_surface(s) for s in browsers)
    assert not any(fence.is_browser_surface(s) for w in wss for s in w.surfaces if s.type != "browser")

def test_real_fixture_dcx_titled_session_without_nonce_is_rejected():
    # A real session whose title literally contains "dcx" but carries no nonce
    # must FAIL provenance (it is NOT one of our self-spawned workspaces).
    wss = load()
    spoofed = [w for w in wss if "dcx" in w.title.lower() and "dcx-" not in w.title.lower()]
    assert spoofed, "fixture should contain a 'dcx'-titled workspace without a nonce"
    for w in spoofed:
        with pytest.raises(fence.FenceError):
            fence.provenance_ok(w.title, "ab12cd34")

def test_provenance_requires_recorded_nonce_in_live_title():
    # live title carries the nonce -> ok; missing/mismatched -> FenceError
    assert fence.provenance_ok("dcx-ab12cd34: my task", "ab12cd34") is True
    with pytest.raises(fence.FenceError):
        fence.provenance_ok("dcx-ffffffff: other", "ab12cd34")
    with pytest.raises(fence.FenceError):
        fence.provenance_ok("Fan CRM Purchases", "ab12cd34")

def test_spoofed_dcx_prefix_without_nonce_is_rejected():
    # a real session literally titled "dcx: ..." (no nonce) must NOT pass
    with pytest.raises(fence.FenceError):
        fence.provenance_ok("dcx: a task about the drive-cmux skill", "ab12cd34")
