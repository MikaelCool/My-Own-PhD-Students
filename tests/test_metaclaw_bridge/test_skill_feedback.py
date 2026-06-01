"""Tests for skill feedback tracking module."""

from pathlib import Path

from researchclaw.metaclaw_bridge.skill_feedback import (
    SkillEffectivenessRecord,
    SkillFeedbackStore,
    record_stage_skills,
)


def test_append_and_load(tmp_path):
    store = SkillFeedbackStore(tmp_path / "feedback.jsonl")
    rec = SkillEffectivenessRecord(
        skill_name="hypothesis-formulation",
        stage_name="hypothesis_gen",
        run_id="test-001",
        stage_success=True,
        timestamp="2026-03-15T00:00:00+00:00",
    )
    store.append(rec)

    loaded = store.load_all()
    assert len(loaded) == 1
    assert loaded[0].skill_name == "hypothesis-formulation"
    assert loaded[0].stage_success is True


def test_append_many(tmp_path):
    store = SkillFeedbackStore(tmp_path / "feedback.jsonl")
    records = [
        SkillEffectivenessRecord("skill-a", "stage-1", "run-1", True, "2026-01-01"),
        SkillEffectivenessRecord("skill-b", "stage-2", "run-1", False, "2026-01-01"),
    ]
    store.append_many(records)
    assert len(store.load_all()) == 2


def test_compute_stats(tmp_path):
    store = SkillFeedbackStore(tmp_path / "feedback.jsonl")
    records = [
        SkillEffectivenessRecord("skill-a", "s1", "r1", True, "t1", wall_time_sec=10.0, quality_gain=0.4, rollback_risk_delta=-0.5, artifact_quality_delta=1.0),
        SkillEffectivenessRecord("skill-a", "s2", "r1", False, "t1", wall_time_sec=20.0, quality_gain=0.0, rollback_risk_delta=0.5, artifact_quality_delta=0.0),
        SkillEffectivenessRecord("skill-a", "s3", "r2", True, "t2", wall_time_sec=30.0, quality_gain=0.8, rollback_risk_delta=-0.5, artifact_quality_delta=1.0),
        SkillEffectivenessRecord("skill-b", "s1", "r1", False, "t1", wall_time_sec=8.0),
    ]
    store.append_many(records)

    stats = store.compute_skill_stats()
    assert stats["skill-a"]["total"] == 3
    assert stats["skill-a"]["successes"] == 2
    assert abs(stats["skill-a"]["success_rate"] - 2 / 3) < 0.01
    assert stats["skill-a"]["avg_wall_time_sec"] == 20.0
    assert abs(stats["skill-a"]["avg_quality_gain"] - 0.4) < 1e-9
    assert abs(stats["skill-a"]["avg_rollback_risk_delta"] + (1 / 6)) < 1e-9
    assert abs(stats["skill-a"]["avg_artifact_quality_delta"] - (2 / 3)) < 1e-9
    assert stats["skill-b"]["total"] == 1
    assert stats["skill-b"]["success_rate"] == 0.0


def test_record_stage_skills(tmp_path):
    store = SkillFeedbackStore(tmp_path / "feedback.jsonl")
    record_stage_skills(
        store,
        stage_name="hypothesis_gen",
        run_id="test-002",
        stage_success=True,
        active_skills=["hypothesis-formulation", "research-gap-identification"],
        wall_time_sec=12.5,
        quality_gain=0.7,
        rollback_risk_delta=-0.5,
        artifact_quality_delta=1.0,
        stage_policy="## Stage Skill Policy\n- Focus: tighten hypothesis quality\n",
    )
    loaded = store.load_all()
    assert len(loaded) == 2
    names = {r.skill_name for r in loaded}
    assert names == {"hypothesis-formulation", "research-gap-identification"}
    assert all(r.wall_time_sec == 12.5 for r in loaded)
    assert all(r.quality_gain == 0.7 for r in loaded)
    assert all(r.rollback_risk_delta == -0.5 for r in loaded)
    assert all(r.artifact_quality_delta == 1.0 for r in loaded)
    assert all("Focus: tighten hypothesis quality" in r.stage_policy for r in loaded)


def test_empty_store(tmp_path):
    store = SkillFeedbackStore(tmp_path / "nonexistent.jsonl")
    assert store.load_all() == []
    assert store.compute_skill_stats() == {}
