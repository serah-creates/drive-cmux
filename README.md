# 🎻 drive-cmux

> **Build _with_ AI, not against it — a whole orchestra of it.**

One genius model writes the plan. A fleet of cheaper models does the work. **You conduct** — from your terminal.

Powered by the **`/drive-cmux`** skill for [Claude Code](https://www.anthropic.com/claude-code), driving the local [**cmux**](https://cmux.com) app. macOS.

> 🎉 **The skill is here.** `skills/drive-cmux/` is the full conductor — see **[docs/install.md](docs/install.md)** to set it up in ~10 minutes. ⭐ Star it if it saves you a few Fable credits.

---

## Why this exists (the 30-second version)

The smartest AI models are incredible — and **expensive**. When Anthropic's **Fable 5** came back on **July 1, 2026**, it came with a catch: you get about **50% of your weekly limit**, then you're **paying per credit**. Genius, but metered.

So here's the trick the pros use: **you don't let the genius type boilerplate.**

You use the expensive, brilliant model as the **architect** — it writes the plan and does the final review (the ~20% of the work that actually decides if the thing is good). Then you hand the other **80% — the research and the typing — to a fleet of cheaper, faster models running in parallel.**

**One expensive brain. A room full of cheap, capable hands.** That's how you afford genius.

drive-cmux is the little conductor's baton that makes that easy.

---

## What it actually is

A tiny command-line toolkit (`dcx`) that lets **Claude Code** drive the **cmux** app to:

- 🎬 **spawn** a fleet of AI coding agents, each in its own pane,
- 🎚️ give each one the **right model for the job** — GPT-5.5 for building, **Sonnet 5** for research, your best model (Opus 4.8 / **Fable 5**) as the architect,
- 📨 get **pinged the moment each one finishes**, read its work, and
- 🧹 clean up after itself.

You stay the conductor. The agents play their parts. Nothing runs that you didn't start, and it never touches a session it didn't open itself.

---

## 🎥 See it in action

This repo is the companion to the Serah Creates launch video:

> **"One Genius, a Room Full of Interns — how to use Fable 5 without going broke"**
> *(link goes here when it's live — follow below so you don't miss it)*

In it, three agents build a neon arcade game **at the same time**, an architect model reviews it, and we play the result. The game — **Neon Maestro** — will be linked here too.

---

## 🚀 Quick start

**Two commands:**
```bash
git clone https://github.com/serah-creates/drive-cmux.git
cd drive-cmux && ./install.sh
```
`install.sh` copies the skill into `~/.claude/skills/` and prints the last one-time steps (cmux Password mode, `set-password`, model auth).

**Or just let Claude Code do it** — clone the repo, open Claude Code inside it, and say:
> *"Read this repo and set up the drive-cmux skill for me."*

Full walkthrough + troubleshooting: **[docs/install.md](docs/install.md)**. (Needs **Python 3.10+** — no specific version.)

Then, from any project, just tell Claude Code: *"use drive-cmux to…"* and start conducting.

---

## 🎻 How it works — the orchestra

| Role in the orchestra | Model (lane) | What it's for |
|---|---|---|
| **Architect / Reviewer** | Opus 4.8 → **Fable 5** | Writes the plan, makes the final call. The expensive genius. |
| **Researcher** | **Sonnet 5** | Reads, gathers, and checks facts. Sharp and cheaper. |
| **Builder** | **GPT-5.5** (Codex) | The workhorse — turns the vetted plan into working code, in parallel. |

The full picture — the plan → fan-out → review loop, how parallel agents stay out of each other's way (git worktrees), and how completion pings work — is in **[docs/how-it-works.md](docs/how-it-works.md)**.

The money playbook — *when* to spend your precious Fable credits vs. the cheap fleet — is in **[docs/the-fable-workflow.md](docs/the-fable-workflow.md)**.

---

## 🛡️ Is it safe?

Short answer: it only ever writes to or closes the panes **it opened itself** (verified by a per-session key every single time). It reads freely, but it will **never** drive your other sessions or any browser. The agents it spawns *do* write code in their own working folders — so you use throwaway branches and review the diffs, just like you'd review a junior dev.

The honest, full version — including **what you should never let a cheap agent touch** — is in **[docs/safety.md](docs/safety.md)**. Please read it.

---

## 📦 What's in this repo

```
drive-cmux/
├── README.md              ← you are here
├── docs/
│   ├── install.md         # step-by-step setup for newcomers
│   ├── how-it-works.md     # the orchestra: roles, loop, parallelism
│   ├── the-fable-workflow.md  # the money playbook (architect + fleet)
│   └── safety.md          # what it can/can't touch — and what NOT to orchestrate
├── skills/
│   └── drive-cmux/         # ✅ the skill (dcx.py, SKILL.md, docs, tests)
└── examples/
    └── neon-maestro/       # ✅ the playable demo the fleet built — open index.html
```

---

## ✅ Requirements

- **macOS** + the **cmux** app.
- **Claude Code** (for the architect + research lanes).
- **Codex CLI** (for the GPT-5.5 builder lane).
- **Python 3.10+**.

(You can run just the GPT lane, or just the Claude lanes — but the magic is using them together.)

---

## 👋 Built by Serah Creates

*Build **with** AI, not against it.* An open workshop — 3D printing, electronics, woodworking, and AI woven through all of it, built in public.

- ▶️ YouTube — [@serahcreates-s7p](https://youtube.com/@serahcreates-s7p)
- 📸 Instagram — [@serah_creates](https://www.instagram.com/serah_creates)
- 🎵 TikTok — [@serah.creates](https://www.tiktok.com/@serah.creates)

---

## 📄 License

Code: **[MIT](LICENSE)** — use it, remix it, build with it. A credit to *Serah Creates* is always appreciated.

*drive-cmux stands on the shoulders of [cmux](https://cmux.com), [Claude Code](https://www.anthropic.com/claude-code), and the [Codex CLI](https://openai.com/). Model names belong to their makers.*
