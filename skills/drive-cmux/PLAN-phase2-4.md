# drive-cmux Phases 2–4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. Builds directly on the verified Phase 1 toolkit (commit `aac7539`).

**Goal:** Compose the Phase 1 primitives into the orchestration loop: a single-session plan-review (Phase 2), a parallel build fan-out with git-worktree isolation (Phase 3), and a read-only watcher (Phase 4).

**Architecture:** A thin `Loop` class over the existing `Ops` (spawn/wait/read/close). `run_session` = spawn → block on the FIFO done-signal → read → close (the proven single-session bridge). `fanout` spawns N sessions and returns their handles+FIFOs (Claude launches one `dcx wait` per agent via `run_in_background`, getting woken per-completion). `status` cross-references the live tree against the self-spawn registry. A `worktrees` helper isolates parallel agents. New CLI subcommands wire it all up.

**Tech Stack:** Python 3.12, pytest. Reuses `dcx/ops.py`, `dcx/tree.py`, `dcx/registry.py`, `dcx/fence.py`.

---

## Phase 1 facts these tasks build on (verified, do not change)
- `Ops.spawn(cwd, command, task_slug) -> {"workspace_ref","surface_ref","nonce","signal_fifo","title"}` — wraps the command with `; echo done > <fifo>` and records the registry.
- `Ops.wait(fifo_path) -> True` — blocking FIFO read (the push bridge).
- `Ops.read(surface_ref, scrollback=False) -> str`; `Ops.close(ws_ref)` (fenced, unlinks FIFO); `Ops.send`, `Ops.send_key` (fenced).
- `Ops.reg` is a `Registry` (`.all()`, `.get(ref)`); `Ops.c` is the `CmuxClient` (`.tree_json()`).
- `tree.parse_tree`, `tree.find_workspace`.

## File structure
```
dcx/loop.py        # Loop: run_session / fanout / status        [Tasks 1-3]
dcx/worktrees.py   # git worktree helpers                        [Task 4]
dcx.py             # + run-session / fanout / watch / worktree-add subcommands  [Task 5]
SKILL.md           # + loop/fanout/watch usage                   [Task 6]
tests/test_loop.py tests/test_worktrees.py (+ test_cli additions, live)
```

**Locked signatures (later tasks must match):**
- `Loop(ops)` with `run_session(cwd, command, task_slug, scrollback=True) -> dict`, `fanout(items) -> list[dict]`, `status() -> list[dict]`.
- `worktrees.add(repo_dir, slug, root=None) -> dict{"path","branch"}`, `worktrees.remove(repo_dir, path) -> None`.

---

### Task 1: Loop.run_session (single-session blocking loop)

**Files:** Create `dcx/loop.py`; Test `tests/test_loop.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_loop.py
from dcx.loop import Loop

class FakeOps:
    def __init__(self):
        self.calls = []
        self.spawned = {"workspace_ref": "workspace:20", "surface_ref": "surface:30",
                        "nonce": "ab12cd34", "signal_fifo": "/tmp/f.fifo", "title": "dcx-ab12cd34: t"}
        self.screen = "review notes: looks good"
    def spawn(self, cwd, command, task_slug):
        self.calls.append(("spawn", cwd, command, task_slug)); return dict(self.spawned)
    def wait(self, fifo): self.calls.append(("wait", fifo)); return True
    def read(self, surface_ref, scrollback=False): self.calls.append(("read", surface_ref, scrollback)); return self.screen
    def close(self, ws_ref): self.calls.append(("close", ws_ref))

def test_run_session_spawn_wait_read_close_in_order():
    ops = FakeOps()
    res = Loop(ops).run_session("/tmp/x", "codex exec hi", "review-1")
    names = [c[0] for c in ops.calls]
    assert names == ["spawn", "wait", "read", "close"]
    assert ops.calls[1] == ("wait", "/tmp/f.fifo")
    assert ops.calls[2] == ("read", "surface:30", True)
    assert ops.calls[3] == ("close", "workspace:20")
    assert res["task"] == "review-1"
    assert res["workspace_ref"] == "workspace:20"
    assert res["output"] == "review notes: looks good"

def test_run_session_closes_even_if_read_fails():
    ops = FakeOps()
    def boom(*a, **k): raise RuntimeError("read failed")
    ops.read = boom
    import pytest
    with pytest.raises(RuntimeError):
        Loop(ops).run_session("/tmp/x", "cmd", "t")
    assert ("close", "workspace:20") in ops.calls   # cleanup still happened
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest tests/test_loop.py -q`
Expected: FAIL — `No module named 'dcx.loop'`.

- [ ] **Step 3: Implement `dcx/loop.py` (run_session only)**

```python
# dcx/loop.py
from .tree import parse_tree, find_workspace

class Loop:
    def __init__(self, ops):
        self.ops = ops

    def run_session(self, cwd, command, task_slug, scrollback=True):
        """Spawn one agent session, block until it signals done, read its output, close it."""
        spawn = self.ops.spawn(cwd, command, task_slug)
        try:
            self.ops.wait(spawn["signal_fifo"])
            output = self.ops.read(spawn["surface_ref"], scrollback=scrollback)
        finally:
            self.ops.close(spawn["workspace_ref"])
        return {"task": task_slug, "workspace_ref": spawn["workspace_ref"],
                "surface_ref": spawn["surface_ref"], "output": output}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest tests/test_loop.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd ~/.claude/skills/drive-cmux && git add -A && git commit -q -m "feat(dcx): Loop.run_session — single-session blocking loop (Phase 2)"
```

---

### Task 2: Loop.fanout (parallel spawn, return handles)

**Files:** Modify `dcx/loop.py`; Test `tests/test_loop.py`

- [ ] **Step 1: Write the failing test (append to tests/test_loop.py)**

```python
def test_fanout_spawns_each_item_and_returns_handles():
    ops = FakeOps()
    seq = [
        {"workspace_ref": "workspace:21", "surface_ref": "surface:31", "nonce": "n1", "signal_fifo": "/tmp/1.fifo", "title": "dcx-n1: a"},
        {"workspace_ref": "workspace:22", "surface_ref": "surface:32", "nonce": "n2", "signal_fifo": "/tmp/2.fifo", "title": "dcx-n2: b"},
    ]
    out = []
    def spawn(cwd, command, task_slug):
        d = seq[len(out)]; out.append(d); ops.calls.append(("spawn", cwd, command, task_slug)); return dict(d)
    ops.spawn = spawn
    items = [
        {"cwd": "/wt/a", "command": "codex exec A", "task_slug": "task-a"},
        {"cwd": "/wt/b", "command": "codex exec B", "task_slug": "task-b"},
    ]
    handles = Loop(ops).fanout(items)
    assert [h["workspace_ref"] for h in handles] == ["workspace:21", "workspace:22"]
    assert [h["signal_fifo"] for h in handles] == ["/tmp/1.fifo", "/tmp/2.fifo"]
    assert [h["task"] for h in handles] == ["task-a", "task-b"]
    # fanout does NOT wait or close — that's the caller's job (per-agent run_in_background waiters)
    assert [c[0] for c in ops.calls] == ["spawn", "spawn"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest tests/test_loop.py::test_fanout_spawns_each_item_and_returns_handles -q`
Expected: FAIL — `Loop has no attribute 'fanout'`.

- [ ] **Step 3: Add `fanout` to `dcx/loop.py`**

```python
    def fanout(self, items):
        """Spawn one agent session per item; return handles (incl signal_fifo). Does NOT wait/close.
        items: list of {cwd, command, task_slug}. Caller waits per-agent (run_in_background) then reads/closes."""
        handles = []
        for it in items:
            sp = self.ops.spawn(it["cwd"], it["command"], it["task_slug"])
            handles.append({"task": it["task_slug"], **sp})
        return handles
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest tests/test_loop.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
cd ~/.claude/skills/drive-cmux && git add -A && git commit -q -m "feat(dcx): Loop.fanout — parallel spawn returning per-agent handles (Phase 3)"
```

---

### Task 3: Loop.status (watcher core)

**Files:** Modify `dcx/loop.py`; Test `tests/test_loop.py`

- [ ] **Step 1: Write the failing test (append)**

```python
def test_status_cross_references_registry_and_live_tree():
    ops = FakeOps()
    class Reg:
        def all(self): return {"workspace:20": {"nonce": "ab12cd34", "cwd": "/x", "command": "c"},
                               "workspace:99": {"nonce": "deadbeef", "cwd": "/y", "command": "d"}}
    class Client:
        def tree_json(self):
            return {"windows": [{"workspaces": [
                {"ref": "workspace:20", "index": 0, "title": "dcx-ab12cd34: live one",
                 "active": False, "selected": False, "panes": [{"surfaces": [
                    {"ref": "surface:30", "type": "terminal", "title": "t", "url": "", "pane_ref": "pane:1"}]}]},
            ]}]}
    ops.reg = Reg(); ops.c = Client()
    st = {s["workspace"]: s for s in Loop(ops).status()}
    assert st["workspace:20"]["present"] is True and st["workspace:20"]["nonce_ok"] is True
    assert st["workspace:20"]["title"] == "dcx-ab12cd34: live one"
    # workspace:99 is in the registry but gone from the tree
    assert st["workspace:99"]["present"] is False and st["workspace:99"]["nonce_ok"] is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest tests/test_loop.py::test_status_cross_references_registry_and_live_tree -q`
Expected: FAIL — `Loop has no attribute 'status'`.

- [ ] **Step 3: Add `status` to `dcx/loop.py`**

```python
    def status(self):
        """Read-only board: cross-reference the self-spawn registry against the live tree."""
        wss = parse_tree(self.ops.c.tree_json())
        out = []
        for ref, rec in self.ops.reg.all().items():
            w = find_workspace(wss, ref)
            present = w is not None
            nonce_ok = present and (f"dcx-{rec['nonce']}:" in (w.title or ""))
            out.append({"workspace": ref, "present": present, "nonce_ok": bool(nonce_ok),
                        "title": (w.title if w else None), "cwd": rec.get("cwd")})
        return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest tests/test_loop.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd ~/.claude/skills/drive-cmux && git add -A && git commit -q -m "feat(dcx): Loop.status — read-only watcher board (Phase 4)"
```

---

### Task 4: git worktree helper

**Files:** Create `dcx/worktrees.py`; Test `tests/test_worktrees.py`

- [ ] **Step 1: Write the failing test (uses a real temp git repo)**

```python
# tests/test_worktrees.py
import os, subprocess
from dcx import worktrees

def _git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True)

def _init_repo(tmp_path):
    repo = str(tmp_path / "repo"); os.makedirs(repo)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t"); _git(repo, "config", "user.name", "t")
    (tmp_path / "repo" / "f.txt").write_text("hi")
    _git(repo, "add", "-A"); _git(repo, "commit", "-q", "-m", "init")
    return repo

def test_add_creates_isolated_worktree_and_branch(tmp_path):
    repo = _init_repo(tmp_path)
    root = str(tmp_path / "wts")
    res = worktrees.add(repo, "task-a", root=root)
    assert os.path.isdir(res["path"])
    assert os.path.isfile(os.path.join(res["path"], "f.txt"))   # checked-out worktree
    # it's a registered worktree of repo
    out = subprocess.run(["git", "-C", repo, "worktree", "list"], capture_output=True, text=True).stdout
    assert res["path"] in out
    assert res["branch"] in out

def test_remove_cleans_up(tmp_path):
    repo = _init_repo(tmp_path)
    res = worktrees.add(repo, "task-b", root=str(tmp_path / "wts"))
    worktrees.remove(repo, res["path"])
    out = subprocess.run(["git", "-C", repo, "worktree", "list"], capture_output=True, text=True).stdout
    assert res["path"] not in out
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest tests/test_worktrees.py -q`
Expected: FAIL — `No module named 'dcx.worktrees'`.

- [ ] **Step 3: Implement `dcx/worktrees.py`**

```python
# dcx/worktrees.py
import os, re, subprocess

def _slug(s):
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", s).strip("-") or "task"

def _git(repo_dir, *args):
    p = subprocess.run(["git", "-C", repo_dir, *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr.strip()}")
    return p.stdout

def add(repo_dir, slug, root=None):
    """Create an isolated git worktree + branch for a fan-out agent. Returns {path, branch}."""
    s = _slug(slug)
    root = root or os.path.join(repo_dir, ".dcx-worktrees")
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, s)
    branch = f"dcx/{s}"
    _git(repo_dir, "worktree", "add", "-b", branch, path)
    return {"path": path, "branch": branch}

def remove(repo_dir, path):
    """Remove a worktree created by add() (best-effort prune of the branch is left to the caller)."""
    _git(repo_dir, "worktree", "remove", "--force", path)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest tests/test_worktrees.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd ~/.claude/skills/drive-cmux && git add -A && git commit -q -m "feat(dcx): git worktree helper for fan-out isolation (Phase 3)"
```

---

### Task 5: CLI subcommands (run-session / fanout / watch / worktree-add)

**Files:** Modify `dcx.py`; Test `tests/test_cli.py`

- [ ] **Step 1: Write the failing test (append to tests/test_cli.py)**

```python
def test_watch_emits_json_status(tmp_path):
    # point at a fake cmux that returns an empty tree; registry empty -> status []
    fake = tmp_path / "cmux"; fake.write_text(
        '#!/bin/bash\n'
        'if [ "$1" = "ping" ]; then echo PONG; exit 0; fi\n'
        'if [ "$1" = "tree" ]; then echo \'{"windows":[{"workspaces":[]}]}\'; exit 0; fi\n'
        'exit 0\n')
    fake.chmod(0o755)
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"cli_path": str(fake), "password_file": str(tmp_path / "pw"),
                               "state_dir": str(tmp_path / "state"), "denylist_patterns": ["ppv"]}))
    (tmp_path / "pw").write_text("x")
    p = run_cli(["watch"], env={"DCX_CONFIG": str(cfg)})
    assert p.returncode == 0
    out = json.loads(p.stdout)
    assert out["ok"] is True and out["status"] == []
```

(`run_cli` and `json`/`os` imports already exist in test_cli.py from Phase 1.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest tests/test_cli.py::test_watch_emits_json_status -q`
Expected: FAIL — `invalid choice: 'watch'`.

- [ ] **Step 3: Wire the subcommands into `dcx.py`**

In the imports near the top, add:
```python
from dcx.loop import Loop
from dcx import worktrees
```

In `main`, after the existing `cl = sub.add_parser("close")...` line, add the new parsers:
```python
    rs = sub.add_parser("run-session"); rs.add_argument("--cwd", required=True); rs.add_argument("--command", required=True); rs.add_argument("--task", required=True); rs.add_argument("--no-scrollback", action="store_true")
    fo = sub.add_parser("fanout"); fo.add_argument("--spec", required=True, help="path to a JSON file: [{cwd, command, task_slug}, ...]")
    sub.add_parser("watch")
    wa = sub.add_parser("worktree-add"); wa.add_argument("--repo", required=True); wa.add_argument("--slug", required=True); wa.add_argument("--root")
```

In the try-block, after the existing `elif args.cmd == "close":` branch, add:
```python
        elif args.cmd == "run-session":
            loop = Loop(ops)
            _emit({"ok": True, **loop.run_session(args.cwd, args.command, args.task, scrollback=not args.no_scrollback)})
        elif args.cmd == "fanout":
            with open(args.spec) as f:
                items = json.load(f)
            _emit({"ok": True, "handles": Loop(ops).fanout(items)})
        elif args.cmd == "watch":
            _emit({"ok": True, "status": Loop(ops).status()})
        elif args.cmd == "worktree-add":
            _emit({"ok": True, **worktrees.add(args.repo, args.slug, root=args.root)})
```

Also broaden the `except` to include `RuntimeError` (worktrees/loop surface it) so those stay fail-closed JSON:
```python
    except (FenceError, CmuxError, RuntimeError) as e:
        _err(e)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest tests/test_cli.py -q`
Expected: PASS (all test_cli tests, including the new one).

- [ ] **Step 5: Run the whole unit suite**

Run: `cd ~/.claude/skills/drive-cmux && python3.12 -m pytest -q`
Expected: PASS (all prior + the new loop/worktrees/cli tests; live smoke skipped).

- [ ] **Step 6: Commit**

```bash
cd ~/.claude/skills/drive-cmux && git add -A && git commit -q -m "feat(dcx): CLI run-session/fanout/watch/worktree-add subcommands"
```

---

### Task 6: SKILL.md update + guarded live loop test

**Files:** Modify `SKILL.md`; Modify `tests/test_smoke_live.py`

- [ ] **Step 1: Append the orchestration verbs + patterns to `SKILL.md`**

Add this section to `SKILL.md` (after the existing "## The push-notification loop" section):

````markdown
## Orchestration verbs (Phases 2–4)
- `dcx.py run-session --cwd <dir> --command "<agent cmd>" --task <slug>` — spawn one agent, **block** until it signals done, return its captured output, close it. This IS the plan-review loop: pass a reviewer agent command. Run it via the harness **run_in_background** so the harness wakes Claude when it returns.
- `dcx.py fanout --spec <items.json>` — `items.json` is `[{ "cwd": "...", "command": "...", "task_slug": "..." }, ...]`. Spawns one agent per item and returns `handles` (each with `surface_ref` + `signal_fifo`). Then launch **one `dcx.py wait --fifo <signal_fifo>` per agent via run_in_background** → Claude is woken per-completion → `read` that agent, review, `close`.
- `dcx.py watch` — read-only status of every self-spawned session (present / nonce_ok / title).
- `dcx.py worktree-add --repo <git repo> --slug <task>` — create an isolated worktree+branch (`dcx/<slug>`) so parallel build agents don't collide; use its `path` as the agent's `--cwd`.

## The full loop (Greg's vision)
1. Claude drafts a plan. 2. Per section: `run-session` with a Codex reviewer (high reasoning) → read notes → refine. 3. On approval: `worktree-add` per task, then `fanout` the build agents. 4. Launch a `wait` per agent (run_in_background); review each as it wakes you; `send` fixes back or `close`. 5. Repeat. `watch` shows the board anytime.
````

- [ ] **Step 2: Add a guarded live test of run-session (append to tests/test_smoke_live.py)**

```python
@pytest.mark.skipif(not LIVE, reason="set DCX_LIVE=1 with a live cmux + password to run")
def test_run_session_live(tmp_path):
    # run-session against a stand-in 'agent' (a shell command), proving spawn->wait->read->close
    out = cli("run-session", "--cwd", str(tmp_path),
              "--command", "echo DCX_LOOP_OK", "--task", "live-loop")
    assert out["ok"] is True
    assert "DCX_LOOP_OK" in out["output"]
    assert out["task"] == "live-loop"
```

- [ ] **Step 3: Run the guarded live test**

Run: `cd ~/.claude/skills/drive-cmux && DCX_LIVE=1 python3.12 -m pytest tests/test_smoke_live.py -q`
Expected: PASS (2 passed) — a `dcx-…: live-loop` tab appears, runs `echo`, signals done via the FIFO, `run-session` returns the captured `DCX_LOOP_OK`, and the tab closes.

- [ ] **Step 4: Commit**

```bash
cd ~/.claude/skills/drive-cmux && git add -A && git commit -q -m "docs(dcx): SKILL.md orchestration verbs + guarded live run-session test"
```

---

## Self-Review

**Spec coverage:** Phase 2 (plan-review loop) → `Loop.run_session` + `run-session` CLI (Tasks 1,5). Phase 3 (build fan-out + worktree isolation) → `Loop.fanout` + `worktrees.add/remove` + `fanout`/`worktree-add` CLI (Tasks 2,4,5). Phase 4 (watcher) → `Loop.status` + `watch` CLI (Tasks 3,5). The push bridge is reused (`Ops.wait`) — no new completion mechanism. SKILL.md documents all (Task 6). Live-verified via the guarded run-session test.

**Placeholder scan:** none — complete code in every step.

**Type consistency:** `Loop(ops)` methods match the locked list; `run_session` consumes `Ops.spawn`'s real return keys (`signal_fifo`, `surface_ref`, `workspace_ref`); `status` uses `Ops.reg.all()` + `Ops.c.tree_json()` + `tree.find_workspace` exactly as Phase 1 exposes them; `fanout` item keys (`cwd/command/task_slug`) match `Ops.spawn`'s parameters; CLI `except` widened to keep new `RuntimeError` paths fail-closed.
