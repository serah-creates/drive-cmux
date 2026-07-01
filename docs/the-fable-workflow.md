# 💸 The Fable workflow — how to use a genius model without going broke

**Fable 5 is back** (July 1, 2026) and it's astonishing. It's also metered: through **July 7** you get about **50% of your weekly usage limit**, and after that it moves to a **pay-per-credit** model. So every Fable call is real money or a real slice of a limited budget.

The mistake is to hand Fable *everything*. The move is to hand it **only the things that decide quality.**

---

## The 20 / 80 split

In almost any build, a small slice of the work decides whether the result is good, and the rest is just… doing it.

- **The ~20% that decides quality:** the architecture, the plan, the tricky trade-offs, and the final review. → **This is Fable's job.**
- **The ~80% that's execution:** the research, the boilerplate, the typing, the obvious fixes. → **This is the fleet's job** (Sonnet 5 to research, GPT-5.5 to build).

**One expensive brain. A room full of cheap, capable hands.**

---

## The recipe

1. **Brief the architect (Fable 5 / your best model).** Give it the goal. Ask for a *plan* and a clear breakdown into independent tasks — not code.
2. **Let the researcher (Sonnet 5) dig.** Facts, docs, options, gotchas — cheaply, in parallel with everything else.
3. **Fan out the builders (GPT-5.5).** One task each, at a sensible reasoning effort, in their own worktrees. Several at once.
4. **Bring the architect back for the review.** This is the second place Fable earns its keep — catching the thing the cheap agents missed.
5. **You conduct.** Approve, redirect, merge.

Fable touches the job **twice** — plan and review. Everything in between is cheap. That's the whole saving.

---

## Why this is cheaper (and often *better*)

- You spend your most expensive tokens only where they compound.
- The fleet runs **in parallel**, so more gets done in the same wall-clock time.
- A well-reviewed plan means the cheap builders don't churn — they build the right thing once.
- Two different model families (Claude + GPT) reviewing each other catches more than one model alone.

---

## 🔜 Part 2: the receipts

The launch video builds this with **Opus 4.8** as the architect (because Fable came back later that same day). The follow-up puts **Fable at the podium** and shows the real numbers side by side:

> **Fable doing everything** vs **Fable conducting the fleet.**

Same build, two bills. Follow [Serah Creates](https://youtube.com/@serahcreates-s7p) to see how big the gap is.

---

## The one rule that keeps you safe

Cheap, fast agents are wonderful for building — and **terrible things to trust blindly**. Never let the fleet ship anything that can hurt you unreviewed: auth, database migrations, payments, anything touching secrets or production. See **[safety.md](safety.md)**. The genius reviews; *you* approve.
