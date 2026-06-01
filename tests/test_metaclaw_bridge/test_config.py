"""Tests for MetaClaw bridge configuration parsing."""

from researchclaw.config import RCConfig


def _minimal_config_data(**overrides):
    """Return minimal valid config data with metaclaw_bridge overrides."""
    base = {
        "project": {"name": "test", "mode": "full-auto"},
        "research": {"topic": "test topic", "domains": ["ml"]},
        "runtime": {"timezone": "UTC"},
        "notifications": {"channel": "console"},
        "knowledge_base": {"backend": "markdown", "root": "docs/kb"},
        "llm": {
            "provider": "openai-compatible",
            "base_url": "http://localhost:8080",
            "api_key_env": "TEST_KEY",
            "api_key": "sk-test",
            "primary_model": "gpt-4o",
        },
    }
    base.update(overrides)
    return base


def test_metaclaw_bridge_defaults():
    """MetaClaw bridge should have sensible defaults when not configured."""
    data = _minimal_config_data()
    cfg = RCConfig.from_dict(data, check_paths=False)
    assert cfg.metaclaw_bridge.enabled is False
    assert cfg.metaclaw_bridge.proxy_url == "http://localhost:30000"
    assert cfg.metaclaw_bridge.prm.enabled is False
    assert cfg.metaclaw_bridge.lesson_to_skill.enabled is True
    assert cfg.metaclaw_bridge.skill_evolution.enabled is True


def test_metaclaw_bridge_enabled():
    """MetaClaw bridge config should be parsed when provided."""
    data = _minimal_config_data(
        metaclaw_bridge={
            "enabled": True,
            "proxy_url": "http://localhost:31000",
            "skills_dir": "/tmp/skills",
            "prm": {
                "enabled": True,
                "api_base": "http://localhost:8080",
                "api_key": "test-key",
                "model": "gpt-5.4",
                "votes": 5,
                "gate_stages": [5, 20],
            },
            "lesson_to_skill": {
                "enabled": True,
                "min_severity": "warning",
                "max_skills_per_run": 5,
            },
            "skill_evolution": {
                "enabled": True,
                "max_candidates_per_run": 4,
                "max_trial_skills": 2,
                "min_trial_records": 3,
                "promote_success_rate": 0.7,
                "reject_success_rate": 0.25,
            },
        }
    )
    cfg = RCConfig.from_dict(data, check_paths=False)
    assert cfg.metaclaw_bridge.enabled is True
    assert cfg.metaclaw_bridge.proxy_url == "http://localhost:31000"
    assert cfg.metaclaw_bridge.prm.enabled is True
    assert cfg.metaclaw_bridge.prm.votes == 5
    assert cfg.metaclaw_bridge.prm.gate_stages == (5, 20)
    assert cfg.metaclaw_bridge.lesson_to_skill.min_severity == "warning"
    assert cfg.metaclaw_bridge.lesson_to_skill.max_skills_per_run == 5
    assert cfg.metaclaw_bridge.skill_evolution.max_candidates_per_run == 4
    assert cfg.metaclaw_bridge.skill_evolution.max_trial_skills == 2
    assert cfg.metaclaw_bridge.skill_evolution.min_trial_records == 3
    assert cfg.metaclaw_bridge.skill_evolution.promote_success_rate == 0.7
    assert cfg.metaclaw_bridge.skill_evolution.reject_success_rate == 0.25


def test_metaclaw_bridge_none_is_default():
    """When metaclaw_bridge is None/missing, defaults should apply."""
    data = _minimal_config_data(metaclaw_bridge=None)
    cfg = RCConfig.from_dict(data, check_paths=False)
    assert cfg.metaclaw_bridge.enabled is False
