"""Core benchmark types for stage and workflow evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class BenchmarkTask:
    task_id: str
    name: str
    stage: int | None = None
    required_metrics: tuple[str, ...] = ()
    source: str = "internal"
    budget_tokens: int | None = None
    budget_usd: float | None = None


@dataclass(frozen=True)
class BenchmarkMetric:
    name: str
    value: float
    threshold: float | None = None
    direction: str = "maximize"

    @property
    def passed(self) -> bool:
        if self.threshold is None:
            return True
        if self.direction == "minimize":
            return self.value <= self.threshold
        if self.direction == "neutral":
            return True
        return self.value >= self.threshold


@dataclass
class BenchmarkResult:
    task: BenchmarkTask
    metrics: list[BenchmarkMetric] = field(default_factory=list)
    cost_usd: float = 0.0
    elapsed_sec: float = 0.0
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        metric_names = {metric.name for metric in self.metrics}
        if any(name not in metric_names for name in self.task.required_metrics):
            return False
        return not self.error and all(metric.passed for metric in self.metrics)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["passed"] = self.passed
        return payload


@dataclass
class BenchmarkReport:
    results: list[BenchmarkResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for result in self.results if result.passed) / len(self.results)

    @property
    def total_cost_usd(self) -> float:
        return sum(result.cost_usd for result in self.results)

    @property
    def total_elapsed_sec(self) -> float:
        return sum(result.elapsed_sec for result in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "result_count": len(self.results),
            "pass_rate": self.pass_rate,
            "total_cost_usd": self.total_cost_usd,
            "total_elapsed_sec": self.total_elapsed_sec,
            "results": [result.to_dict() for result in self.results],
        }
