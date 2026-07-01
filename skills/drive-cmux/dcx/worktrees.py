# dcx/worktrees.py
import os, re, subprocess

def _slug(s):
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", s).strip("-") or "task"

def _git(repo_dir, *args):
    p = subprocess.run(["git", "-C", repo_dir, *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr.strip()}")
    return p.stdout

def add(repo_dir, slug, root=None):
    """Create an isolated git worktree + branch for a fan-out agent. Returns {path, branch}."""
    s = _slug(slug)
    root = root or os.path.join(repo_dir, ".dcx-worktrees")
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, s)
    branch = f"dcx/{s}"
    _git(repo_dir, "worktree", "add", "-b", branch, path)
    return {"path": path, "branch": branch}

def remove(repo_dir, path):
    """Remove a worktree created by add() (best-effort prune of the branch is left to the caller)."""
    _git(repo_dir, "worktree", "remove", "--force", path)
