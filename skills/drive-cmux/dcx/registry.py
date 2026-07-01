# dcx/registry.py
import json, os

class Registry:
    def __init__(self, state_file):
        self.state_file = state_file
        os.makedirs(os.path.dirname(state_file), exist_ok=True)

    def _load(self):
        try:
            with open(self.state_file) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save(self, data):
        tmp = self.state_file + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.state_file)

    def record(self, ref, nonce, cwd, command):
        data = self._load()
        data[ref] = {"nonce": nonce, "cwd": cwd, "command": command}
        self._save(data)

    def get(self, ref):
        return self._load().get(ref)

    def remove(self, ref):
        data = self._load()
        data.pop(ref, None)
        self._save(data)

    def all(self):
        return self._load()
