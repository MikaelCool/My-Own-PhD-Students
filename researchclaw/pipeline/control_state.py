from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from researchclaw.config import RCConfig
from researchclaw.observability.tracing import TraceContext
from researchclaw.pipeline.stages import ControlAction, Stage, StageStatus

CONTROL_STATE_FILENAME = "run_control_state.json"
RUN_INDEX_FILENAME = "run_index.json"


def control_state_path(run_dir: Path) -> Path:
    return run_dir / CONTROL_STATE_FILENAME


def run_index_path(run_dir: Path) -> Path:
    return run_dir / RUN_INDEX_FILENAME


def read_control_state(run_dir: Path) -> dict[str, Any]:
    path = control_state_path(run_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def append_run_index_event(
    run_dir: Path,
    *,
    event: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = run_index_path(run_dir)
    data: dict[str, Any] = {"schema_version": 1, "events": []}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            data = {"schema_version": 1, "events": []}
    events = data.get("events")
    if not isinstance(events, list):
        events = []
        data["events"] = events
    event_payload: dict[str, Any] = {
        "event": event,
        "timestamp": _utcnow_iso(),
    }
    if isinstance(payload, dict):
        event_payload.update(payload)
    events.append(event_payload)
    data["schema_version"] = 1
    _atomic_write_json(path, data)
    return event_payload


def append_supervisor_event(
    run_dir: Path,
    *,
    event_type: str,
    status: str = "info",
    summary: str = "",
    stage: int | None = None,
    stage_name: str = "",
    substep: str = "",
    action: str = "",
    backend: str = "",
    waiting_reason: str = "",
    alerts: list[str] | tuple[str, ...] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    control = read_control_state(run_dir)
    observer_summary = summarize_control_state(run_dir, control) if control else {}
    merged_alerts: list[str] = []
    for item in alerts or ():
        if isinstance(item, str) and item.strip():
            merged_alerts.append(item.strip())
    existing_alerts = observer_summary.get("alerts")
    if isinstance(existing_alerts, list):
        for item in existing_alerts:
            if isinstance(item, str) and item.strip():
                merged_alerts.append(item.strip())
    merged_alerts = list(dict.fromkeys(merged_alerts))

    current_stage = int(
        stage
        if stage is not None
        else control.get("current_stage")
        or observer_summary.get("current_stage")
        or 0
    )
    current_stage_name = (
        stage_name
        or str(control.get("current_stage_name") or observer_summary.get("current_stage_name") or "")
    )
    current_substep = (
        substep
        or str(control.get("current_substep") or observer_summary.get("current_substep") or "")
    )
    event_payload: dict[str, Any] = {
        "event_type": event_type,
        "status": status,
        "summary": summary or str(observer_summary.get("headline") or event_type),
        "stage": current_stage,
        "stage_name": current_stage_name,
        "substep": current_substep,
        "action": action or str(control.get("current_action") or ""),
        "backend": backend or str(control.get("active_session_backend") or ""),
        "waiting_reason": waiting_reason or str(control.get("waiting_reason") or ""),
        "alerts": merged_alerts,
    }
    if isinstance(payload, dict):
        event_payload.update(payload)
    trace = TraceContext.from_dict(event_payload.get("trace") if isinstance(event_payload.get("trace"), dict) else None)
    if trace is not None:
        event_payload.setdefault("trace_id", trace.trace_id)
        event_payload.setdefault("span_id", trace.span_id)
        event_payload.setdefault("parent_span_id", trace.parent_span_id)
        event_payload.setdefault("run_id", trace.run_id)
        if trace.stage is not None:
            event_payload.setdefault("trace_stage", trace.stage)
    return append_run_index_event(
        run_dir,
        event="supervisor_event",
        payload=event_payload,
    )


def recent_supervisor_events(run_dir: Path, *, limit: int = 8) -> list[dict[str, Any]]:
    path = run_index_path(run_dir)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return []
    events = payload.get("events")
    if not isinstance(events, list):
        return []
    recent: list[dict[str, Any]] = []
    for item in reversed(events):
        if not isinstance(item, dict):
            continue
        if item.get("event") != "supervisor_event":
            continue
        recent.append(item)
        if len(recent) >= max(limit, 1):
            break
    recent.reverse()
    return recent


def summarize_control_state(
    run_dir: Path,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = state if isinstance(state, dict) else read_control_state(run_dir)
    observers = payload.get("observers") if isinstance(payload.get("observers"), dict) else {}
    stage_progress = observers.get("stage_progress") if isinstance(observers.get("stage_progress"), dict) else {}
    session_health = observers.get("session_health") if isinstance(observers.get("session_health"), dict) else {}
    resource_state = observers.get("resource_state") if isinstance(observers.get("resource_state"), dict) else {}
    risk_flags = observers.get("risk_flags") if isinstance(observers.get("risk_flags"), list) else []

    latest_stage = payload.get("latest_stage_result") if isinstance(payload.get("latest_stage_result"), dict) else {}
    current_stage = int(
        payload.get("current_stage")
        or stage_progress.get("current_stage")
        or latest_stage.get("stage")
        or 0
    )
    current_stage_name = str(
        payload.get("current_stage_name")
        or stage_progress.get("current_stage_name")
        or latest_stage.get("stage_name")
        or ""
    )
    current_substep = str(
        payload.get("current_substep")
        or stage_progress.get("current_substep")
        or ""
    )
    waiting_reason = str(
        payload.get("waiting_reason")
        or stage_progress.get("waiting_reason")
        or resource_state.get("waiting_reason")
        or ""
    ).strip()

    stage12_observer = _read_json(run_dir / "stage-12" / "runtime_observer.json")
    stage13_bundle = _read_json(run_dir / "stage-13" / "refine_diagnostic_bundle.json")
    if not stage13_bundle:
        stage13_candidates = sorted(run_dir.glob("stage-13*/refine_diagnostic_bundle.json"), reverse=True)
        if stage13_candidates:
            stage13_bundle = _read_json(stage13_candidates[0])

    alerts: list[str] = []
    headline = ""

    dataset_readiness = (
        stage12_observer.get("dataset_readiness")
        if isinstance(stage12_observer.get("dataset_readiness"), dict)
        else {}
    )
    gpu_availability = (
        stage12_observer.get("gpu_availability")
        if isinstance(stage12_observer.get("gpu_availability"), dict)
        else {}
    )
    runtime_watchdog = (
        stage12_observer.get("runtime_watchdog")
        if isinstance(stage12_observer.get("runtime_watchdog"), dict)
        else {}
    )
    stage13_aggregates = (
        stage13_bundle.get("aggregates")
        if isinstance(stage13_bundle.get("aggregates"), dict)
        else {}
    )

    dataset_status = str(dataset_readiness.get("status") or "")
    gpu_status = str(gpu_availability.get("status") or "")
    watchdog_status = str(runtime_watchdog.get("status") or "")

    if waiting_reason:
        headline = waiting_reason
    elif current_stage == 12 and dataset_status in {"blocked", "warning"}:
        headline = str(dataset_readiness.get("summary") or "Stage 12 dataset readiness needs attention.")
    elif current_stage == 12 and gpu_status in {"waiting", "busy", "unknown"}:
        headline = str(gpu_availability.get("summary") or "Stage 12 is waiting for GPU availability.")
    elif current_stage == 12 and watchdog_status in {"timed_out", "near_budget", "failed", "heartbeat_stale"}:
        headline = str(runtime_watchdog.get("summary") or "Stage 12 runtime watchdog reported risk.")
    elif current_stage == 13 and stage13_aggregates:
        dominant_failures = stage13_aggregates.get("dominant_failure_types") or []
        if isinstance(dominant_failures, list) and dominant_failures:
            headline = (
                "Stage 13 refining against dominant failures: "
                + ", ".join(str(item) for item in dominant_failures[:3])
            )
    elif current_substep:
        headline = f"{current_stage_name or 'Pipeline'} @ {current_substep}"
    else:
        headline = current_stage_name or "Pipeline state available"

    if dataset_status in {"blocked", "warning"}:
        alerts.append(f"dataset:{dataset_status}")
    if gpu_status in {"waiting", "busy", "unknown"}:
        alerts.append(f"gpu:{gpu_status}")
    if watchdog_status in {"timed_out", "near_budget", "failed", "heartbeat_stale"}:
        alerts.append(f"watchdog:{watchdog_status}")
    for flag in risk_flags:
        if isinstance(flag, str):
            alerts.append(flag)
    alerts = list(dict.fromkeys(alerts))

    return {
        "headline": headline,
        "alerts": alerts,
        "current_stage": current_stage,
        "current_stage_name": current_stage_name,
        "current_substep": current_substep,
        "active_session_backend": str(payload.get("active_session_backend") or ""),
        "waiting_reason": waiting_reason,
        "observer_details": {
            "dataset_readiness": dataset_readiness,
            "gpu_availability": gpu_availability,
            "runtime_watchdog": runtime_watchdog,
            "stage13_aggregates": stage13_aggregates,
            "session_health": session_health,
            "session_backend_state": payload.get("session_backend_state", {}),
        },
    }


def active_backend_name(config: RCConfig) -> str:
    provider = str(getattr(config.llm, "provider", "") or "").strip().lower()
    if provider == "acp":
        agent = str(getattr(config.llm.acp, "agent", "") or "").strip() or "unknown"
        return f"acp:{agent}"
    if provider:
        return provider
    return "unknown"


def write_control_state(
    run_dir: Path,
    *,
    merge: bool = True,
    **updates: Any,
) -> dict[str, Any]:
    current = read_control_state(run_dir) if merge else {}
    payload = _deep_merge(current, updates)
    payload["schema_version"] = 1
    payload["updated_at"] = _utcnow_iso()
    _atomic_write_json(control_state_path(run_dir), payload)
    return payload


def update_notification_state(
    run_dir: Path,
    *,
    subject: str,
    status: str,
    error: str = "",
) -> dict[str, Any]:
    state = read_control_state(run_dir)
    attempts = int(
        (((state.get("notification_state") or {}) if isinstance(state, dict) else {}).get("attempt_count"))
        or 0
    )
    return write_control_state(
        run_dir,
        notification_state={
            "last_subject": subject,
            "last_status": status,
            "last_error": error,
            "last_attempt_at": _utcnow_iso(),
            "attempt_count": attempts + 1,
        },
    )


def stage_observer_snapshot(
    run_dir: Path,
    *,
    stage: Stage | None = None,
    run_id: str = "",
    result: Any | None = None,
    stage_dir: Path | None = None,
    artifact_refs: tuple[str, ...] | list[str] | None = None,
    current_action: ControlAction | str | None = None,
    status: StageStatus | str | None = None,
    substep: str | None = None,
    waiting_reason: str = "",
) -> dict[str, Any]:
    heartbeat = _read_json(run_dir / "heartbeat.json")
    checkpoint = _read_json(run_dir / "checkpoint.json")
    stop_requested = (run_dir / "STOP_REQUESTED.json").exists()
    artifact_manifest = _build_artifact_manifest(stage_dir, artifact_refs or ())
    notification_state = read_control_state(run_dir).get("notification_state", {})
    backend = str(read_control_state(run_dir).get("active_session_backend") or "unknown")
    heartbeat_ts = str(heartbeat.get("timestamp") or "")
    heartbeat_age_sec = _age_sec(heartbeat_ts)
    stage_value = int(stage) if stage is not None else checkpoint.get("stage")
    stage_name = stage.name if stage is not None else str(checkpoint.get("stage_name") or "")
    normalized_status = (
        status.value if isinstance(status, StageStatus) else (str(status) if status else "")
    )
    action_value = (
        current_action.value
        if isinstance(current_action, ControlAction)
        else (str(current_action) if current_action else "")
    )
    result_error = getattr(result, "error", None) if result is not None else None
    result_decision = getattr(result, "decision", None) if result is not None else None
    return {
        "stage_progress": {
            "run_id": run_id or str(read_control_state(run_dir).get("run_id") or ""),
            "current_stage": stage_value,
            "current_stage_name": stage_name,
            "current_substep": substep or str(read_control_state(run_dir).get("current_substep") or ""),
            "status": normalized_status,
            "decision": result_decision or "",
            "stop_requested": stop_requested,
            "waiting_reason": waiting_reason,
        },
        "session_health": {
            "backend": backend,
            "heartbeat_present": bool(heartbeat),
            "heartbeat_age_sec": heartbeat_age_sec,
            "healthy": heartbeat_age_sec is None or heartbeat_age_sec <= 300,
            "last_heartbeat_at": heartbeat_ts,
        },
        "artifact_integrity": {
            "artifact_count": len(artifact_manifest),
            "artifacts": artifact_manifest,
            "healthy": all(item.get("exists", False) for item in artifact_manifest),
        },
        "notification_delivery": {
            "last_subject": str(notification_state.get("last_subject") or ""),
            "last_status": str(notification_state.get("last_status") or "unknown"),
            "last_error": str(notification_state.get("last_error") or ""),
        },
        "resource_state": {
            "waiting": action_value == ControlAction.WAIT_FOR_RESOURCE.value,
            "waiting_reason": waiting_reason,
        },
        "risk_flags": _risk_flags(
            stop_requested=stop_requested,
            heartbeat_age_sec=heartbeat_age_sec,
            status=normalized_status,
            error=str(result_error or ""),
            notification_state=notification_state if isinstance(notification_state, dict) else {},
        ),
    }


def control_action_for_result(result: Any) -> ControlAction:
    status = getattr(result, "status", None)
    decision = str(getattr(result, "decision", "") or "").strip().lower()
    if status == StageStatus.BLOCKED_APPROVAL:
        return ControlAction.REQUEST_HUMAN_GATE
    if status == StageStatus.FAILED:
        if decision in {"pivot", "rework_innovation"}:
            return ControlAction.PIVOT_HYPOTHESIS
        if decision in {"rollback", "redo"}:
            return ControlAction.ROLLBACK_TO_STAGE
        if "repair" in decision:
            return ControlAction.REPAIR_LOCAL_BLOCK
        return ControlAction.RETRY_SAME_STEP
    if decision == "pivot":
        return ControlAction.PIVOT_HYPOTHESIS
    if decision in {"refine", "rollback"}:
        return ControlAction.ROLLBACK_TO_STAGE
    if decision == "degraded":
        return ControlAction.PROCEED
    return ControlAction.PROCEED


def action_for_code_agent(next_action: str) -> ControlAction:
    lowered = (next_action or "").strip().lower()
    if any(token in lowered for token in ("repair", "fix")):
        return ControlAction.REPAIR_LOCAL_BLOCK
    if "review" in lowered:
        return ControlAction.PROCEED
    if "sandbox" in lowered or "run" in lowered:
        return ControlAction.PROCEED
    return ControlAction.PROCEED


def write_code_agent_control_state(
    run_dir: Path,
    *,
    stage: Stage,
    phase: str,
    phase_substate: str,
    next_action: str,
    current_file: str,
    file_index: int | None,
    blueprint_index: int | None,
    file_manifest: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    waiting_reason = ""
    substep = f"code_agent:{phase}/{phase_substate}" if phase or phase_substate else "code_agent"
    observers = stage_observer_snapshot(
        run_dir,
        stage=stage,
        substep=substep,
        current_action=action_for_code_agent(next_action),
        waiting_reason=waiting_reason,
        artifact_refs=(),
    )
    return write_control_state(
        run_dir,
        current_stage=int(stage),
        current_stage_name=stage.name,
        current_substep=substep,
        current_action=action_for_code_agent(next_action).value,
        code_agent={
            "phase": phase,
            "phase_substate": phase_substate,
            "next_action": next_action,
            "current_file": current_file,
            "file_index": file_index,
            "blueprint_index": blueprint_index,
            "file_manifest": file_manifest or [],
        },
        observers=observers,
    )


def _risk_flags(
    *,
    stop_requested: bool,
    heartbeat_age_sec: float | None,
    status: str,
    error: str,
    notification_state: dict[str, Any],
) -> list[str]:
    flags: list[str] = []
    if stop_requested:
        flags.append("stop_requested")
    if heartbeat_age_sec is not None and heartbeat_age_sec > 300:
        flags.append("heartbeat_stale")
    if status == StageStatus.FAILED.value:
        flags.append("stage_failed")
    if error:
        flags.append("has_error")
    if str(notification_state.get("last_status") or "") == "failed":
        flags.append("notification_failed")
    return flags


def _build_artifact_manifest(
    stage_dir: Path | None,
    artifact_refs: tuple[str, ...] | list[str],
) -> list[dict[str, Any]]:
    if stage_dir is None:
        return []
    manifest: list[dict[str, Any]] = []
    for artifact in artifact_refs:
        path = stage_dir / str(artifact)
        entry: dict[str, Any] = {
            "artifact": str(artifact),
            "path": str(path),
            "exists": path.exists(),
        }
        if path.is_file():
            try:
                data = path.read_bytes()
                stat = path.stat()
                entry.update(
                    {
                        "kind": "file",
                        "size": stat.st_size,
                        "mtime_ns": stat.st_mtime_ns,
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
            except OSError:
                entry["kind"] = "file"
        elif path.is_dir():
            try:
                count = sum(1 for _ in path.rglob("*"))
            except OSError:
                count = 0
            entry.update({"kind": "dir", "entry_count": count})
        manifest.append(entry)
    return manifest


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _age_sec(ts: str) -> float | None:
    if not ts:
        return None
    try:
        from datetime import datetime, timezone

        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return max((datetime.now(timezone.utc) - dt).total_seconds(), 0.0)
    except Exception:
        return None


def _deep_merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        if (
            isinstance(value, dict)
            and isinstance(merged.get(key), dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.stem}.",
        suffix=".tmp",
    )
    os.close(fd)
    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, indent=2, ensure_ascii=False))
        Path(tmp_path).replace(path)
    except BaseException:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def _utcnow_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")
