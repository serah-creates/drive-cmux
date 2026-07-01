---
name: drive-cmux
description: Use when Claude should drive the local cmux app to spawn agent sessions, type into them, read them back, detect completion, and tear them down — for orchestrating coding/review agent fleets (plan-review, build fan-out, watcher). Global skill, usable from any project. macOS + cmux only.
---

# drive-cmux

Drive the local **cmux** app to orchestrate agent fleets. **Reads are unrestricted; writes only ever touch sessions `dcx` spawned itself** (disk registry + per-session nonce, re-verified against a fresh `tree --json` on every write). Never drive live PPV/OnlyFans/CRM/Gemma sessions; browser surfaces are hard-blocked.

## Invocation (works from ANY project directory)
The toolkit lives at `~/.claude/skills/drive-cmux/`. Run it by **absolute path** — it does NOT depend on your current directory (config + state resolve relative to the skill itself). Set this once at the start of each shell command:

```bash
DCX=~/.claude/skills/drive-cmux/dcx.py
python3 "$DCX" preflight        # → {"ok": true}
```

In the examples below, `dcx` means `python3 ~/.claude/skills/drive-cmux/dcx.py`. Every verb prints exactly one JSON object to stdout.

## Prereqs
- cmux Settings → Socket Control Mode = **Password mode**; password in the file named in `config.json` (portable default: `~/.claude/skills/drive-cmux/state/socket-password.txt`, git-ignored).
- `python3 "$DCX" preflight` → `{"ok": true}` confirms the socket is reachable (fails loud otherwise).
- **New machine?** See `SETUP.md` (next to this file) — clone the repo into `~/.claude/skills/drive-cmux/`, enable Password mode, then `dcx set-password` (writes the secret to the configured path with `0600`; `--generate` makes one to paste into cmux), run `preflight`. The skill is portable; no paths are hard-coded to one machine. The user should run `set-password` themselves so the password stays out of the transcript.

## Core verbs
- `dcx tree` — read the fleet.
- `dcx spawn --cwd <dir> --command "<agent cmd>" --task <slug> [--role <preset>] [--fast]` → `{workspace_ref, surface_ref, nonce, signal_fifo}`. The command is auto-wrapped to write the FIFO when it completes. `--role` injects the right `-c model_reasoning_effort=…` for the phase; `--fast` opts this run into the pricier Fast tier (both: see **Codex fleet defaults**).
- `dcx send --ref <surface:N> "<text>"` · `dcx send-key --ref <surface:N> <key>`.
- `dcx read --ref <surface:N> [--scrollback]`.
- `dcx close --ref <workspace:N>`.
- `dcx wait --fifo <path> [--timeout <secs>] [--read-ref <surface>] [--close-ref <workspace>]` — blocks until the agent signals done (the push bridge). **Defaults to a 30-min cap**; on timeout it returns `{"ok": false, "timed_out": true}` and **leaves the pane running** — so you're always woken to `read`/re-`wait`/recover, never hung forever. `--timeout 0` blocks indefinitely. **Auto-close:** pass `--read-ref <surface>` to capture the agent's output into the result and `--close-ref <workspace>` to close its pane once done (reads before closing, so nothing is lost). This is the self-cleaning finish — use it so panes don't pile up. A timeout wake is still non-destructive: nothing is read or closed.

## Orchestration verbs
- `dcx run-session --cwd <dir> --command "<agent cmd>" --task <slug>` — spawn one agent, **block** until done, return captured output, close. This IS the plan-review loop (pass a reviewer command). Run via the harness **run_in_background** so the harness wakes Claude when it returns.
- `dcx fanout --spec <items.json>` — `items.json` = `[{ "cwd": "...", "command": "...", "task_slug": "...", "role": "...", "fast": true }, ...]` (`role` and `fast` optional, per item). Spawns one agent per item; returns `handles` (each with `surface_ref` + `signal_fifo`). Then launch **one `dcx wait --fifo <signal_fifo>` per agent via run_in_background** → Claude is woken per-completion → `read`, review, `close`.
- `dcx watch` — read-only board of every self-spawned session (present / nonce_ok / title).
- `dcx worktree-add --repo <git repo> --slug <task>` — isolated worktree+branch (`dcx/<slug>`) so parallel build agents don't collide; use its `path` as the agent's `--cwd`.

## The push-notification loop
1. `spawn` (or `fanout`); note `surface_ref`, `workspace_ref`, `signal_fifo`.
2. Run `dcx wait --fifo <signal_fifo> --read-ref <surface_ref> --close-ref <workspace_ref>` via **run_in_background**, then END the turn. (The `--read-ref`/`--close-ref` make it self-cleaning: the pane auto-closes and its output comes back in the wake.)
3. The harness wakes Claude when the waiter exits, handing back the captured `output` with the pane already closed → review it. One `wait` per agent → woken per-completion. (Omit `--close-ref` if you want to inspect the live pane first and `close` it yourself.)
   - **If woken with `timed_out: true`:** the agent didn't signal within the cap (still working, stalled, or a TUI that never exits). `read` the surface: if output is still growing, just re-launch the `wait` (run_in_background) and END the turn again; if it's wedged before any output, `close` and re-spawn with `--ignore-user-config`. The pane is never auto-closed on timeout, so nothing is lost.
   - (For an interactive TUI agent that never exits on its own, instruct it in its prompt to run `echo done > <signal_fifo>` as its final step.)

## The full loop (the vision)
1. Claude drafts a plan. 2. Per section: `run-session` with a Codex reviewer at `--role plan-review` → read notes → refine. 3. On approval: `worktree-add` per task → `fanout` the build agents at `--role build` (per-item `"role"` in the spec). 4. One `wait` per agent (run_in_background); review each as it wakes you (a diff-review pass = `--role code-review`); `send` fixes back or `close`. 5. Repeat. `watch` shows the board anytime.

## Codex fleet defaults
- **Service tier: Normal (default).** Fleets run the standard tier — the standing cost default (`~/.codex/config.toml` sets `service_tier = "default"`). The **Fast** (priority) lane is ~2x the cost; it is **opt-in per run via `--fast`** (or `"fast": true` in a fanout item). Only use `--fast` when the user explicitly asks for speed on a specific run; never make it the default.
- **Reasoning effort: pick it by phase via `--role`.** Don't run everything at `xhigh` — that's the main driver of token *volume*. Pass the matching `--role` on every `spawn`/`fanout`/`run-session` so the right `-c model_reasoning_effort=…` is injected automatically. Spend reasoning where it compounds (plans/reviews), run cheap where the vetted plan already did the hard thinking (implementation/mechanical):

  | Phase / `--role` | Effort | When |
  |---|---|---|
  | `plan-review`, `design-review`, `adversarial`, `security-review` | **xhigh** | designing/critiquing plans, adversarial & security passes — a bad plan compounds |
  | `code-review`, `diff-review`, `review` | **high** | reviewing a diff or code for bugs |
  | `build`, `implement` | **medium** | implementing from a vetted plan (deliberate floor — *not* low; avoids review churn) |
  | `mechanical`, `scaffold` | **low** | rename / boilerplate / well-specified data transforms |

  An explicit `-c model_reasoning_effort=…` in the command still wins over `--role`. Run `dcx roles` to print this map. Bump a specific run to `xhigh` only when the task genuinely needs maximum depth.

## Model lanes — Codex (GPT-5.5) + Claude (Sonnet 5 / Opus / Fable)
`--role` is **engine-aware** — the spawn command you pass decides the lane, and the role picks the right knob for it:
- **Codex command** (`codex exec …`) → role injects the **reasoning effort** (`-c model_reasoning_effort=…`), exactly as before. GPT-5.5 is the default builder.
- **Claude command** (`claude -p …`) → role injects the **model** (`--model …`): `architect`/`plan-review`/`design-review`/`security-review`/`adversarial` → **Opus 4.8** (pin `--model claude-fable-5` yourself to ration Fable); `research`/`review`/`code-review`/`build`/… → **Sonnet 5**. An explicit `--model` in the command always wins — that's the Fable swap-in.

The orchestra maps to lanes like this:
- **architect / final review** → `claude -p … --role architect` (Opus 4.8 → Fable)
- **research + first-pass review** → `claude -p … --role research` / `--role review` (Sonnet 5)
- **build, in parallel** → `codex exec … --role build` (GPT-5.5)

`dcx roles` prints both maps. Claude runs in `-p/--print` mode, so the pane **exits when done** and the FIFO completion signal fires just like Codex. Two things to confirm on your **first live pane run**:
- **Write-capable Claude agents must not block on approval prompts** (that would stall the pane and only end on the `wait` timeout). Add an autonomous permission mode (e.g. `--permission-mode acceptEdits`) for build/fix agents; read-only `research`/`review` agents don't need it.
- **Auth:** the pane authenticates with your on-disk Claude login (`~/.claude/.credentials.json`). Two failure modes seen live: (a) if that token is **stale/expired** — a managed Claude Code session can refresh in-memory but not on disk — a fresh `claude -p` pane gets `401 Invalid authentication credentials`; refresh it by running `claude` once interactively, or `claude setup-token` for a long-lived headless token. (b) Don't export a harness `ANTHROPIC_BASE_URL` into the pane. **Preflight the lane** before fanning out: `claude -p "ping"` should print a reply, not a 401.
- `--fast` (priority tier) is **Codex-only** and is ignored on the Claude lane.

## Safety (always)
- Fully-qualified refs only (`workspace:N`/`surface:N`); never a bare integer/index.
- Writes/close are fail-closed: any ambiguity, parse failure, missing registry record, nonce mismatch, or browser surface → refused. The real guarantee is **registry membership + the per-spawn nonce** — dcx only ever touches panes it provably created itself, so the user's pre-existing OnlyFans/CRM/etc. sessions (never in the registry) are always safe.
- **Close is gated by registry+nonce, not the denylist** — dcx may close its own agents even when their cwd/title contains a denylisted word (so they auto-clean), but it can never close a pane it didn't spawn.
- Never modify cmux Settings, never drive a pane you didn't spawn, never touch a `browser` surface.
