from dcx.loop import Loop

class FakeOps:
    def __init__(self):
        self.calls = []
        self.spawned = {"workspace_ref": "workspace:20", "surface_ref": "surface:30",
                        "nonce": "ab12cd34", "signal_fifo": "/tmp/f.fifo", "title": "dcx-ab12cd34: t"}
        self.screen = "review notes: looks good"
    def spawn(self, cwd, command, task_slug, role=None, fast=False):
        self.calls.append(("spawn", cwd, command, task_slug, role, fast)); return dict(self.spawned)
    def wait(self, fifo, timeout=None): self.calls.append(("wait", fifo)); return {"signaled": True, "timed_out": False}
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

def test_run_session_surfaces_role_effort_tier_from_spawn():
    ops = FakeOps()
    base = dict(ops.spawned)
    def spawn(cwd, command, task_slug, role=None, fast=False):
        ops.calls.append(("spawn", cwd, command, task_slug, role, fast))
        return {**base, "role": role, "reasoning_effort": "xhigh", "service_tier": "priority"}
    ops.spawn = spawn
    res = Loop(ops).run_session("/tmp/x", "codex exec hi", "planner", role="plan-review", fast=True)
    assert res["role"] == "plan-review"
    assert res["reasoning_effort"] == "xhigh"
    assert res["service_tier"] == "priority"

def test_run_session_leaves_pane_open_on_timeout():
    # A timeout must be non-destructive: read the surface but do NOT close the
    # still-running agent, and surface timed_out=True to the caller.
    ops = FakeOps()
    ops.wait = lambda fifo, timeout=None: (ops.calls.append(("wait", fifo)) or {"signaled": False, "timed_out": True})
    res = Loop(ops).run_session("/tmp/x", "codex exec hi", "review-1", timeout=0.1)
    names = [c[0] for c in ops.calls]
    assert names == ["spawn", "wait", "read"]      # NO close
    assert ("close", "workspace:20") not in ops.calls
    assert res["timed_out"] is True and res["signaled"] is False and res["closed"] is False
    assert res["output"] == "review notes: looks good"

def test_fanout_spawns_each_item_and_returns_handles():
    ops = FakeOps()
    seq = [
        {"workspace_ref": "workspace:21", "surface_ref": "surface:31", "nonce": "n1", "signal_fifo": "/tmp/1.fifo", "title": "dcx-n1: a"},
        {"workspace_ref": "workspace:22", "surface_ref": "surface:32", "nonce": "n2", "signal_fifo": "/tmp/2.fifo", "title": "dcx-n2: b"},
    ]
    out = []
    def spawn(cwd, command, task_slug, role=None, fast=False):
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

def test_fanout_passes_per_item_role_and_fast_to_spawn():
    ops = FakeOps()
    seen = []
    def spawn(cwd, command, task_slug, role=None, fast=False):
        seen.append((role, fast)); return dict(ops.spawned)
    ops.spawn = spawn
    items = [{"cwd": "/a", "command": "codex exec A", "task_slug": "t-a", "role": "plan-review", "fast": True},
             {"cwd": "/b", "command": "codex exec B", "task_slug": "t-b"}]  # no role/fast
    Loop(ops).fanout(items)
    assert seen == [("plan-review", True), (None, False)]

def test_await_agent_reads_then_closes_on_signal():
    ops = FakeOps()
    out = Loop(ops).await_agent("/tmp/f.fifo", read_ref="surface:30", close_ref="workspace:20")
    assert out["signaled"] is True and out["closed"] is True
    assert out["output"] == ops.screen
    names = [c[0] for c in ops.calls]
    assert names == ["wait", "read", "close"]          # read happens BEFORE close

def test_await_agent_leaves_pane_open_on_timeout():
    ops = FakeOps()
    ops.wait = lambda fifo, timeout=None: {"signaled": False, "timed_out": True}
    out = Loop(ops).await_agent("/tmp/f.fifo", read_ref="surface:30", close_ref="workspace:20", timeout=0.1)
    assert out["timed_out"] is True and out["signaled"] is False
    assert "closed" not in out
    assert ("close", "workspace:20") not in ops.calls   # nothing closed on timeout

def test_await_agent_captures_close_error_but_keeps_output():
    from dcx.fence import FenceError
    ops = FakeOps()
    def boom(ws_ref): raise FenceError("vanished")
    ops.close = boom
    out = Loop(ops).await_agent("/tmp/f.fifo", read_ref="surface:30", close_ref="workspace:20")
    assert out["output"] == ops.screen                  # output still returned
    assert out["closed"] is False and "close_error" in out

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
