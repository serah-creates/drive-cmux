# dcx/tree.py
from dataclasses import dataclass, field

@dataclass
class Surface:
    ref: str
    type: str
    title: str
    url: str
    pane_ref: str

@dataclass
class Workspace:
    ref: str
    index: int
    title: str
    active: bool
    selected: bool
    surfaces: list = field(default_factory=list)

def _surfaces_in(node):
    """Recursively collect surface dicts under a workspace/pane node."""
    out = []
    if isinstance(node, dict):
        if isinstance(node.get("ref"), str) and node["ref"].startswith("surface:"):
            out.append(node)
        for v in node.values():
            out.extend(_surfaces_in(v))
    elif isinstance(node, list):
        for v in node:
            out.extend(_surfaces_in(v))
    return out

def parse_tree(obj):
    workspaces = []
    for win in obj.get("windows", []):
        for w in win.get("workspaces", []):
            surfaces = []
            seen = set()
            for s in _surfaces_in(w):
                if s["ref"] in seen:
                    continue
                seen.add(s["ref"])
                surfaces.append(Surface(
                    ref=s["ref"],
                    type=s.get("type", ""),
                    title=s.get("title", ""),
                    url=s.get("url", "") or "",
                    pane_ref=s.get("pane_ref", "") or "",
                ))
            workspaces.append(Workspace(
                ref=w["ref"],
                index=w.get("index", -1),
                title=w.get("title", ""),
                active=bool(w.get("active")),
                selected=bool(w.get("selected")),
                surfaces=surfaces,
            ))
    return workspaces

def find_workspace(workspaces, ref):
    for w in workspaces:
        if w.ref == ref:
            return w
    return None

def find_surface(workspaces, surface_ref):
    for w in workspaces:
        for s in w.surfaces:
            if s.ref == surface_ref:
                return (w, s)
    return None

def first_surface_ref(workspace):
    return workspace.surfaces[0].ref if workspace.surfaces else None
