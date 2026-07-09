# dcx/loop.py
from .tree import parse_tree, find_workspace
from .fence import FenceError
from .cmux import CmuxError

class Loop:
    def __init__(self, ops):
        self.ops = ops

    def run_session(self, cwd, command, task_slug, scrollback=True, timeout=None, role=None, fast=False):
        """Spawn one agent session, block until it signals done (or `timeout`
        seconds elapse), read its output, and close it.

        On a clean completion the pane is closed (as before). On a TIMEOUT the
        pane is LEFT OPEN (non-destructive) so the caller can inspect it and
        re-wait or recover instead of losing a still-running agent."""
        spawn = self.ops.spawn(cwd, command, task_slug, role=role, fast=fast)
        res = self.ops.wait(spawn["signal_fifo"], timeout=timeout)
        if isinstance(res, dict):
            signaled, timed_out = bool(res.get("signaled")), bool(res.get("timed_out"))
        else:  # tolerate fakes/legacy callers that return a bare bool
            signaled, timed_out = bool(res), False
        closed = False
        try:
            output = self.ops.read(spawn["surface_ref"], scrollback=scrollback)
        finally:
            if signaled:
                self.ops.close(spawn["workspace_ref"])
                closed = True
        result = {"task": task_slug, "workspace_ref": spawn["workspace_ref"],
                  "surface_ref": spawn["surface_ref"], "output": output,
                  "signaled": signaled, "timed_out": timed_out, "closed": closed}
        for k in ("role", "engine", "model", "reasoning_effort", "service_tier"):  # surface what was launched
            if k in spawn:
                result[k] = spawn[k]
        return result

    def fanout(self, items):
        """Spawn one agent session per item; return handles (incl signal_fifo). Does NOT wait/close.
        items: list of {cwd, command, task_slug, role?, fast?}. Caller waits per-agent (run_in_background) then reads/closes."""
        handles = []
        for it in items:
            sp = self.ops.spawn(it["cwd"], it["command"], it["task_slug"],
                                 role=it.get("role"), fast=bool(it.get("fast")))
            handles.append({"task": it["task_slug"], **sp})
        return handles

    def await_agent(self, fifo, read_ref=None, close_ref=None, timeout=None, scrollback=True):
        """The self-closing finish for the fanout pattern: block on an agent's
        completion FIFO, then optionally read its output and close its pane. Run
        per handle via run_in_background so Claude is woken with the output AND
        the pane is already gone — no separate read/close step to forget.

        Reads BEFORE closing so output is never lost. On timeout it leaves the
        pane open (non-destructive). A close failure (e.g. the pane vanished) is
        captured, not raised, so the captured output still comes back."""
        res = self.ops.wait(fifo, timeout=timeout)
        signaled = bool(res.get("signaled")) if isinstance(res, dict) else bool(res)
        out = {"signaled": signaled,
               "timed_out": bool(res.get("timed_out")) if isinstance(res, dict) else False}
        if signaled and read_ref:
            out["output"] = self.ops.read(read_ref, scrollback=scrollback)
        if signaled and close_ref:
            try:
                self.ops.close(close_ref)
                out["closed"] = True
            except (FenceError, CmuxError) as e:
                out["closed"] = False
                out["close_error"] = str(e)
        return out

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
