# dcx/config.py
import json, os

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_DEFAULTS = {
    "cli_path": "/Applications/cmux.app/Contents/Resources/bin/cmux",
    # Portable default: resolves relative to wherever this skill is installed,
    # and lands inside the git-ignored state/ dir so the secret never gets
    # committed. Override per-machine via config.json (see config.example.json).
    "password_file": os.path.join(_HERE, "state", "socket-password.txt"),
    "state_dir": os.path.join(_HERE, "state"),
    "denylist_patterns": ["ppv", "onlyfans", "serah", "vault", "fan",
                          "crm", "purchase", "gemma", "chat-app", "orchestrator"],
}

_PATH_KEYS = ("cli_path", "password_file", "state_dir")

def load_config(path=None):
    path = path or os.path.join(_HERE, "config.json")
    data = dict(_DEFAULTS)
    try:
        with open(path) as f:
            data.update(json.load(f))
    except FileNotFoundError:
        pass
    for k in _PATH_KEYS:
        data[k] = os.path.expanduser(data[k])
    return data
