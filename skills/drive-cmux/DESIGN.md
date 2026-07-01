# drive-cmux — Design Spec

- **Date:** 2026-06-17
- **Status:** Draft v2 — rewritten after a code-grounded adversarial review (4 critics) + live-binary verification against cmux 0.62.2.
- **Author:** Claude (with Greg)
- **Verified-live foundation:** spawn → resolve → send → read → review → send-back → re-review → close, proven on scratch workspaces 2026-06-17. CLI facts below were re-checked against the installed binary.

## 1. Goal

Give Claude a safe, reusable way to drive Greg's local **cmux** terminal app programmatically so it can orchestrate fleets of coding/review agents — spawn sessions, type into them, read them back, and tear them down — without GUI clicking and **without ever disturbing income-critical live sessions**.

## 2. The vision (the orchestration loop)

1. **Plan** — Claude breaks a hard project into a detailed, sectioned plan.
2. **Review each section** — Claude fires it to a Codex session (high reasoning) for an adversarial review pass.
3. **Refine** — review notes return; Claude tightens the plan; repeat per section.
4. **Fan out the build** — on approval, Claude spawns coding agents (high reasoning), one task each, in isolated workspaces.
5. **Review as they return** — Claude reviews each diff and accepts or sends it back.
6. **Repeat** — until the project is done.

**Honest framing:** the *spawn/send/read/close* mechanics are proven primitives, and as of 2026-06-17 so is **completion detection** — via a push bridge (agent emits a done-signal → a harness background-waiter wakes Claude on exit), since cmux 0.62.2 has no event stream (see §3.5). Steps 4–5 are now built on proven mechanisms, not assumptions.

## 3. Verified CLI ground truth (cmux 0.62.2, installed binary)

This section is the source of truth; everything below depends on it.

### 3.1 Access
- CLI: `/Applications/cmux.app/Contents/Resources/bin/cmux` (NOT on PATH; call by full path, configurable).
- Socket: `~/Library/Application Support/cmux/cmux.sock` (no TCP port). `capabilities` reports `access_mode: password`, protocol v2, 144 methods.

### 3.2 Verbs that EXIST and we use
`tree [--all] [--workspace <ref>] [--json]`, `read-screen [--workspace][--surface][--scrollback][--lines]`, `send [--workspace][--surface] <text>`, `send-key [--workspace][--surface] <key>`, `new-workspace [--cwd][--command]`, `rename-workspace`, `close-workspace`, `capabilities`, `ping`, `set-hook <event> <command>` / `claude-hook <…>` (one-shot callbacks). Non-deprecated forms exist as `workspace create|close|rename`.

### 3.3 Things that DO NOT exist in this build (v1 spec wrongly assumed them)
- **No `events` verb / no event stream.** `cmux events` → "Unknown command". `capabilities` has **0** of 144 methods matching event/subscribe/watch/hook/idle/lifecycle.
- **No `rpc` passthrough verb.** `cmux rpc` → "Unknown command".
- **No `hooks setup`.** Only the one-shot `set-hook`/`claude-hook` callbacks exist.
- **No global `--json`.** It is per-verb: `tree --json` works; `new-workspace --json` errors. Spawn output is the text line `OK workspace:NN` (parse stdout).
- **No UUID handles / no `--id-format`.** `tree --id-format` is rejected. Handles are `ref` (`workspace:N`/`surface:N`) and a volatile `index` only.

### 3.4 `tree --json` shape (mandated for all safety-critical reads)
Each workspace object: `{ ref:"workspace:N", index, title, active, selected, pinned, panes:[…] }`. Each surface object: `{ ref:"surface:N", type:"terminal"|"browser", title, url, pane_ref, index, … }`. **Use `ref` only; never `index`.** Note the top-level `selected_workspace_ref` is index-formatted and unreliable — ignore it.

### 3.5 Completion detection — PROVEN (push via harness bridge, 2026-06-17)
No subscribable lifecycle exists, but we don't need one. Verified end-to-end: the agent emits a **done-signal** as its final step (a sentinel file / FIFO write / unique token — universal, any agent/command). A **harness background-waiter** (`run_in_background`) blocks on that signal and exits; when it exits, the orchestrator's harness **re-invokes Claude automatically** — event-driven wake-up, no polling cadence. One waiter per agent → Claude is woken per-completion. `cmux notify --workspace <ref>` in the same step gives Greg a native popup. Fallbacks: `read-screen` polling; `set-hook` pane-exit for non-interactive (`codex exec`) runs. There is no direct cmux→Claude channel — the bridge realizes "push" by having a process Claude owns wait on cmux's signal, with the harness waking Claude when it exits.

### 3.6 Auth (corrected)
- cmux Settings → Socket Control Mode = **Password mode** (the exact mode; distinct from "automation"/"allowAll"). Only Password mode forces the handshake for external clients.
- The bundled CLI resolves the password: `--password` > `CMUX_SOCKET_PASSWORD` env > a canonical file `~/.local/state/cmux/socket-control-password` > keychain. **On this machine the canonical file does not exist**, so the working source is the operator file `/Users/gregorymaier/General/CMUX/socket-password.txt`, read into `CMUX_SOCKET_PASSWORD` per call (proven). Drift risk: if Greg rotates the password in Settings, that file must be updated too — so dcx runs an **auth preflight (`ping`) that fails loud** if it doesn't authenticate.
- **There is NO "inside-pane = auto-authorized" privilege** (v1 was wrong). Password mode gates every connection equally. In-pane CLI calls "just work" only via password auto-discovery, not a bypass.
- **Never** dump env / log the password. (Note: the password was inadvertently surfaced in a debug transcript on 2026-06-17 — Greg may wish to rotate it; it is a local socket secret.)

## 4. Architecture

- **Location:** user-level `~/.claude/skills/drive-cmux/` (cmux drives all of Greg's projects).
- **`SKILL.md`** — when/how to use the toolkit, safety rules first.
- **`dcx.py`** — Python 3.12 helper wrapping the CLI. Runs every CLI call with `CMUX_QUIET=1` (suppresses legacy-verb deprecation noise on stderr) and parses **`tree --json`** for all resolution/provenance/cleanup. Owns auth, the fence, the run-registry, and (later phases) the loop.
- **`config.json`** — CLI path, password-file path, the **safe-cwd allowlist**, and the denylist (second layer).
- **dcx.py output contract:** every invocation prints **one JSON object** to stdout, e.g. `{"ok":true,"workspace_ref":"workspace:N","surface_ref":"surface:N","sentinel_seen":bool,"error_type":null}` so Claude parses results structurally, never by scraping prose.

## 5. The safety fence (rewritten — fail-closed, allowlist-primary)

The v1 title-denylist was **fail-open** and let writes through to live sessions (`Fan CRM Purchases`, `Gemma Box 2`, `Fan CRM PT 2` matched none of the patterns). Inverted:

### 5.1 Reads — unrestricted
`tree`, `read-screen` run anywhere.

### 5.2 Writes (`send`, `send-key`, `close`) — default DENY
A write is permitted **only if** it targets a workspace/surface in the **in-run registry** (something dcx itself spawned this run). Everything else is "pre-existing" and denied unless it passes §5.4.

### 5.3 Provenance — registry, not title
- Each `spawn` records `{ref, nonce, cwd, command, spawn_ts}` in a per-run registry (in-memory for one orchestration; a `run_id`-keyed file under the skill dir for multi-invocation runs) **and** tags the workspace title with a per-session nonce: `dcx-<8hex>:<run_id>:<taskN>:<slug>`.
- Before **every** write/close: re-read `tree --json`, re-resolve the handle, and require the live title to still carry the recorded nonce **and** the recorded cwd to still match (TOCTOU guard). Title is a human label; the **registry + nonce** is the authorization check. A coincidental real session containing "dcx" cannot match the random nonce.

### 5.4 Writing to a pre-existing pane (explicit, guarded)
Requires ALL of: an explicit `--target <workspace:N|surface:N>` (fully-qualified `ref` — **bare integers/index rejected**, regex `^(workspace|surface):\d+$`); the target's cwd is under the **safe-cwd allowlist** (e.g. `~/developer/unity-erp`, quotes scratch — Greg-confirmed roots); AND it clears the denylist (redundant second layer) evaluated against **the workspace title AND every surface title in its subtree AND surface cwds** (`ppv`, `onlyfans`, `serah`, `vault`, `fan`, `crm`, `purchase`, `gemma`, `chat-app`, `orchestrator`, plus the hard-coded `PPV Terminal` workspace ref). Any match → refuse.

### 5.5 Hard rules
- **Fully-qualified refs only.** Never `index`, never `selected_workspace_ref`, never bare integers, never env-default targeting — every `send`/`send-key`/`close`/`read` carries an explicit resolved `ref` or it is a fail-closed error.
- **Browser hard-block.** Refuse any surface whose `type == "browser"`, and any `browser.*` method, unconditionally, in all phases (the live OnlyFans session is a browser context; a synthesized browser write is the account-killing action the standing OF rail exists to prevent). No raw method passthrough.
- **Fail-closed everywhere.** A write proceeds only if a fresh `tree --json` read succeeded, parsed cleanly, found the target unambiguously, and it passed §5.2–5.4. Socket error, parse error, timeout, target-not-found, or **any ambiguity → DENY** with a typed error.
- **Same fence inside and outside cmux.** Running inside a pane confers no extra trust.
- The standing OnlyFans safety rails apply in full; never drive the live PPV/OnlyFans/CRM/Gemma sessions.

### 5.6 Cleanup
Close by **recorded ref**, but only after re-verifying the live nonce-title + cwd still match (refs reset on cmux app restart — the Mac mini auto-restarts — so never persist a raw ref across a restart; the nonce-title is the tiebreaker). Tag-sweep (by nonce via `tree --json`) is a backup only.

## 6. Phases (re-sequenced by proven-ness and value)

### Phase 1 — toolkit + one sequential loop (build now)
Mechanics (`spawn`/`resolve`/`send`/`read`/`close`) + the §5 fence + §3.6 auth + the dcx.py JSON contract, **plus one end-to-end sequential loop**: drive a single session (send a task → poll `read-screen` for a sentinel → return output → close). This makes Phase 1 independently valuable (it can already run Greg's "review one plan section" loop), not just raw mechanics. Includes the safe-cwd allowlist.

### Phase 2 — plan-review sub-loop
`dcx review-plan <section>`: spawn one Codex session (high reasoning), send the plan section, poll until the sentinel, return notes, close. Single-session, sequential — the proven dry-run shape.

### Phase 3 — build fan-out
`dcx fanout <task-list>`: N parallel agent sessions, **one git worktree per task** (DP-2, default) to avoid write conflicts. Completion via the **proven push bridge** (§3.5): each agent emits a done-signal; one background-waiter per agent wakes Claude as that agent finishes; review-and-send-back per task. The completion mechanism is no longer a risk (proven 2026-06-17) — Phase 3 is now just parallelism + worktree isolation on top of it.

### Phase 4 — watcher
`dcx watch`: read-only status board of all agent sessions via **polling** `tree --json` + `read-screen` (no event stream), flagging idle/needs-input/done by sentinel/heuristic, optional `notify`.

## 7. Testing
- **Unit (must):** the fence — allowlist + denylist matching (against **both** workspace and subtree surface titles + cwds), registry/nonce provenance, fully-qualified-ref validation, browser-type refusal, fail-closed-on-ambiguity. Seed from a **sanitized snapshot of the real `tree --json`**, including adversarial rows: a `Fan CRM`/`Gemma Box` pane the naive denylist would ALLOW (proves the allowlist), an `index` that points at `PPV Terminal`, a real surface whose title contains "dcx", a `browser`-type surface, and malformed/truncated JSON (must DENY).
- **Integration smoke (guarded):** the spawn→send→read→close loop on a scratch workspace, behind an env flag (live cmux + password required).

## 8. Decision points
- **DP-1 (resolved):** `new-workspace --command` types the command + Enter into an interactive shell (good for TUI agents); `spawn` must wait for prompt-readiness before relying, and completion is output-only (no exit code).
- **DP-2:** one git worktree per fan-out agent (default) vs shared cwd.
- **DP-3 (resolved):** safe-cwd **allowlist is the primary write gate**, denylist is the redundant second layer. Greg confirms the allowlisted roots.
- **DP-4 (RESOLVED, proven 2026-06-17):** completion detection = agent done-signal (sentinel/FIFO/token) + a harness background-waiter that wakes the orchestrator on its exit; `cmux notify` for Greg; polling/`set-hook` as fallbacks. No event stream needed.

## 9. Rollback / blast radius
A skill + helper under `~/.claude/` + the existing password file. No daemons, no changes to cmux. Disable by not invoking. Reverting Socket Control Mode to "cmux processes only" instantly cuts all external access. Every write is fail-closed.

## 10. Out of scope (YAGNI)
No protocol reimplementation (ride the CLI). No remote/cloud cmux. No non-cmux apps. **No browser-surface writes ever (enforced in §5.5, not just scope).**

## 11. Safety rails (always)
Never drive live PPV/OnlyFans/CRM/Gemma sessions; OF API rails unchanged. Password never logged; read per-call; auth-preflight fails loud. Writes fail-closed, fully-qualified-ref only, allowlist-gated, browser-blocked, refuse-not-silent. See [[project_cmux_orchestration]], [[feedback_of_api_safety]], [[project_ppv_save_library]].
