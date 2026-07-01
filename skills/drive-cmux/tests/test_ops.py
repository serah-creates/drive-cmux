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

def test_close_self_spawned_denylisted_pane_now_succeeds(tmp_path):
    # Option 1: close is gated by registry + nonce, NOT the denylist. A self-spawned
    # pane whose title contains a denylisted word ("ppv") is still closable.
    ops, c, reg = make(tmp_path)   # DENY = ["ppv","fan","gemma"]
    reg.record("workspace:20", "ab12cd34", "/tmp/x", "echo")
    c.tree = {"windows": [{"workspaces": [_ws("workspace:20", "dcx-ab12cd34: ppv-review", [_sf("surface:30")])]}]}
    ops.close("workspace:20")   # must NOT raise despite "ppv" in the title
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

def test_spawn_with_role_injects_reasoning_effort(tmp_path):
    ops, c, reg = make(tmp_path)
    def tree_after():
        return {"windows": [{"workspaces": [_ws("workspace:20", c._title, [_sf("surface:30")])]}]}
    c.tree_json = tree_after
    res = ops.spawn("/tmp/x", 'codex exec -c sandbox_mode=read-only "$(cat /tmp/p.txt)"', "review-1", role="plan-review")
    assert res["role"] == "plan-review" and res["reasoning_effort"] == "xhigh"
    assert "-c model_reasoning_effort=xhigh" in c.last_command   # injected into the agent command
    assert "echo done >" in c.last_command                       # still wrapped for the FIFO signal

def test_spawn_without_role_omits_effort_keys(tmp_path):
    ops, c, reg = make(tmp_path)
    def tree_after():
        return {"windows": [{"workspaces": [_ws("workspace:20", c._title, [_sf("surface:30")])]}]}
    c.tree_json = tree_after
    res = ops.spawn("/tmp/x", "echo hi", "mytask")
    assert "role" not in res and "reasoning_effort" not in res
    assert "model_reasoning_effort" not in c.last_command
    assert "service_tier" not in c.last_command   # default = Normal tier, nothing injected

def test_spawn_fast_injects_priority_tier(tmp_path):
    ops, c, reg = make(tmp_path)
    def tree_after():
        return {"windows": [{"workspaces": [_ws("workspace:20", c._title, [_sf("surface:30")])]}]}
    c.tree_json = tree_after
    res = ops.spawn("/tmp/x", 'codex exec "$(cat /tmp/p.txt)"', "fast-run", role="plan-review", fast=True)
    assert res["service_tier"] == "priority" and res["reasoning_effort"] == "xhigh"
    assert "-c service_tier=priority" in c.last_command
    assert "-c model_reasoning_effort=xhigh" in c.last_command   # role + fast compose

def test_spawn_with_claude_command_injects_model(tmp_path):
    ops, c, reg = make(tmp_path)
    def tree_after():
        return {"windows": [{"workspaces": [_ws("workspace:20", c._title, [_sf("surface:30")])]}]}
    c.tree_json = tree_after
    res = ops.spawn("/tmp/x", 'claude -p "$(cat /tmp/p.txt)"', "research-1", role="research")
    assert res["role"] == "research" and res["engine"] == "claude"
    assert res["model"] == "claude-sonnet-5"
    assert "reasoning_effort" not in res            # the claude lane has no codex reasoning effort
    assert "--model claude-sonnet-5" in c.last_command
    assert "echo done >" in c.last_command          # still wrapped for the FIFO completion signal


def test_spawn_claude_architect_uses_opus(tmp_path):
    ops, c, reg = make(tmp_path)
    def tree_after():
        return {"windows": [{"workspaces": [_ws("workspace:20", c._title, [_sf("surface:30")])]}]}
    c.tree_json = tree_after
    res = ops.spawn("/tmp/x", 'claude -p "plan the build"', "arch-1", role="architect")
    assert res["engine"] == "claude" and res["model"] == "claude-opus-4-8"
    assert "--model claude-opus-4-8" in c.last_command


def test_spawn_long_command_runs_via_temp_script(tmp_path):
    import os as _os
    ops, c, reg = make(tmp_path)
    def tree_after():
        return {"windows": [{"workspaces": [_ws("workspace:20", c._title, [_sf("surface:30")])]}]}
    c.tree_json = tree_after
    long_cmd = "codex exec -s workspace-write '" + ("build the neon game " * 40) + "'"
    assert len(long_cmd) > 300
    res = ops.spawn("/tmp/x", long_cmd, "big")
    # cmux only ever receives a SHORT line (zsh <script>), never the giant paste that truncates
    assert "zsh " in c.last_command
    assert long_cmd not in c.last_command
    assert res["signal_fifo"] in c.last_command       # still FIFO-wrapped for completion
    # the full command lives in the temp script
    sp = res["command_script"]
    assert _os.path.exists(sp) and long_cmd in open(sp).read()

def test_spawn_short_command_stays_inline(tmp_path):
    ops, c, reg = make(tmp_path)
    def tree_after():
        return {"windows": [{"workspaces": [_ws("workspace:20", c._title, [_sf("surface:30")])]}]}
    c.tree_json = tree_after
    res = ops.spawn("/tmp/x", "echo hi", "small")
    assert "echo hi" in c.last_command                # short commands paste inline, unchanged
    assert "command_script" not in res

def test_close_removes_command_script(tmp_path):
    import os as _os
    ops, c, reg = make(tmp_path)
    def tree_after():
        return {"windows": [{"workspaces": [_ws("workspace:20", c._title, [_sf("surface:30")])]}]}
    c.tree_json = tree_after
    res = ops.spawn("/tmp/x", "echo " + ("x" * 400), "big")
    sp = res["command_script"]
    assert _os.path.exists(sp)
    ops.close("workspace:20")
    assert not _os.path.exists(sp)                     # close cleans up the temp script too


def test_prune_removes_gone_and_reused_entries_keeps_live(tmp_path):
    import os
    ops, c, reg = make(tmp_path)
    reg.record("workspace:20", "live0001", "/a", "cmd")   # live: present + nonce matches
    reg.record("workspace:30", "gone0002", "/b", "cmd")   # gone: absent from tree
    reg.record("workspace:40", "reuse003", "/c", "cmd")   # ref reused by a non-ours pane
    c.tree = {"windows": [{"workspaces": [
        _ws("workspace:20", "dcx-live0001: keep-me", [_sf("surface:1")]),
        _ws("workspace:40", "someone-elses-window", [_sf("surface:2")]),
    ]}]}
    for n in ("live0001", "gone0002", "reuse003", "orphan99"):   # incl. one orphan FIFO
        open(os.path.join(ops.state_dir, f"done-{n}.fifo"), "w").close()
    res = ops.prune()
    assert res["kept_entries"] == ["workspace:20"]
    assert set(res["pruned_entries"]) == {"workspace:30", "workspace:40"}
    assert reg.get("workspace:20") and reg.get("workspace:30") is None and reg.get("workspace:40") is None
    # live FIFO kept; gone/reused/orphan FIFOs removed and ALL reported
    assert os.path.exists(os.path.join(ops.state_dir, "done-live0001.fifo"))
    for n in ("gone0002", "reuse003", "orphan99"):
        assert not os.path.exists(os.path.join(ops.state_dir, f"done-{n}.fifo"))
    assert set(res["removed_fifos"]) == {"done-gone0002.fifo", "done-reuse003.fifo", "done-orphan99.fifo"}

def test_read_allows_any_surface_readonly(tmp_path):
    ops, c, reg = make(tmp_path)
    # reads are unrestricted
    assert ops.read("surface:30") == "screen of surface:30"

def test_close_removes_spawn_fifo(tmp_path):
    import os
    ops, c, reg = make(tmp_path)
    # spawn so a real FIFO is created in state_dir, and the tree exposes the new ws+surface
    def tree_after():
        return {"windows": [{"workspaces": [_ws("workspace:20", c._title, [_sf("surface:30")])]}]}
    c.tree_json = tree_after
    res = ops.spawn("/tmp/x", "echo hi", "mytask")
    fifo = res["signal_fifo"]
    assert os.path.exists(fifo)
    ops.close("workspace:20")
    assert c.closed == ["workspace:20"]
    assert reg.get("workspace:20") is None
    # close best-effort removes the spawn FIFO
    assert not os.path.exists(fifo)

def test_wait_returns_signaled_when_fifo_written(tmp_path):
    import os, threading
    ops, c, reg = make(tmp_path)
    fifo = str(tmp_path / "done.fifo")
    os.mkfifo(fifo)
    # writer blocks on open() until wait() attaches the read end, then signals
    def writer():
        with open(fifo, "w") as f:
            f.write("done\n")
    t = threading.Thread(target=writer, daemon=True); t.start()
    res = ops.wait(fifo, timeout=5, poll_interval=0.1)
    assert res == {"signaled": True, "timed_out": False}
    t.join(timeout=2)

def test_wait_times_out_when_agent_never_signals(tmp_path):
    # The hang fix: a FIFO that no one ever writes must NOT block forever.
    import os
    ops, c, reg = make(tmp_path)
    fifo = str(tmp_path / "stuck.fifo")
    os.mkfifo(fifo)
    res = ops.wait(fifo, timeout=0.4, poll_interval=0.1)
    assert res == {"signaled": False, "timed_out": True}

def test_close_is_best_effort_when_fifo_already_gone(tmp_path):
    import os
    ops, c, reg = make(tmp_path)
    def tree_after():
        return {"windows": [{"workspaces": [_ws("workspace:20", c._title, [_sf("surface:30")])]}]}
    c.tree_json = tree_after
    res = ops.spawn("/tmp/x", "echo hi", "mytask")
    os.unlink(res["signal_fifo"])  # remove it out from under close()
    # close must not raise even though the FIFO is missing
    ops.close("workspace:20")
    assert c.closed == ["workspace:20"]
    assert reg.get("workspace:20") is None
