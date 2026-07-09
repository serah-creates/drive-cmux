# dcx/roles.py
"""Map a fleet *role* (the kind of work an agent does) to a Codex reasoning
effort, and inject it into the agent command. This is the "agent picks a skill
level" policy: spend reasoning where it compounds (planning / review) and run
cheap where the plan already did the hard thinking (implementation / mechanical).

Effort-by-phase (see SKILL.md):
  plan/design review, adversarial, security   -> xhigh
  code / diff review                          -> high
  implementation from a vetted plan           -> medium   (floor; deliberately NOT low)
  mechanical (scaffold, boilerplate, rename)  -> low

An explicit `-c model_reasoning_effort=...` already in the command always WINS
over the preset (explicit beats preset); the role only fills in when unset.
"""
import re


class RoleError(RuntimeError):
    pass


# canonical roles + sensible aliases -> reasoning effort (Codex lane)
ROLE_EFFORT = {
    "plan-review":     "xhigh",
    "design-review":   "xhigh",
    "adversarial":     "xhigh",
    "security-review": "xhigh",
    "architect":       "xhigh",
    "code-review":     "high",
    "diff-review":     "high",
    "review":          "high",
    "research":        "high",
    "build":           "medium",
    "implement":       "medium",
    "mechanical":      "low",
    "scaffold":        "low",
}

# Codex model tier per role (GPT-5.6 family; gpt-5.5 is retired). Match the model
# tier to task value, not just the effort — model tier is the bigger cost lever:
#   sol   ($5/$30)   flagship  -> high-value judgment: plans, adversarial/security
#   terra ($2.50/$15) all-rounder -> everyday strong reasoning: reviews, builds
#   luna  ($1/$6)    high-volume -> well-specified mechanical work
ROLE_CODEX_MODEL = {
    "plan-review":     "gpt-5.6-sol",
    "design-review":   "gpt-5.6-sol",
    "adversarial":     "gpt-5.6-sol",
    "security-review": "gpt-5.6-sol",
    "architect":       "gpt-5.6-sol",
    "code-review":     "gpt-5.6-terra",
    "diff-review":     "gpt-5.6-terra",
    "review":          "gpt-5.6-terra",
    "research":        "gpt-5.6-terra",
    "build":           "gpt-5.6-terra",
    "implement":       "gpt-5.6-terra",
    "mechanical":      "gpt-5.6-luna",
    "scaffold":        "gpt-5.6-luna",
}

# The Claude lane: the same roles -> a Claude model. Spend the "genius" tier
# (Opus 4.8; pin claude-fable-5 to ration Fable) where reasoning compounds
# (plans, deep reviews); use the cheap "workhorse" (Sonnet 5) for research and
# routine review. Builds normally go to the Codex lane, but a build role run on
# `claude` falls back to the workhorse.
_GENIUS_MODEL = "claude-opus-4-8"      # architect / deep-reasoning tier (swap in claude-fable-5)
_WORKHORSE_MODEL = "claude-sonnet-5"   # cheap Claude: research + routine review
ROLE_MODEL = {
    "plan-review":     _GENIUS_MODEL,
    "design-review":   _GENIUS_MODEL,
    "adversarial":     _GENIUS_MODEL,
    "security-review": _GENIUS_MODEL,
    "architect":       _GENIUS_MODEL,
    "code-review":     _WORKHORSE_MODEL,
    "diff-review":     _WORKHORSE_MODEL,
    "review":          _WORKHORSE_MODEL,
    "research":        _WORKHORSE_MODEL,
    "build":           _WORKHORSE_MODEL,
    "implement":       _WORKHORSE_MODEL,
    "mechanical":      _WORKHORSE_MODEL,
    "scaffold":        _WORKHORSE_MODEL,
}

# Service tier ("speed"): Normal is the standing default (config.toml). Fast is
# the priority lane — faster but ~2x the cost — opt-in per run via `--fast`.
TIER_VALUE = {"normal": "default", "fast": "priority"}

_CODEX_RE = re.compile(r"\bcodex(?:\s+exec)?\b")
_CLAUDE_RE = re.compile(r"\bclaude\b")
_EFFORT_RE = re.compile(r"model_reasoning_effort\s*=\s*([A-Za-z]+)")
_TIER_RE = re.compile(r"service_tier\s*=\s*([A-Za-z]+)")
_MODEL_RE = re.compile(r"--model[=\s]+(\S+)")
# Codex accepts either `-m <model>` or `--model <model>`; require a word boundary
# so it can't match `-m` inside another token (e.g. `-c model_reasoning_effort=`).
_CODEX_MODEL_RE = re.compile(r"(?<!\S)(?:-m|--model)[=\s]+(\S+)")


def effort_for(role):
    key = (role or "").strip().lower()
    if key not in ROLE_EFFORT:
        valid = ", ".join(sorted(ROLE_EFFORT))
        raise RoleError(f"unknown role {role!r}; valid roles: {valid}")
    return ROLE_EFFORT[key]


def codex_model_for(role):
    key = (role or "").strip().lower()
    if key not in ROLE_CODEX_MODEL:
        valid = ", ".join(sorted(ROLE_CODEX_MODEL))
        raise RoleError(f"unknown role {role!r}; valid roles: {valid}")
    return ROLE_CODEX_MODEL[key]


def model_for(role):
    key = (role or "").strip().lower()
    if key not in ROLE_MODEL:
        valid = ", ".join(sorted(ROLE_MODEL))
        raise RoleError(f"unknown role {role!r}; valid roles: {valid}")
    return ROLE_MODEL[key]


def detect_engine(command):
    """Return 'codex' or 'claude' for a spawn command. Codex is checked first so
    a codex command that merely mentions 'claude' in its prompt is still codex."""
    if _CODEX_RE.search(command):
        return "codex"
    if _CLAUDE_RE.search(command):
        return "claude"
    raise RoleError("could not detect engine: no `codex` or `claude` token in --command")


def _splice_after_codex(command, fragment):
    m = _CODEX_RE.search(command)
    if not m:
        raise RoleError("expected a codex command (no `codex` token found in --command)")
    idx = m.end()
    return command[:idx] + fragment + command[idx:]


def apply_role(command, role):
    """Return (new_command, effort, injected).

    If the command already sets model_reasoning_effort, leave it untouched and
    report that explicit value (injected=False). Otherwise splice
    `-c model_reasoning_effort=<effort>` right after the `codex`/`codex exec`
    token and report the preset value (injected=True)."""
    preset = effort_for(role)
    existing = _EFFORT_RE.search(command)
    if existing:
        return command, existing.group(1), False
    return _splice_after_codex(command, f" -c model_reasoning_effort={preset}"), preset, True


def apply_codex_model(command, role):
    """Return (new_command, model, injected) for the Codex lane.

    Inject `-m <gpt-5.6 variant>` for the role (sol/terra/luna) unless the command
    already pins a model with `-m`/`--model`, in which case that explicit model
    wins and is reported (injected=False)."""
    preset = codex_model_for(role)
    existing = _CODEX_MODEL_RE.search(command)
    if existing:
        return command, existing.group(1), False
    return _splice_after_codex(command, f" -m {preset}"), preset, True


def _splice_after_claude(command, fragment):
    m = _CLAUDE_RE.search(command)
    if not m:
        raise RoleError("expected a claude command (no `claude` token found in --command)")
    idx = m.end()
    return command[:idx] + fragment + command[idx:]


def apply_model(command, role):
    """Return (new_command, model, injected) for the Claude lane.

    If the command already sets `--model`, leave it untouched and report that
    explicit model (injected=False) — this is how you pin `--model claude-fable-5`
    to ration Fable. Otherwise splice `--model <preset>` right after the `claude`
    token and report the preset model (injected=True)."""
    preset = model_for(role)
    existing = _MODEL_RE.search(command)
    if existing:
        return command, existing.group(1), False
    return _splice_after_claude(command, f" --model {preset}"), preset, True


def apply_tier(command, tier):
    """Return (new_command, service_tier_value, injected).

    `normal` is the config.toml default, so nothing is injected (injected=False).
    `fast` splices `-c service_tier=priority`. An explicit service_tier already in
    the command always wins."""
    key = (tier or "").strip().lower()
    if key not in TIER_VALUE:
        raise RoleError(f"unknown tier {tier!r}; valid: {', '.join(sorted(TIER_VALUE))}")
    value = TIER_VALUE[key]
    existing = _TIER_RE.search(command)
    if existing:
        return command, existing.group(1), False
    if key == "normal":
        return command, value, False
    return _splice_after_codex(command, f" -c service_tier={value}"), value, True
