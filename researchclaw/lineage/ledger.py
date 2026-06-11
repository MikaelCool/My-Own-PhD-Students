"""Research lineage ledger for reproducible scientific claims."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from researchclaw.observability.tracing import hash_file


@dataclass(frozen=True)
class LineageIssue:
    severity: str
    message: str
    record_type: str
    record_id: str = ""


@dataclass
class DatasetRecord:
    name: str
    version: str
    split: str
    source: str
    path: str = ""
    sha256: str = ""
    leakage_status: str = "unknown"


@dataclass
class CodeRecord:
    commit: str
    command: str
    environment_image: str = ""
    dependency_hash: str = ""


@dataclass
class MetricRecord:
    name: str
    value: float
    direction: str
    source_artifact: str


@dataclass
class ArtifactRecord:
    path: str
    role: str
    sha256: str = ""
    simulated: bool = False
    simulation_label: str = ""


@dataclass
class DecisionRecord:
    decision_id: str
    selected: str
    rejected: list[str] = field(default_factory=list)
    selection_rule: str = ""
    human_reviewer: str = ""


@dataclass
class LineageLedger:
    run_id: str
    schema_version: int = 1
    datasets: list[DatasetRecord] = field(default_factory=list)
    code: list[CodeRecord] = field(default_factory=list)
    metrics: list[MetricRecord] = field(default_factory=list)
    artifacts: list[ArtifactRecord] = field(default_factory=list)
    decisions: list[DecisionRecord] = field(default_factory=list)

    def add_dataset(
        self,
        *,
        name: str,
        version: str,
        split: str,
        source: str,
        path: str | Path | None = None,
        leakage_status: str = "unknown",
    ) -> DatasetRecord:
        sha256 = hash_file(path) if path and Path(path).is_file() else ""
        record = DatasetRecord(
            name=name,
            version=version,
            split=split,
            source=source,
            path=str(path or ""),
            sha256=sha256,
            leakage_status=leakage_status,
        )
        self.datasets.append(record)
        return record

    def add_code(
        self,
        *,
        commit: str,
        command: str,
        environment_image: str = "",
        dependency_hash: str = "",
    ) -> CodeRecord:
        record = CodeRecord(
            commit=commit,
            command=command,
            environment_image=environment_image,
            dependency_hash=dependency_hash,
        )
        self.code.append(record)
        return record

    def add_metric(
        self,
        *,
        name: str,
        value: float,
        direction: str,
        source_artifact: str,
    ) -> MetricRecord:
        record = MetricRecord(name=name, value=float(value), direction=direction, source_artifact=source_artifact)
        self.metrics.append(record)
        return record

    def add_artifact(
        self,
        *,
        path: str | Path,
        role: str,
        simulated: bool = False,
        simulation_label: str = "",
    ) -> ArtifactRecord:
        file_path = Path(path)
        record = ArtifactRecord(
            path=str(path),
            role=role,
            sha256=hash_file(file_path) if file_path.is_file() else "",
            simulated=simulated,
            simulation_label=simulation_label,
        )
        self.artifacts.append(record)
        return record

    def add_decision(
        self,
        *,
        decision_id: str,
        selected: str,
        rejected: list[str] | tuple[str, ...] = (),
        selection_rule: str = "",
        human_reviewer: str = "",
    ) -> DecisionRecord:
        record = DecisionRecord(
            decision_id=decision_id,
            selected=selected,
            rejected=list(rejected),
            selection_rule=selection_rule,
            human_reviewer=human_reviewer,
        )
        self.decisions.append(record)
        return record

    def validate(self) -> list[LineageIssue]:
        issues: list[LineageIssue] = []
        for dataset in self.datasets:
            if dataset.path and not dataset.sha256:
                issues.append(LineageIssue("error", "dataset path is not content hashed", "dataset", dataset.name))
            if dataset.leakage_status in {"", "unknown"}:
                issues.append(LineageIssue("warning", "dataset leakage status is unknown", "dataset", dataset.name))
        for artifact in self.artifacts:
            if artifact.path and not artifact.sha256:
                issues.append(LineageIssue("error", "artifact path is not content hashed", "artifact", artifact.path))
            if artifact.simulated and not artifact.simulation_label:
                issues.append(LineageIssue("error", "simulated artifact lacks an explicit simulation label", "artifact", artifact.path))
        for metric in self.metrics:
            if metric.direction not in {"maximize", "minimize", "neutral"}:
                issues.append(LineageIssue("error", "metric direction must be maximize, minimize, or neutral", "metric", metric.name))
            if not metric.source_artifact:
                issues.append(LineageIssue("error", "metric source artifact is missing", "metric", metric.name))
        for decision in self.decisions:
            if not decision.selection_rule:
                issues.append(LineageIssue("error", "decision selection rule is missing", "decision", decision.decision_id))
        return issues

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LineageLedger":
        ledger = cls(run_id=str(data.get("run_id") or ""), schema_version=int(data.get("schema_version") or 1))
        ledger.datasets = [DatasetRecord(**item) for item in data.get("datasets", []) if isinstance(item, dict)]
        ledger.code = [CodeRecord(**item) for item in data.get("code", []) if isinstance(item, dict)]
        ledger.metrics = [MetricRecord(**item) for item in data.get("metrics", []) if isinstance(item, dict)]
        ledger.artifacts = [ArtifactRecord(**item) for item in data.get("artifacts", []) if isinstance(item, dict)]
        ledger.decisions = [DecisionRecord(**item) for item in data.get("decisions", []) if isinstance(item, dict)]
        return ledger

    def write_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @classmethod
    def read_json(cls, path: str | Path) -> "LineageLedger":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
