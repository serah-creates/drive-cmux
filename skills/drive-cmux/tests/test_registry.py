from dcx.registry import Registry

def test_record_get_remove_roundtrip(tmp_path):
    r = Registry(str(tmp_path / "reg.json"))
    r.record("workspace:5", "ab12cd34", "/tmp/x", "echo hi")
    rec = r.get("workspace:5")
    assert rec["nonce"] == "ab12cd34" and rec["cwd"] == "/tmp/x" and rec["command"] == "echo hi"
    assert "workspace:5" in r.all()
    r.remove("workspace:5")
    assert r.get("workspace:5") is None

def test_persists_across_instances(tmp_path):
    path = str(tmp_path / "reg.json")
    Registry(path).record("workspace:9", "deadbeef", "/tmp/y", "ls")
    assert Registry(path).get("workspace:9")["nonce"] == "deadbeef"

def test_get_missing_returns_none(tmp_path):
    assert Registry(str(tmp_path / "reg.json")).get("workspace:1") is None
