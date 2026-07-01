# dcx/ops.py
import os, secrets, shlex, select, time
from . import fence
from .roles import apply_role, apply_tier, apply_model, detect_engine
from .tree import parse_tree, find_workspace, find_surface, first_surface_ref

# Commands longer than this are run from a short temp script instead of pasted
# inline: cmux truncates very long pastes (and a long paste can fail to auto-run).
_MAX_INLINE_COMMAND = 300

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
        # The denylist is intentionally NOT applied to close. Registry membership +
        # the per-spawn nonce already prove dcx created this pane itself, so it's our
        # own worker (a review/build agent) — never the user's real OnlyFans/CRM/etc.
        # session (those are never in the registry, so they're already refused above).
        # This lets dcx clean up its own agents even when their cwd/title contains a
        # denylisted word (e.g. a repo named '*-vault-*'). Writes still route through
        # _verify_self_spawned_surface.
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
    def spawn(self, cwd, command, task_slug, role=None, fast=False):
        effort = None
        model = None
        engine = None
        if role:
            engine = detect_engine(command)
            if engine == "codex":
                command, effort, _ = apply_role(command, role)
            else:  # claude lane: pick the model for the role instead of codex effort
                command, model, _ = apply_model(command, role)
        if fast and engine != "claude":   # service tier is a Codex-only concept
            command, _, _ = apply_tier(command, "fast")
        nonce = secrets.token_hex(4)
        os.makedirs(self.state_dir, exist_ok=True)
        fifo = os.path.join(self.state_dir, f"done-{nonce}.fifo")
        try:
            os.mkfifo(fifo)
        except FileExistsError:
            pass
        # Long commands get truncated when cmux pastes them into the shell, so run
        # them from a short temp script — cmux then only ever receives a short line.
        run_command = command
        script_path = None
        if len(command) > _MAX_INLINE_COMMAND:
            script_path = os.path.join(self.state_dir, f"cmd-{nonce}.sh")
            with open(script_path, "w") as f:
                f.write("#!/bin/zsh\n" + command + "\n")
            os.chmod(script_path, 0o700)
            run_command = "zsh " + shlex.quote(script_path)
        # wrap the agent command so it signals completion on the FIFO when done
        wrapped = f"{run_command} ; echo done > {shlex.quote(fifo)}"
        ws_ref = self.c.new_workspace(cwd, command=wrapped)
        title = f"dcx-{nonce}: {task_slug}"
        self.c.rename_workspace(ws_ref, title)
        self.reg.record(ws_ref, nonce, cwd, command)
        surface_ref = self._resolve_surface(ws_ref)
        result = {"workspace_ref": ws_ref, "surface_ref": surface_ref,
                  "nonce": nonce, "signal_fifo": fifo, "title": title}
        if script_path:
            result["command_script"] = script_path
        if role:
            result["role"] = role
            result["engine"] = engine
            if effort is not None:
                result["reasoning_effort"] = effort
            if model is not None:
                result["model"] = model
        if fast:
            result["service_tier"] = "priority"
        return result

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
        rec = self.reg.get(ws_ref)  # look up nonce BEFORE deregistering
        self.c.close_workspace(ws_ref)
        self.reg.remove(ws_ref)
        # best-effort cleanup of the spawn FIFO + temp command script
        if rec and rec.get("nonce"):
            for name in (f"done-{rec['nonce']}.fifo", f"cmd-{rec['nonce']}.sh"):
                try:
                    os.unlink(os.path.join(self.state_dir, name))
                except FileNotFoundError:
                    pass

    # ---- read (unrestricted) ----
    def read(self, surface_ref, scrollback=False):
        if not fence.validate_ref(surface_ref, "surface"):
            raise fence.FenceError(f"not a fully-qualified surface ref: {surface_ref!r}")
        return self.c.read_screen(surface_ref, scrollback=scrollback)

    # ---- prune (housekeeping; never touches live panes) ----
    def prune(self):
        """Remove self-spawn registry entries whose workspace is gone (or whose
        ref was reused by a pane that no longer carries our nonce), and unlink
        orphaned done-*.fifo files. Pure bookkeeping: it only deletes records of
        agents that are already gone and never closes a live pane, so the
        denylist/fence are irrelevant here."""
        wss = self._live_workspaces()
        pruned, kept, removed_fifos = [], [], []

        def _rm_fifo(nonce):
            if not nonce:
                return
            try:
                os.unlink(os.path.join(self.state_dir, f"done-{nonce}.fifo"))
                removed_fifos.append(f"done-{nonce}.fifo")
            except FileNotFoundError:
                pass

        for ref, rec in list(self.reg.all().items()):
            w = find_workspace(wss, ref)
            nonce = rec.get("nonce")
            still_ours = w is not None and f"dcx-{nonce}:" in (w.title or "")
            if still_ours:
                kept.append(ref)
                continue
            self.reg.remove(ref)
            pruned.append(ref)
            _rm_fifo(nonce)
        # sweep any remaining orphaned FIFOs whose nonce matches no live entry
        live_nonces = {rec.get("nonce") for rec in self.reg.all().values()}
        try:
            for fn in os.listdir(self.state_dir):
                if fn.startswith("done-") and fn.endswith(".fifo"):
                    nonce = fn[len("done-"):-len(".fifo")]
                    if nonce not in live_nonces:
                        try:
                            os.unlink(os.path.join(self.state_dir, fn))
                            removed_fifos.append(fn)
                        except FileNotFoundError:
                            pass
        except FileNotFoundError:
            pass
        return {"pruned_entries": pruned, "kept_entries": kept, "removed_fifos": removed_fifos}

    # ---- wait (the push bridge; run via run_in_background) ----
    def wait(self, fifo_path, timeout=None, poll_interval=2.0):
        """Block until the agent writes its done-signal on the FIFO.

        Returns {"signaled": bool, "timed_out": bool}.

        With timeout=None (or <=0) this blocks indefinitely (legacy behavior).
        With a timeout in seconds it returns {"signaled": False, "timed_out": True}
        instead of hanging forever when an agent never reaches its wrapped
        `; echo done > <fifo>` step (crash / never-exits / interactive TUI /
        codex stalls before output). A timeout is NON-DESTRUCTIVE: the pane is
        left running so the caller can `read` it and re-`wait` or recover.

        Implementation note: the FIFO is opened non-blocking and polled with
        select, so a never-arriving writer can't wedge the waiter open. A FIFO
        read end only becomes readable once a writer has connected — i.e. the
        wrapped `echo done` actually ran — so readability == the agent finished.
        """
        deadline = None if (timeout is None or timeout <= 0) else time.monotonic() + timeout
        fd = os.open(fifo_path, os.O_RDONLY | os.O_NONBLOCK)
        try:
            while True:
                if deadline is None:
                    wait_for = poll_interval
                else:
                    wait_for = max(0.0, min(poll_interval, deadline - time.monotonic()))
                readable, _, _ = select.select([fd], [], [], wait_for)
                if readable:
                    try:
                        os.read(fd, 4096)
                    except OSError:
                        pass
                    return {"signaled": True, "timed_out": False}
                if deadline is not None and time.monotonic() >= deadline:
                    return {"signaled": False, "timed_out": True}
        finally:
            os.close(fd)
