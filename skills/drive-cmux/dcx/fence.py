# dcx/fence.py
import re

REF_RE = re.compile(r"^(workspace|surface):\d+$")

class FenceError(Exception):
    pass

def validate_ref(ref, kind):
    if not isinstance(ref, str) or not REF_RE.match(ref):
        return False
    return ref.split(":", 1)[0] == kind

def denylist_match(text, patterns):
    if not text:
        return None
    low = text.lower()
    for p in patterns:
        if p.lower() in low:
            return p
    return None

def subtree_text(workspace):
    texts = [workspace.title]
    for s in workspace.surfaces:
        if s.title:
            texts.append(s.title)
        if s.url:
            texts.append(s.url)
    return texts

def is_browser_surface(surface):
    return surface.type == "browser"

def provenance_ok(live_title, nonce):
    """True only if the workspace's live title carries the exact recorded nonce tag."""
    tag = f"dcx-{nonce}:"
    if tag not in (live_title or ""):
        raise FenceError(f"provenance: live title {live_title!r} does not carry tag {tag!r}")
    return True
