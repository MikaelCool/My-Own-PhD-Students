"""Process-level trajectories for future agent optimization."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Transition:
    state: dict[str, Any]
    action: dict[str, Any]
    artifact_refs: list[str] = field(default_factory=list)
    reward: dict[str, float] = field(default_factory=dict)
    cost: dict[str, float | int] = field(default_factory=dict)
    next_state: dict[str, Any] = field(default_factory=dict)
    terminal: bool = False

    @property
    def reward_total(self) -> float:
        return float(sum(self.reward.values()))


@dataclass
class Trajectory:
    run_id: str
    schema_version: int = 1
    transitions: list[Transition] = field(default_factory=list)

    def add(self, transition: Transition) -> None:
        self.transitions.append(transition)

    @property
    def reward_total(self) -> float:
        return float(sum(transition.reward_total for transition in self.transitions))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "reward_total": self.reward_total,
            "transitions": [asdict(transition) for transition in self.transitions],
        }

    def to_jsonl(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True) + "\n"
