# 🎻 How it works — the orchestra

drive-cmux doesn't run any AI itself. It's a **conductor**. It tells the [cmux](https://cmux.dev) app to open agent sessions, hands each one a task and the right model, and then waits to be told when they're done. You watch it all happen in real panes on your screen.

Here's the whole idea in four movements.

---

## 1. The players (roles → models)

Not every task deserves your most expensive model. The trick is matching the model to the job:

| Role | Model lane | Why |
|---|---|---|
| **Architect / Reviewer** | Opus 4.8 → **Fable 5** | The plan and the final review are where quality is decided. Spend your genius here. |
| **Researcher** | **Sonnet 5** | Reading, gathering, fact-checking. Very capable, much cheaper than the top tier. |
| **Builder** | **GPT-5.5** (via Codex) | Turning a good plan into working code. The workhorse — and you run several at once. |

You pick the lane with a simple `--role` (or `--engine` + `--model`). A good plan does the hard thinking once, so the builders can run at a lower, cheaper reasoning effort without churning.

> 💡 **The rule of thumb:** spend reasoning where it *compounds* (plans and reviews). Run cheap where the plan already did the thinking (implementation).

---

## 2. The score (the loop)

1. **Claude Code drafts a plan.** You're the conductor — you approve it.
2. **Optional: send the plan to a reviewer** (an architect-lane agent) and refine it. A bad plan multiplies into a lot of bad code, so this cheap step pays for itself.
3. **Fan out the builders.** One agent per task, each in its own pane, all at once.
4. **Get pinged as each finishes**, read its work, and either send a fix back or close the pane.
5. **The architect reviews and integrates.** Repeat until it's good.

That's the "one genius directing many hands" pattern, made literal on your screen.

---

## 3. Staying out of each other's way (worktrees)

When several builders touch the same repo at once, they'd trip over each other. So drive-cmux can give each one its **own git worktree + branch** (`dcx/<task>`). They build in isolation, and you merge the good ones. No collisions, no half-finished files stepping on each other.

---

## 4. Knowing when they're done (the ping)

You don't want to babysit panes. When an agent is launched, its command is wrapped so that **the moment it finishes, it fires a signal**. Claude Code is woken up, reads that agent's output, and (if you asked it to) **closes the pane automatically** — so the work comes back to you and the desk stays clean.

If an agent takes too long, you're woken with a "still working" note instead of hanging forever — nothing is ever lost, and you decide whether to wait more or step in.

---

## In one sentence

> **You approve a plan; a fleet of right-sized models builds it in parallel; you get pinged as each part lands; your best model reviews the whole; you conduct.**

Next: the money playbook — **[the-fable-workflow.md](the-fable-workflow.md)** — for *when* to spend your expensive model vs. the cheap fleet.
