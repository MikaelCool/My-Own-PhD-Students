"""Macro-phase governance, stage skill overlays, and editorial routing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
_WRITING_STAGES = {
    "paper_outline",
    "paper_draft",
    "peer_review",
    "paper_revision",
    "quality_gate",
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


def build_launch_mode_overlay(
    stage_name: str,
    *,
    launch_mode: str,
    startup_contract: dict[str, Any] | None = None,
) -> str:
    mode = (launch_mode or "standard_full_run").strip().lower()
    contract = startup_contract or {}
    lines = [
        "## Startup Contract",
        f"- Launch mode: `{mode}`",
    ]

    goal = str(contract.get("goal") or "").strip()
    if goal:
        lines.append(f"- Goal: {goal[:280]}")

    objectives = [str(item).strip() for item in contract.get("objectives", []) if str(item).strip()]
    if objectives:
        lines.append("- Objectives:")
        lines.extend(f"  - {item}" for item in objectives[:4])

    baselines = [str(item).strip() for item in contract.get("baseline_urls", []) if str(item).strip()]
    if baselines:
        lines.append(f"- Baseline anchors: {', '.join(baselines[:3])}")

    paper_urls = [str(item).strip() for item in contract.get("paper_urls", []) if str(item).strip()]
    if paper_urls:
        lines.append(f"- Reference anchors: {', '.join(paper_urls[:3])}")

    runtime_constraints = str(contract.get("runtime_constraints") or "").strip()
    if runtime_constraints:
        lines.append(f"- Runtime constraints: {runtime_constraints[:280]}")

    intensity = str(contract.get("research_intensity") or "balanced").strip()
    decision_policy = str(contract.get("decision_policy") or "autonomous").strip()
    lines.append(f"- Research intensity: `{intensity}`")
    lines.append(f"- Decision policy: `{decision_policy}`")
    lines.extend(["", "## Launch Mode Strategy"])

    if mode == "continue_existing_state":
        lines.extend(
            [
                "- Treat prior artifacts as primary context, not disposable drafts.",
                "- Audit what is already validated before proposing new work.",
                "- Reuse prior baselines, charts, and review findings unless they are stale, contradictory, or missing.",
                "- Prefer the smallest delta that restores rigor or moves the project forward.",
            ]
        )
        if stage_name in _DISCOVERY_STAGES:
            lines.append("- Discovery stages should narrow open gaps in existing artifacts instead of redoing broad exploration.")
        elif stage_name in _INNOVATION_STAGES:
            lines.append("- Experiment stages should patch missing evidence and fairness gaps before inventing new variants.")
        elif stage_name in _WRITING_STAGES:
            lines.append("- Writing and review stages should preserve validated claims and rewrite only where evidence changed.")
    elif mode == "review_only":
        lines.extend(
            [
                "- Operate in editorial audit mode.",
                "- Prioritize skeptical evaluation, claim-evidence checking, and issue triage over generation.",
                "- Do not request new experiments unless a contradiction or fatal evidence gap makes audit impossible.",
                "- Produce reviewer-ready findings, scorecards, and rollback recommendations.",
            ]
        )
        if stage_name in _WRITING_STAGES:
            lines.append("- Keep recommendations concrete and evidence-linked; optimize for peer review, not narrative expansion.")
    elif mode == "rebuttal_revision":
        lines.extend(
            [
                "- Treat reviewer findings and the current manuscript as the active contract.",
                "- Focus on rebuttal-grade deltas: claim calibration, missing evidence, and targeted prose revision.",
                "- Preserve the existing problem framing unless evidence clearly invalidates it.",
                "- Prefer narrow supplemental work over full-project re-scoping.",
            ]
        )
        if stage_name in _INNOVATION_STAGES:
            lines.append("- Any new experiment must directly answer a reviewer objection or close a decisive evidence gap.")
        elif stage_name in _WRITING_STAGES:
            lines.append("- Revisions should read like a disciplined response to review, not a brand-new paper story.")
    else:
        lines.extend(
            [
                "- Run the full research cycle end-to-end.",
                "- Preserve baseline awareness and keep claims proportional to evidence.",
                "- Favor publishable, reproducible outputs over novelty theater.",
            ]
        )

    return "\n".join(lines) + "\n"


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
