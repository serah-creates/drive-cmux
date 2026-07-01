# tests/test_worktrees.py
import os, subprocess
from dcx import worktrees

def _git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True)

def _init_repo(tmp_path):
    repo = str(tmp_path / "repo"); os.makedirs(repo)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t"); _git(repo, "config", "user.name", "t")
    (tmp_path / "repo" / "f.txt").write_text("hi")
    _git(repo, "add", "-A"); _git(repo, "commit", "-q", "-m", "init")
    return repo

def test_add_creates_isolated_worktree_and_branch(tmp_path):
    repo = _init_repo(tmp_path)
    root = str(tmp_path / "wts")
    res = worktrees.add(repo, "task-a", root=root)
    assert os.path.isdir(res["path"])
    assert os.path.isfile(os.path.join(res["path"], "f.txt"))   # checked-out worktree
    # it's a registered worktree of repo
    out = subprocess.run(["git", "-C", repo, "worktree", "list"], capture_output=True, text=True).stdout
    assert res["path"] in out
    assert res["branch"] in out

def test_remove_cleans_up(tmp_path):
    repo = _init_repo(tmp_path)
    res = worktrees.add(repo, "task-b", root=str(tmp_path / "wts"))
    worktrees.remove(repo, res["path"])
    out = subprocess.run(["git", "-C", repo, "worktree", "list"], capture_output=True, text=True).stdout
    assert res["path"] not in out
