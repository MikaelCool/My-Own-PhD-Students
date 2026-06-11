"""Lightweight tracing primitives for research runs.

The module deliberately uses only the standard library so tracing can be
enabled in local, SSH, Docker, and CI execution without optional services.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def hash_file(path: str | Path) -> str:
    """Return the SHA-256 hash for a file."""
    file_path = Path(path)
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utcnow_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass(frozen=True)
class TraceContext:
    """Context carried across model, tool, artifact, and decision events."""

    trace_id: str
    span_id: str
    parent_span_id: str = ""
    run_id: str = ""
    stage: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def start(
        cls,
        *,
        run_id: str = "",
        stage: int | None = None,
        trace_id: str = "",
        parent_span_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> "TraceContext":
        """Create a new trace context."""
        return cls(
            trace_id=trace_id or uuid.uuid4().hex,
            span_id=uuid.uuid4().hex[:16],
            parent_span_id=parent_span_id,
            run_id=run_id,
            stage=stage,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TraceContext | None":
        """Build a context from serialized data, returning None on bad input."""
        if not isinstance(data, dict):
            return None
        trace_id = str(data.get("trace_id") or "").strip()
        span_id = str(data.get("span_id") or "").strip()
        if not trace_id or not span_id:
            return None
        stage_raw = data.get("stage")
        try:
            stage = int(stage_raw) if stage_raw is not None and stage_raw != "" else None
        except (TypeError, ValueError):
            stage = None
        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        return cls(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=str(data.get("parent_span_id") or ""),
            run_id=str(data.get("run_id") or ""),
            stage=stage,
            metadata=dict(metadata),
        )

    def child(self, *, stage: int | None = None, metadata: dict[str, Any] | None = None) -> "TraceContext":
        """Create a child span under the current trace."""
        merged = dict(self.metadata)
        if metadata:
            merged.update(metadata)
        return TraceContext.start(
            trace_id=self.trace_id,
            parent_span_id=self.span_id,
            run_id=self.run_id,
            stage=self.stage if stage is None else stage,
            metadata=merged,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the context."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "run_id": self.run_id,
            "stage": self.stage,
            "metadata": dict(self.metadata),
        }

    def event(
        self,
        event_type: str,
        *,
        payload: dict[str, Any] | None = None,
        model: str = "",
        prompt_version: str = "",
        latency_ms: float | None = None,
        token_input: int | None = None,
        token_output: int | None = None,
        cost_usd: float | None = None,
        artifact_paths: list[str | Path] | tuple[str | Path, ...] | None = None,
        decision_reason: str = "",
        rollback_reason: str = "",
    ) -> dict[str, Any]:
        """Create a normalized event payload."""
        token_total = None
        if token_input is not None or token_output is not None:
            token_total = int(token_input or 0) + int(token_output or 0)

        artifact_hashes: dict[str, str] = {}
        for path in artifact_paths or ():
            file_path = Path(path)
            if file_path.is_file():
                artifact_hashes[str(file_path)] = hash_file(file_path)

        event: dict[str, Any] = {
            "event_type": event_type,
            "timestamp": _utcnow_iso(),
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "run_id": self.run_id,
            "stage": self.stage,
            "model": model or str(self.metadata.get("model") or ""),
            "prompt_version": prompt_version or str(self.metadata.get("prompt_version") or ""),
            "latency_ms": latency_ms,
            "token_input": token_input,
            "token_output": token_output,
            "token_total": token_total,
            "cost_usd": cost_usd,
            "artifact_hashes": artifact_hashes,
            "decision_reason": decision_reason,
            "rollback_reason": rollback_reason,
            "metadata": dict(self.metadata),
        }
        if payload:
            event.update(payload)
        return event
