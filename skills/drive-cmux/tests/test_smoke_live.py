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

@pytest.mark.skipif(not LIVE, reason="set DCX_LIVE=1 with a live cmux + password to run")
def test_run_session_live(tmp_path):
    # run-session against a stand-in 'agent' (a shell command), proving spawn->wait->read->close
    out = cli("run-session", "--cwd", str(tmp_path),
              "--command", "echo DCX_LOOP_OK", "--task", "live-loop")
    assert out["ok"] is True
    assert "DCX_LOOP_OK" in out["output"]
    assert out["task"] == "live-loop"
