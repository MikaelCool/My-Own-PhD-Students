"""Deterministic orchestration policy for research agents."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OrchestrationInput:
    stage: int
    task_type: str
    coupling: str
    parallelizable: bool
    risk: str
    uncertainty: str
    branch_budget: int = 1


@dataclass(frozen=True)
class OrchestrationDecision:
    mode: str
    branch_budget: int
    requires_human_review: bool = False
    reasons: list[str] = field(default_factory=list)


def choose_orchestration(request: OrchestrationInput) -> OrchestrationDecision:
    """Choose an execution mode with explicit constraints."""
    reasons: list[str] = []
    risk = request.risk.lower()
    coupling = request.coupling.lower()
    uncertainty = request.uncertainty.lower()
    budget = max(int(request.branch_budget), 1)

    requires_review = risk == "high" or request.stage in {9, 15, 20}
    if requires_review:
        reasons.append("high-impact scientific decision requires human review")

    if coupling == "high" or not request.parallelizable:
        reasons.append("sequential or tightly coupled task")
        return OrchestrationDecision(
            mode="centralized",
            branch_budget=1,
            requires_human_review=requires_review,
            reasons=reasons,
        )

    if request.parallelizable and coupling == "low" and budget >= 2 and risk in {"low", "medium"}:
        reasons.append("low-coupling task can be explored in parallel")
        if uncertainty == "high":
            reasons.append("high uncertainty keeps branch budget explicit")
        return OrchestrationDecision(
            mode="parallel_multi_agent",
            branch_budget=min(budget, 8),
            requires_human_review=requires_review,
            reasons=reasons,
        )

    reasons.append("moderate coupling favors a single accountable agent")
    return OrchestrationDecision(
        mode="single_agent",
        branch_budget=1,
        requires_human_review=requires_review,
        reasons=reasons,
    )
