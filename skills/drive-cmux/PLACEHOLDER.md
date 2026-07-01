# 🚧 The skill lands here

The **`drive-cmux`** skill — the actual conductor (`dcx`) — will be published into this folder right after the launch video.

**Why it isn't here yet:** it's being cut as a clean, safe *public* release (secrets and machine-local config stripped out) from a private working copy, and the new **Sonnet 5 research lane** is being added first — the exact upgrade the video is about.

**What will be here:**

```
skills/drive-cmux/
├── SKILL.md              # how Claude Code uses it
├── SETUP.md              # per-machine setup
├── dcx.py               # the conductor entrypoint
├── dcx/                 # the toolkit (spawn, fanout, wait, worktrees, roles)
├── config.example.json  # portable defaults (real config.json is git-ignored)
└── ...
```

**Want it the moment it drops?** ⭐ **Star / Watch** this repo, or follow [Serah Creates](https://youtube.com/@serahcreates-s7p).

In the meantime, the docs in [`../../docs/`](../../docs/) explain exactly what it does and how you'll set it up.
