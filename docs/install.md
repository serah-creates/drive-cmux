# 🛠️ Install & setup (newcomer-friendly)

This takes about 10 minutes. You don't need to be a developer — just comfortable copy-pasting a couple of commands. macOS only for now.

> ⚡ **Fastest path:** `git clone https://github.com/serah-creates/drive-cmux.git && cd drive-cmux && ./install.sh` — or open Claude Code in the cloned repo and say *"read this repo and set up the drive-cmux skill for me."* The steps below are the manual version.

---

## What you'll need

| Thing | What it's for | Where |
|---|---|---|
| **macOS** | The whole thing runs on Mac | — |
| **cmux app** | The "stage" where the agents perform | [cmux.com](https://cmux.com) |
| **Claude Code** | Runs the conductor + the Claude/Sonnet/Fable lanes | [anthropic.com/claude-code](https://www.anthropic.com/claude-code) |
| **Codex CLI** | Runs the GPT-5.5 builder lane | [openai.com](https://openai.com/) |
| **Python 3.10+** | Runs the little `dcx` conductor tool | any modern `python3` |

You can start with just one lane (e.g. only GPT-5.5, or only Claude) and add the other later. The full orchestra uses both.

---

## Step 1 — Install & sign in

1. Install the **cmux** app and open it once.
2. Install and sign in to **Claude Code** and the **Codex CLI** (whichever lanes you want).
3. Make sure **Python 3.10+** is available: `python3 --version`.

## Step 2 — Turn on cmux socket control

In the cmux app:

1. Open **Settings → Socket Control Mode**.
2. Set it to **Password mode**.

This is what lets the conductor talk to cmux safely. (Password mode means only something holding your local password can drive it.)

## Step 3 — Add the skill

Put this skill where Claude Code looks for global skills:

```bash
git clone https://github.com/serah-creates/drive-cmux.git
# copy the skill into place (path may be finalized in the release):
cp -R drive-cmux/skills/drive-cmux ~/.claude/skills/drive-cmux
```

## Step 4 — Set the password & preflight

Set the cmux socket password (the tool writes it to a local, git-ignored file — it never goes into any chat):

```bash
DCX=~/.claude/skills/drive-cmux/dcx.py
python3 "$DCX" set-password --generate   # prints a password to paste into cmux Settings
python3 "$DCX" preflight                 # → {"ok": true} means you're ready
```

When `preflight` returns `{"ok": true}`, you're set.

---

## Step 5 — Conduct something

From **any** project folder, open Claude Code and say:

> *"Use drive-cmux to spin up a GPT-5.5 agent that adds a README to this project, and ping me when it's done."*

You'll see a pane open in cmux, do the work, and report back. Congratulations — you just conducted your first (very small) orchestra. 🎻

---

## Troubleshooting

- **`preflight` isn't `ok`** → cmux isn't in Password mode, or the password in cmux doesn't match the one you set. Redo Steps 2 & 4.
- **An agent never finishes** → it may be a task that waits for input. Give it a clearer, self-contained instruction, or step in via the pane.
- **Wrong model ran** → check the `--role` / `--engine` you passed; see [how-it-works.md](how-it-works.md).

Stuck? Open an issue on the repo — building in public means we fix these together.
