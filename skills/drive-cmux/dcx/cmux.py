# dcx/cmux.py
import json, os, re, subprocess

class CmuxError(Exception):
    pass

_WS_RE = re.compile(r"workspace:\d+")

def _default_run(argv, env):
    try:
        p = subprocess.run(argv, env=env, capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr
    except OSError as e:
        raise CmuxError(f"could not launch cmux binary {argv[0]!r}: {e}") from e

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
        out = self._cli("tree", "--json")
        try:
            return json.loads(out)
        except json.JSONDecodeError as e:
            raise CmuxError(f"could not parse tree --json output: {e}") from e

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
