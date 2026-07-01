# drive-cmux Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `dcx` — a safe Python toolkit that drives the local cmux app to spawn one agent session, type into it, read it back, detect completion via a push bridge, and tear it down — fenced so it can only ever write to sessions it spawned itself.

**Architecture:** A small, testable Python package wrapping the bundled `cmux` CLI. Pure functions for the safety fence (validated by adversarial unit tests seeded from a real `tree --json` snapshot). A disk-backed registry of self-spawned sessions (survives fresh-process Bash invocations). Every write is fail-closed: it proceeds only after a fresh `tree --json` read confirms the target is a registry-recorded, nonce-tagged, non-browser surface. Completion uses the proven push bridge (agent writes a FIFO on done → `dcx wait` blocks on it → harness wakes Claude).

**Tech Stack:** Python 3.12, pytest, the cmux 0.62.2 CLI at `/Applications/cmux.app/Contents/Resources/bin/cmux`.

---

## Scope (Phase 1)

In scope: `spawn`, `send`, `send-key`, `read`, `wait`, `close`, `tree`, `preflight`; the fail-closed fence; the disk registry; the JSON output contract; `SKILL.md`; unit tests + one guarded live smoke test.

**Deliberately deferred (not Phase 1):** writing to *pre-existing* panes (the §5.4 allowlist path). The Phase-1 loop only ever writes to sessions `dcx` spawned, so this path isn't needed yet and omitting it removes the unreliable-cwd problem. The denylist/browser/ref-validation fence code is still built and fully tested here as defense-in-depth and so the later phase can switch it on.

## File structure

```
~/.claude/skills/drive-cmux/
├── DESIGN.md                 # (exists) the approved spec
├── PLAN-phase1.md            # (this file)
├── SKILL.md                  # how Claude invokes the toolkit + the loop/bridge pattern  [Task 9]
├── config.json               # cli_path, password_file, state_dir, denylist_patterns      [Task 1]
├── dcx/
│   ├── __init__.py
│   ├── config.py             # load_config()                                              [Task 1]
│   ├── cmux.py               # CmuxClient: thin subprocess wrapper over the cmux CLI       [Task 2]
│   ├── tree.py               # parse tree --json -> Workspace/Surface; resolve helpers     [Task 3]
│   ├── fence.py              # PURE safety functions (ref/denylist/browser/provenance)     [Task 4]
│   ├── registry.py           # disk-backed registry of self-spawned sessions              [Task 5]
│   └── ops.py                # Ops: spawn/send/send_key/read/close/wait (uses fence)       [Task 6]
├── dcx.py                    # CLI entrypoint: argparse subcommands + JSON output contract [Task 7]
└── tests/
    ├── fixtures/tree_snapshot.json   # sanitized real `tree --json`                        [Task 3]
    ├── test_tree.py                                                                        [Task 3]
    ├── test_fence.py                 # adversarial, seeded from the real snapshot          [Task 4]
    ├── test_registry.py                                                                    [Task 5]
    ├── test_ops.py                   # uses a fake CmuxClient                               [Task 6]
    ├── test_cli.py                                                                         [Task 7]
    └── test_smoke_live.py            # env-gated; needs live cmux + password               [Task 8]
```

**Shared types/signatures (locked — later tasks must match these names):**
- `CmuxClient(cli_path, password_file, run=None)` with `ping()`, `tree_json()`, `new_workspace(cwd, command=None)`, `rename_workspace(ws_ref, title)`, `send(surface_ref, text)`, `send_key(surface_ref, key)`, `read_screen(surface_ref, scrollback=False, lines=None)`, `close_workspace(ws_ref)`, `notify(ws_ref, title, body)`.
- `dataclass Surface(ref, type, title, url, pane_ref)`; `dataclass Workspace(ref, index, title, active, selected, surfaces)`.
- `parse_tree(obj) -> list[Workspace]`, `find_workspace(wss, ref)`, `find_surface(wss, ref) -> tuple[Workspace, Surface] | None`, `first_surface_ref(ws) -> str | None`.
- `fence.REF_RE`, `fence.validate_ref(ref, kind)`, `fence.denylist_match(text, patterns) -> str|None`, `fence.subtree_text(ws) -> list[str]`, `fence.is_browser_surface(surface) -> bool`, `fence.FenceError`.
- `Registry(state_file)` with `record(ref, nonce, cwd, command)`, `get(ref) -> dict|None`, `remove(ref)`, `all() -> dict`.
- `Ops(client, registry, denylist_patterns)` with `spawn(cwd, command, task_slug) -> dict`, `send(surface_ref, text)`, `send_key(surface_ref, key)`, `read(surface_ref, scrollback=False)`, `close(ws_ref)`, `wait(fifo_path)`.

---

### Task 1: Scaffold + config

**Files:**
- Create: `~/.claude/skills/drive-cmux/dcx/__init__.py`
- Create: `~/.claude/skills/drive-cmux/dcx/config.py`
- Create: `~/.claude/skills/drive-cmux/config.json`
- Create: `~/.claude/skills/drive-cmux/tests/__init__.py`
- Test: `~/.claude/skills/drive-cmux/tests/test_config.py`

- [ ] **Step 1: Init the repo and package dirs**

```bash
cd ~/.claude/skills/drive-cmux
git init -q
mkdir -p dcx tests/fixtures
: > dcx/__init__.py
: > tests/__init__.py
printf '__pycache__/\n*.pyc\nstate/\n' > .gitignore
```

- [ ] **Step 2: Write `config.json`**

```json
{
  "cli_path": "/Applications/cmux.app/Contents/Resources/bin/cmux",
  "password_file": "/Users/gregorymaier/General/CMUX/socket-password.txt",
  "state_dir": "~/.claude/skills/drive-cmux/state",
  "denylist_patterns": ["ppv", "onlyfans", "serah", "vault", "fan", "crm", "purchase", "gemma", "chat-app", "orchestrator"]
}
```

- [ ] **Step 3: Write the failing test for config loading**

```python
# tests/test_config.py
import json, os
from dcx.config import load_config

def test_load_config_expands_paths_and_has_defaults(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({
        "cli_path": "/x/cmux",
        "password_file": "~/pw.txt",
        "state_dir": "~/state",
        "denylist_patterns": ["ppv"],
    }))
    cfg = load_config(str(cfg_file))
    assert cfg["cli_path"] == "/x/cmux"
    assert cfg["password_file"] == os.path.expanduser("~/pw.txt")
    assert cfg["state_dir"] == os.path.expanduser("~/state")
    assert cfg["denylist_patterns"] == ["ppv"]

def test_load_config_defaults_when_file_missing(tmp_path):
    cfg = load_config(str(tmp_path / "nope.json"))
    assert cfg["cli_path"].endswith("/cmux")
    assert "ppv" in cfg["denylist_patterns"]
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest tests/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'dcx.config'`.

- [ ] **Step 5: Implement `dcx/config.py`**

```python
# dcx/config.py
import json, os

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_DEFAULTS = {
    "cli_path": "/Applications/cmux.app/Contents/Resources/bin/cmux",
    "password_file": "/Users/gregorymaier/General/CMUX/socket-password.txt",
    "state_dir": os.path.join(_HERE, "state"),
    "denylist_patterns": ["ppv", "onlyfans", "serah", "vault", "fan",
                          "crm", "purchase", "gemma", "chat-app", "orchestrator"],
}

_PATH_KEYS = ("cli_path", "password_file", "state_dir")

def load_config(path=None):
    path = path or os.path.join(_HERE, "config.json")
    data = dict(_DEFAULTS)
    try:
        with open(path) as f:
            data.update(json.load(f))
    except FileNotFoundError:
        pass
    for k in _PATH_KEYS:
        data[k] = os.path.expanduser(data[k])
    return data
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest tests/test_config.py -q`
Expected: PASS (2 passed).

- [ ] **Step 7: Commit**

```bash
cd ~/.claude/skills/drive-cmux
git add -A && git commit -q -m "feat(dcx): scaffold + config loader"
```

---

### Task 2: cmux CLI wrapper

**Files:**
- Create: `~/.claude/skills/drive-cmux/dcx/cmux.py`
- Test: `~/.claude/skills/drive-cmux/tests/test_cmux.py`

The wrapper never blocks and never trusts global flags. It injects `CMUX_QUIET=1` (suppresses legacy-verb deprecation noise on stderr) and `CMUX_SOCKET_PASSWORD` from the file. The `run` callable is injectable so unit tests don't need a live cmux.

- [ ] **Step 1: Write the failing test (fake runner, no live cmux)**

```python
# tests/test_cmux.py
import pytest
from dcx.cmux import CmuxClient, CmuxError

class FakeRun:
    def __init__(self, mapping): self.mapping = mapping; self.calls = []
    def __call__(self, argv, env):
        self.calls.append((argv, env))
        rc, out, err = self.mapping.get(tuple(argv[1:]), (0, "", ""))
        return rc, out, err

def make(tmp_path, mapping):
    pw = tmp_path / "pw.txt"; pw.write_text("secret123\n")
    return CmuxClient("/x/cmux", str(pw), run=FakeRun(mapping)), pw

def test_env_has_quiet_and_password(tmp_path):
    c, _ = make(tmp_path, {("ping",): (0, "PONG", "")})
    assert c.ping() is True
    argv, env = c._run.calls[-1]
    assert argv[0] == "/x/cmux"
    assert env["CMUX_QUIET"] == "1"
    assert env["CMUX_SOCKET_PASSWORD"] == "secret123"   # trailing newline stripped

def test_new_workspace_parses_ref(tmp_path):
    c, _ = make(tmp_path, {("new-workspace", "--cwd", "/tmp/x"): (0, "OK workspace:7\n", "")})
    assert c.new_workspace("/tmp/x") == "workspace:7"

def test_nonzero_raises_cmuxerror(tmp_path):
    c, _ = make(tmp_path, {("ping",): (1, "", "Access denied")})
    with pytest.raises(CmuxError):
        c.ping()

def test_tree_json_parses(tmp_path):
    c, _ = make(tmp_path, {("tree", "--json"): (0, '{"windows":[]}', "")})
    assert c.tree_json() == {"windows": []}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest tests/test_cmux.py -q`
Expected: FAIL — `No module named 'dcx.cmux'`.

- [ ] **Step 3: Implement `dcx/cmux.py`**

```python
# dcx/cmux.py
import json, os, re, subprocess

class CmuxError(Exception):
    pass

_WS_RE = re.compile(r"workspace:\d+")

def _default_run(argv, env):
    p = subprocess.run(argv, env=env, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr

class CmuxClient:
    def __init__(self, cli_path, password_file, run=None):
        self.cli_path = cli_path
        self.password_file = password_file
        self._run = run or _default_run

    def _env(self):
        env = dict(os.environ)
        env["CMUX_QUIET"] = "1"
        with open(self.password_file) as f:
            env["CMUX_SOCKET_PASSWORD"] = f.read().strip()
        return env

    def _cli(self, *args):
        argv = [self.cli_path, *args]
        rc, out, err = self._run(argv, self._env())
        if rc != 0:
            raise CmuxError(f"cmux {' '.join(args)} -> rc={rc}: {err.strip() or out.strip()}")
        return out

    def ping(self):
        return self._cli("ping").strip().upper().startswith("PONG")

    def tree_json(self):
        return json.loads(self._cli("tree", "--json"))

    def new_workspace(self, cwd, command=None):
        args = ["new-workspace", "--cwd", cwd]
        if command is not None:
            args += ["--command", command]
        out = self._cli(*args)
        m = _WS_RE.search(out)
        if not m:
            raise CmuxError(f"could not parse workspace ref from: {out!r}")
        return m.group(0)

    def rename_workspace(self, ws_ref, title):
        self._cli("rename-workspace", "--workspace", ws_ref, title)

    def send(self, surface_ref, text):
        self._cli("send", "--surface", surface_ref, text)

    def send_key(self, surface_ref, key):
        self._cli("send-key", "--surface", surface_ref, key)

    def read_screen(self, surface_ref, scrollback=False, lines=None):
        args = ["read-screen", "--surface", surface_ref]
        if scrollback:
            args.append("--scrollback")
        if lines is not None:
            args += ["--lines", str(lines)]
        return self._cli(*args)

    def close_workspace(self, ws_ref):
        self._cli("close-workspace", "--workspace", ws_ref)

    def notify(self, ws_ref, title, body):
        self._cli("notify", "--workspace", ws_ref, "--title", title, "--body", body)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest tests/test_cmux.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd ~/.claude/skills/drive-cmux && git add -A && git commit -q -m "feat(dcx): cmux CLI wrapper (quiet env, password, ref parsing)"
```

---

### Task 3: tree parsing + a real snapshot fixture

**Files:**
- Create: `~/.claude/skills/drive-cmux/dcx/tree.py`
- Create: `~/.claude/skills/drive-cmux/tests/fixtures/tree_snapshot.json`
- Test: `~/.claude/skills/drive-cmux/tests/test_tree.py`

- [ ] **Step 1: Capture a sanitized real snapshot**

Run (live cmux required; this is a one-time fixture capture, read-only):
```bash
CLI=/Applications/cmux.app/Contents/Resources/bin/cmux
CMUX_QUIET=1 CMUX_SOCKET_PASSWORD="$(cat /Users/gregorymaier/General/CMUX/socket-password.txt)" \
  "$CLI" tree --json > ~/.claude/skills/drive-cmux/tests/fixtures/tree_snapshot.json
```
The snapshot intentionally contains real sensitive titles (Fan CRM, Gemma Box, PPV Terminal) — that is the point: the fence tests prove those are handled. If you prefer, hand-edit the titles to representative stand-ins, but keep the *shapes* (truncated `…/` cwds, a `browser`-type surface, an `index` that collides with a sensitive workspace's position).

- [ ] **Step 2: Write the failing test**

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest tests/test_tree.py -q`
Expected: FAIL — `No module named 'dcx.tree'`.

- [ ] **Step 4: Implement `dcx/tree.py`**

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest tests/test_tree.py -q`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
cd ~/.claude/skills/drive-cmux && git add -A && git commit -q -m "feat(dcx): tree --json parser + real snapshot fixture"
```

---

### Task 4: the safety fence (pure functions + adversarial tests)

**Files:**
- Create: `~/.claude/skills/drive-cmux/dcx/fence.py`
- Test: `~/.claude/skills/drive-cmux/tests/test_fence.py`

This is the safety-critical core. All functions are pure (operate on parsed `Workspace`/`Surface` + the live registry record passed in). Tests are adversarial and seeded from the real snapshot.

- [ ] **Step 1: Write the failing adversarial tests**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest tests/test_fence.py -q`
Expected: FAIL — `No module named 'dcx.fence'` (and `subtree_text` undefined).

- [ ] **Step 3: Implement `dcx/fence.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest tests/test_fence.py -q`
Expected: PASS (8 passed). If `test_denylist_matches_sensitive_titles_from_real_tree` fails, the snapshot lacks those sessions — recapture it (Task 3 Step 1) while they're open, or add representative rows.

- [ ] **Step 5: Commit**

```bash
cd ~/.claude/skills/drive-cmux && git add -A && git commit -q -m "feat(dcx): fail-closed safety fence (ref/denylist/browser/provenance) + adversarial tests"
```

---

### Task 5: disk-backed registry

**Files:**
- Create: `~/.claude/skills/drive-cmux/dcx/registry.py`
- Test: `~/.claude/skills/drive-cmux/tests/test_registry.py`

The registry survives fresh-process Bash invocations (one JSON file under `state/`). It records what `dcx` spawned this session.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_registry.py
from dcx.registry import Registry

def test_record_get_remove_roundtrip(tmp_path):
    r = Registry(str(tmp_path / "reg.json"))
    r.record("workspace:5", "ab12cd34", "/tmp/x", "echo hi")
    rec = r.get("workspace:5")
    assert rec["nonce"] == "ab12cd34" and rec["cwd"] == "/tmp/x" and rec["command"] == "echo hi"
    assert "workspace:5" in r.all()
    r.remove("workspace:5")
    assert r.get("workspace:5") is None

def test_persists_across_instances(tmp_path):
    path = str(tmp_path / "reg.json")
    Registry(path).record("workspace:9", "deadbeef", "/tmp/y", "ls")
    assert Registry(path).get("workspace:9")["nonce"] == "deadbeef"

def test_get_missing_returns_none(tmp_path):
    assert Registry(str(tmp_path / "reg.json")).get("workspace:1") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest tests/test_registry.py -q`
Expected: FAIL — `No module named 'dcx.registry'`.

- [ ] **Step 3: Implement `dcx/registry.py`**

```python
# dcx/registry.py
import json, os

class Registry:
    def __init__(self, state_file):
        self.state_file = state_file
        os.makedirs(os.path.dirname(state_file), exist_ok=True)

    def _load(self):
        try:
            with open(self.state_file) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save(self, data):
        tmp = self.state_file + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.state_file)

    def record(self, ref, nonce, cwd, command):
        data = self._load()
        data[ref] = {"nonce": nonce, "cwd": cwd, "command": command}
        self._save(data)

    def get(self, ref):
        return self._load().get(ref)

    def remove(self, ref):
        data = self._load()
        data.pop(ref, None)
        self._save(data)

    def all(self):
        return self._load()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest tests/test_registry.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd ~/.claude/skills/drive-cmux && git add -A && git commit -q -m "feat(dcx): disk-backed self-spawn registry"
```

---

### Task 6: ops (spawn/send/read/close/wait) wired to the fence

**Files:**
- Create: `~/.claude/skills/drive-cmux/dcx/ops.py`
- Test: `~/.claude/skills/drive-cmux/tests/test_ops.py`

Every write re-reads `tree --json`, re-resolves the target, and verifies (a) the parent workspace is in the registry, (b) the live title carries the recorded nonce, (c) the surface is not a browser. Any failure/ambiguity raises `FenceError` and nothing is sent.

- [ ] **Step 1: Write the failing test (fake CmuxClient)**

```python
# tests/test_ops.py
import pytest
from dcx.registry import Registry
from dcx.fence import FenceError
from dcx.ops import Ops

class FakeClient:
    def __init__(self):
        self.tree = {"windows": [{"workspaces": []}]}
        self.sent = []
        self.closed = []
        self._next = 50
    def tree_json(self): return self.tree
    def new_workspace(self, cwd, command=None):
        self.last_command = command
        return "workspace:20"
    def rename_workspace(self, ws_ref, title): self._title = title
    def send(self, surface_ref, text): self.sent.append((surface_ref, text))
    def send_key(self, surface_ref, key): self.sent.append((surface_ref, "KEY:" + key))
    def read_screen(self, surface_ref, scrollback=False, lines=None): return "screen of " + surface_ref
    def close_workspace(self, ws_ref): self.closed.append(ws_ref)
    def notify(self, *a, **k): pass

def _ws(ref, title, surfaces):
    return {"ref": ref, "index": 0, "title": title, "active": False, "selected": False, "panes": [{"surfaces": surfaces}]}

def _sf(ref, type="terminal", title="t"):
    return {"ref": ref, "type": type, "title": title, "url": "", "pane_ref": "pane:1"}

DENY = ["ppv","fan","gemma"]

def make(tmp_path):
    reg = Registry(str(tmp_path / "reg.json"))
    c = FakeClient()
    return Ops(c, reg, DENY), c, reg

def test_send_to_self_spawned_succeeds(tmp_path):
    ops, c, reg = make(tmp_path)
    reg.record("workspace:20", "ab12cd34", "/tmp/x", "echo")
    c.tree = {"windows": [{"workspaces": [_ws("workspace:20", "dcx-ab12cd34: task", [_sf("surface:30")])]}]}
    ops.send("surface:30", "hello")
    assert c.sent == [("surface:30", "hello")]

def test_send_to_unregistered_pane_is_denied(tmp_path):
    ops, c, reg = make(tmp_path)
    c.tree = {"windows": [{"workspaces": [_ws("workspace:14", "PPV Terminal", [_sf("surface:99")])]}]}
    with pytest.raises(FenceError):
        ops.send("surface:99", "rm -rf /")
    assert c.sent == []

def test_send_rejects_bare_integer_ref(tmp_path):
    ops, c, reg = make(tmp_path)
    with pytest.raises(FenceError):
        ops.send("4", "echo")
    assert c.sent == []

def test_send_denied_when_nonce_mismatch(tmp_path):
    ops, c, reg = make(tmp_path)
    reg.record("workspace:20", "ab12cd34", "/tmp/x", "echo")
    c.tree = {"windows": [{"workspaces": [_ws("workspace:20", "dcx-ffffffff: hijacked", [_sf("surface:30")])]}]}
    with pytest.raises(FenceError):
        ops.send("surface:30", "hello")
    assert c.sent == []

def test_send_denied_to_browser_surface(tmp_path):
    ops, c, reg = make(tmp_path)
    reg.record("workspace:20", "ab12cd34", "/tmp/x", "echo")
    c.tree = {"windows": [{"workspaces": [_ws("workspace:20", "dcx-ab12cd34: t", [_sf("surface:30", type="browser")])]}]}
    with pytest.raises(FenceError):
        ops.send("surface:30", "hello")
    assert c.sent == []

def test_send_denied_when_target_not_found(tmp_path):
    ops, c, reg = make(tmp_path)
    reg.record("workspace:20", "ab12cd34", "/tmp/x", "echo")
    c.tree = {"windows": [{"workspaces": []}]}  # vanished
    with pytest.raises(FenceError):
        ops.send("surface:30", "hello")

def test_close_self_spawned_then_deregisters(tmp_path):
    ops, c, reg = make(tmp_path)
    reg.record("workspace:20", "ab12cd34", "/tmp/x", "echo")
    c.tree = {"windows": [{"workspaces": [_ws("workspace:20", "dcx-ab12cd34: t", [_sf("surface:30")])]}]}
    ops.close("workspace:20")
    assert c.closed == ["workspace:20"]
    assert reg.get("workspace:20") is None

def test_close_unregistered_denied(tmp_path):
    ops, c, reg = make(tmp_path)
    c.tree = {"windows": [{"workspaces": [_ws("workspace:14", "PPV Terminal", [_sf("surface:1")])]}]}
    with pytest.raises(FenceError):
        ops.close("workspace:14")
    assert c.closed == []

def test_spawn_records_registry_and_wraps_command(tmp_path):
    ops, c, reg = make(tmp_path)
    # after spawn, the tree must expose the new workspace+surface so resolve works
    def tree_after():
        return {"windows": [{"workspaces": [_ws("workspace:20", c._title, [_sf("surface:30")])]}]}
    c.tree_json = tree_after
    res = ops.spawn("/tmp/x", "echo hi", "mytask")
    assert res["workspace_ref"] == "workspace:20"
    assert res["surface_ref"] == "surface:30"
    rec = reg.get("workspace:20")
    assert rec and rec["nonce"] == res["nonce"]
    assert c._title.startswith(f"dcx-{res['nonce']}:")
    # the command was wrapped to write the done-signal FIFO
    assert res["signal_fifo"] in c.last_command
    assert "echo hi" in c.last_command

def test_read_allows_any_surface_readonly(tmp_path):
    ops, c, reg = make(tmp_path)
    # reads are unrestricted
    assert ops.read("surface:30") == "screen of surface:30"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest tests/test_ops.py -q`
Expected: FAIL — `No module named 'dcx.ops'`.

- [ ] **Step 3: Implement `dcx/ops.py`**

```python
# dcx/ops.py
import os, secrets, shlex, time
from . import fence
from .tree import parse_tree, find_workspace, find_surface, first_surface_ref

class Ops:
    def __init__(self, client, registry, denylist_patterns, state_dir=None):
        self.c = client
        self.reg = registry
        self.deny = denylist_patterns
        self.state_dir = state_dir or os.path.dirname(registry.state_file)

    # ---- internal: fresh, fail-closed resolution of a self-spawned target ----
    def _live_workspaces(self):
        return parse_tree(self.c.tree_json())

    def _verify_self_spawned_ws(self, ws_ref):
        if not fence.validate_ref(ws_ref, "workspace"):
            raise fence.FenceError(f"not a fully-qualified workspace ref: {ws_ref!r}")
        rec = self.reg.get(ws_ref)
        if not rec:
            raise fence.FenceError(f"{ws_ref} is not in the self-spawn registry (pre-existing pane; denied in Phase 1)")
        wss = self._live_workspaces()
        w = find_workspace(wss, ws_ref)
        if w is None:
            raise fence.FenceError(f"{ws_ref} not found in live tree (vanished/ambiguous) -> deny")
        fence.provenance_ok(w.title, rec["nonce"])
        if fence.denylist_match(" ".join(fence.subtree_text(w)), self.deny):
            raise fence.FenceError(f"{ws_ref} title/subtree matches denylist -> deny (defense in depth)")
        return w

    def _verify_self_spawned_surface(self, surface_ref):
        if not fence.validate_ref(surface_ref, "surface"):
            raise fence.FenceError(f"not a fully-qualified surface ref: {surface_ref!r}")
        wss = self._live_workspaces()
        found = find_surface(wss, surface_ref)
        if found is None:
            raise fence.FenceError(f"{surface_ref} not found in live tree -> deny")
        w, s = found
        rec = self.reg.get(w.ref)
        if not rec:
            raise fence.FenceError(f"{surface_ref}'s workspace {w.ref} is not self-spawned -> deny")
        fence.provenance_ok(w.title, rec["nonce"])
        if fence.is_browser_surface(s):
            raise fence.FenceError(f"{surface_ref} is a browser surface -> deny (unconditional)")
        return w, s

    # ---- spawn ----
    def spawn(self, cwd, command, task_slug):
        nonce = secrets.token_hex(4)
        os.makedirs(self.state_dir, exist_ok=True)
        fifo = os.path.join(self.state_dir, f"done-{nonce}.fifo")
        try:
            os.mkfifo(fifo)
        except FileExistsError:
            pass
        # wrap the agent command so it signals completion on the FIFO when done
        wrapped = f"{command} ; echo done > {shlex.quote(fifo)}"
        ws_ref = self.c.new_workspace(cwd, command=wrapped)
        title = f"dcx-{nonce}: {task_slug}"
        self.c.rename_workspace(ws_ref, title)
        self.reg.record(ws_ref, nonce, cwd, command)
        surface_ref = self._resolve_surface(ws_ref)
        return {"workspace_ref": ws_ref, "surface_ref": surface_ref,
                "nonce": nonce, "signal_fifo": fifo, "title": title}

    def _resolve_surface(self, ws_ref, retries=10):
        for _ in range(retries):
            w = find_workspace(self._live_workspaces(), ws_ref)
            if w:
                sref = first_surface_ref(w)
                if sref:
                    return sref
            time.sleep(0.3)
        raise fence.FenceError(f"could not resolve a surface for {ws_ref}")

    # ---- writes (fenced) ----
    def send(self, surface_ref, text):
        self._verify_self_spawned_surface(surface_ref)
        self.c.send(surface_ref, text)

    def send_key(self, surface_ref, key):
        self._verify_self_spawned_surface(surface_ref)
        self.c.send_key(surface_ref, key)

    def close(self, ws_ref):
        self._verify_self_spawned_ws(ws_ref)
        self.c.close_workspace(ws_ref)
        self.reg.remove(ws_ref)

    # ---- read (unrestricted) ----
    def read(self, surface_ref, scrollback=False):
        if not fence.validate_ref(surface_ref, "surface"):
            raise fence.FenceError(f"not a fully-qualified surface ref: {surface_ref!r}")
        return self.c.read_screen(surface_ref, scrollback=scrollback)

    # ---- wait (the push bridge; run via run_in_background) ----
    def wait(self, fifo_path):
        with open(fifo_path) as f:   # blocks until the agent writes its done-signal
            f.read()
        return True
```

> Note on `_resolve_surface`'s `time.sleep`: this runs in a fresh short-lived `dcx` process (not the harness foreground), so a bounded poll is fine. `wait()` does a blocking FIFO read (no sleep) — exactly the bridge proven on 2026-06-17.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest tests/test_ops.py -q`
Expected: PASS (10 passed).

- [ ] **Step 5: Commit**

```bash
cd ~/.claude/skills/drive-cmux && git add -A && git commit -q -m "feat(dcx): fenced ops (spawn/send/read/close/wait) with TOCTOU re-verify"
```

---

### Task 7: CLI entrypoint + JSON output contract

**Files:**
- Create: `~/.claude/skills/drive-cmux/dcx.py`
- Test: `~/.claude/skills/drive-cmux/tests/test_cli.py`

`dcx.py` wires config → client → registry → ops, and prints exactly one JSON object to stdout. Errors print `{"ok": false, "error_type": "...", "error": "..."}` and exit 1.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
import json, subprocess, sys, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run_cli(args, env=None):
    p = subprocess.run([sys.executable, os.path.join(ROOT, "dcx.py"), *args],
                       capture_output=True, text=True, env={**os.environ, **(env or {})})
    return p

def test_unknown_ref_is_fail_closed_json(tmp_path):
    # 'send' with a bare integer must exit 1 with a JSON error and not touch cmux
    env = {"DCX_CONFIG": str(tmp_path / "cfg.json")}
    (tmp_path / "cfg.json").write_text(json.dumps({
        "cli_path": "/bin/false", "password_file": str(tmp_path / "pw"),
        "state_dir": str(tmp_path / "state"), "denylist_patterns": ["ppv"],
    }))
    (tmp_path / "pw").write_text("x")
    p = run_cli(["send", "--ref", "4", "hi"], env=env)
    assert p.returncode == 1
    out = json.loads(p.stdout)
    assert out["ok"] is False and out["error_type"] == "FenceError"

def test_help_lists_subcommands():
    p = run_cli(["--help"])
    assert p.returncode == 0
    for verb in ["spawn", "send", "read", "close", "wait", "tree", "preflight"]:
        assert verb in p.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest tests/test_cli.py -q`
Expected: FAIL — `dcx.py` doesn't exist.

- [ ] **Step 3: Implement `dcx.py`**

```python
# dcx.py
import argparse, json, os, sys
from dcx.config import load_config
from dcx.cmux import CmuxClient, CmuxError
from dcx.registry import Registry
from dcx.fence import FenceError
from dcx.ops import Ops

def _emit(obj, code=0):
    print(json.dumps(obj))
    sys.exit(code)

def _err(e):
    _emit({"ok": False, "error_type": type(e).__name__, "error": str(e)}, code=1)

def _build(cfg):
    client = CmuxClient(cfg["cli_path"], cfg["password_file"])
    reg = Registry(os.path.join(cfg["state_dir"], "registry.json"))
    ops = Ops(client, reg, cfg["denylist_patterns"], state_dir=cfg["state_dir"])
    return client, ops

def main(argv=None):
    p = argparse.ArgumentParser(prog="dcx", description="drive cmux (Phase 1)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preflight")
    sub.add_parser("tree")
    sp = sub.add_parser("spawn"); sp.add_argument("--cwd", required=True); sp.add_argument("--command", required=True); sp.add_argument("--task", required=True)
    se = sub.add_parser("send"); se.add_argument("--ref", required=True); se.add_argument("text")
    sk = sub.add_parser("send-key"); sk.add_argument("--ref", required=True); sk.add_argument("key")
    rd = sub.add_parser("read"); rd.add_argument("--ref", required=True); rd.add_argument("--scrollback", action="store_true")
    wt = sub.add_parser("wait"); wt.add_argument("--fifo", required=True)
    cl = sub.add_parser("close"); cl.add_argument("--ref", required=True)
    args = p.parse_args(argv)

    cfg = load_config(os.environ.get("DCX_CONFIG"))
    client, ops = _build(cfg)
    try:
        if args.cmd == "preflight":
            _emit({"ok": client.ping()})
        elif args.cmd == "tree":
            _emit({"ok": True, "tree": client.tree_json()})
        elif args.cmd == "spawn":
            _emit({"ok": True, **ops.spawn(args.cwd, args.command, args.task)})
        elif args.cmd == "send":
            ops.send(args.ref, args.text); _emit({"ok": True, "surface_ref": args.ref})
        elif args.cmd == "send-key":
            ops.send_key(args.ref, args.key); _emit({"ok": True, "surface_ref": args.ref})
        elif args.cmd == "read":
            _emit({"ok": True, "screen": ops.read(args.ref, scrollback=args.scrollback)})
        elif args.cmd == "wait":
            _emit({"ok": ops.wait(args.fifo), "signaled": True})
        elif args.cmd == "close":
            ops.close(args.ref); _emit({"ok": True, "closed": args.ref})
    except (FenceError, CmuxError) as e:
        _err(e)

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest tests/test_cli.py -q`
Expected: PASS (2 passed). (The fence rejects `--ref 4` before any cmux call, so `/bin/false` is never invoked.)

- [ ] **Step 5: Run the whole unit suite**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest -q`
Expected: PASS (all tests from Tasks 1–7).

- [ ] **Step 6: Commit**

```bash
cd ~/.claude/skills/drive-cmux && git add -A && git commit -q -m "feat(dcx): CLI entrypoint with JSON output contract"
```

---

### Task 8: guarded live smoke test (real cmux)

**Files:**
- Test: `~/.claude/skills/drive-cmux/tests/test_smoke_live.py`

This exercises the real spawn→send→read→close loop against live cmux. It is skipped unless `DCX_LIVE=1` so the normal suite stays hermetic.

- [ ] **Step 1: Write the live smoke test**

```python
# tests/test_smoke_live.py
import json, os, subprocess, sys, time, pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE = os.environ.get("DCX_LIVE") == "1"

def cli(*args):
    p = subprocess.run([sys.executable, os.path.join(ROOT, "dcx.py"), *args],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    return json.loads(p.stdout)

@pytest.mark.skipif(not LIVE, reason="set DCX_LIVE=1 with a live cmux + password to run")
def test_full_loop_live(tmp_path):
    assert cli("preflight")["ok"] is True
    cwd = str(tmp_path)
    spawn = cli("spawn", "--cwd", cwd, "--command", "echo DCX_SMOKE_OK", "--task", "smoke")
    sref = spawn["surface_ref"]; wref = spawn["workspace_ref"]
    try:
        # poll the screen for the marker
        seen = False
        for _ in range(20):
            if "DCX_SMOKE_OK" in cli("read", "--ref", sref)["screen"]:
                seen = True; break
            time.sleep(0.5)
        assert seen, "marker never appeared"
    finally:
        assert cli("close", "--ref", wref)["ok"] is True
```

- [ ] **Step 2: Run it live**

Run: `cd ~/.claude/skills/drive-cmux && DCX_LIVE=1 python3.12 -m pytest tests/test_smoke_live.py -q`
Expected: PASS (1 passed) — a `dcx-…: smoke` tab briefly appears in cmux and is closed. Without `DCX_LIVE=1`: `1 skipped`.

- [ ] **Step 3: Commit**

```bash
cd ~/.claude/skills/drive-cmux && git add -A && git commit -q -m "test(dcx): guarded live smoke for the full loop"
```

---

### Task 9: SKILL.md (how Claude uses it, safety first)

**Files:**
- Create: `~/.claude/skills/drive-cmux/SKILL.md`

- [ ] **Step 1: Write `SKILL.md`**

````markdown
---
name: drive-cmux
description: Use when Claude should drive the local cmux app to spawn an agent session, type into it, read it back, detect completion, and close it — for orchestrating coding/review agents. macOS + cmux only.
---

# drive-cmux (Phase 1)

Drive cmux through `dcx.py`. **Reads are unrestricted; writes only ever touch sessions `dcx` spawned itself** (registry + nonce verified on every write). Never drive live PPV/OnlyFans/CRM/Gemma sessions; browser surfaces are hard-blocked.

## Prereqs
- cmux Settings → Socket Control Mode = **Password mode**; password in the file named in `config.json`.
- Verify access: `python3.12 dcx.py preflight` → `{"ok": true}`.

## Verbs (all print one JSON object to stdout)
- `dcx.py tree` — read the fleet.
- `dcx.py spawn --cwd <dir> --command "<agent cmd>" --task <slug>` → `{workspace_ref, surface_ref, nonce, signal_fifo}`.
- `dcx.py send --ref <surface:N> "<text>"` / `send-key --ref <surface:N> <key>`.
- `dcx.py read --ref <surface:N> [--scrollback]`.
- `dcx.py close --ref <workspace:N>`.
- `dcx.py wait --fifo <path>` — blocks until the agent signals done.

## The push-notification loop (proven 2026-06-17)
1. `spawn` an agent; note `surface_ref` and `signal_fifo`. The spawned command is auto-wrapped to write the FIFO when it completes. (For an interactive TUI agent that never exits, instead instruct the agent in its prompt to run `echo done > <signal_fifo>` as its final step.)
2. Run `dcx.py wait --fifo <signal_fifo>` via the harness **run_in_background** — then END the turn.
3. The harness wakes Claude when the waiter exits (the agent finished). Now `read --ref <surface_ref>` to review, then `close`.
4. For a fleet, one `wait` per agent → Claude is woken per-completion.

## Safety (always)
- Fully-qualified refs only (`workspace:N`/`surface:N`); never a bare integer/index.
- Writes are fail-closed: any ambiguity, parse failure, missing registry record, nonce mismatch, or browser surface → refused.
- Never modify cmux Settings, never drive a pane you didn't spawn, never touch a `browser` surface.
````

- [ ] **Step 2: Commit**

```bash
cd ~/.claude/skills/drive-cmux && git add -A && git commit -q -m "docs(dcx): SKILL.md — usage, the push loop, safety"
```

---

## Self-Review

**Spec coverage:** §3 CLI facts → encoded in `cmux.py`/`tree.py` (per-verb `--json`, `OK workspace:NN` parse, `ref` not `index`, `CMUX_QUIET`). §3.5 push bridge → `ops.wait` + SKILL.md loop. §3.6 auth → `cmux._env` + `preflight`. §4 components/JSON contract → Tasks 1,7. §5 fence (fail-closed, registry+nonce provenance, fully-qualified refs, browser block, deny-on-ambiguity) → Task 4 + Task 6 `_verify_*`. §5.6 cleanup by ref + re-verify → `ops.close`. §6 Phase 1 (mechanics + one loop) → Tasks 6,9. §7 tests (adversarial from real snapshot + guarded smoke) → Tasks 3,4,8. **Deferred & flagged:** §5.4 pre-existing-pane writes (allowlist) — out of Phase 1 by design; `ops._verify_self_spawned_*` denies any unregistered ref.

**Placeholder scan:** none — every code/test step has complete content.

**Type consistency:** `Ops`/`CmuxClient`/`Registry`/`fence.*` signatures match the locked list in the File-structure section and are used identically in Tasks 6 and 7. `signal_fifo` key is produced by `spawn` (Task 6) and documented in SKILL.md (Task 9).
