# dcx.py
import argparse, json, os, sys
from dcx.config import load_config
from dcx.cmux import CmuxClient, CmuxError
from dcx.registry import Registry
from dcx.fence import FenceError
from dcx.ops import Ops
from dcx.loop import Loop
from dcx import worktrees
from dcx.passwd import set_password
from dcx.roles import ROLE_EFFORT, ROLE_MODEL

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
    sub.add_parser("roles", help="print the role maps used by --role: reasoning-effort (Codex lane) + model (Claude lane)")
    sub.add_parser("prune", help="remove registry entries for gone panes + orphaned FIFOs (housekeeping; never closes a live pane)")
    spw = sub.add_parser("set-password", help="write the cmux socket password to the configured password_file (per-machine setup)")
    spw.add_argument("--generate", action="store_true", help="generate a strong random password to paste INTO cmux (printed once)")
    spw.add_argument("--from-stdin", action="store_true", help="read the password from stdin instead of prompting (non-interactive)")
    spw.add_argument("--no-verify", action="store_true", help="skip the preflight check after writing")
    sp = sub.add_parser("spawn"); sp.add_argument("--cwd", required=True); sp.add_argument("--command", required=True); sp.add_argument("--task", required=True); sp.add_argument("--role", help="role preset (see `dcx roles`): a codex command gets the reasoning effort; a claude command gets the model (architect/plan-review -> Opus/Fable, research/review -> Sonnet 5)"); sp.add_argument("--fast", action="store_true", help="use the Fast (priority) tier for this run — faster but ~2x cost. Codex lane only. Default is Normal.")
    se = sub.add_parser("send"); se.add_argument("--ref", required=True); se.add_argument("text")
    sk = sub.add_parser("send-key"); sk.add_argument("--ref", required=True); sk.add_argument("key")
    rd = sub.add_parser("read"); rd.add_argument("--ref", required=True); rd.add_argument("--scrollback", action="store_true")
    wt = sub.add_parser("wait"); wt.add_argument("--fifo", required=True); wt.add_argument("--timeout", type=float, default=1800.0, help="seconds to wait before giving up (default 1800; 0 = block forever). On timeout the pane is left running."); wt.add_argument("--read-ref", help="surface to capture into the result when the agent finishes (read before close)"); wt.add_argument("--close-ref", help="workspace to auto-close when the agent finishes (pair with --read-ref so output isn't lost)")
    cl = sub.add_parser("close"); cl.add_argument("--ref", required=True)
    rs = sub.add_parser("run-session"); rs.add_argument("--cwd", required=True); rs.add_argument("--command", required=True); rs.add_argument("--task", required=True); rs.add_argument("--no-scrollback", action="store_true"); rs.add_argument("--timeout", type=float, default=1800.0, help="seconds to wait before giving up (default 1800; 0 = block forever). On timeout the pane is left open."); rs.add_argument("--role", help="effort preset injected into the codex command (see `dcx roles`)"); rs.add_argument("--fast", action="store_true", help="use the Fast (priority) tier for this run — faster but ~2x cost. Default is Normal.")
    fo = sub.add_parser("fanout"); fo.add_argument("--spec", required=True, help="path to a JSON file: [{cwd, command, task_slug}, ...]")
    sub.add_parser("watch")
    wa = sub.add_parser("worktree-add"); wa.add_argument("--repo", required=True); wa.add_argument("--slug", required=True); wa.add_argument("--root")
    args = p.parse_args(argv)

    cfg = load_config(os.environ.get("DCX_CONFIG"))
    client, ops = _build(cfg)
    try:
        if args.cmd == "preflight":
            _emit({"ok": client.ping()})
        elif args.cmd == "set-password":
            _emit(set_password(cfg, client, generate=args.generate,
                               from_stdin=args.from_stdin, verify=not args.no_verify))
        elif args.cmd == "tree":
            _emit({"ok": True, "tree": client.tree_json()})
        elif args.cmd == "roles":
            _emit({"ok": True, "roles": ROLE_EFFORT, "models": ROLE_MODEL})
        elif args.cmd == "prune":
            _emit({"ok": True, **ops.prune()})
        elif args.cmd == "spawn":
            _emit({"ok": True, **ops.spawn(args.cwd, args.command, args.task, role=args.role, fast=args.fast)})
        elif args.cmd == "send":
            ops.send(args.ref, args.text); _emit({"ok": True, "surface_ref": args.ref})
        elif args.cmd == "send-key":
            ops.send_key(args.ref, args.key); _emit({"ok": True, "surface_ref": args.ref})
        elif args.cmd == "read":
            _emit({"ok": True, "screen": ops.read(args.ref, scrollback=args.scrollback)})
        elif args.cmd == "wait":
            to = None if args.timeout <= 0 else args.timeout
            res = Loop(ops).await_agent(args.fifo, read_ref=args.read_ref, close_ref=args.close_ref, timeout=to)
            _emit({"ok": bool(res["signaled"]), **res})
        elif args.cmd == "close":
            ops.close(args.ref); _emit({"ok": True, "closed": args.ref})
        elif args.cmd == "run-session":
            loop = Loop(ops)
            to = None if args.timeout <= 0 else args.timeout
            _emit({"ok": True, **loop.run_session(args.cwd, args.command, args.task, scrollback=not args.no_scrollback, timeout=to, role=args.role, fast=args.fast)})
        elif args.cmd == "fanout":
            with open(args.spec) as f:
                items = json.load(f)
            _emit({"ok": True, "handles": Loop(ops).fanout(items)})
        elif args.cmd == "watch":
            _emit({"ok": True, "status": Loop(ops).status()})
        elif args.cmd == "worktree-add":
            _emit({"ok": True, **worktrees.add(args.repo, args.slug, root=args.root)})
    except (FenceError, CmuxError, RuntimeError) as e:
        _err(e)

if __name__ == "__main__":
    main()
