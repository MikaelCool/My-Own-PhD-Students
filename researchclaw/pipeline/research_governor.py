"""Macro-phase governance, stage skill overlays, and editorial routing."""

from __future__ import annotations

from pathlib import Path

from researchclaw.assessor.venue_profiles import VenueProfile, get_venue_profile
from researchclaw.config import RCConfig
from researchclaw.skills.registry import SkillRegistry


_DISCOVERY_STAGES = {
    "topic_init",
    "problem_decompose",
    "search_strategy",
    "literature_collect",
    "literature_screen",
    "knowledge_extract",
    "synthesis",
    "hypothesis_gen",
}
_INNOVATION_STAGES = {
    "experiment_design",
    "code_generation",
    "resource_planning",
    "experiment_run",
    "iterative_refine",
    "result_analysis",
    "research_decision",
}


def build_phase_charter(stage_name: str, venue_profile: VenueProfile | None = None) -> str:
    venue = venue_profile or get_venue_profile("CCF-A")
    if stage_name in _DISCOVERY_STAGES:
        return (
            "## Macro Phase: Discovery Council\n"
            "- Personality: skeptical strategist and literature cartographer.\n"
            "- Responsibility: narrow the problem, absorb baselines, and reject shallow novelty.\n"
            "- Constraint: do not pass vague innovation ideas downstream; communicate concrete gaps and proof obligations.\n"
        )
    if stage_name in _INNOVATION_STAGES:
        return (
            "## Macro Phase: Innovation Forge\n"
            "- Personality: hard-nosed scientist-engineer.\n"
            "- Responsibility: turn claims into algorithms, code, and experiments that can survive baseline comparison.\n"
            "- Constraint: if the method does not beat or meaningfully outperform strong baselines, treat the innovation as unproven.\n"
        )
    return (
        f"## Macro Phase: Editorial Board\n"
        f"- Personality: {venue.editorial_stance}\n"
        "- Responsibility: judge the paper as if publication slots are scarce and standards are high.\n"
        "- Constraint: require innovation, evidence, and writing quality to jointly clear the bar; weak novelty or weak experiments should trigger rollback.\n"
    )


def build_stage_skill_overlay(
    config: RCConfig,
    *,
    stage_name: str,
    context: str,
) -> str:
    if not getattr(config.skills, "enabled", True):
        return ""
    try:
        registry = SkillRegistry(
            builtin_dir=config.skills.builtin_dir,
            custom_dirs=config.skills.custom_dirs,
            external_dirs=config.skills.external_dirs,
            auto_match=config.skills.auto_match,
            max_skills_per_stage=config.skills.max_skills_per_stage,
            fallback_matching=config.skills.fallback_matching,
        )
        matched = registry.match(context, stage_name)
        if not matched:
            return ""
        exported = registry.export_for_prompt(matched, max_chars=2400)
        if not exported.strip():
            return ""
        return f"## Active Skills\n{exported}\n"
    except Exception:
        return ""


def write_phase_handoff(path: Path, title: str, sections: dict[str, str]) -> None:
    lines = [f"# {title}", ""]
    for heading, body in sections.items():
        lines.extend([f"## {heading}", body.strip(), ""])
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def infer_editorial_action(
    *,
    review_text: str,
    scores: dict[str, float],
    must_fix: list[str],
    venue_profile: VenueProfile,
) -> tuple[str, str]:
    lowered = "\n".join(must_fix).lower() + "\n" + review_text.lower()
    novelty_score = scores.get("novelty", 0.0)
    rigor_score = scores.get("technical_soundness", scores.get("rigor", 0.0))
    empirical_score = scores.get("empirical_adequacy", scores.get("experiments", 0.0))

    innovation_markers = (
        "incremental",
        "novelty is weak",
        "not novel",
        "unclear contribution",
        "innovation point",
        "main contribution is unclear",
    )
    experiment_markers = (
        "missing baseline",
        "baseline fairness",
        "missing ablation",
        "missing experiment",
        "statistical",
        "significance",
        "insufficient experiment",
        "empirical",
        "reproduce",
    )

    if novelty_score and novelty_score < venue_profile.novelty_floor:
        return "rework_innovation", "Novelty score is below the venue's editorial floor."
    if any(marker in lowered for marker in innovation_markers):
        return "rework_innovation", "Review finds the innovation insufficient or unclear."
    if empirical_score and empirical_score < venue_profile.experiment_floor:
        return "supplement_experiments", "Empirical adequacy is below the venue's editorial floor."
    if rigor_score and rigor_score < venue_profile.experiment_floor:
        return "supplement_experiments", "Technical soundness is below the editorial floor."
    if any(marker in lowered for marker in experiment_markers):
        return "supplement_experiments", "Review highlights missing empirical support or unfair baseline evaluation."
    return "revise_paper", "Primary issues are editorial and can be addressed in paper revision."

