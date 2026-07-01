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

def test_tree_json_malformed_raises_cmuxerror(tmp_path):
    # rc=0 but garbage (non-JSON) stdout must DENY with a typed CmuxError, not bubble JSONDecodeError.
    c, _ = make(tmp_path, {("tree", "--json"): (0, "not json <<truncated", "")})
    import json as _json
    with pytest.raises(CmuxError):
        c.tree_json()
    # be explicit that it is NOT the raw decode error
    try:
        c.tree_json()
    except CmuxError as e:
        assert not isinstance(e, _json.JSONDecodeError)
