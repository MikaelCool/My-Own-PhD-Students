"""Tests for the controlled skill evolution loop."""

from __future__ import annotations

import json
from pathlib import Path

from researchclaw.evolution import LessonEntry
from researchclaw.metaclaw_bridge.skill_evolution import SkillEvolutionManager
from researchclaw.metaclaw_bridge.skill_feedback import (
    SkillEffectivenessRecord,
    SkillFeedbackStore,
)


def _lesson(
    *,
    stage_name: str = "experiment_run",
    stage_num: int = 12,
    category: str = "experiment",
    severity: str = "error",
    description: str = "Runtime timeout while collecting GPU metrics",
) -> LessonEntry:
    return LessonEntry(
        stage_name=stage_name,
        stage_num=stage_num,
        category=category,
        severity=severity,
        description=description,
        timestamp="2026-04-20T00:00:00+00:00",
        run_id="run-001",
    )


def test_create_candidate_skills_writes_sandbox_skill_and_state(tmp_path: Path) -> None:
    manager = SkillEvolutionManager(tmp_path / "skills")

    created = manager.create_candidate_skills(
        [_lesson(), _lesson(description="Runtime timeout while syncing dataset shards")],
        max_candidates=2,
    )

    assert len(created) == 1
    candidate = created[0]
    skill_path = manager.candidates_dir / candidate.name / "SKILL.md"
    state_path = manager.candidates_dir / candidate.name / "candidate_state.json"
    assert skill_path.exists()
    assert state_path.exists()
    content = skill_path.read_text(encoding="utf-8")
    assert "candidate-status: candidate" in content
    assert "trigger-keywords" in content
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["status"] == "candidate"
    assert state["stage_name"] == "experiment_run"


def test_schedule_trials_copies_candidate_into_trial_sandbox(tmp_path: Path) -> None:
    manager = SkillEvolutionManager(tmp_path / "skills")
    created = manager.create_candidate_skills([_lesson()], max_candidates=1)

    scheduled = manager.schedule_trials(max_trial_skills=1)

    assert scheduled == [created[0].name]
    trial_skill = manager.trials_dir / created[0].name / "SKILL.md"
    assert trial_skill.exists()
    assert "candidate-status: trial" in trial_skill.read_text(encoding="utf-8")
    state = manager.load_candidate_states()[created[0].name]
    assert state.status == "trial"
    assert state.activated_at


def test_evaluate_trials_promotes_successful_trial_skill(tmp_path: Path) -> None:
    manager = SkillEvolutionManager(tmp_path / "skills")
    created = manager.create_candidate_skills([_lesson()], max_candidates=1)
    manager.schedule_trials(max_trial_skills=1)
    candidate_name = created[0].name

    store = SkillFeedbackStore(tmp_path / "feedback.jsonl")
    store.append_many(
        [
            SkillEffectivenessRecord(
                skill_name=candidate_name,
                stage_name="experiment_run",
                run_id="run-a",
                stage_success=True,
                timestamp="2026-04-20T00:00:00+00:00",
                quality_gain=0.5,
                rollback_risk_delta=-0.5,
            ),
            SkillEffectivenessRecord(
                skill_name=candidate_name,
                stage_name="experiment_run",
                run_id="run-b",
                stage_success=True,
                timestamp="2026-04-21T00:00:00+00:00",
                quality_gain=0.4,
                rollback_risk_delta=-0.5,
            ),
        ]
    )

    decisions = manager.evaluate_trials(
        store,
        min_trial_records=2,
        promote_success_rate=0.6,
        reject_success_rate=0.2,
    )

    assert decisions["promoted"] == [candidate_name]
    assert (manager.skills_dir / candidate_name / "SKILL.md").exists()
    assert not (manager.trials_dir / candidate_name).exists()
    state = manager.load_candidate_states()[candidate_name]
    assert state.status == "promoted"


def test_evaluate_existing_skills_demotes_low_value_skill(tmp_path: Path) -> None:
    manager = SkillEvolutionManager(tmp_path / "skills")
    prod_skill_dir = manager.skills_dir / "arc-low-value-skill"
    prod_skill_dir.mkdir(parents=True)
    (prod_skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: arc-low-value-skill\n"
        "description: test skill\n"
        "metadata:\n"
        "  category: tooling\n"
        "  priority: \"4\"\n"
        "---\n\n"
        "Body\n",
        encoding="utf-8",
    )
    store = SkillFeedbackStore(tmp_path / "feedback.jsonl")
    store.append_many(
        [
            SkillEffectivenessRecord(
                skill_name="arc-low-value-skill",
                stage_name="code_generation",
                run_id="run-a",
                stage_success=False,
                timestamp="2026-04-20T00:00:00+00:00",
                rollback_risk_delta=0.8,
            ),
            SkillEffectivenessRecord(
                skill_name="arc-low-value-skill",
                stage_name="code_generation",
                run_id="run-b",
                stage_success=False,
                timestamp="2026-04-21T00:00:00+00:00",
                rollback_risk_delta=0.7,
            ),
        ]
    )

    actions = manager.evaluate_existing_skills(store)

    assert any(item["skill"] == "arc-low-value-skill" and item["action"] == "demote" for item in actions)
    skill_text = (prod_skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert 'priority: "5"' in skill_text or "priority: '5'" in skill_text or "priority: '5'" in skill_text
