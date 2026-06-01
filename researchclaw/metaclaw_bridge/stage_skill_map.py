"""Maps AutoResearchClaw pipeline stages to MetaClaw skill categories.

Each stage maps to:
- task_type: MetaClaw's task category for skill retrieval
- skills: Preferred research-specific skills to inject
- top_k: Number of skills to inject at this stage
"""

from __future__ import annotations

from typing import Any

STAGE_SKILL_MAP: dict[str, dict[str, Any]] = {
    "topic_init": {
        "task_type": "research",
        "skills": ["literature-search-strategy"],
        "top_k": 4,
        "preferred_categories": ["modeling", "evidence-quality"],
        "bad_combos": [],
        "good_combos": ["literature-search-strategy+research-gap-identification"],
        "escalation_rule": "request_human_gate_on_ambiguous_problem_scope",
        "policy_focus": "narrow problem framing before broad execution",
    },
    "problem_decompose": {
        "task_type": "research",
        "skills": ["research-gap-identification"],
        "top_k": 4,
    },
    "search_strategy": {
        "task_type": "research",
        "skills": ["literature-search-strategy"],
        "top_k": 6,
    },
    "literature_collect": {
        "task_type": "research",
        "skills": ["literature-search-strategy", "nature-academic-search", "nature-reader"],
        "top_k": 4,
    },
    "literature_screen": {
        "task_type": "research",
        "skills": ["paper-relevance-screening", "nature-reader", "nature-academic-search"],
        "top_k": 6,
    },
    "knowledge_extract": {
        "task_type": "research",
        "skills": ["knowledge-card-extraction", "nature-reader"],
        "top_k": 4,
    },
    "synthesis": {
        "task_type": "research",
        "skills": ["research-gap-identification"],
        "top_k": 6,
    },
    "hypothesis_gen": {
        "task_type": "research",
        "skills": ["hypothesis-formulation"],
        "top_k": 6,
    },
    "experiment_design": {
        "task_type": "research",
        "skills": ["experiment-design-rigor"],
        "top_k": 6,
        "preferred_categories": ["observation", "evidence-quality"],
        "bad_combos": ["paper-drafting+experiment-design-rigor"],
        "good_combos": ["experiment-design-rigor+statistical-analysis"],
        "escalation_rule": "rollback_to_stage_8_if_baselines_or_metrics_are_weak",
        "policy_focus": "maximize design adequacy before code generation",
    },
    "code_generation": {
        "task_type": "coding",
        "skills": ["hardware-aware-coding"],
        "top_k": 6,
        "preferred_categories": ["recovery", "control-policy"],
        "bad_combos": ["prompt-compression+deep-repair"],
        "good_combos": ["hardware-aware-coding+experiment-debugging"],
        "escalation_rule": "switch_to_block_level_repair_on_large_file_failures",
        "policy_focus": "prefer local block repair over full-file regeneration",
    },
    "resource_planning": {
        "task_type": "productivity",
        "skills": [],
        "top_k": 3,
    },
    "experiment_run": {
        "task_type": "automation",
        "skills": ["experiment-debugging"],
        "top_k": 4,
        "preferred_categories": ["observation", "recovery"],
        "bad_combos": ["dataset-fallback+paper-review-methodology"],
        "good_combos": ["experiment-debugging+statistical-analysis"],
        "escalation_rule": "wait_for_resource_then_retry_before_pivot",
        "policy_focus": "diagnose environment and runtime mismatches before redesign",
    },
    "iterative_refine": {
        "task_type": "coding",
        "skills": ["experiment-debugging"],
        "top_k": 6,
        "preferred_categories": ["recovery", "diagnosis"],
        "bad_combos": ["prompt-compression+deep-repair"],
        "good_combos": ["experiment-debugging+peer-review-methodology"],
        "escalation_rule": "rollback_to_stage_9_when_failures_repeat_without_gain",
        "policy_focus": "refine from structured diagnostics, not raw transcript replay",
    },
    "result_analysis": {
        "task_type": "data_analysis",
        "skills": ["statistical-analysis"],
        "top_k": 6,
    },
    "research_decision": {
        "task_type": "research",
        "skills": ["research-pivot-decision"],
        "top_k": 4,
    },
    "paper_outline": {
        "task_type": "communication",
        "skills": ["academic-writing-structure", "nature-writing", "nature-polishing", "nature-figure", "nature-data"],
        "top_k": 4,
        "preferred_categories": ["writing-governance", "evidence-quality"],
        "good_combos": ["nature-writing+nature-figure", "nature-polishing+nature-data", "academic-writing-structure+nature-polishing"],
        "policy_focus": "turn validated evidence into a defensible high-impact paper story and figure plan",
    },
    "paper_draft": {
        "task_type": "communication",
        "skills": ["academic-writing-structure", "nature-writing", "nature-polishing", "nature-figure", "nature-citation", "nature-data"],
        "top_k": 6,
        "preferred_categories": ["writing-governance", "evidence-quality"],
        "bad_combos": ["literature-breadth+paper-drafting"],
        "good_combos": ["nature-writing+nature-polishing", "nature-citation+nature-data", "nature-polishing+nature-figure"],
        "escalation_rule": "request_human_gate_if_claims_outrun_evidence",
        "policy_focus": "preserve claim-evidence alignment while drafting polished high-impact prose",
    },
    "peer_review": {
        "task_type": "communication",
        "skills": ["peer-review-methodology", "nature-response"],
        "top_k": 6,
    },
    "paper_revision": {
        "task_type": "communication",
        "skills": ["academic-writing-structure", "peer-review-methodology", "nature-response", "nature-writing", "nature-polishing", "nature-figure", "nature-citation"],
        "top_k": 6,
        "preferred_categories": ["writing-governance", "evidence-quality"],
        "good_combos": ["nature-response+nature-polishing", "nature-citation+nature-figure", "peer-review-methodology+nature-polishing"],
        "escalation_rule": "downgrade_or_remove_claims_when_review_findings_exceed_evidence",
        "policy_focus": "fix reviewer risks first, then polish prose and figure/caption clarity",
    },
    "quality_gate": {
        "task_type": "research",
        "skills": ["peer-review-methodology"],
        "top_k": 4,
        "preferred_categories": ["writing-governance", "evidence-quality"],
        "bad_combos": [],
        "good_combos": ["peer-review-methodology+statistical-analysis"],
        "escalation_rule": "rollback_to_stage_16_or_14_when_quality_gate_fails",
        "policy_focus": "treat low-quality acceptance as rollback, not pass-through",
    },
    "knowledge_archive": {
        "task_type": "automation",
        "skills": [],
        "top_k": 2,
    },
    "export_publish": {
        "task_type": "automation",
        "skills": ["nature-polishing", "nature-figure", "nature-citation", "nature-data", "nature-paper2ppt"],
        "top_k": 3,
        "preferred_categories": ["writing-governance"],
        "good_combos": ["nature-polishing+nature-figure", "nature-citation+nature-data"],
        "policy_focus": "preserve citation keys and verified numbers while applying final publication formatting",
    },
    "citation_verify": {
        "task_type": "research",
        "skills": ["citation-integrity", "nature-citation", "nature-academic-search"],
        "top_k": 4,
    },
}

# Mapping from AutoResearchClaw lesson categories to skill categories.
# Uses the new taxonomy: writing, domain, experiment, tooling.
LESSON_CATEGORY_TO_SKILL_CATEGORY: dict[str, str] = {
    "system": "tooling",
    "experiment": "experiment",
    "writing": "writing",
    "analysis": "experiment",
    "literature": "experiment",
    "pipeline": "tooling",
}


def get_stage_config(stage_name: str) -> dict[str, Any]:
    """Return the MetaClaw skill config for a given pipeline stage.

    Falls back to a generic research config if the stage is unknown.
    """
    return STAGE_SKILL_MAP.get(
        stage_name,
        {
            "task_type": "research",
            "skills": [],
            "top_k": 4,
            "preferred_categories": [],
            "bad_combos": [],
            "good_combos": [],
            "escalation_rule": "",
            "policy_focus": "",
        },
    )


def summarize_stage_policy(stage_name: str) -> str:
    """Return a concise human-readable skill policy summary for a stage."""
    cfg = get_stage_config(stage_name)
    lines = ["## Stage Skill Policy"]
    focus = str(cfg.get("policy_focus") or "").strip()
    if focus:
        lines.append(f"- Focus: {focus}")
    preferred = cfg.get("preferred_categories") or []
    if isinstance(preferred, list) and preferred:
        lines.append("- Preferred categories: " + ", ".join(str(item) for item in preferred))
    good = cfg.get("good_combos") or []
    if isinstance(good, list) and good:
        lines.append("- Good combos: " + ", ".join(str(item) for item in good[:3]))
    bad = cfg.get("bad_combos") or []
    if isinstance(bad, list) and bad:
        lines.append("- Avoid combos: " + ", ".join(str(item) for item in bad[:3]))
    escalation = str(cfg.get("escalation_rule") or "").strip()
    if escalation:
        lines.append(f"- Escalation: {escalation}")
    return "\n".join(lines) + "\n"
