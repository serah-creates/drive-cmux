# 🛡️ Safety — the honest version

Agent Orchestra drives real agents that write real code on your machine. That's powerful, so here's exactly what it will and won't do — and where **you** stay responsible.

---

## What the conductor guarantees

- **It only ever writes to or closes panes it opened itself.** Every session it spawns gets a private one-time key, re-checked on every action. No key, no touch.
- **Your other sessions are invisible to it.** Anything you had open before — work chats, dashboards, personal stuff — is never in its registry, so it can never drive or close them.
- **It never touches a browser surface.** Hard-blocked.
- **Reads are open; writes are locked down.** It can look around freely, but any ambiguity, mismatch, or missing record → it refuses rather than guesses.

In short: it's a conductor that can only wave at *its own* musicians, never the audience.

---

## What's still on you

The conductor is safe. The **agents it spawns are as powerful as any coding agent** — they write files in their working folder. So treat them like capable, fast, slightly overconfident juniors:

- ✅ **Use throwaway branches / worktrees** (the toolkit sets these up for you). Build in isolation, merge on purpose.
- ✅ **Review the diffs.** Always. Especially the architect's review pass — but your eyes are the last gate.
- ✅ **Point it at code, not at your life.** Give it a repo, not your whole home folder.

---

## 🚫 What to NEVER orchestrate unreviewed

Some work is too important to hand a cheap, fast agent and merge on trust. For these, slow down, keep a human (and your best model) in the loop, and never auto-merge:

- **Authentication & authorization** — login, sessions, permissions.
- **Database migrations** — schema changes that can't be un-run.
- **Payments & money movement** — billing, transfers, anything financial.
- **Secrets & credentials** — API keys, tokens, `.env` files.
- **Anything in production** — deploys, infra, live data.
- **Deleting or overwriting things you didn't create** — look first.

A tiny game? Perfect. A refactor on a branch you'll review? Great. Anything that can ruin your week? That's a decision, not a delegation.

---

## Reporting something

Building in public means fixing in public. If you find a way the conductor touches something it shouldn't, open an issue — that's exactly the kind of bug we want to hear about first.

> The tool is careful. The models are capable. **You are the conductor** — the final call is always yours.
