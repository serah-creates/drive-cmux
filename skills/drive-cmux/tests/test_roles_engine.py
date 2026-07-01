# tests/test_roles_engine.py
# The Claude lane: a role can now run on the `claude` CLI (Sonnet 5 / Opus / Fable),
# not just `codex`. roles.py must detect the engine and pick the right --model.
import pytest
from dcx.roles import detect_engine, model_for, apply_model, RoleError


# --- detect_engine: which CLI is this command? ---
def test_detect_engine_codex():
    assert detect_engine('codex exec "$(cat /tmp/p.txt)"') == "codex"


def test_detect_engine_claude():
    assert detect_engine('claude -p --output-format text "$(cat /tmp/p.txt)"') == "claude"


def test_detect_engine_claude_with_abs_path():
    assert detect_engine('/Users/x/.local/bin/claude -p "hi"') == "claude"


def test_detect_engine_prefers_codex_when_prompt_mentions_claude():
    # a codex command whose PROMPT happens to mention "claude" must still be codex
    assert detect_engine('codex exec "compare gpt vs claude"') == "codex"


def test_detect_engine_unknown_raises():
    with pytest.raises(RoleError):
        detect_engine("echo hello")


# --- model_for: role -> Claude model (genius tier vs workhorse tier) ---
def test_model_for_genius_roles_use_opus():
    assert model_for("architect") == "claude-opus-4-8"
    assert model_for("plan-review") == "claude-opus-4-8"
    assert model_for("security-review") == "claude-opus-4-8"


def test_model_for_workhorse_roles_use_sonnet():
    assert model_for("research") == "claude-sonnet-5"
    assert model_for("code-review") == "claude-sonnet-5"
    assert model_for("review") == "claude-sonnet-5"


def test_model_for_is_case_insensitive_and_trims():
    assert model_for("  Architect ") == "claude-opus-4-8"


def test_model_for_unknown_role_raises():
    with pytest.raises(RoleError):
        model_for("wizard")


# --- apply_model: inject --model into a claude command for its role ---
def test_apply_model_injects_after_claude():
    new, model, injected = apply_model('claude -p "$(cat /tmp/p.txt)"', "research")
    assert injected is True and model == "claude-sonnet-5"
    assert new == 'claude --model claude-sonnet-5 -p "$(cat /tmp/p.txt)"'


def test_apply_model_architect_gets_opus():
    new, model, injected = apply_model('claude -p "plan this"', "architect")
    assert injected and model == "claude-opus-4-8"
    assert "--model claude-opus-4-8" in new


def test_apply_model_explicit_model_wins_over_preset():
    # This is exactly the Fable swap-in: pin --model claude-fable-5 and it wins.
    cmd = 'claude --model claude-fable-5 -p "$(cat /tmp/p.txt)"'
    new, model, injected = apply_model(cmd, "research")   # preset would be sonnet
    assert injected is False
    assert model == "claude-fable-5"     # explicit value reported, preset does NOT override
    assert new == cmd                    # command unchanged


def test_apply_model_non_claude_command_raises():
    with pytest.raises(RoleError):
        apply_model('codex exec "hi"', "research")
