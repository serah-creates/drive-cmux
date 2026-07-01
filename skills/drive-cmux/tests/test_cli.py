import json, subprocess, sys, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def run_cli(args, env=None):
    p = subprocess.run([sys.executable, os.path.join(ROOT, "dcx.py"), *args],
                       capture_output=True, text=True, env={**os.environ, **(env or {})})
    return p

def _make_cfg(tmp_path, cli_path):
    """Write a minimal config pointing at cli_path and return the env dict."""
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({
        "cli_path": cli_path,
        "password_file": str(tmp_path / "pw"),
        "state_dir": str(tmp_path / "state"),
        "denylist_patterns": ["ppv"],
    }))
    (tmp_path / "pw").write_text("x")
    return {"DCX_CONFIG": str(cfg)}

def test_unknown_ref_is_fail_closed_json(tmp_path):
    # 'send' with a bare integer must exit 1 with a JSON error and not touch cmux.
    # The fence rejects the ref before any subprocess call — this tests the FenceError path.
    env = _make_cfg(tmp_path, "/no/such/binary")
    p = run_cli(["send", "--ref", "4", "hi"], env=env)
    assert p.returncode == 1
    out = json.loads(p.stdout)
    assert out["ok"] is False and out["error_type"] == "FenceError"

def test_missing_binary_is_fail_closed_json(tmp_path):
    # preflight with a non-existent cli_path must produce JSON error, not a raw traceback.
    # This is the most common real-world failure: cmux unreachable / wrong path.
    env = _make_cfg(tmp_path, "/no/such/binary/cmux")
    p = run_cli(["preflight"], env=env)
    assert p.returncode == 1, f"expected exit 1, got {p.returncode}; stdout={p.stdout!r} stderr={p.stderr!r}"
    # stdout must be exactly one parseable JSON object — no traceback noise
    out = json.loads(p.stdout)
    assert out["ok"] is False
    assert out["error_type"] == "CmuxError"
    assert "error" in out
    # stderr should be empty (the error was routed into JSON, not a traceback)
    assert "Traceback" not in p.stderr

def test_binary_exits_nonzero_is_fail_closed_json(tmp_path):
    # preflight where the binary exists but exits non-zero (e.g. /usr/bin/false)
    # must produce a JSON error, not a raw traceback.
    env = _make_cfg(tmp_path, "/usr/bin/false")
    p = run_cli(["preflight"], env=env)
    assert p.returncode == 1
    out = json.loads(p.stdout)
    assert out["ok"] is False
    assert out["error_type"] == "CmuxError"
    assert "Traceback" not in p.stderr

def test_tree_malformed_json_is_fail_closed_json(tmp_path):
    # A fake cmux that PONGs for ping but prints non-JSON for `tree --json`.
    # `dcx.py tree` must exit 1 with a typed CmuxError JSON and NO Python traceback.
    fake = tmp_path / "fake_cmux"
    fake.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        '  ping) echo PONG ;;\n'
        '  tree) echo "this is <<not>> json" ;;\n'
        '  *) echo "" ;;\n'
        "esac\n"
    )
    fake.chmod(0o755)
    env = _make_cfg(tmp_path, str(fake))
    p = run_cli(["tree"], env=env)
    assert p.returncode == 1, f"expected exit 1; stdout={p.stdout!r} stderr={p.stderr!r}"
    out = json.loads(p.stdout)
    assert out["ok"] is False
    assert out["error_type"] == "CmuxError"
    assert "error" in out
    assert "Traceback" not in p.stdout

def test_set_password_writes_configured_file_0600(tmp_path):
    # set-password --from-stdin writes the secret to the CONFIGURED password_file
    # (so it always lands where preflight looks), with 0600 perms, no cmux needed.
    import stat as _stat
    pwfile = tmp_path / "secrets" / "socket-password.txt"   # parent dir must be created
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"cli_path": "/usr/bin/true", "password_file": str(pwfile),
                               "state_dir": str(tmp_path / "state"), "denylist_patterns": ["ppv"]}))
    p = subprocess.run([sys.executable, os.path.join(ROOT, "dcx.py"), "set-password", "--from-stdin", "--no-verify"],
                       input="s3cr3t-pw\n", capture_output=True, text=True,
                       env={**os.environ, "DCX_CONFIG": str(cfg)})
    assert p.returncode == 0, f"stdout={p.stdout!r} stderr={p.stderr!r}"
    out = json.loads(p.stdout)
    assert out["ok"] is True and out["password_file"] == str(pwfile)
    assert pwfile.read_text() == "s3cr3t-pw"          # no trailing newline
    assert _stat.S_IMODE(os.stat(pwfile).st_mode) == 0o600

def test_set_password_generate_emits_password_and_writes_file(tmp_path):
    pwfile = tmp_path / "pw.txt"
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"cli_path": "/usr/bin/true", "password_file": str(pwfile),
                               "state_dir": str(tmp_path / "state"), "denylist_patterns": ["ppv"]}))
    p = subprocess.run([sys.executable, os.path.join(ROOT, "dcx.py"), "set-password", "--generate"],
                       capture_output=True, text=True, env={**os.environ, "DCX_CONFIG": str(cfg)})
    assert p.returncode == 0, f"stdout={p.stdout!r} stderr={p.stderr!r}"
    out = json.loads(p.stdout)
    assert out["generated"] is True and out["password"]
    assert pwfile.read_text() == out["password"]      # file matches the printed value to paste into cmux

def test_roles_verb_lists_effort_map(tmp_path):
    env = _make_cfg(tmp_path, "/usr/bin/true")   # roles is static; no cmux needed
    p = run_cli(["roles"], env=env)
    assert p.returncode == 0, f"stdout={p.stdout!r} stderr={p.stderr!r}"
    out = json.loads(p.stdout)
    assert out["ok"] is True
    assert out["roles"]["plan-review"] == "xhigh"
    assert out["roles"]["build"] == "medium"
    assert out["roles"]["mechanical"] == "low"

def test_roles_verb_lists_claude_model_map(tmp_path):
    env = _make_cfg(tmp_path, "/usr/bin/true")   # static; no cmux needed
    p = run_cli(["roles"], env=env)
    assert p.returncode == 0, f"stdout={p.stdout!r} stderr={p.stderr!r}"
    out = json.loads(p.stdout)
    assert out["ok"] is True
    # the Claude lane: genius roles -> Opus, workhorse roles -> Sonnet 5
    assert out["models"]["architect"] == "claude-opus-4-8"
    assert out["models"]["plan-review"] == "claude-opus-4-8"
    assert out["models"]["research"] == "claude-sonnet-5"
    assert out["models"]["code-review"] == "claude-sonnet-5"

def test_help_lists_subcommands():
    p = run_cli(["--help"])
    assert p.returncode == 0
    for verb in ["spawn", "send", "read", "close", "wait", "tree", "preflight"]:
        assert verb in p.stdout

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
