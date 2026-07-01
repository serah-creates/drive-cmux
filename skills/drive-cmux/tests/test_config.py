# tests/test_config.py
import json, os
from dcx.config import load_config

def test_load_config_expands_paths_and_has_defaults(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({
        "cli_path": "/x/cmux",
        "password_file": "~/pw.txt",
        "state_dir": "~/state",
        "denylist_patterns": ["ppv"],
    }))
    cfg = load_config(str(cfg_file))
    assert cfg["cli_path"] == "/x/cmux"
    assert cfg["password_file"] == os.path.expanduser("~/pw.txt")
    assert cfg["state_dir"] == os.path.expanduser("~/state")
    assert cfg["denylist_patterns"] == ["ppv"]

def test_load_config_defaults_when_file_missing(tmp_path):
    cfg = load_config(str(tmp_path / "nope.json"))
    assert cfg["cli_path"].endswith("/cmux")
    assert "ppv" in cfg["denylist_patterns"]
