# drive-cmux — setup on a new machine

`drive-cmux` is a **global Claude Code skill**. Installed once into `~/.claude/skills/drive-cmux/`,
it's available from every project on that machine. The repo is portable; the only per-machine work
is the local prerequisites below (cmux + a socket password + Python). macOS + cmux only.

> **Fastest path:** clone the repo (step 2), then paste the prompt at the bottom of this file into
> Claude Code and let it walk through the rest with you.

---

## 1. Prerequisites (install once per machine)

| Need | Check | Install |
|------|-------|---------|
| **cmux** desktop app | `ls /Applications/cmux.app` | Install cmux normally into `/Applications`. |
| **Python 3.10+** | `python3 --version` | any modern `python3` |
| **Codex CLI** *(only for Codex/GPT-5.5 fleets)* | `codex --version` | Install per your Codex setup, then create `~/.codex/config.toml` (see step 6). |

## 2. Get the skill onto the machine

```bash
git clone https://github.com/serah-creates/drive-cmux.git
cd drive-cmux && ./install.sh   # copies skills/drive-cmux into ~/.claude/skills/
```

Later, to pull updates (e.g. the wait-timeout fix) on any machine:

```bash
git -C ~/.claude/skills/drive-cmux pull
```

## 3. Turn on cmux socket control

In cmux: **Settings → Socket Control Mode → Password mode**. Pick/copy the password it shows.
(`drive-cmux` only talks to cmux through this password-protected socket — it never touches Settings.)

## 4. Store the socket password (one command)

Use the built-in helper — it writes the secret to the **configured** path (so it always lands exactly
where `preflight` looks), with `0600` perms, and creates the dir for you. Pick the flow that matches
how cmux gave you the password:

**A — cmux showed you a password (copy it from Settings):** run this in your own terminal and paste
when prompted (hidden, never echoed). It runs `preflight` right after:

```bash
python3 ~/.claude/skills/drive-cmux/dcx.py set-password
# → {"ok": true, "preflight_ok": true}   ← fully set up
```

**B — you'd rather set your own password:** let dcx generate a strong one, then paste it into cmux:

```bash
python3 ~/.claude/skills/drive-cmux/dcx.py set-password --generate
# copy the printed "password" into cmux Settings → Socket Control Mode → Password, then:
python3 ~/.claude/skills/drive-cmux/dcx.py preflight
```

> Run `set-password` **in your terminal, not via Claude** — that keeps the password out of any chat
> transcript. The file it writes is **machine-local and git-ignored**; it is never committed or synced.
> (Manual fallback / automation: `… set-password --from-stdin` reads the password from a pipe, or just
> write it into `state/socket-password.txt` yourself.)

## 5. Verify

```bash
python3 ~/.claude/skills/drive-cmux/dcx.py preflight    # → {"ok": true}
```

`{"ok": true}` means the socket is reachable and you're done. If it errors, see **Troubleshooting**.

## 6. (Optional) Codex defaults for the agent fleets

The fleets run `codex exec`. To match the standing setup, create `~/.codex/config.toml`:

```toml
model = "gpt-5.5"
model_reasoning_effort = "xhigh"
service_tier = "default"
```

**Tier default = Normal.** The fleets run on the standard (`default`) service tier — which the
`config.toml` above already sets, so **no per-command override is needed**. Add `-c service_tier=priority`
to a single command only when you explicitly want the faster, pricier **Fast** lane for that run.

## 7. (Optional) Override the portable defaults

You usually need **no** `config.json` — `dcx/config.py` ships portable defaults (password file under
`state/`, standard `/Applications` cmux path, the safety denylist). To override on a machine:

```bash
cp ~/.claude/skills/drive-cmux/config.example.json ~/.claude/skills/drive-cmux/config.json
# then edit cli_path / password_file / denylist_patterns as needed
```

`config.json` is git-ignored, so each machine keeps its own.

---

## Troubleshooting `preflight`

| Symptom | Fix |
|---------|-----|
| `{"ok": false, "error_type": "CmuxError", ...}` mentioning the binary | cmux not at `/Applications/cmux.app/...`; set `cli_path` in a local `config.json`. |
| Error opening the password file | File missing or at the wrong path — redo step 4 (or point `password_file` at it in `config.json`). |
| Connects but rejects | Password in the file doesn't match cmux Settings → re-copy it (step 3–4). |
| `python3: command not found` | any modern `python3`. |

After fixing, re-run step 5.

---

## Paste-into-Claude-Code setup prompt

> Set up the **drive-cmux** skill on this machine. Read `~/.claude/skills/drive-cmux/SETUP.md` and walk
> me through it: confirm cmux, `python3`, and (if I want the Codex fleets) the `codex` CLI are
> present; remind me to switch cmux to **Password mode**. For the password, **don't ask me to type it
> to you** — tell me to run `python3 ~/.claude/skills/drive-cmux/dcx.py set-password` myself in my
> terminal so it never lands in this transcript. Then run `dcx preflight` and confirm `{"ok": true}`.
> Don't change any cmux Settings yourself — just guide me. Stop and show me the `preflight` output.
