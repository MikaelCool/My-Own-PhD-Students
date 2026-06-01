"""Controlled skill evolution loop.

This module turns skill feedback and extracted lessons into:
- priority recommendations for existing skills
- candidate skills written into a sandbox
- trial scheduling for candidate A/B evaluation
- promotion / rejection decisions once enough evidence exists
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from researchclaw.evolution import LessonEntry
from researchclaw.metaclaw_bridge.stage_skill_map import (
    LESSON_CATEGORY_TO_SKILL_CATEGORY,
)
from researchclaw.metaclaw_bridge.skill_feedback import SkillFeedbackStore

logger = logging.getLogger(__name__)

_SEVERITY_WEIGHT = {"info": 1.0, "warning": 2.0, "error": 3.0, "critical": 4.0}
_STOPWORDS = {
    "stage", "failed", "failure", "error", "warning", "with", "from", "into",
    "this", "that", "when", "while", "where", "there", "their", "experiment",
    "pipeline", "paper", "draft", "review", "results", "metrics", "quality",
    "output", "issue", "requires", "required", "detected", "missing", "using",
}
_CONTROL_CATEGORY_BY_LESSON = {
    "system": "recovery",
    "experiment": "diagnosis",
    "analysis": "observation",
    "literature": "evidence-quality",
    "writing": "writing-governance",
    "pipeline": "control-policy",
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug)


def _extract_keywords(*texts: str, limit: int = 6) -> list[str]:
    counts: dict[str, int] = {}
    for text in texts:
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{3,}", text.lower()):
            if token in _STOPWORDS:
                continue
            counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [token for token, _ in ranked[:limit]]


def _read_frontmatter(skill_path: Path) -> tuple[dict[str, Any], str]:
    text = skill_path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        header = yaml.safe_load(parts[1]) or {}
    except Exception:
        header = {}
    if not isinstance(header, dict):
        header = {}
    return header, parts[2].lstrip("\n")


def _write_frontmatter(skill_path: Path, header: dict[str, Any], body: str) -> None:
    payload = "---\n" + yaml.safe_dump(header, sort_keys=False, allow_unicode=True).strip() + "\n---\n\n" + body.rstrip() + "\n"
    skill_path.write_text(payload, encoding="utf-8")


@dataclass
class SkillCandidateState:
    name: str
    stage_name: str
    stage_num: int
    source_category: str
    source_descriptions: list[str]
    keywords: list[str]
    status: str = "candidate"
    priority_score: float = 0.0
    created_at: str = field(default_factory=_utcnow_iso)
    activated_at: str = ""
    decision_at: str = ""
    decision_reason: str = ""
    trial_records: int = 0
    trial_success_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillCandidateState":
        return cls(
            name=str(data.get("name", "")),
            stage_name=str(data.get("stage_name", "")),
            stage_num=int(data.get("stage_num", 0)),
            source_category=str(data.get("source_category", "pipeline")),
            source_descriptions=[str(item) for item in data.get("source_descriptions", []) if str(item).strip()],
            keywords=[str(item) for item in data.get("keywords", []) if str(item).strip()],
            status=str(data.get("status", "candidate")),
            priority_score=float(data.get("priority_score", 0.0)),
            created_at=str(data.get("created_at", "")),
            activated_at=str(data.get("activated_at", "")),
            decision_at=str(data.get("decision_at", "")),
            decision_reason=str(data.get("decision_reason", "")),
            trial_records=int(data.get("trial_records", 0)),
            trial_success_rate=float(data.get("trial_success_rate", 0.0)),
        )


class SkillEvolutionManager:
    """Persistent manager for controlled skill evolution."""

    def __init__(self, skills_dir: str | Path) -> None:
        self.skills_dir = Path(skills_dir).expanduser()
        self.skills_dir.mkdir(parents=True, exist_ok=True)

    @property
    def candidates_dir(self) -> Path:
        return self.skills_dir / ".candidates"

    @property
    def trials_dir(self) -> Path:
        return self.skills_dir / ".trials"

    @property
    def reports_dir(self) -> Path:
        return self.skills_dir / ".evolution"

    def _candidate_state_path(self, name: str) -> Path:
        return self.candidates_dir / name / "candidate_state.json"

    def _candidate_skill_path(self, name: str) -> Path:
        return self.candidates_dir / name / "SKILL.md"

    def _trial_skill_path(self, name: str) -> Path:
        return self.trials_dir / name / "SKILL.md"

    def _production_skill_path(self, name: str) -> Path:
        return self.skills_dir / name / "SKILL.md"

    def load_candidate_states(self) -> dict[str, SkillCandidateState]:
        states: dict[str, SkillCandidateState] = {}
        if not self.candidates_dir.exists():
            return states
        for path in sorted(self.candidates_dir.glob("*/candidate_state.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(payload, dict):
                state = SkillCandidateState.from_dict(payload)
                if state.name:
                    states[state.name] = state
        return states

    def _persist_candidate_state(self, state: SkillCandidateState) -> None:
        target_dir = self.candidates_dir / state.name
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "candidate_state.json").write_text(
            json.dumps(state.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def evaluate_existing_skills(
        self,
        feedback_store: SkillFeedbackStore,
    ) -> list[dict[str, Any]]:
        stats = feedback_store.compute_skill_stats()
        actions: list[dict[str, Any]] = []
        for skill_name, stat in sorted(stats.items()):
            total = int(stat.get("total", 0))
            success_rate = float(stat.get("success_rate", 0.0))
            avg_quality_gain = float(stat.get("avg_quality_gain", 0.0))
            avg_rollback_risk = float(stat.get("avg_rollback_risk_delta", 0.0))
            if total < 2:
                action = "keep"
                reason = "insufficient evidence"
            elif success_rate >= 0.75 and avg_quality_gain > 0.0 and avg_rollback_risk <= 0.0:
                action = "promote"
                reason = "high success rate with positive quality gain"
            elif success_rate <= 0.35 or avg_rollback_risk > 0.25:
                action = "demote"
                reason = "low success rate or elevated rollback risk"
            else:
                action = "keep"
                reason = "performance is mixed"
            applied = self._apply_priority_action(skill_name, action)
            actions.append(
                {
                    "skill": skill_name,
                    "action": action,
                    "applied": applied,
                    "reason": reason,
                    "success_rate": round(success_rate, 4),
                    "total": total,
                    "avg_quality_gain": round(avg_quality_gain, 4),
                    "avg_rollback_risk_delta": round(avg_rollback_risk, 4),
                }
            )
        return actions

    def _apply_priority_action(self, skill_name: str, action: str) -> bool:
        if action not in {"promote", "demote"}:
            return False
        skill_path = self._production_skill_path(skill_name)
        if not skill_path.exists():
            return False
        header, body = _read_frontmatter(skill_path)
        metadata = header.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            header["metadata"] = metadata
        current_priority = 5
        try:
            current_priority = int(metadata.get("priority", 5))
        except (TypeError, ValueError):
            current_priority = 5
        new_priority = current_priority
        if action == "promote":
            new_priority = max(1, current_priority - 1)
        elif action == "demote":
            new_priority = min(9, current_priority + 1)
        if new_priority == current_priority:
            return False
        metadata["priority"] = str(new_priority)
        metadata["last-evolution-action"] = action
        metadata["last-evolution-at"] = _utcnow_iso()
        _write_frontmatter(skill_path, header, body)
        return True

    def create_candidate_skills(
        self,
        lessons: list[LessonEntry],
        *,
        max_candidates: int = 2,
    ) -> list[SkillCandidateState]:
        existing_states = self.load_candidate_states()
        existing_names = set(existing_states)
        existing_names.update(path.name for path in self.skills_dir.iterdir() if path.is_dir())
        groups: dict[tuple[str, int, str], list[LessonEntry]] = {}
        for lesson in lessons:
            if not lesson.stage_name:
                continue
            key = (lesson.stage_name, int(lesson.stage_num), lesson.category)
            groups.setdefault(key, []).append(lesson)

        ranked_groups = sorted(
            groups.items(),
            key=lambda item: (
                -sum(_SEVERITY_WEIGHT.get(l.severity, 1.0) for l in item[1]),
                item[0][1],
                item[0][0],
            ),
        )
        created: list[SkillCandidateState] = []
        for (stage_name, stage_num, category), grouped in ranked_groups:
            if len(created) >= max_candidates:
                break
            keywords = _extract_keywords(*(lesson.description for lesson in grouped), stage_name, category)
            lesson_focus = keywords[0] if keywords else category
            name = _slugify(f"arc-{stage_name}-{lesson_focus}")
            if not name or name in existing_names:
                continue
            descriptions = [lesson.description for lesson in grouped[:4]]
            state = SkillCandidateState(
                name=name,
                stage_name=stage_name,
                stage_num=stage_num,
                source_category=category,
                source_descriptions=descriptions,
                keywords=keywords,
                priority_score=round(sum(_SEVERITY_WEIGHT.get(l.severity, 1.0) for l in grouped), 2),
            )
            self._write_candidate_skill(state)
            self._persist_candidate_state(state)
            existing_names.add(name)
            created.append(state)
        return created

    def _write_candidate_skill(self, state: SkillCandidateState) -> None:
        skill_path = self._candidate_skill_path(state.name)
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_category = LESSON_CATEGORY_TO_SKILL_CATEGORY.get(state.source_category, "tooling")
        control_category = _CONTROL_CATEGORY_BY_LESSON.get(state.source_category, "control-policy")
        metadata = {
            "category": skill_category,
            "trigger-keywords": ",".join(state.keywords),
            "applicable-stages": str(state.stage_num),
            "priority": "4",
            "preconditions": f"stage {state.stage_name} exhibits repeated {state.source_category} failures",
            "expected-gain": "reduce recurrence of the same failure pattern",
            "token-cost-band": "low",
            "failure-types-covered": ",".join(state.keywords[:4] or [state.source_category]),
            "escalation-rule": f"rollback_to_stage_{max(1, state.stage_num - 1)}_if_failure_persists",
            "control-category": control_category,
            "candidate-status": "candidate",
        }
        body = "\n".join(
            [
                f"## {state.stage_name.replace('_', ' ').title()} Recovery Skill",
                "",
                "Use this skill when the pipeline repeats the same failure pattern and needs a local control law instead of another blind retry.",
                "",
                "1. Confirm the failure matches the recurring signature listed below.",
                "2. Inspect the most recent structured diagnostics before editing prompts or code.",
                "3. Prefer the smallest local intervention that removes the recurrent fault.",
                "4. If the same failure repeats after the intervention, escalate according to the configured rollback rule.",
                "",
                "### Recurring Signatures",
                *[f"- {desc}" for desc in state.source_descriptions],
                "",
                "### Anti-Patterns",
                "- Do not regenerate whole stages when a local repair or diagnostic pass is sufficient.",
                "- Do not mix this skill with unrelated broad-context drafting skills in the same repair loop.",
                "- Do not mark the issue as solved without verifying the latest structured artifact or observer state.",
            ]
        )
        header = {
            "name": state.name,
            "description": f"Use when {state.stage_name} repeats {state.source_category} failures.",
            "metadata": metadata,
        }
        _write_frontmatter(skill_path, header, body)

    def schedule_trials(self, *, max_trial_skills: int = 1) -> list[str]:
        states = self.load_candidate_states()
        self.trials_dir.mkdir(parents=True, exist_ok=True)
        active_trials = {path.name for path in self.trials_dir.iterdir() if path.is_dir()}
        scheduled: list[str] = []
        available_slots = max(0, max_trial_skills - len(active_trials))
        if available_slots == 0:
            return scheduled
        candidates = sorted(
            (
                state for state in states.values()
                if state.status == "candidate"
                and not self._production_skill_path(state.name).exists()
                and state.name not in active_trials
            ),
            key=lambda state: (-state.priority_score, state.name),
        )
        for state in candidates[:available_slots]:
            source = self._candidate_skill_path(state.name)
            if not source.exists():
                continue
            target = self._trial_skill_path(state.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            header, body = _read_frontmatter(target)
            metadata = header.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
                header["metadata"] = metadata
            metadata["candidate-status"] = "trial"
            metadata["candidate-origin"] = "skill-evolution-loop"
            _write_frontmatter(target, header, body)
            state.status = "trial"
            state.activated_at = _utcnow_iso()
            self._persist_candidate_state(state)
            scheduled.append(state.name)
        return scheduled

    def evaluate_trials(
        self,
        feedback_store: SkillFeedbackStore,
        *,
        min_trial_records: int = 2,
        promote_success_rate: float = 0.65,
        reject_success_rate: float = 0.35,
    ) -> dict[str, list[str]]:
        stats = feedback_store.compute_skill_stats()
        states = self.load_candidate_states()
        promoted: list[str] = []
        rejected: list[str] = []
        kept: list[str] = []
        for state in states.values():
            if state.status != "trial":
                continue
            stat = stats.get(state.name)
            if not isinstance(stat, dict):
                kept.append(state.name)
                continue
            total = int(stat.get("total", 0))
            success_rate = float(stat.get("success_rate", 0.0))
            avg_quality_gain = float(stat.get("avg_quality_gain", 0.0))
            avg_rollback_risk = float(stat.get("avg_rollback_risk_delta", 0.0))
            state.trial_records = total
            state.trial_success_rate = round(success_rate, 4)
            if total < min_trial_records:
                self._persist_candidate_state(state)
                kept.append(state.name)
                continue
            if success_rate >= promote_success_rate and avg_quality_gain >= 0.0 and avg_rollback_risk <= 0.25:
                self._promote_trial(state)
                promoted.append(state.name)
            elif success_rate <= reject_success_rate and avg_rollback_risk > 0.0:
                self._reject_trial(state, reason="trial underperformed against gate thresholds")
                rejected.append(state.name)
            else:
                self._persist_candidate_state(state)
                kept.append(state.name)
        return {"promoted": promoted, "rejected": rejected, "kept": kept}

    def _promote_trial(self, state: SkillCandidateState) -> None:
        source = self._candidate_skill_path(state.name)
        if not source.exists():
            return
        target = self._production_skill_path(state.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        header, body = _read_frontmatter(target)
        metadata = header.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            header["metadata"] = metadata
        metadata["candidate-status"] = "promoted"
        metadata["promoted-at"] = _utcnow_iso()
        _write_frontmatter(target, header, body)
        shutil.rmtree(self.trials_dir / state.name, ignore_errors=True)
        state.status = "promoted"
        state.decision_at = _utcnow_iso()
        state.decision_reason = "trial passed promotion gate"
        self._persist_candidate_state(state)

    def _reject_trial(self, state: SkillCandidateState, *, reason: str) -> None:
        shutil.rmtree(self.trials_dir / state.name, ignore_errors=True)
        state.status = "rejected"
        state.decision_at = _utcnow_iso()
        state.decision_reason = reason
        self._persist_candidate_state(state)

    def write_report(
        self,
        *,
        run_id: str,
        policy_actions: list[dict[str, Any]],
        created_candidates: list[SkillCandidateState],
        scheduled_trials: list[str],
        trial_decisions: dict[str, list[str]],
    ) -> dict[str, Any]:
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": run_id,
            "generated": _utcnow_iso(),
            "policy_actions": policy_actions,
            "created_candidates": [item.to_dict() for item in created_candidates],
            "scheduled_trials": scheduled_trials,
            "trial_decisions": trial_decisions,
            "candidate_states": [state.to_dict() for state in self.load_candidate_states().values()],
        }
        (self.reports_dir / "skill_evolution_report.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return payload

    def run_loop(
        self,
        *,
        lessons: list[LessonEntry],
        feedback_store: SkillFeedbackStore,
        run_id: str,
        max_candidates_per_run: int = 2,
        max_trial_skills: int = 1,
        min_trial_records: int = 2,
        promote_success_rate: float = 0.65,
        reject_success_rate: float = 0.35,
    ) -> dict[str, Any]:
        policy_actions = self.evaluate_existing_skills(feedback_store)
        created_candidates = self.create_candidate_skills(
            lessons,
            max_candidates=max_candidates_per_run,
        )
        scheduled_trials = self.schedule_trials(max_trial_skills=max_trial_skills)
        trial_decisions = self.evaluate_trials(
            feedback_store,
            min_trial_records=min_trial_records,
            promote_success_rate=promote_success_rate,
            reject_success_rate=reject_success_rate,
        )
        return self.write_report(
            run_id=run_id,
            policy_actions=policy_actions,
            created_candidates=created_candidates,
            scheduled_trials=scheduled_trials,
            trial_decisions=trial_decisions,
        )
