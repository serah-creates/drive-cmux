# tests/test_roles.py
import pytest
from dcx.roles import apply_role, apply_tier, effort_for, ROLE_EFFORT, RoleError


def test_effort_for_canonical_roles_match_the_policy():
    assert effort_for("plan-review") == "xhigh"
    assert effort_for("security-review") == "xhigh"
    assert effort_for("adversarial") == "xhigh"
    assert effort_for("code-review") == "high"
    assert effort_for("build") == "medium"        # implementation floor (deliberately not low)
    assert effort_for("mechanical") == "low"


def test_effort_for_is_case_insensitive_and_trims():
    assert effort_for("  Plan-Review ") == "xhigh"


def test_effort_for_unknown_role_raises():
    with pytest.raises(RoleError):
        effort_for("wizard")


def test_apply_role_injects_after_codex_exec():
    cmd = 'codex exec -c sandbox_mode=read-only "$(cat /tmp/x.txt)"'
    new, effort, injected = apply_role(cmd, "plan-review")
    assert injected is True and effort == "xhigh"
    assert new == 'codex exec -c model_reasoning_effort=xhigh -c sandbox_mode=read-only "$(cat /tmp/x.txt)"'


def test_apply_role_injects_after_bare_codex():
    new, effort, injected = apply_role('codex "$(cat /tmp/x.txt)"', "build")
    assert injected and effort == "medium"
    assert new.startswith('codex -c model_reasoning_effort=medium ')


def test_apply_role_explicit_effort_wins_over_preset():
    cmd = 'codex exec -c model_reasoning_effort=xhigh "$(cat /tmp/x.txt)"'
    new, effort, injected = apply_role(cmd, "build")   # preset says medium
    assert injected is False
    assert effort == "xhigh"     # the explicit value is reported, preset does NOT override
    assert new == cmd            # command unchanged


def test_apply_role_non_codex_command_raises():
    with pytest.raises(RoleError):
        apply_role("echo hello", "build")


def test_apply_tier_normal_injects_nothing():
    cmd = 'codex exec -c sandbox_mode=read-only "$(cat /tmp/x.txt)"'
    new, value, injected = apply_tier(cmd, "normal")
    assert injected is False and value == "default" and new == cmd


def test_apply_tier_fast_injects_priority():
    cmd = 'codex exec -c sandbox_mode=read-only "$(cat /tmp/x.txt)"'
    new, value, injected = apply_tier(cmd, "fast")
    assert injected is True and value == "priority"
    assert new == 'codex exec -c service_tier=priority -c sandbox_mode=read-only "$(cat /tmp/x.txt)"'


def test_apply_tier_explicit_service_tier_wins():
    cmd = 'codex exec -c service_tier=flex "$(cat /tmp/x.txt)"'
    new, value, injected = apply_tier(cmd, "fast")
    assert injected is False and value == "flex" and new == cmd


def test_apply_tier_unknown_raises():
    with pytest.raises(RoleError):
        apply_tier("codex exec x", "turbo")
