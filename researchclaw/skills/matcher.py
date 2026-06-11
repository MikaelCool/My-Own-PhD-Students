"""Skill-to-stage matching engine."""

from __future__ import annotations

import logging
import re

from researchclaw.skills.schema import STAGE_NAME_TO_NUMBER, Skill

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> set[str]:
    """Extract lowercase tokens from text."""
    return set(re.findall(r"[a-z0-9_]+", text.lower()))


def _resolve_stage(stage: int | str) -> int:
    """Convert a stage name to its number, or pass through an int."""
    if isinstance(stage, int):
        return stage
    return STAGE_NAME_TO_NUMBER.get(stage, -1)


def match_skills(
    skills: list[Skill],
    context: str,
    stage: int | str,
    top_k: int = 3,
    *,
    fallback_matching: bool = True,
    token_budget_band: str = "medium",
    active_skill_names: set[str] | frozenset[str] | None = None,
    required_control_category: str = "",
) -> list[Skill]:
    """Match skills to the current context and stage.

    Scoring:
    - Stage applicability (must match, or empty = all stages)
    - Keyword overlap with context
    - Description-based fallback at 0.5x discount (for skills without trigger_keywords)
    - Priority (lower = higher priority)
    - Optional expected-gain and token-cost metadata
    - Optional conflict and control-category constraints

    Args:
        skills: Available skills to match against.
        context: Current task context text.
        stage: Current pipeline stage number or name.
        top_k: Maximum number of skills to return.
        fallback_matching: Enable description-based matching for skills
            without trigger_keywords.
        token_budget_band: Current budget pressure, one of low, medium, high.
        active_skill_names: Skill names already active in the prompt/workflow.
        required_control_category: If set, only skills with this control
            category (or no declared category) are considered.

    Returns:
        List of matched skills sorted by relevance.
    """
    stage_num = _resolve_stage(stage)
    context_tokens = _tokenize(context)
    active = set(active_skill_names or set())
    budget = str(token_budget_band or "medium").lower()
    required_category = str(required_control_category or "").strip().lower()
    scored: list[tuple[float, Skill]] = []

    for skill in skills:
        # Filter by stage applicability
        if skill.applicable_stages and stage_num not in skill.applicable_stages:
            continue
        if active and active.intersection(skill.conflict_skills):
            continue
        control_category = skill.control_category.strip().lower()
        if required_category and control_category and control_category != required_category:
            continue

        # Keyword matching score
        keyword_score = 0.0
        has_keywords = bool(skill.trigger_keywords)
        for kw in skill.trigger_keywords:
            kw_tokens = _tokenize(kw)
            if kw_tokens & context_tokens:
                keyword_score += 1.0

        # Description-based fallback for external skills without keywords
        if keyword_score == 0.0 and not has_keywords and fallback_matching:
            desc_tokens = _tokenize(skill.description)
            overlap = len(desc_tokens & context_tokens)
            if overlap > 0:
                keyword_score = overlap * 0.5  # 0.5x discount
                max_possible = max(len(desc_tokens), 1)
                normalized_kw = keyword_score / max_possible
            else:
                continue
        elif keyword_score == 0.0:
            continue
        else:
            max_possible = max(len(skill.trigger_keywords), 1)
            normalized_kw = keyword_score / max_possible

        # Priority adjustment (priority 1 → boost 0.5, priority 10 → boost 0.0)
        priority_boost = (10 - skill.priority) / 20.0
        gain_boost = _expected_gain_boost(skill.expected_gain)
        cost_penalty = _token_cost_penalty(skill.token_cost_band, budget)
        precondition_boost = _precondition_boost(skill.preconditions, context_tokens)
        category_boost = 0.1 if required_category and control_category == required_category else 0.0

        total_score = normalized_kw + priority_boost + gain_boost + precondition_boost + category_boost - cost_penalty
        scored.append((total_score, skill))

    scored.sort(key=lambda x: (-x[0], x[1].priority))
    return [skill for _, skill in scored[:top_k]]


def _expected_gain_boost(raw: str) -> float:
    value = raw.strip().lower()
    if value in {"high", "large", "strong"}:
        return 0.35
    if value in {"medium", "moderate"}:
        return 0.2
    if value in {"low", "small"}:
        return 0.05
    return 0.0


def _token_cost_penalty(raw: str, budget: str) -> float:
    cost = raw.strip().lower()
    if not cost:
        return 0.0
    cost_rank = {"low": 1, "medium": 2, "high": 3}.get(cost, 2)
    budget_rank = {"low": 1, "medium": 2, "high": 3}.get(budget, 2)
    if cost_rank <= budget_rank:
        return 0.0
    return 0.25 * (cost_rank - budget_rank)


def _precondition_boost(preconditions: list[str], context_tokens: set[str]) -> float:
    if not preconditions:
        return 0.0
    matched = 0
    for item in preconditions:
        if _tokenize(item) & context_tokens:
            matched += 1
    return min(0.15, matched * 0.05)


def format_skills_for_prompt(skills: list[Skill], max_chars: int = 4000) -> str:
    """Format matched skills as prompt injection text.

    Uses ``skill.body`` as primary content.  Truncates long bodies
    (common with external skills) to ``max_chars / len(skills)`` per skill.

    Args:
        skills: List of matched skills.
        max_chars: Maximum character limit.

    Returns:
        Formatted string for LLM prompt injection.
    """
    if not skills:
        return ""

    per_skill_budget = max_chars // max(len(skills), 1)
    parts: list[str] = []
    total_len = 0

    for skill in skills:
        content = skill.body or skill.prompt_template
        # Truncate long bodies
        if len(content) > per_skill_budget:
            content = content[:per_skill_budget - 20] + "\n\n[... truncated]"

        section = f"### {skill.name} ({skill.category})\n{content}"
        if skill.code_template:
            section += f"\n**Code Template:**\n```python\n{skill.code_template}\n```"
        if skill.references:
            section += "\n**References:** " + "; ".join(skill.references)

        if total_len + len(section) > max_chars:
            break
        parts.append(section)
        total_len += len(section)

    return "\n\n".join(parts)
