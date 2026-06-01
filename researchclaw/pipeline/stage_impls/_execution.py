"""Stages 11-13: Resource planning, experiment execution, and iterative refinement."""

from __future__ import annotations

import ast
import difflib
import json
import logging
import math
import os
import re
import subprocess
import sys
import tempfile
import time as _time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from researchclaw.adapters import AdapterBundle
from researchclaw.config import RCConfig
from researchclaw.experiment.validator import (
    CodeValidation,
    format_issues_for_llm,
    validate_code,
)
from researchclaw.llm.client import LLMClient
from researchclaw.pipeline._domain import _detect_domain
from researchclaw.pipeline._helpers import (
    StageResult,
    _chat_with_prompt,
    _detect_runtime_issues,
    _ensure_sandbox_deps,
    _extract_hypothesis_claims,
    _extract_code_block,
    _extract_multi_file_blocks,
    _get_evolution_overlay,
    _load_hardware_profile,
    _parse_metrics_from_stdout,
    _read_prior_artifact,
    _safe_filename,
    _safe_json_loads,
    _utcnow_iso,
    _write_stage_meta,
)
from researchclaw.pipeline.control_state import (
    append_supervisor_event,
    stage_observer_snapshot,
    write_control_state,
)
from researchclaw.pipeline.research_governor import build_phase_charter, build_stage_skill_overlay
from researchclaw.pipeline.stages import ControlAction, Stage, StageStatus
from researchclaw.prompts import PromptManager

logger = logging.getLogger(__name__)


def _metric_is_better(
    metric_direction: str,
    candidate: float | None,
    current: float | None,
) -> bool:
    if candidate is None:
        return False
    if current is None:
        return True
    if metric_direction == "maximize":
        return candidate > current
    return candidate < current


def _query_stage12_gpu_inventory() -> list[dict[str, Any]]:
    try:
        from researchclaw.experiment.sandbox import _query_gpu_inventory

        inventory = _query_gpu_inventory()
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(inventory, list):
        return []
    return [item for item in inventory if isinstance(item, dict)]


def _read_heartbeat_age_sec(run_dir: Path) -> float | None:
    heartbeat_path = run_dir / "heartbeat.json"
    if not heartbeat_path.is_file():
        return None
    heartbeat = _safe_json_loads(heartbeat_path.read_text(encoding="utf-8"), {})
    if not isinstance(heartbeat, dict):
        return None
    raw = str(heartbeat.get("timestamp") or "").strip()
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max((datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds(), 0.0)


def _selected_stage12_benchmarks(run_dir: Path) -> list[dict[str, Any]]:
    benchmark_plan_path = run_dir / "stage-09" / "benchmark_plan.json"
    if not benchmark_plan_path.is_file():
        return []
    payload = _safe_json_loads(benchmark_plan_path.read_text(encoding="utf-8"), {})
    selected = payload.get("selected_benchmarks") if isinstance(payload, dict) else []
    if not isinstance(selected, list):
        return []
    return [item for item in selected if isinstance(item, dict)]


def _build_stage12_dataset_readiness_observer(
    *,
    run_dir: Path,
    exp_dir: Path | None,
    preflight_errors: list[str],
    preflight_warnings: list[str],
) -> dict[str, Any]:
    file_text: dict[str, str] = {}
    if exp_dir is not None and exp_dir.is_dir():
        for path in sorted(exp_dir.glob("*.py")):
            try:
                file_text[path.name] = path.read_text(encoding="utf-8")
            except OSError:
                continue
    all_code = "\n\n".join(file_text.values())
    setup_exists = bool(exp_dir and (exp_dir / "setup.py").exists())
    requirements_exists = bool(exp_dir and (exp_dir / "requirements.txt").exists())
    uses_hf_dataset = "load_dataset(" in all_code
    local_files_only = "local_files_only=True" in all_code
    selected_benchmarks = _selected_stage12_benchmarks(run_dir)
    tier2_names: list[str] = []
    declared_datasets: list[str] = []
    for item in selected_benchmarks:
        name = str(item.get("name") or "").strip()
        if name:
            declared_datasets.append(name)
        tier = item.get("tier", item.get("download_tier", 0))
        try:
            if int(tier) >= 2 and name:
                tier2_names.append(name)
        except (TypeError, ValueError):
            continue

    lowered_errors = " ".join(preflight_errors).lower()
    lowered_warnings = " ".join(preflight_warnings).lower()
    if "dataset" in lowered_errors or "setup.py is missing" in lowered_errors:
        status = "blocked"
        summary = "Dataset preparation is blocked by preflight errors."
    elif "dataset" in lowered_warnings or "huggingface datasets" in lowered_warnings:
        status = "warning"
        summary = "Dataset preparation may still hit runtime/network risks."
    elif uses_hf_dataset or tier2_names or declared_datasets:
        status = "ready"
        summary = "Dataset requirements are declared before runtime execution."
    else:
        status = "not_applicable"
        summary = "No explicit dataset preparation requirements were detected."

    return {
        "status": status,
        "summary": summary,
        "uses_huggingface_datasets": uses_hf_dataset,
        "local_files_only": local_files_only,
        "setup_py_present": setup_exists,
        "requirements_txt_present": requirements_exists,
        "tier2_datasets": sorted(set(tier2_names)),
        "declared_datasets": sorted(set(declared_datasets)),
        "preflight_error_count": len(preflight_errors),
        "preflight_warning_count": len(preflight_warnings),
    }


def _build_stage12_gpu_availability_observer(
    *,
    config: RCConfig,
    schedule_text: str,
    run_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    schedule = _safe_json_loads(schedule_text or "{}", {})
    requested_budget = schedule.get("total_gpu_budget") if isinstance(schedule, dict) else None
    try:
        requested_budget_int = int(requested_budget) if requested_budget is not None else 0
    except (TypeError, ValueError):
        requested_budget_int = 0
    requested_budget_int = max(0, min(requested_budget_int, 3))

    allowed_ids = tuple(int(g) for g in getattr(config.experiment.sandbox, "gpu_allowed_ids", ()) or ())
    inventory = _query_stage12_gpu_inventory()
    filtered_inventory = [
        gpu for gpu in inventory
        if int(gpu.get("index", -1)) <= 6 and (not allowed_ids or int(gpu.get("index", -1)) in allowed_ids)
    ]
    idle_gpu_ids = [
        int(gpu.get("index", -1))
        for gpu in filtered_inventory
        if not list(gpu.get("compute_apps") or [])
    ]
    busy_gpu_ids = [
        int(gpu.get("index", -1))
        for gpu in filtered_inventory
        if list(gpu.get("compute_apps") or [])
    ]
    failure_text = ""
    if isinstance(run_payload, dict):
        failure_text = " ".join(
            str(run_payload.get(key) or "")
            for key in ("failure_type", "stderr", "stdout")
        ).lower()

    if idle_gpu_ids:
        status = "ready"
        summary = f"Process-free GPUs detected: {idle_gpu_ids[:3]}."
    elif not config.experiment.sandbox.gpu_required:
        status = "cpu_fallback"
        summary = "No idle GPU detected, but CPU fallback is allowed."
    elif filtered_inventory and ("idle gpu" in failure_text or "gpu wait" in failure_text):
        status = "waiting"
        summary = "All allowed GPUs are currently busy; runtime is waiting for a process-free card."
    elif filtered_inventory:
        status = "busy"
        summary = "GPU inventory is visible, but no process-free GPU is currently available."
    else:
        status = "unknown"
        summary = "GPU inventory is unavailable; nvidia-smi data could not be read."

    return {
        "status": status,
        "summary": summary,
        "gpu_required": bool(config.experiment.sandbox.gpu_required),
        "allowed_gpu_ids": list(allowed_ids),
        "requested_gpu_budget": requested_budget_int,
        "idle_gpu_ids": idle_gpu_ids[:3],
        "busy_gpu_ids": busy_gpu_ids,
        "inventory_visible": bool(filtered_inventory),
        "inventory": [
            {
                "index": int(gpu.get("index", -1)),
                "utilization": int(gpu.get("utilization", 0) or 0),
                "memory_used_mb": int(gpu.get("memory_used_mb", 0) or 0),
                "memory_total_mb": int(gpu.get("memory_total_mb", 0) or 0),
                "process_count": len(list(gpu.get("compute_apps") or [])),
            }
            for gpu in filtered_inventory
        ],
    }


def _build_stage12_runtime_watchdog_observer(
    *,
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    run_payload: dict[str, Any] | None,
    status: str,
) -> dict[str, Any]:
    payload = run_payload or {}
    elapsed_sec = payload.get("elapsed_sec")
    try:
        elapsed_float = float(elapsed_sec) if elapsed_sec is not None else None
    except (TypeError, ValueError):
        elapsed_float = None
    time_budget_sec = int(config.experiment.time_budget_sec or 0)
    budget_utilization = (
        (elapsed_float / time_budget_sec)
        if elapsed_float is not None and time_budget_sec > 0
        else None
    )
    near_budget = bool(
        budget_utilization is not None and budget_utilization >= 0.9
    )
    timed_out = bool(payload.get("timed_out", False))
    stop_requested_flag = (run_dir / "STOP_REQUESTED.json").exists()
    heartbeat_age_sec = _read_heartbeat_age_sec(run_dir)
    time_budget_warning_path = stage_dir / "time_budget_warning.json"

    if stop_requested_flag:
        watchdog_status = "stopped"
        summary = "A stop request was recorded during Stage 12."
    elif timed_out:
        watchdog_status = "timed_out"
        summary = "The experiment exceeded its time budget and timed out."
    elif near_budget:
        watchdog_status = "near_budget"
        summary = "The experiment consumed at least 90% of the configured time budget."
    elif status == "preflight":
        watchdog_status = "preflight"
        summary = "Stage 12 is still in preflight / readiness validation."
    elif status == "failed":
        watchdog_status = "failed"
        summary = "Stage 12 failed before exhausting the time budget."
    elif heartbeat_age_sec is not None and heartbeat_age_sec > 300:
        watchdog_status = "heartbeat_stale"
        summary = "Pipeline heartbeat is stale; watchdog confidence is degraded."
    elif status in {"completed", "partial", "simulated"}:
        watchdog_status = "healthy"
        summary = "Runtime stayed within the configured watchdog limits."
    else:
        watchdog_status = "active"
        summary = "Runtime watchdog has no hard signal yet, but execution metadata is being tracked."

    return {
        "status": watchdog_status,
        "summary": summary,
        "time_budget_sec": time_budget_sec,
        "elapsed_sec": elapsed_float,
        "budget_utilization": round(budget_utilization, 4) if budget_utilization is not None else None,
        "near_budget": near_budget,
        "timed_out": timed_out,
        "stop_requested": stop_requested_flag,
        "heartbeat_age_sec": round(heartbeat_age_sec, 2) if heartbeat_age_sec is not None else None,
        "time_budget_warning_present": time_budget_warning_path.is_file(),
    }


def _default_schedule(config: RCConfig, exp_plan: str) -> dict[str, Any]:
    """Build a minimal but actionable resource plan."""
    est_minutes = max(10, int(math.ceil(config.experiment.time_budget_sec / 60)))
    allowed_gpu_budget = min(3, len(config.experiment.sandbox.gpu_allowed_ids) or 7)
    return {
        "schema_version": 1,
        "generated": _utcnow_iso(),
        "execution_strategy": "use_up_to_three_process_free_gpus",
        "gpu_wait_policy": "wait_for_process_free_gpu_0_6_and_assign_up_to_three_idle",
        "checkpoint_strategy": "resume_from_latest_successful_stage_artifact",
        "estimated_total_minutes": est_minutes,
        "total_gpu_budget": allowed_gpu_budget,
        "tasks": [
            {
                "id": "primary_experiment",
                "name": "Run generated experiment code",
                "depends_on": [],
                "gpu_count": allowed_gpu_budget,
                "estimated_minutes": est_minutes,
                "priority": "high",
            }
        ],
        "plan_summary": (
            "Execute one primary experiment job using up to three process-free GPUs among gpu0-6. "
            "If no process-free GPU is available, wait and resume automatically when one, two, or three cards become free."
        ),
        "plan_source": "fallback",
        "exp_plan_present": bool(exp_plan.strip()),
    }


def _is_meaningful_schedule(schedule: dict[str, Any]) -> bool:
    tasks = schedule.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return False
    has_budget = isinstance(schedule.get("total_gpu_budget"), int)
    has_estimate = any(
        isinstance(task, dict)
        and isinstance(task.get("estimated_minutes"), (int, float))
        and task.get("estimated_minutes", 0) > 0
        for task in tasks
    )
    return has_budget and has_estimate


def _augment_stage12_error(error: str, run_payload: dict[str, Any] | None = None) -> str:
    message = str(error or "").strip()
    payload = run_payload or {}
    stderr = str(payload.get("stderr") or "")
    if (
        "This experiment requires CUDA as requested" in stderr
        or "CUDA requested by experiment but unavailable" in stderr
    ):
        torch_version = "unknown"
        torch_cuda = "unknown"
        cuda_visible = os.environ.get("CUDA_VISIBLE_DEVICES", "<unset>")
        try:
            import torch

            torch_version = getattr(torch, "__version__", "unknown")
            torch_cuda = str(getattr(torch.version, "cuda", None))
        except Exception:
            pass
        return (
            "CUDA requested by generated experiment but runtime CUDA is unavailable. "
            f"torch={torch_version}, torch_cuda={torch_cuda}, "
            f"CUDA_VISIBLE_DEVICES={cuda_visible}. "
            f"Original error: {stderr.splitlines()[-1] if stderr else message}"
        )
    return message


def _stage12_preflight(
    *,
    stage_dir: Path,
    run_dir: Path,
    exp_dir: Path,
    config: RCConfig,
    schedule_text: str,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    file_text: dict[str, str] = {}
    for path in sorted(exp_dir.glob("*.py")):
        try:
            file_text[path.name] = path.read_text(encoding="utf-8")
        except OSError:
            continue
    all_code = "\n\n".join(file_text.values())
    setup_exists = (exp_dir / "setup.py").exists()
    requirements_exists = (exp_dir / "requirements.txt").exists()
    contract_path = run_dir / "stage-10" / "experiment_contract.json"
    contract: dict[str, Any] = {}
    if contract_path.exists():
        try:
            payload = json.loads(contract_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                contract = payload
        except (json.JSONDecodeError, OSError):
            warnings.append("experiment_contract.json exists but could not be parsed.")

    benchmark_plan_path = run_dir / "stage-09" / "benchmark_plan.json"
    tier2_names: list[str] = []
    if benchmark_plan_path.exists():
        try:
            benchmark_plan = json.loads(benchmark_plan_path.read_text(encoding="utf-8"))
            selected = benchmark_plan.get("selected_benchmarks", [])
            if isinstance(selected, list):
                for item in selected:
                    if not isinstance(item, dict):
                        continue
                    tier = item.get("tier", item.get("download_tier", 0))
                    try:
                        if int(tier) >= 2:
                            tier2_names.append(str(item.get("name") or "unknown"))
                    except (TypeError, ValueError):
                        continue
        except (json.JSONDecodeError, OSError):
            pass

    if tier2_names and not setup_exists:
        errors.append(
            "Tier 2 datasets selected but setup.py is missing: "
            + ", ".join(sorted(set(tier2_names)))
        )
    if "load_dataset(" in all_code and not setup_exists:
        errors.append(
            "Experiment code uses HuggingFace datasets but setup.py is missing, "
            "so dataset preparation would be pushed into runtime."
        )
    if "load_dataset(" in all_code and "local_files_only=True" not in all_code:
        warnings.append(
            "HuggingFace datasets detected without local_files_only=True; runtime may still hit the network."
        )
    if any(token in all_code for token in ("bfloat16", "float16", "torch.float16", "torch.bfloat16")):
        if not any(marker in all_code for marker in (".to(x.dtype)", ".type_as(x)", "dtype=x.dtype")):
            warnings.append(
                "Mixed-precision code detected without explicit dtype-alignment markers; dtype mismatches may reappear."
            )
    if any(token in all_code for token in ("controller_optimizer", "policy_optimizer", "rl_dynamic_projection")):
        if "controller_params" not in all_code and "id(p) not in controller_params" not in all_code:
            warnings.append(
                "Controller-specific optimizer logic detected without an explicit parameter split; autograd version conflicts are likely."
            )

    schedule = _safe_json_loads(schedule_text or "{}", {})
    total_gpu_budget = schedule.get("total_gpu_budget") if isinstance(schedule, dict) else None
    if isinstance(total_gpu_budget, int) and total_gpu_budget > 3:
        warnings.append(
            f"Schedule requests {total_gpu_budget} GPUs, but runtime policy caps experiments at 3 idle GPUs."
        )
    if config.experiment.mode == "docker" and not requirements_exists:
        warnings.append(
            "requirements.txt is absent; Docker will infer dependencies heuristically."
        )
    if contract:
        if str(contract.get("primary_metric") or "") != str(config.experiment.metric_key):
            errors.append(
                f"Experiment contract metric ({contract.get('primary_metric')}) does not match config metric ({config.experiment.metric_key})."
            )
        try:
            contract_budget = int(contract.get("time_budget_sec", 0) or 0)
            if contract_budget and contract_budget != int(config.experiment.time_budget_sec):
                warnings.append(
                    f"Experiment contract time budget ({contract_budget}) differs from config ({config.experiment.time_budget_sec})."
                )
        except (TypeError, ValueError):
            pass

    (stage_dir / "preflight_report.json").write_text(
        json.dumps(
            {
                "generated": _utcnow_iso(),
                "mode": config.experiment.mode,
                "errors": errors,
                "warnings": warnings,
                "checks": {
                    "setup_py_present": setup_exists,
                    "requirements_txt_present": requirements_exists,
                    "experiment_contract_present": bool(contract),
                    "tier2_datasets": tier2_names,
                    "python_file_count": len(file_text),
                },
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return errors, warnings


def _write_stage12_runtime_observer(
    *,
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    schedule_text: str,
    exp_dir: Path | None,
    preflight_errors: list[str],
    preflight_warnings: list[str],
    run_payload: dict[str, Any] | None,
    status: str,
) -> None:
    schedule = _safe_json_loads(schedule_text or "{}", {})
    payload = run_payload or {}
    dataset_readiness = _build_stage12_dataset_readiness_observer(
        run_dir=run_dir,
        exp_dir=exp_dir,
        preflight_errors=preflight_errors,
        preflight_warnings=preflight_warnings,
    )
    gpu_availability = _build_stage12_gpu_availability_observer(
        config=config,
        schedule_text=schedule_text,
        run_payload=payload,
    )
    runtime_watchdog = _build_stage12_runtime_watchdog_observer(
        stage_dir=stage_dir,
        run_dir=run_dir,
        config=config,
        run_payload=payload,
        status=status,
    )
    observer = {
        "generated": _utcnow_iso(),
        "stage": int(Stage.EXPERIMENT_RUN),
        "status": status,
        "mode": config.experiment.mode,
        "experiment_source": {
            "has_experiment_dir": bool(exp_dir and exp_dir.is_dir()),
            "experiment_dir": str(exp_dir) if exp_dir is not None else "",
            "python_file_count": (
                len(list(exp_dir.glob("*.py")))
                if exp_dir is not None and exp_dir.is_dir()
                else 0
            ),
        },
        "resource_plan": {
            "execution_strategy": schedule.get("execution_strategy") if isinstance(schedule, dict) else "",
            "gpu_wait_policy": schedule.get("gpu_wait_policy") if isinstance(schedule, dict) else "",
            "total_gpu_budget": schedule.get("total_gpu_budget") if isinstance(schedule, dict) else None,
        },
        "preflight": {
            "errors": list(preflight_errors),
            "warnings": list(preflight_warnings),
            "ok": not preflight_errors,
        },
        "runtime_outcome": {
            "run_id": str(payload.get("run_id") or ""),
            "status": str(payload.get("status") or ""),
            "failure_type": str(payload.get("failure_type") or ""),
            "retryable": bool(payload.get("retryable", False)),
            "timed_out": bool(payload.get("timed_out", False)),
            "elapsed_sec": payload.get("elapsed_sec"),
            "metrics_keys": sorted((payload.get("metrics") or {}).keys()) if isinstance(payload.get("metrics"), dict) else [],
        },
        "dataset_readiness": dataset_readiness,
        "gpu_availability": gpu_availability,
        "runtime_watchdog": runtime_watchdog,
    }
    (stage_dir / "runtime_observer.json").write_text(
        json.dumps(observer, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _load_stage12_runtime_observer(run_dir: Path) -> dict[str, Any]:
    observer_path = run_dir / "stage-12" / "runtime_observer.json"
    if not observer_path.is_file():
        return {}
    return _safe_json_loads(observer_path.read_text(encoding="utf-8"), {})


def _build_stage13_diagnostic_bundle(
    *,
    stage_dir: Path,
    run_dir: Path,
    metric_key: str,
    metric_direction: str,
    baseline_metric: float | None,
    run_payloads: list[dict[str, Any]],
    exp_plan_text: str,
    condition_coverage_hint: str,
) -> str:
    runtime_observer = _load_stage12_runtime_observer(run_dir)
    recent_runs: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    failure_counts: dict[str, int] = {}
    timed_out_runs = 0
    no_metric_runs = 0

    for payload in run_payloads[:12]:
        metrics = payload.get("metrics")
        if not isinstance(metrics, dict):
            metrics = payload.get("key_metrics") if isinstance(payload.get("key_metrics"), dict) else {}
        metric_keys = sorted(metrics.keys()) if isinstance(metrics, dict) else []
        status = str(payload.get("status") or "unknown")
        failure_type = str(payload.get("failure_type") or "")
        timed_out = bool(payload.get("timed_out", False))
        if timed_out:
            timed_out_runs += 1
        if not metric_keys:
            no_metric_runs += 1
        status_counts[status] = status_counts.get(status, 0) + 1
        if failure_type:
            failure_counts[failure_type] = failure_counts.get(failure_type, 0) + 1
        recent_runs.append(
            {
                "run_id": str(payload.get("run_id") or ""),
                "status": status,
                "failure_type": failure_type,
                "timed_out": timed_out,
                "elapsed_sec": payload.get("elapsed_sec"),
                "metric_keys": metric_keys,
                "primary_metric": payload.get(metric_key, payload.get("primary_metric")),
                "stderr_tail": str(payload.get("stderr") or "")[-300:],
            }
        )

    dominant_failure_types = [
        name
        for name, _count in sorted(
            failure_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[:4]
    ]
    runtime_outcome = (
        runtime_observer.get("runtime_outcome")
        if isinstance(runtime_observer.get("runtime_outcome"), dict)
        else {}
    )
    dataset_readiness = (
        runtime_observer.get("dataset_readiness")
        if isinstance(runtime_observer.get("dataset_readiness"), dict)
        else {}
    )
    gpu_availability = (
        runtime_observer.get("gpu_availability")
        if isinstance(runtime_observer.get("gpu_availability"), dict)
        else {}
    )
    runtime_watchdog = (
        runtime_observer.get("runtime_watchdog")
        if isinstance(runtime_observer.get("runtime_watchdog"), dict)
        else {}
    )
    resource_plan = (
        runtime_observer.get("resource_plan")
        if isinstance(runtime_observer.get("resource_plan"), dict)
        else {}
    )
    preflight = (
        runtime_observer.get("preflight")
        if isinstance(runtime_observer.get("preflight"), dict)
        else {}
    )
    observer_failure_type = str(runtime_outcome.get("failure_type") or "")
    if not dominant_failure_types and observer_failure_type:
        dominant_failure_types = [observer_failure_type]

    guidance: list[str] = []
    if timed_out_runs:
        guidance.append(
            "Timeouts were observed. Reduce run scale, add earlier metric emission, and stop gracefully before the budget ceiling."
        )
    if "dataset_prep" in failure_counts:
        guidance.append(
            "Dataset preparation failed previously. Reuse the existing dataset contract and verify download/extract paths before training starts."
        )
    if "dtype_mismatch" in failure_counts:
        guidance.append(
            "Dtype mismatches were seen. Normalize tensor/device dtypes at data ingress and before the forward pass."
        )
    if no_metric_runs and no_metric_runs == len(recent_runs):
        guidance.append(
            "No runs produced metrics. Prioritize restoring metric logging before expanding the experiment design."
        )
    if str(dataset_readiness.get("status") or "") in {"blocked", "warning"}:
        guidance.append(
            "Resolve dataset readiness before another refine round. Keep download/setup in explicit preparation steps instead of deferring it to the main training loop."
        )
    if str(gpu_availability.get("status") or "") in {"waiting", "busy", "unknown"}:
        guidance.append(
            "Treat GPU availability as a first-class constraint. Reuse the idle-GPU policy and avoid starting a new attempt until the observer reports a process-free card."
        )
    if str(runtime_watchdog.get("status") or "") in {"timed_out", "near_budget", "heartbeat_stale"}:
        guidance.append(
            "Honor the runtime watchdog signals. Simplify the next attempt before adding new algorithmic branches."
        )
    if condition_coverage_hint:
        guidance.append(
            "Condition coverage is incomplete. Preserve planned condition names and emit per-condition labeled metrics."
        )
    if not guidance:
        guidance.append(
            "Preserve the experiment plan, change the minimum code required, and improve execution reliability before adding new complexity."
        )

    payload = {
        "generated": _utcnow_iso(),
        "stage": int(Stage.ITERATIVE_REFINE),
        "metric_key": metric_key,
        "metric_direction": metric_direction,
        "baseline_metric": baseline_metric,
        "runtime_observer": runtime_observer,
        "aggregates": {
            "run_count": len(run_payloads),
            "status_counts": status_counts,
            "timed_out_runs": timed_out_runs,
            "no_metric_runs": no_metric_runs,
            "dominant_failure_types": dominant_failure_types,
            "exp_plan_present": bool(exp_plan_text.strip()),
            "condition_coverage_gap": bool(condition_coverage_hint.strip()),
            "dataset_observer_status": str(dataset_readiness.get("status") or ""),
            "gpu_observer_status": str(gpu_availability.get("status") or ""),
            "watchdog_status": str(runtime_watchdog.get("status") or ""),
        },
        "recent_runs": recent_runs,
        "guidance": guidance,
    }
    (stage_dir / "refine_diagnostic_bundle.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines = [
        "# Stage 13 Diagnostic Bundle",
        "",
        "## Runtime Summary",
        f"- Metric: `{metric_key}` ({metric_direction})",
        f"- Baseline metric: `{baseline_metric}`",
        f"- Run count: {len(run_payloads)}",
        f"- Status counts: {json.dumps(status_counts, ensure_ascii=False)}",
        f"- Dominant failure types: {', '.join(dominant_failure_types) if dominant_failure_types else 'none'}",
        f"- Timed out runs: {timed_out_runs}",
        f"- Runs without metrics: {no_metric_runs}",
        "",
        "## Stage 12 Observer",
        f"- Observer status: {runtime_observer.get('status', 'unknown') if isinstance(runtime_observer, dict) else 'unknown'}",
        f"- Preflight ok: {preflight.get('ok') if isinstance(preflight, dict) else False}",
        f"- Execution strategy: {resource_plan.get('execution_strategy', '')}",
        f"- GPU wait policy: {resource_plan.get('gpu_wait_policy', '')}",
        f"- Last runtime outcome: {runtime_outcome.get('status', '')}",
        f"- Last failure type: {runtime_outcome.get('failure_type', '')}",
        f"- Dataset readiness: {dataset_readiness.get('status', '')}",
        f"- GPU availability: {gpu_availability.get('status', '')}",
        f"- Runtime watchdog: {runtime_watchdog.get('status', '')}",
    ]
    if condition_coverage_hint.strip():
        lines.extend(
            [
                "",
                "## Condition Coverage",
                "- Condition coverage gap detected from Stage 12 outputs.",
            ]
        )
    if recent_runs:
        lines.extend(["", "## Recent Runs"])
        for item in recent_runs[:8]:
            lines.append(
                "- "
                + json.dumps(
                    {
                        "run_id": item["run_id"],
                        "status": item["status"],
                        "failure_type": item["failure_type"],
                        "timed_out": item["timed_out"],
                        "metric_keys": item["metric_keys"],
                    },
                    ensure_ascii=False,
                )
            )
    lines.extend(["", "## Repair Guidance"])
    lines.extend(f"- {entry}" for entry in guidance)
    summary = "\n".join(lines)
    (stage_dir / "refine_diagnostic_bundle.md").write_text(
        summary,
        encoding="utf-8",
    )
    return summary


def _load_stage13_result_metric_keys(stage_dir: Path) -> list[str]:
    keys: set[str] = set()
    for results_path in sorted(
        list(stage_dir.glob("refine_sandbox_v*/_docker_project_*/results.json"))
        + list(stage_dir.glob("refine_sandbox_v*_fix/_docker_project_*/results.json"))
    ):
        payload = _safe_json_loads(results_path.read_text(encoding="utf-8"), {})
        metrics = payload.get("metrics") if isinstance(payload, dict) else {}
        if isinstance(metrics, dict):
            keys.update(str(key) for key in metrics if isinstance(key, str))
    return sorted(keys)


def _parse_stage13_screening_budget(config_text: str) -> dict[str, int | None]:
    def _match_int(pattern: str) -> int | None:
        match = re.search(pattern, config_text)
        if not match:
            return None
        try:
            return int(match.group(1))
        except (TypeError, ValueError):
            return None

    max_steps = _match_int(r"max_steps_screening(?:\s*:\s*[^=]+)?\s*=\s*(\d+)")
    probe_interval = _match_int(r"probe_interval(?:\s*:\s*[^=]+)?\s*=\s*(\d+)")
    estimated_probes = None
    if max_steps and probe_interval and probe_interval > 0:
        estimated_probes = max_steps // probe_interval
    return {
        "max_steps_screening": max_steps,
        "probe_interval": probe_interval,
        "estimated_probe_events": estimated_probes,
    }


def _infer_advantage_axes(text: str) -> list[str]:
    lowered = text.lower()
    axes: list[str] = []
    token_map = {
        "quality": ("quality", "accuracy", "validation", "error rate", "loss"),
        "vram": ("vram", "memory", "peak vram", "显存"),
        "time": ("time", "wall-clock", "overhead", "throughput", "latency", "速度"),
        "rank": ("rank", "average rank", "active rank", "low-rank"),
        "trigger": ("trigger", "controller", "probe", "retained energy", "agreement"),
    }
    for axis, tokens in token_map.items():
        if any(token in lowered for token in tokens):
            axes.append(axis)
    return axes or ["quality"]


def _select_best_condition(
    condition_names: list[str],
    means: dict[str, float],
    metric_direction: str,
) -> tuple[str, float] | None:
    best_name = ""
    best_metric: float | None = None
    for name in condition_names:
        metric = means.get(name)
        if metric is None:
            continue
        if _metric_is_better(metric_direction, metric, best_metric):
            best_name = name
            best_metric = metric
    if not best_name or best_metric is None:
        return None
    return best_name, best_metric


def _extract_method_change_summary(response_text: str) -> dict[str, Any]:
    for payload in re.findall(r"```json\s*(.*?)```", response_text, flags=re.DOTALL):
        parsed = _safe_json_loads(payload.strip(), {})
        if not isinstance(parsed, dict):
            continue
        if isinstance(parsed.get("method_change_summary"), dict):
            parsed = parsed["method_change_summary"]
        if any(
            key in parsed
            for key in (
                "substantive_method_change",
                "changed_conditions",
                "advantage_targets",
                "redesign_goal",
            )
        ):
            return parsed
    return {}


def _extract_stage13_condition_names_from_metrics(metrics: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for raw_key in metrics:
        if not isinstance(raw_key, str):
            continue
        key = raw_key.strip()
        if not key:
            continue
        if "/" in key:
            names.add(key.split("/", 1)[0])
            continue
        match = re.match(r"^([A-Za-z0-9_]+)_seed_\d+$", key)
        if match:
            names.add(match.group(1))
    return names


def _build_stage13_completion_gate(log: dict[str, Any]) -> dict[str, Any]:
    def _local_to_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            out = float(value)
            if math.isnan(out) or math.isinf(out):
                return None
            return out
        except (TypeError, ValueError):
            return None

    iterations = log.get("iterations", [])
    verified_conditions: set[str] = set()
    successful_iterations = 0
    expected_conditions: set[str] = set()

    for iteration in iterations if isinstance(iterations, list) else []:
        if not isinstance(iteration, dict):
            continue
        incremental_plan = iteration.get("incremental_plan")
        if isinstance(incremental_plan, dict):
            for key in ("active_conditions", "frozen_conditions", "reuse_conditions"):
                values = incremental_plan.get(key)
                if isinstance(values, list):
                    expected_conditions.update(
                        str(value) for value in values if isinstance(value, str) and value.strip()
                    )
        for sandbox_key in ("sandbox", "sandbox_after_fix"):
            sandbox_payload = iteration.get(sandbox_key)
            if not isinstance(sandbox_payload, dict):
                continue
            metrics = sandbox_payload.get("metrics")
            if isinstance(metrics, dict):
                verified_conditions.update(_extract_stage13_condition_names_from_metrics(metrics))
            metric_val = _local_to_float(iteration.get("metric"))
            if sandbox_payload.get("returncode") == 0 and metric_val is not None:
                successful_iterations += 1

    best_metric = _local_to_float(log.get("best_metric"))
    converged = bool(log.get("converged"))
    stop_reason = str(log.get("stop_reason") or "")
    required_verified = 0 if not expected_conditions else min(2, len(expected_conditions))

    ok = True
    reasons: list[str] = []
    if best_metric is None:
        ok = False
        reasons.append("best_metric_missing")
    if successful_iterations <= 0:
        ok = False
        reasons.append("no_successful_refine_iteration")
    if len(verified_conditions) < required_verified:
        ok = False
        reasons.append("insufficient_verified_condition_coverage")
    if not converged and stop_reason in {
        "consecutive_no_metrics",
        "wall_clock_time_cap",
    }:
        ok = False
        reasons.append(f"non_converged_stop:{stop_reason}")

    return {
        "ok": ok,
        "reasons": reasons,
        "best_metric": best_metric,
        "converged": converged,
        "stop_reason": stop_reason,
        "successful_iterations": successful_iterations,
        "verified_conditions": sorted(verified_conditions),
        "expected_conditions": sorted(expected_conditions),
        "required_verified_conditions": required_verified,
    }


def _stage13_has_substantive_method_change(
    *,
    best_files: dict[str, str],
    candidate_files: dict[str, str],
    llm_change_summary: dict[str, Any],
) -> bool:
    declared = llm_change_summary.get("substantive_method_change")
    if isinstance(declared, bool):
        return declared

    changed_files = {
        fname
        for fname in set(best_files) | set(candidate_files)
        if best_files.get(fname) != candidate_files.get(fname)
    }
    if "methods.py" in changed_files or "evaluate.py" in changed_files:
        return True

    if "config.py" in changed_files:
        old_changed, new_changed = _stage13_changed_line_numbers(
            best_files.get("config.py", ""),
            candidate_files.get("config.py", ""),
        )
        candidate_lines = candidate_files.get("config.py", "").splitlines()
        changed_text = "\n".join(
            candidate_lines[line_no - 1]
            for line_no in sorted(new_changed)
            if 0 < line_no <= len(candidate_lines)
        ).lower()
        if any(
            token in changed_text
            for token in (
                "max_steps_screening",
                "probe_interval",
                "screening_seeds",
                "quality_cost",
                "advantage",
                "step_time",
                "peak_vram",
                "average_active_rank",
                "trigger",
            )
        ):
            return True

    changed_conditions = llm_change_summary.get("changed_conditions")
    if isinstance(changed_conditions, list) and any(
        isinstance(item, str) and item.strip() for item in changed_conditions
    ):
        return True

    return False


def _build_stage13_method_diagnosis(
    *,
    stage_dir: Path,
    run_dir: Path,
    metric_key: str,
    metric_direction: str,
    condition_coverage_hint: str,
    config_text: str,
) -> tuple[str, dict[str, Any]]:
    registry = _parse_stage13_condition_registry(config_text)
    ordered_conditions = [entry["condition_name"] for entry in registry]
    family_by_condition = {
        entry["condition_name"]: entry.get("family", "")
        for entry in registry
    }
    seed_cache = _load_stage13_condition_seed_cache(stage_dir)
    condition_means: dict[str, float] = {}
    seed_counts: dict[str, int] = {}
    for condition_name, seed_map in seed_cache.items():
        metrics = [float(value) for value in seed_map.values()]
        if not metrics:
            continue
        condition_means[condition_name] = sum(metrics) / len(metrics)
        seed_counts[condition_name] = len(metrics)

    baseline_conditions = [
        name for name in ordered_conditions if family_by_condition.get(name) == "baseline"
    ]
    non_baseline_conditions = [
        name for name in ordered_conditions if family_by_condition.get(name) != "baseline"
    ]
    strongest_baseline = _select_best_condition(
        baseline_conditions,
        condition_means,
        metric_direction,
    )
    strongest_non_baseline = _select_best_condition(
        non_baseline_conditions,
        condition_means,
        metric_direction,
    )

    adequacy_payload = _safe_json_loads(
        _read_prior_artifact(run_dir, "experiment_adequacy_report.json") or "{}",
        {},
    )
    hypotheses_text = _read_prior_artifact(run_dir, "hypotheses.md") or ""
    hypothesis_claims = _extract_hypothesis_claims(hypotheses_text, max_items=4)
    advantage_axes = _infer_advantage_axes(hypotheses_text)
    screening_budget = _parse_stage13_screening_budget(config_text)
    result_metric_keys = _load_stage13_result_metric_keys(stage_dir)
    baseline_coverage = _build_stage13_baseline_coverage_snapshot(
        stage_dir=stage_dir,
        run_dir=run_dir,
        config_text=config_text,
    )

    efficiency_signals_present = {
        "vram": any("vram" in key.lower() or "memory" in key.lower() for key in result_metric_keys),
        "time": any("time" in key.lower() or "throughput" in key.lower() for key in result_metric_keys),
        "rank": any("rank" in key.lower() for key in result_metric_keys),
        "trigger": any("trigger" in key.lower() or "energy" in key.lower() or "agreement" in key.lower() for key in result_metric_keys),
    }
    redesign_reasons: list[str] = []
    redesign_actions: list[str] = []
    if strongest_baseline and strongest_non_baseline:
        best_baseline_name, best_baseline_metric = strongest_baseline
        best_non_baseline_name, best_non_baseline_metric = strongest_non_baseline
        if _metric_is_better(metric_direction, best_baseline_metric, best_non_baseline_metric):
            redesign_reasons.append(
                f"Best baseline `{best_baseline_name}` ({best_baseline_metric:.6f}) beats best non-baseline `{best_non_baseline_name}` ({best_non_baseline_metric:.6f})."
            )
            redesign_actions.append(
                "Do not rerun unchanged proposed methods. Redesign only proposed/ablation conditions and keep completed baselines frozen."
            )

    estimated_probes = screening_budget.get("estimated_probe_events")
    if isinstance(estimated_probes, int) and estimated_probes < 6:
        redesign_reasons.append(
            f"Screening budget is too short for adaptive control ({estimated_probes} probe events < 6)."
        )
        redesign_actions.append(
            "Increase screening horizon or reduce probe interval so adaptive controllers get at least 6 probe opportunities."
        )

    if "vram" in advantage_axes and not efficiency_signals_present["vram"]:
        redesign_reasons.append("Hypotheses mention memory/VRAM advantage but no VRAM metrics are emitted.")
        redesign_actions.append(
            "Add explicit peak VRAM or memory metrics before claiming memory advantages."
        )
    if "time" in advantage_axes and not efficiency_signals_present["time"]:
        redesign_reasons.append("Hypotheses mention time/overhead advantage but no timing metrics are emitted.")
        redesign_actions.append(
            "Emit wall-clock or step-time metrics and evaluate quality-cost tradeoff, not quality alone."
        )
    if "rank" in advantage_axes and not efficiency_signals_present["rank"]:
        redesign_reasons.append("Hypotheses mention rank efficiency but no rank usage metrics are emitted.")
        redesign_actions.append(
            "Emit average/final active rank and use it in the comparative analysis."
        )
    if "trigger" in advantage_axes and not efficiency_signals_present["trigger"]:
        redesign_reasons.append("Hypotheses mention probe/controller signal quality but no trigger/probe metrics are emitted.")
        redesign_actions.append(
            "Emit trigger, retained-energy, or agreement metrics so the mechanism claim is testable."
        )

    methods_text = ""
    for candidate_name in ("methods.py",):
        methods_text = (
            (stage_dir / "experiment" / candidate_name).read_text(encoding="utf-8")
            if (stage_dir / "experiment" / candidate_name).is_file()
            else ""
        )
        if methods_text:
            break
    if "resize_rank_basic(" in methods_text and "state_consistent" in methods_text.lower():
        redesign_reasons.append(
            "Current method code still uses basic rank resizing while a state-consistent path exists."
        )
        redesign_actions.append(
            "Prefer state-consistent rank morphing over basic resize when testing dynamic-rank claims."
        )

    if str(adequacy_payload.get("verdict") or "") == "weak_design":
        redesign_reasons.append("Stage 9 already marked the experiment design as weak.")
        redesign_actions.append(
            "Realign Stage 13 changes to Stage 9 adequacy gaps before launching another full experiment round."
        )
    if baseline_coverage["baseline_coverage_gap"]:
        redesign_reasons.append(
            "same-round baseline coverage is incomplete: "
            + ", ".join(baseline_coverage["missing_active_conditions"])
        )
        redesign_actions.append(
            "Restore the prior Stage 13 baseline grid and all Stage 15 required same-round baselines, or explicitly document a reproducibility-driven exclusion before rerunning."
        )
    if baseline_coverage["missing_registered_conditions"]:
        redesign_reasons.append(
            "Required comparison conditions are not implemented in the current registry: "
            + ", ".join(baseline_coverage["missing_registered_conditions"])
        )
        redesign_actions.append(
            "Implement the missing comparison conditions before claiming broad baseline superiority."
        )
    if baseline_coverage["related_work_comparators"]:
        redesign_reasons.append(
            "related-work comparators require explicit coverage or exclusion: "
            + ", ".join(baseline_coverage["related_work_comparators"])
        )
        redesign_actions.append(
            "related-work comparators require explicit coverage or exclusion: "
            + ", ".join(baseline_coverage["related_work_comparators"])
        )

    method_redesign_required = bool(redesign_reasons)
    payload = {
        "generated": _utcnow_iso(),
        "metric_key": metric_key,
        "metric_direction": metric_direction,
        "condition_coverage_gap": bool(condition_coverage_hint.strip()),
        "condition_means": condition_means,
        "seed_counts": seed_counts,
        "strongest_baseline": (
            {"condition": strongest_baseline[0], "metric": strongest_baseline[1]}
            if strongest_baseline
            else {}
        ),
        "strongest_non_baseline": (
            {"condition": strongest_non_baseline[0], "metric": strongest_non_baseline[1]}
            if strongest_non_baseline
            else {}
        ),
        "screening_budget": screening_budget,
        "advantage_axes": advantage_axes,
        "efficiency_signal_coverage": efficiency_signals_present,
        **baseline_coverage,
        "hypothesis_claims": hypothesis_claims,
        "adequacy_verdict": str(adequacy_payload.get("verdict") or ""),
        "adequacy_score": adequacy_payload.get("score"),
        "method_redesign_required": method_redesign_required,
        "redesign_reasons": redesign_reasons,
        "redesign_actions": redesign_actions,
    }
    (stage_dir / "method_diagnosis.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines = [
        "# Stage 13 Method Diagnosis",
        "",
        f"- Metric: `{metric_key}` ({metric_direction})",
        f"- Condition coverage gap: {bool(condition_coverage_hint.strip())}",
        f"- Adequacy verdict: {payload['adequacy_verdict'] or 'unknown'}",
        f"- Method redesign required: {method_redesign_required}",
    ]
    if strongest_baseline:
        lines.append(
            f"- Strongest baseline: `{strongest_baseline[0]}` = {strongest_baseline[1]:.6f}"
        )
    if strongest_non_baseline:
        lines.append(
            f"- Strongest non-baseline: `{strongest_non_baseline[0]}` = {strongest_non_baseline[1]:.6f}"
        )
    lines.extend(
        [
            "",
            "## Hypothesis Alignment",
            *([f"- {claim}" for claim in hypothesis_claims] or ["- No hypothesis claims found."]),
            "",
            "## Redesign Reasons",
            *([f"- {reason}" for reason in redesign_reasons] or ["- No redesign trigger detected."]),
            "",
            "## Required Actions",
            *([f"- {action}" for action in redesign_actions] or ["- Preserve current method and avoid unnecessary reruns."]),
        ]
    )
    summary = "\n".join(lines).strip() + "\n"
    (stage_dir / "method_diagnosis.md").write_text(summary, encoding="utf-8")
    return summary, payload


def _parse_stage13_condition_registry(config_text: str) -> list[dict[str, str]]:
    pattern = re.compile(
        r'register\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*"([^"]+)"'
    )
    registry: list[dict[str, str]] = []
    for match in pattern.finditer(config_text):
        registry.append(
            {
                "condition_name": match.group(1),
                "class_name": match.group(2),
                "family": match.group(3),
            }
        )
    return registry


_STAGE13_BASELINE_ALIASES: dict[str, str] = {
    "full fine-tuning": "full_finetuning",
    "full fine tuning": "full_finetuning",
    "lora-fa": "lora_fa",
    "lora fa": "lora_fa",
    "adalora": "adalora_like_budget",
    "dora": "dora",
    "qlora": "qlora_fixed",
    "lora": "lora_fixed",
}

_RELATED_WORK_COMPARATORS: tuple[str, ...] = (
    "GRIT",
    "LoRA-Squeeze",
    "LoRA-drop",
    "ID-LoRA",
    "SECURA",
    "PLoP",
    "Layer-wise LoRA",
)

_STAGE13_REQUIRED_BASELINE_GRID: tuple[str, ...] = (
    "lora_fixed",
    "qlora_fixed",
    "lora_fixed_matched_rank",
    "dora",
    "pissa_init",
    "milora_init",
    "lora_ga_init",
    "sensitivity_lora",
    "full_finetuning",
    "lora_fa",
    "adalora_like_budget",
)

_STAGE13_REQUIRED_MECHANISM_GRID: tuple[str, ...] = (
    "probe_control",
    "cheap_proxy_controller",
    "exact_svd_oracle_controller",
    "falcon_qb_weight_init",
    "falcon_qb_activation_rank",
    "falcon_qb_init_plus_cheap_proxy",
)


def _append_unique(values: list[str], candidate: str) -> None:
    if candidate and candidate not in values:
        values.append(candidate)


def _build_stage13_baseline_coverage_snapshot(
    *,
    stage_dir: Path,
    run_dir: Path,
    config_text: str,
) -> dict[str, Any]:
    """Collect required baseline/comparator coverage from prior artifacts."""
    benchmark_payload = _safe_json_loads(
        _read_prior_artifact(run_dir, "benchmark_plan.json") or "{}",
        {},
    )
    required_conditions: list[str] = []
    if isinstance(benchmark_payload, dict):
        selected_baselines = benchmark_payload.get("selected_baselines")
        if isinstance(selected_baselines, list):
            for item in selected_baselines:
                if isinstance(item, dict):
                    _append_unique(required_conditions, str(item.get("condition") or "").strip())

    evidence_text = "\n".join(
        filter(
            None,
            (
                _read_prior_artifact(run_dir, "exp_plan.yaml") or "",
                _read_prior_artifact(run_dir, "claims_from_results.md") or "",
                _read_prior_artifact(run_dir, "phase2_handoff.md") or "",
            ),
        )
    )
    normalized_evidence = evidence_text.lower()
    for alias, condition in _STAGE13_BASELINE_ALIASES.items():
        if alias in normalized_evidence:
            _append_unique(required_conditions, condition)

    main_text = ""
    main_path = stage_dir / "experiment" / "main.py"
    if main_path.is_file():
        main_text = main_path.read_text(encoding="utf-8")
    active_conditions = _parse_stage13_active_condition_names(config_text, main_text)
    registered_conditions = [
        entry["condition_name"] for entry in _parse_stage13_condition_registry(config_text)
    ]
    missing_active_conditions = [
        condition for condition in required_conditions if condition not in active_conditions
    ]
    missing_registered_conditions = [
        condition for condition in required_conditions if condition not in registered_conditions
    ]

    related_work_text = "\n".join(
        filter(
            None,
            (
                _read_prior_artifact(run_dir, "related_work_map.md") or "",
                _read_prior_artifact(run_dir, "synthesis.md") or "",
            ),
        )
    ).lower()
    related_work_comparators = [
        comparator
        for comparator in _RELATED_WORK_COMPARATORS
        if comparator.lower() in related_work_text
    ]

    return {
        "required_baseline_conditions": required_conditions,
        "active_conditions": active_conditions,
        "registered_conditions": registered_conditions,
        "missing_active_conditions": missing_active_conditions,
        "missing_registered_conditions": missing_registered_conditions,
        "baseline_coverage_gap": bool(missing_active_conditions),
        "related_work_comparators": related_work_comparators,
    }


def _parse_stage13_active_condition_names(
    config_text: str,
    main_text: str = "",
) -> list[str]:
    patterns = [
        r"REQUIRED_ACTIVE_CONDITIONS\s*:\s*list\[str\]\s*=\s*(\[[^\]]*\])",
        r"ACTIVE_CONDITIONS\s*:\s*list\[str\]\s*=\s*(\[[^\]]*\])",
        r"self\.active_condition_names\s*:\s*list\[str\]\s*=\s*(\[[^\]]*\])",
    ]
    for text in (main_text or "", config_text or ""):
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.DOTALL)
            if not match:
                continue
            try:
                parsed = ast.literal_eval(match.group(1))
            except (SyntaxError, ValueError):
                continue
            if isinstance(parsed, list):
                active = [
                    str(item)
                    for item in parsed
                    if isinstance(item, str) and item.strip()
                ]
                if active:
                    return active
    return []


def _parse_stage13_seed_plan(config_text: str) -> list[int]:
    pattern = re.compile(r"self\.screening_seeds\s*:\s*list\[int\]\s*=\s*(\[[^\]]*\])")
    match = pattern.search(config_text)
    if not match:
        return [0, 1, 2]
    try:
        parsed = ast.literal_eval(match.group(1))
    except (SyntaxError, ValueError):
        return [0, 1, 2]
    if isinstance(parsed, list) and all(isinstance(item, int) for item in parsed):
        return list(parsed)
    return [0, 1, 2]


def _stage13_manual_redesign_active_conditions(stage_dir: Path) -> list[str]:
    manual_path = stage_dir / "manual_redesign.json"
    if not manual_path.is_file():
        return []

    payload = _safe_json_loads(manual_path.read_text(encoding="utf-8"), {})
    if isinstance(payload, dict):
        raw_conditions = payload.get("active_conditions")
        if isinstance(raw_conditions, list):
            active = [
                str(item).strip()
                for item in raw_conditions
                if isinstance(item, str) and item.strip()
            ]
            if active:
                return active

    main_text = ""
    config_text = ""
    try:
        main_text = (stage_dir / "experiment" / "main.py").read_text(encoding="utf-8")
    except OSError:
        pass
    try:
        config_text = (stage_dir / "experiment" / "config.py").read_text(encoding="utf-8")
    except OSError:
        pass

    patterns = [
        r"REQUIRED_ACTIVE_CONDITIONS\s*:\s*list\[str\]\s*=\s*(\[[^\]]*\])",
        r"self\.active_condition_names\s*:\s*list\[str\]\s*=\s*(\[[^\]]*\])",
    ]
    for text in (main_text, config_text):
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.DOTALL)
            if not match:
                continue
            try:
                parsed = ast.literal_eval(match.group(1))
            except (SyntaxError, ValueError):
                continue
            if isinstance(parsed, list):
                active = [str(item) for item in parsed if isinstance(item, str) and item.strip()]
                if active:
                    return active
    return []


def _stage15_refine_handoff_text(run_dir: Path) -> tuple[bool, str]:
    decision = ""
    structured_raw = _read_prior_artifact(run_dir, "decision_structured.json")
    if structured_raw:
        structured = _safe_json_loads(structured_raw, {})
        if isinstance(structured, dict):
            decision = str(structured.get("decision") or "").strip().lower()

    handoff_text = _read_prior_artifact(run_dir, "phase2_handoff.md") or ""
    decision_text = _read_prior_artifact(run_dir, "decision.md") or ""
    combined = f"{handoff_text}\n\n{decision_text}"
    normalized = combined.lower()
    is_refine = decision == "refine" or bool(
        re.search(r"(?:^|\n)\s*\*{0,2}refine\*{0,2}\s*(?:\n|$)", normalized)
    )
    return is_refine, combined


def _stage15_refine_handoff_requires_stage13_rerun(run_dir: Path) -> bool:
    is_refine, text = _stage15_refine_handoff_text(run_dir)
    if not is_refine:
        return False
    normalized = text.lower()
    evidence_tokens = (
        "补实验",
        "missing experiments",
        "fair same-version",
        "公平同版本",
        "qb-init",
        "qb init",
        "二因素",
        "matched-budget",
        "matched budget",
        "strict h1",
        "严格 h1",
    )
    condition_tokens = (
        "lora_fixed",
        "qlora_fixed",
        "cheap_proxy_controller",
        "probe_control",
        "exact_svd_oracle_controller",
        "falcon_qb",
    )
    return any(token in normalized for token in evidence_tokens) and any(
        token in normalized for token in condition_tokens
    )


def _ensure_stage13_refine_handoff_manual_redesign(
    *,
    run_dir: Path,
    stage_dir: Path,
) -> dict[str, Any] | None:
    if not _stage15_refine_handoff_requires_stage13_rerun(run_dir):
        return None

    active_conditions = list(_STAGE13_REQUIRED_BASELINE_GRID) + list(
        _STAGE13_REQUIRED_MECHANISM_GRID
    )
    payload: dict[str, Any] = {
        "schema_version": 1,
        "source": "stage15_refine_handoff",
        "source_stage": 15,
        "generated": _utcnow_iso(),
        "reason": (
            "Stage 15 returned REFINE with same-version baseline rerun, "
            "QB-init/controller ablation, and matched-budget H1 requirements."
        ),
        "cache_policy": "invalidate_existing_stage13_cache_for_refine_handoff",
        "requires_same_version_rerun": True,
        "active_conditions": active_conditions,
        "required_experiment_blocks": [
            "fair_same_version_core_rerun",
            "qb_init_controller_factorial_ablation",
            "strict_h1_matched_budget_comparison",
        ],
        "required_reports": [
            "quality",
            "peak_vram",
            "mean_step_time",
            "wall_clock_overhead",
            "trigger_agreement",
            "retained_energy_error",
        ],
    }

    stage_dir.mkdir(parents=True, exist_ok=True)
    manual_path = stage_dir / "manual_redesign.json"
    existing = _safe_json_loads(manual_path.read_text(encoding="utf-8"), {}) if manual_path.is_file() else {}
    if existing != payload:
        manual_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _parse_stage13_results_seed_cache(results_path: Path) -> dict[str, dict[int, float]]:
    payload = _safe_json_loads(results_path.read_text(encoding="utf-8"), {})
    cache: dict[str, dict[int, float]] = {}

    def _normalize_condition_name(raw_name: object) -> str:
        condition = str(raw_name).strip()
        if "/" in condition:
            condition = condition.rsplit("/", 1)[-1]
        if "__" in condition:
            condition = condition.rsplit("__", 1)[-1]
        return condition

    def _record(condition_name: object, seed_idx: object, raw_value: object) -> None:
        try:
            condition = _normalize_condition_name(condition_name)
            seed = int(seed_idx)
            metric = float(raw_value)
        except (TypeError, ValueError):
            return
        if math.isnan(metric) or math.isinf(metric):
            return
        if not condition:
            return
        cache.setdefault(condition, {})[seed] = metric

    metrics = payload.get("metrics") if isinstance(payload, dict) else {}
    if isinstance(metrics, dict):
        for raw_key, raw_value in metrics.items():
            if not isinstance(raw_key, str):
                continue
            match = re.match(r"(.+)_seed_(\d+)$", raw_key)
            if not match:
                continue
            _record(match.group(1), match.group(2), raw_value)

    rows = payload.get("results") if isinstance(payload, dict) else []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            condition_name = (
                row.get("condition_registry_name")
                or row.get("condition_name")
                or row.get("condition")
                or row.get("name")
            )
            seed_idx = row.get("seed")
            metric = row.get("primary_metric")
            if metric is None:
                metric = row.get("quality_cost_score")
            if condition_name is not None and seed_idx is not None:
                _record(condition_name, seed_idx, metric)

    by_condition = payload.get("by_condition") if isinstance(payload, dict) else {}
    if isinstance(by_condition, dict):
        for condition_name, rows_or_values in by_condition.items():
            if isinstance(rows_or_values, list):
                for item in rows_or_values:
                    if isinstance(item, dict):
                        _record(condition_name, item.get("seed"), item.get("primary_metric"))
            elif isinstance(rows_or_values, dict):
                for seed_idx, metric in rows_or_values.items():
                    if isinstance(metric, dict):
                        metric = metric.get("primary_metric")
                    _record(condition_name, seed_idx, metric)
    return cache


def _latest_stage13_partial_checkpoint(stage_dir: Path) -> Path | None:
    """Return the newest Stage 13 partial/interrupted result checkpoint."""
    candidates: list[Path] = []
    candidates.extend(stage_dir.glob("refine_sandbox_v*/_docker_project_*/partial_results.json"))
    candidates.extend(stage_dir.glob("refine_sandbox_v*_fix/_docker_project_*/partial_results.json"))
    candidates.extend(stage_dir.glob("refine_sandbox_v*/_docker_project_*/*/partial_results.json"))
    candidates.extend(stage_dir.glob("refine_sandbox_v*_fix/_docker_project_*/*/partial_results.json"))
    candidates.extend(stage_dir.glob("refine_sandbox_v*/_docker_project_*/partial_seed_metrics*.json"))
    candidates.extend(stage_dir.glob("refine_sandbox_v*_fix/_docker_project_*/partial_seed_metrics*.json"))
    candidates.extend(stage_dir.glob("refine_sandbox_v*/_docker_project_*/*/partial_seed_metrics*.json"))
    candidates.extend(stage_dir.glob("refine_sandbox_v*_fix/_docker_project_*/*/partial_seed_metrics*.json"))
    candidates.extend(stage_dir.glob("refine_sandbox_v*/_docker_project_*/results.json"))
    candidates.extend(stage_dir.glob("refine_sandbox_v*_fix/_docker_project_*/results.json"))
    candidates.extend(stage_dir.glob("refine_sandbox_v*/_docker_project_*/*/results.json"))
    candidates.extend(stage_dir.glob("refine_sandbox_v*_fix/_docker_project_*/*/results.json"))
    for path in sorted(candidates, key=lambda p: p.stat().st_mtime if p.exists() else -1.0, reverse=True):
        try:
            payload = _safe_json_loads(path.read_text(encoding="utf-8"), {})
        except OSError:
            continue
        if not isinstance(payload, dict):
            continue
        if bool(payload.get("superseded_by_manual_redesign")):
            continue
        status = str(payload.get("status") or "").strip().lower()
        source = str(payload.get("source") or "").strip().lower()
        is_partial = (
            path.name.startswith("partial_")
            or status in {"partial", "interrupted"}
            or "partial" in source
            or "interrupted" in source
        )
        if not is_partial:
            continue
        seed_cache = _parse_stage13_results_seed_cache(path)
        if not seed_cache:
            continue
        manual_active = _stage13_manual_redesign_active_conditions(stage_dir)
        if manual_active and not set(seed_cache).issubset(set(manual_active)):
            continue
        if seed_cache:
            return path
    return None


def _stage13_checkpoint_project_root(path: Path) -> Path:
    for parent in [path.parent, *path.parents]:
        if parent.name.startswith("_docker_project_"):
            return parent
    return path.parent


def _stage13_project_checkpoint_paths(project_dir: Path) -> list[Path]:
    names = ("results.json", "partial_results.json")
    paths: list[Path] = []
    for name in names:
        paths.append(project_dir / name)
    for child in sorted(project_dir.iterdir() if project_dir.is_dir() else []):
        if not child.is_dir() or not child.name.startswith("_parallel_"):
            continue
        for name in names:
            paths.append(child / name)
        paths.extend(sorted(child.glob("partial_seed_metrics*.json")))
    paths.extend(sorted(project_dir.glob("partial_seed_metrics*.json")))
    return [path for path in paths if path.is_file()]


def _stage13_checkpoint_is_superseded(path: Path) -> bool:
    try:
        payload = _safe_json_loads(path.read_text(encoding="utf-8"), {})
    except OSError:
        return False
    return isinstance(payload, dict) and bool(payload.get("superseded_by_manual_redesign"))


def _latest_stage13_partial_project_dir(stage_dir: Path) -> Path | None:
    checkpoint = _latest_stage13_partial_checkpoint(stage_dir)
    if checkpoint is None:
        return None
    project_dir = _stage13_checkpoint_project_root(checkpoint)
    if (project_dir / "main.py").is_file():
        return project_dir
    return None


def _latest_stage13_experiment_version_dir(stage_dir: Path) -> Path | None:
    candidates: list[tuple[int, float, Path]] = []
    for project_dir in stage_dir.glob("experiment_v*"):
        if not project_dir.is_dir() or not (project_dir / "main.py").is_file():
            continue
        suffix = project_dir.name.removeprefix("experiment_v")
        try:
            version = int(suffix)
        except ValueError:
            version = -1
        try:
            mtime = float(project_dir.stat().st_mtime)
        except OSError:
            mtime = 0.0
        candidates.append((version, mtime, project_dir))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (item[0], item[1]), reverse=True)[0][2]


def _load_stage13_condition_seed_cache(stage_dir: Path) -> dict[str, dict[int, float]]:
    merged: dict[str, dict[int, float]] = {}

    def _merge(cache: dict[str, dict[int, float]]) -> None:
        for condition_name, seed_map in cache.items():
            if not isinstance(seed_map, dict):
                continue
            target = merged.setdefault(str(condition_name), {})
            for seed_idx, metric in seed_map.items():
                if isinstance(metric, dict):
                    metric = metric.get("primary_metric")
                try:
                    seed_int = int(seed_idx)
                    metric_float = float(metric)
                except (TypeError, ValueError):
                    continue
                if math.isnan(metric_float) or math.isinf(metric_float):
                    continue
                target[seed_int] = metric_float

    # If the latest Stage 13 sandbox was interrupted and wrote a partial
    # checkpoint, treat that partial checkpoint as the authoritative resume
    # source for this continuation.  Merging older completed refinement
    # attempts here can falsely mark later conditions as complete and skip the
    # remaining seeds of the interrupted experiment.
    latest_partial = _latest_stage13_partial_checkpoint(stage_dir)
    manual_redesign_path = stage_dir / "manual_redesign.json"
    manual_mtime = (
        manual_redesign_path.stat().st_mtime
        if manual_redesign_path.is_file()
        else -1.0
    )

    def _merge_completed_results_after_manual_redesign() -> None:
        if not manual_redesign_path.is_file():
            return
        manual_active = _stage13_manual_redesign_active_conditions(stage_dir)
        result_patterns = (
            "refine_sandbox_v*/_docker_project_*/results.json",
            "refine_sandbox_v*_fix/_docker_project_*/results.json",
        )
        for pattern in result_patterns:
            for results_path in sorted(stage_dir.glob(pattern)):
                if _stage13_checkpoint_is_superseded(results_path):
                    continue
                try:
                    payload = _safe_json_loads(results_path.read_text(encoding="utf-8"), {})
                except OSError:
                    continue
                if not isinstance(payload, dict):
                    continue
                if str(payload.get("status") or "").strip().lower() != "completed":
                    continue
                result_cache = _parse_stage13_results_seed_cache(results_path)
                if manual_active and not set(manual_active).issubset(set(result_cache)):
                    continue
                _merge(result_cache)

    if manual_redesign_path.is_file():
        partial_mtime = latest_partial.stat().st_mtime if latest_partial is not None else -1.0
        if latest_partial is None or partial_mtime < manual_mtime:
            _merge_completed_results_after_manual_redesign()
            if merged:
                return merged
            return {}

    if latest_partial is not None:
        project_root = _stage13_checkpoint_project_root(latest_partial)
        checkpoint_paths = _stage13_project_checkpoint_paths(project_root) or [latest_partial]
        for checkpoint_path in checkpoint_paths:
            if _stage13_checkpoint_is_superseded(checkpoint_path):
                continue
            _merge(_parse_stage13_results_seed_cache(checkpoint_path))
        _merge_completed_results_after_manual_redesign()
        if merged:
            return merged

    if manual_redesign_path.is_file():
        _merge_completed_results_after_manual_redesign()
        if merged:
            return merged
        return {}

    registry_candidates = [
        stage_dir / "experiment" / "resume_seed_registry.json",
        stage_dir / "experiment_v1" / "resume_seed_registry.json",
        stage_dir / "experiment_v2" / "resume_seed_registry.json",
        stage_dir / "experiment_v3" / "resume_seed_registry.json",
    ]
    for path in registry_candidates:
        if not path.is_file():
            continue
        payload = _safe_json_loads(path.read_text(encoding="utf-8"), {})
        conditions = payload.get("conditions") if isinstance(payload, dict) else {}
        if isinstance(conditions, dict):
            _merge(conditions)

    for results_path in sorted(
        stage_dir.glob("refine_sandbox_v*/_docker_project_*/results.json")
    ):
        if _stage13_checkpoint_is_superseded(results_path):
            continue
        _merge(_parse_stage13_results_seed_cache(results_path))
    for results_path in sorted(
        stage_dir.glob("refine_sandbox_v*_fix/_docker_project_*/results.json")
    ):
        if _stage13_checkpoint_is_superseded(results_path):
            continue
        _merge(_parse_stage13_results_seed_cache(results_path))
    for partial_path in sorted(
        stage_dir.glob("refine_sandbox_v*/_docker_project_*/partial_results.json")
    ):
        if _stage13_checkpoint_is_superseded(partial_path):
            continue
        _merge(_parse_stage13_results_seed_cache(partial_path))
    for partial_path in sorted(
        stage_dir.glob("refine_sandbox_v*_fix/_docker_project_*/partial_results.json")
    ):
        if _stage13_checkpoint_is_superseded(partial_path):
            continue
        _merge(_parse_stage13_results_seed_cache(partial_path))
    for partial_path in sorted(
        stage_dir.glob("refine_sandbox_v*/_docker_project_*/*/partial_results.json")
    ):
        if _stage13_checkpoint_is_superseded(partial_path):
            continue
        _merge(_parse_stage13_results_seed_cache(partial_path))
    for partial_path in sorted(
        stage_dir.glob("refine_sandbox_v*_fix/_docker_project_*/*/partial_results.json")
    ):
        if _stage13_checkpoint_is_superseded(partial_path):
            continue
        _merge(_parse_stage13_results_seed_cache(partial_path))
    for partial_path in sorted(
        stage_dir.glob("refine_sandbox_v*/_docker_project_*/partial_seed_metrics*.json")
    ):
        if _stage13_checkpoint_is_superseded(partial_path):
            continue
        _merge(_parse_stage13_results_seed_cache(partial_path))
    for partial_path in sorted(
        stage_dir.glob("refine_sandbox_v*_fix/_docker_project_*/partial_seed_metrics*.json")
    ):
        if _stage13_checkpoint_is_superseded(partial_path):
            continue
        _merge(_parse_stage13_results_seed_cache(partial_path))
    for partial_path in sorted(
        stage_dir.glob("refine_sandbox_v*/_docker_project_*/*/partial_seed_metrics*.json")
    ):
        if _stage13_checkpoint_is_superseded(partial_path):
            continue
        _merge(_parse_stage13_results_seed_cache(partial_path))
    for partial_path in sorted(
        stage_dir.glob("refine_sandbox_v*_fix/_docker_project_*/*/partial_seed_metrics*.json")
    ):
        if _stage13_checkpoint_is_superseded(partial_path):
            continue
        _merge(_parse_stage13_results_seed_cache(partial_path))

    return merged


def _stage13_candidate_config_signature(
    project_files: dict[str, str],
    *,
    stage_dir: Path,
    iteration: int,
) -> str | None:
    """Compute ``ExperimentConfig().config_signature()`` for generated code.

    Stage 13 frequently changes metric definitions while keeping baseline
    training code unchanged.  The generated experiment code normally refuses a
    resume registry when the config signature differs.  To freeze completed
    baselines without rerunning them, the controller writes a registry that is
    explicitly compatible with the candidate code's current signature.
    """
    config_text = project_files.get("config.py", "")
    if "class ExperimentConfig" not in config_text or "config_signature" not in config_text:
        return None

    with tempfile.TemporaryDirectory(
        prefix=f".stage13_sig_v{iteration}_",
        dir=str(stage_dir),
    ) as tmp_name:
        tmp_dir = Path(tmp_name)
        for fname, text in project_files.items():
            if not isinstance(text, str):
                continue
            if Path(fname).suffix not in {".py", ".json", ".txt", ".yaml", ".yml", ".cfg", ".ini"}:
                continue
            target = tmp_dir / fname
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")

        code = (
            "from config import ExperimentConfig\n"
            "print(ExperimentConfig().config_signature())\n"
        )
        env = dict(os.environ)
        env["PYTHONPATH"] = str(tmp_dir)
        try:
            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=str(tmp_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Stage 13 iteration %d: failed to compute candidate config signature", iteration)
            return None
        if completed.returncode != 0:
            logger.info(
                "Stage 13 iteration %d: candidate config signature unavailable: %s",
                iteration,
                (completed.stderr or completed.stdout or "").strip()[:500],
            )
            return None
        signature = (completed.stdout or "").strip().splitlines()[-1].strip()
        if re.fullmatch(r"[0-9a-fA-F]{8,64}", signature):
            return signature
        return None


def _stage13_resume_registry_payload(
    resume_registry: dict[str, Any],
    *,
    project_files: dict[str, str],
    stage_dir: Path,
    iteration: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"conditions": resume_registry}
    signature = _stage13_candidate_config_signature(
        project_files,
        stage_dir=stage_dir,
        iteration=iteration,
    )
    if signature:
        payload["config_signature"] = signature
        payload["signature_source"] = "candidate_experiment_config"
        payload["cache_policy"] = (
            "freeze_completed_baseline_training_results; metric changes should "
            "prefer cached seed records or lightweight metric recomputation over full retraining"
        )
    return payload


def _stage13_align_resume_registry_signature(
    registry_text: str,
    *,
    project_files: dict[str, str],
    stage_dir: Path,
    iteration: int,
) -> str:
    if not registry_text.strip():
        return registry_text
    payload = _safe_json_loads(registry_text, {})
    if not isinstance(payload, dict):
        return registry_text
    conditions = payload.get("conditions")
    if not isinstance(conditions, dict):
        return registry_text
    signature = _stage13_candidate_config_signature(
        project_files,
        stage_dir=stage_dir,
        iteration=iteration,
    )
    if not signature:
        return registry_text
    old_signature = payload.get("config_signature")
    if old_signature and old_signature != signature:
        payload.setdefault("source_config_signatures", [])
        if isinstance(payload["source_config_signatures"], list):
            payload["source_config_signatures"].append(str(old_signature))
    payload["config_signature"] = signature
    payload["signature_source"] = "candidate_experiment_config"
    payload["cache_policy"] = (
        "freeze_completed_baseline_training_results; metric changes should "
        "prefer cached seed records or lightweight metric recomputation over full retraining"
    )
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _stage13_changed_line_numbers(old_text: str, new_text: str) -> tuple[set[int], set[int]]:
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    old_changed: set[int] = set()
    new_changed: set[int] = set()
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
        a=old_lines,
        b=new_lines,
    ).get_opcodes():
        if tag == "equal":
            continue
        old_changed.update(range(i1 + 1, i2 + 1))
        new_changed.update(range(j1 + 1, j2 + 1))
    return old_changed, new_changed


def _stage13_class_spans(source_text: str) -> dict[str, tuple[int, int]]:
    try:
        module = ast.parse(source_text)
    except SyntaxError:
        return {}
    spans: dict[str, tuple[int, int]] = {}
    for node in module.body:
        if isinstance(node, ast.ClassDef):
            end_lineno = getattr(node, "end_lineno", node.lineno)
            spans[str(node.name)] = (int(node.lineno), int(end_lineno))
    return spans


def _stage13_class_names_for_changed_lines(
    source_text: str,
    changed_lines: set[int],
) -> set[str]:
    class_names: set[str] = set()
    for class_name, (start, end) in _stage13_class_spans(source_text).items():
        if any(start <= line_no <= end for line_no in changed_lines):
            class_names.add(class_name)
    return class_names


def _stage13_affected_conditions_for_methods_change(
    previous_text: str,
    candidate_text: str,
    class_to_condition: dict[str, str],
) -> tuple[set[str], bool]:
    old_changed, new_changed = _stage13_changed_line_numbers(previous_text, candidate_text)
    changed_classes = (
        _stage13_class_names_for_changed_lines(previous_text, old_changed)
        | _stage13_class_names_for_changed_lines(candidate_text, new_changed)
    )
    if not changed_classes:
        return set(), True

    shared_method_classes = {
        "NumpyAdamW",
        "DynamicLoRALinear",
        "BackboneWithAdapters",
        "SpectralProbeEngine",
    }
    if changed_classes & shared_method_classes:
        return set(), True

    affected: set[str] = set()
    for class_name in changed_classes:
        condition_name = class_to_condition.get(class_name)
        if condition_name:
            affected.add(condition_name)
        else:
            return set(), True
    return affected, False


def _rewrite_stage13_active_conditions(
    config_text: str,
    active_conditions: list[str],
) -> str:
    if not active_conditions:
        return config_text
    pattern = re.compile(
        r"(self\.active_condition_names\s*:\s*list\[str\]\s*=\s*)\[(.*?)\]",
        re.DOTALL,
    )
    replacement = (
        "[\n"
        + "".join(f'            "{name}",\n' for name in active_conditions)
        + "        ]"
    )
    rewritten = pattern.sub(rf"\1{replacement}", config_text, count=1)
    # Incremental replay may intentionally run fewer than the original
    # screening conditions. Keep the upper-bound guard, but remove rigid
    # "exactly N conditions" assertions that make valid resume plans fail.
    return _remove_stage13_active_condition_count_guard(rewritten)


def _rewrite_stage13_main_required_conditions(
    main_text: str,
    active_conditions: list[str],
) -> str:
    if not active_conditions:
        return main_text
    pattern = re.compile(
        r"(REQUIRED_ACTIVE_CONDITIONS\s*:\s*list\[str\]\s*=\s*)\[(.*?)\]",
        re.DOTALL,
    )
    replacement = (
        "[\n"
        + "".join(f'    "{name}",\n' for name in active_conditions)
        + "]"
    )
    return pattern.sub(rf"\1{replacement}", main_text, count=1)


def _remove_stage13_active_condition_count_guard(config_text: str) -> str:
    exact_count_guard = re.compile(
        r"\n\s*if\s+len\(self\.condition_registry\)\s*!=\s*\d+:\n"
        r"\s*raise\s+ValueError\([^\n]*Active condition count must be exactly[^\n]*\)\n",
        re.DOTALL,
    )
    upper_count_guard = re.compile(
        r"\n\s*if\s+len\(self\.condition_registry\)\s*>\s*\d+:\n"
        r"\s*raise\s+ValueError\([^\n]*Active condition count must be <=[^\n]*\)\n",
        re.DOTALL,
    )
    text = exact_count_guard.sub("\n", config_text)
    return upper_count_guard.sub("\n", text)


def _stage13_forced_active_grid(
    candidate_files: dict[str, str],
    method_diagnosis_payload: dict[str, Any],
) -> list[str]:
    config_text = candidate_files.get("config.py", "")
    main_text = candidate_files.get("main.py", "")
    forced: list[str] = []
    for condition_name in _parse_stage13_active_condition_names(config_text, main_text):
        _append_unique(forced, condition_name)
    for key in ("required_baseline_conditions", "missing_active_conditions"):
        raw_conditions = method_diagnosis_payload.get(key)
        if isinstance(raw_conditions, list):
            for condition_name in raw_conditions:
                _append_unique(forced, str(condition_name).strip())
    for condition_name in _STAGE13_REQUIRED_BASELINE_GRID:
        _append_unique(forced, condition_name)
    for condition_name in _STAGE13_REQUIRED_MECHANISM_GRID:
        _append_unique(forced, condition_name)
    return forced


def _ensure_stage13_related_work_baseline_registrations(config_text: str) -> str:
    if not config_text:
        return config_text
    insertions: list[str] = []
    if 'register("lora_fa"' not in config_text:
        insertions.append(
            '        register("lora_fa", "LoRAFACondition", "recent_baseline", False, False, list(self.screening_datasets))'
        )
    if 'register("adalora_like_budget"' not in config_text:
        insertions.append(
            '        register("adalora_like_budget", "AdaLoRALikeBudgetCondition", "recent_baseline", False, True, list(self.screening_datasets))'
        )
    if not insertions:
        return config_text
    marker = "\n        active_names = list(self.active_condition_names)"
    if marker not in config_text:
        return config_text
    return config_text.replace(marker, "\n" + "\n".join(insertions) + marker, 1)


def _ensure_stage13_related_work_baseline_methods(methods_text: str) -> str:
    if not methods_text:
        return methods_text
    text = methods_text
    if "class LoRAFACondition" not in text:
        lora_fa_block = '''

class LoRAFACondition(LiteratureBaselineMixin, FixedLoRACondition):
    baseline_reference = "LoRA-FA fixed-A low-rank adaptation"

    def prepare_model(self, **kwargs: Any) -> None:
        model = kwargs["model"]
        frozen_layers: list[str] = []
        for layer_name, adapter in model.iter_dynamic_adapters():
            adapter.lora_A.requires_grad_(False)
            frozen_layers.append(str(layer_name))
        rank_map = self._current_rank_map(model)
        self._append_rank_history(0, rank_map)
        self._record_baseline_preparation(
            {
                "event": "lora_fa_fixed_a_training",
                "triggered": False,
                "reference": self.baseline_reference,
                "average_new_rank": self._average_rank(rank_map),
                "frozen_lora_a_layers": frozen_layers,
            }
        )
'''
        marker = "\nclass FalconQBPreparationMixin:"
        if marker in text:
            text = text.replace(marker, lora_fa_block + marker, 1)
        else:
            text = text.rstrip() + lora_fa_block

    if "class AdaLoRALikeBudgetCondition" not in text:
        adalora_block = '''

class AdaLoRALikeBudgetCondition(SensitivityLoRACondition):
    baseline_reference = "AdaLoRA-like sensitivity-driven rank-budget adaptation"

    def prepare_model(self, **kwargs: Any) -> None:
        self.config.falcon_layer_target_average_rank = float(
            min(
                float(getattr(self.config, "falcon_layer_target_average_rank", self.config.lora_rank_init)),
                float(getattr(self.config, "hybrid_target_average_rank", self.config.lora_rank_init)),
            )
        )
        super().prepare_model(**kwargs)
        if self.trigger_history:
            self.trigger_history[-1]["event"] = "adalora_like_initial_rank_budget"
            self.trigger_history[-1]["reference"] = self.baseline_reference

    def maybe_update_rank(self, model: BackboneWithAdapters, optimizer: NumpyAdamW, step_idx: int) -> dict[str, Any]:
        event = super().maybe_update_rank(model, optimizer, step_idx)
        event["controller"] = "adalora_like_budget"
        event["reference"] = self.baseline_reference
        return event
'''
        marker = "\nclass FalconQBPreparationMixin:"
        if marker in text:
            text = text.replace(marker, adalora_block + marker, 1)
        else:
            text = text.rstrip() + adalora_block

    if '"lora_fa": LoRAFACondition' not in text:
        marker = "CONDITION_CLASS_REGISTRY: dict[str, type[BaseConditionStrategy]] = {"
        if marker not in text:
            marker = "CONDITION_CLASS_REGISTRY: dict[str, object] = {"
        if marker in text:
            text = text.replace(
                marker,
                marker + '\n    "lora_fa": LoRAFACondition,\n    "adalora_like_budget": AdaLoRALikeBudgetCondition,',
                1,
            )
    elif '"adalora_like_budget": AdaLoRALikeBudgetCondition' not in text:
        marker = '"lora_fa": LoRAFACondition,'
        text = text.replace(
            marker,
            marker + '\n    "adalora_like_budget": AdaLoRALikeBudgetCondition,',
            1,
        )
    return text


def _force_stage13_bf16_precision(file_text: str) -> str:
    """Keep Stage 13 7B screening in bf16; float32 full fine-tuning OOMs on 40GB GPUs."""
    if not file_text:
        return file_text
    text = re.sub(
        r'(self\.precision\s*:\s*str\s*=\s*)["\'](?:float32|fp32)["\']',
        r'\1"bf16"',
        file_text,
        count=0,
    )
    text = re.sub(
        r'(config\.precision\s*=\s*)["\'](?:float32|fp32)["\']',
        r'\1"bf16"',
        text,
        count=0,
    )
    text = re.sub(
        r'(os\.environ\.setdefault\(\s*["\']EXPERIMENT_PRECISION["\']\s*,\s*)["\'](?:float32|fp32)["\'](\s*\))',
        r'\1"bf16"\2',
        text,
        count=0,
    )
    return text


def _force_stage13_full_ft_stateless_optimizer(project_files: dict[str, str]) -> dict[str, str]:
    """Avoid full fine-tuning Adam moment OOMs during Stage 13 screening."""
    updated = dict(project_files)
    methods_text = updated.get("methods.py", "")
    if methods_text and "use_moments" not in methods_text and "class NumpyAdamW" in methods_text:
        methods_text = methods_text.replace(
            "        max_grad_norm: float = 1.0,\n    ) -> None:\n",
            "        max_grad_norm: float = 1.0,\n        use_moments: bool = True,\n    ) -> None:\n",
            1,
        )
        methods_text = methods_text.replace(
            "        self.max_grad_norm = float(max_grad_norm)\n        self.state: dict[int, dict[str, Any]] = {}\n",
            "        self.max_grad_norm = float(max_grad_norm)\n        self.use_moments = bool(use_moments)\n        self.state: dict[int, dict[str, Any]] = {}\n",
            1,
        )
        methods_text = methods_text.replace(
            "            grad = torch.nan_to_num(param.grad.detach(), nan=0.0, posinf=0.0, neginf=0.0)\n            param_id = id(param)\n",
            (
                "            grad = torch.nan_to_num(param.grad.detach(), nan=0.0, posinf=0.0, neginf=0.0)\n"
                "            if not self.use_moments:\n"
                "                if self.weight_decay > 0.0:\n"
                "                    param.data.add_(param.data, alpha=-self.lr * self.weight_decay)\n"
                "                param.data.add_(grad.to(dtype=param.data.dtype), alpha=-self.lr)\n"
                "                param.grad = None\n"
                "                continue\n"
                "            param_id = id(param)\n"
            ),
            1,
        )
        updated["methods.py"] = methods_text

    evaluate_text = updated.get("evaluate.py", "")
    if evaluate_text and "use_moments=use_moments" not in evaluate_text and "def _optimizer_for_model" in evaluate_text:
        evaluate_text = evaluate_text.replace(
            "        lr = float(self.config.learning_rate_full_ft) if str(model.mode) == \"full_ft\" else float(self.config.learning_rate_peft)\n        return NumpyAdamW(\n",
            (
                "        lr = float(self.config.learning_rate_full_ft) if str(model.mode) == \"full_ft\" else float(self.config.learning_rate_peft)\n"
                "        use_moments = str(model.mode) != \"full_ft\"\n"
                "        return NumpyAdamW(\n"
            ),
            1,
        )
        evaluate_text = evaluate_text.replace(
            "            max_grad_norm=float(self.config.max_grad_norm),\n        )\n",
            "            max_grad_norm=float(self.config.max_grad_norm),\n            use_moments=use_moments,\n        )\n",
            1,
        )
        updated["evaluate.py"] = evaluate_text
    return updated


def _force_stage13_adapter_dtype_alignment(project_files: dict[str, str]) -> dict[str, str]:
    """Keep Stage 13 bf16 activations compatible with generated adapter weights."""
    updated = dict(project_files)
    methods_text = updated.get("methods.py", "")
    if not methods_text:
        return updated
    polluted_block = (
        "            scaled_weight = scaled_weight.to(dtype=x.dtype, device=x.device)\n"
        "        bias = self.base_linear.bias\n"
        "        if bias is not None:\n"
        "            bias = bias.to(dtype=x.dtype, device=x.device)\n"
        "        return F.linear(x, scaled_weight, bias)\n"
    )
    repaired_block = (
        "            scaled_weight = scaled_weight.to(dtype=x.dtype, device=x.device)\n"
        "            bias = self.base_linear.bias\n"
        "            if bias is not None:\n"
        "                bias = bias.to(dtype=x.dtype, device=x.device)\n"
        "            return F.linear(x, scaled_weight, bias)\n"
    )
    if polluted_block in methods_text:
        methods_text = methods_text.replace(polluted_block, repaired_block)
        updated["methods.py"] = methods_text
        return updated
    if "scaled_weight = scaled_weight.to(dtype=x.dtype, device=x.device)" in methods_text:
        return updated
    methods_text = re.sub(
        r"(?m)^(?P<indent>\s*)return F\.linear\(x, scaled_weight, self\.base_linear\.bias\)$",
        lambda match: (
            f"{match.group('indent')}scaled_weight = scaled_weight.to(dtype=x.dtype, device=x.device)\n"
            f"{match.group('indent')}bias = self.base_linear.bias\n"
            f"{match.group('indent')}if bias is not None:\n"
            f"{match.group('indent')}    bias = bias.to(dtype=x.dtype, device=x.device)\n"
            f"{match.group('indent')}return F.linear(x, scaled_weight, bias)"
        ),
        methods_text,
    )
    updated["methods.py"] = methods_text
    return updated


def _enforce_stage13_required_baseline_grid(
    candidate_files: dict[str, str],
    method_diagnosis_payload: dict[str, Any],
) -> dict[str, str]:
    """Prevent Stage 13 rewrites from silently dropping Stage 15 baselines."""
    updated = dict(candidate_files)
    if "main.py" in updated:
        updated["main.py"] = _force_stage13_bf16_precision(updated["main.py"])
    if "config.py" in updated:
        updated["config.py"] = _force_stage13_bf16_precision(updated["config.py"])
    if not bool(method_diagnosis_payload.get("baseline_coverage_gap")):
        return _force_stage13_adapter_dtype_alignment(
            _force_stage13_full_ft_stateless_optimizer(updated)
        )
    forced_grid = _stage13_forced_active_grid(updated, method_diagnosis_payload)
    if not forced_grid:
        return updated

    if "main.py" in updated:
        updated["main.py"] = _force_stage13_bf16_precision(
            _rewrite_stage13_main_required_conditions(
                updated["main.py"],
                forced_grid,
            )
        )
    if "config.py" in updated:
        updated["config.py"] = _force_stage13_bf16_precision(
            _rewrite_stage13_active_conditions(
                _ensure_stage13_related_work_baseline_registrations(
                    _remove_stage13_active_condition_count_guard(updated["config.py"])
                ),
                forced_grid,
            ),
        )
    if "methods.py" in updated:
        updated["methods.py"] = _ensure_stage13_related_work_baseline_methods(
            updated["methods.py"]
        )
    return _force_stage13_adapter_dtype_alignment(
        _force_stage13_full_ft_stateless_optimizer(updated)
    )


def _ensure_stage13_main_parallel_wrapper(main_text: str) -> str:
    """Preserve Stage 13 multi-GPU sharding in LLM-regenerated main.py."""
    has_condition_list = "ACTIVE_CONDITIONS" in main_text or "REQUIRED_ACTIVE_CONDITIONS" in main_text
    if not has_condition_list:
        return main_text
    if "_run_stage13_experiment" not in main_text:
        return _ensure_stage13_plain_main_parallel_wrapper(main_text)

    text = main_text
    if "import time" not in text:
        text = text.replace("import os\n", "import os\nimport time\n", 1)
    if "from multiprocessing import Process, Queue" not in text:
        if "import time\n" in text:
            text = text.replace(
                "import time\n",
                "import time\nfrom multiprocessing import Process, Queue\n",
                1,
            )
        else:
            text = text.replace(
                "from pathlib import Path\n",
                "from multiprocessing import Process, Queue\nfrom pathlib import Path\n",
                1,
            )

    if "PARALLEL_WORKER_START_STAGGER_SEC" not in text:
        marker = "\ndef _json_ready(value: Any) -> Any:\n"
        text = text.replace(
            marker,
            "\nPARALLEL_WORKER_START_STAGGER_SEC = 75\n" + marker,
            1,
        )

    if "def _run_parallel_stage13_if_requested" not in text:
        helper_block = r'''
def _safe_load_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}

def _parse_assigned_gpu_ids() -> list[str]:
    raw = os.environ.get("RC_ASSIGNED_GPU_IDS", "").strip()
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "").strip()
    if visible:
        return [item.strip() for item in visible.split(",") if item.strip()]
    if torch.cuda.is_available():
        return [str(idx) for idx in range(torch.cuda.device_count())]
    return []

def _analysis_results_path(output_suffix: str = "") -> Path:
    suffix = str(output_suffix).strip()
    return Path(f"analysis_results_{suffix}.json") if suffix else Path("analysis_results.json")

def _selected_active_conditions() -> list[str]:
    base_conditions = ACTIVE_CONDITIONS if "ACTIVE_CONDITIONS" in globals() else REQUIRED_ACTIVE_CONDITIONS
    override = os.environ.get("EXPERIMENT_ACTIVE_CONDITIONS", "").strip()
    requested = [item.strip() for item in override.split(",") if item.strip()] if override else list(base_conditions)
    allowed = set(base_conditions)
    return [name for name in requested if name in allowed]

def _partition_conditions_evenly(conditions: list[str], worker_count: int) -> list[tuple[str, list[str]]]:
    count = max(1, int(worker_count))
    base = len(conditions) // count
    extra = len(conditions) % count
    groups: list[tuple[str, list[str]]] = []
    start = 0
    for idx in range(count):
        size = base + (1 if idx < extra else 0)
        chunk = conditions[start : start + size]
        start += size
        if chunk:
            groups.append((f"group{idx + 1}_{chunk[0]}", chunk))
    return groups

def _parallel_worker_entry(
    group_name: str,
    conditions: list[str],
    worker_index: int,
    assigned_gpu_id: str,
    status_queue: Any,
) -> None:
    try:
        os.environ["STAGE13_PARALLEL_WORKER"] = "1"
        os.environ["STAGE13_DISABLE_PARALLEL"] = "1"
        os.environ["EXPERIMENT_ACTIVE_CONDITIONS"] = ",".join(conditions)
        os.environ["RC_ASSIGNED_GPU_IDS"] = str(assigned_gpu_id)
        os.environ["CUDA_VISIBLE_DEVICES"] = str(worker_index)
        if torch.cuda.is_available():
            torch.cuda.set_device(0)
        print(
            "PARALLEL_STAGE13_WORKER_DEVICE "
            + json.dumps(
                {
                    "group": group_name,
                    "worker_index": int(worker_index),
                    "container_cuda_visible_devices": str(worker_index),
                    "local_cuda_device": 0,
                    "physical_gpu_id": str(assigned_gpu_id),
                    "conditions": conditions,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )
        _run_stage13_experiment(output_suffix=group_name)
        status_queue.put({"group": group_name, "ok": True})
    except BaseException as exc:
        print(
            "PARALLEL_STAGE13_WORKER_FAILED "
            + json.dumps(
                {
                    "group": group_name,
                    "worker_index": int(worker_index),
                    "physical_gpu_id": str(assigned_gpu_id),
                    "error": repr(exc),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )
        status_queue.put({"group": group_name, "ok": False, "error": repr(exc)})

def _run_parallel_stage13_if_requested() -> bool:
    if os.environ.get("STAGE13_PARALLEL_WORKER") == "1":
        return False
    if os.environ.get("STAGE13_DISABLE_PARALLEL") == "1":
        return False

    assigned_gpu_ids = _parse_assigned_gpu_ids()[:3]
    conditions = _selected_active_conditions()
    worker_count = min(len(assigned_gpu_ids), len(conditions), 3)
    if worker_count <= 1:
        return False

    selected_groups = _partition_conditions_evenly(conditions, worker_count)
    print(
        "PARALLEL_STAGE13_START "
        + json.dumps(
            {
                "assigned_gpu_ids": assigned_gpu_ids[:worker_count],
                "groups": {name: group_conditions for name, group_conditions in selected_groups},
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )

    status_queue = Queue()
    processes: list[tuple[str, Process]] = []
    for worker_index, (group_name, group_conditions) in enumerate(selected_groups):
        proc = Process(
            target=_parallel_worker_entry,
            args=(group_name, group_conditions, int(worker_index), str(assigned_gpu_ids[worker_index]), status_queue),
        )
        proc.start()
        processes.append((group_name, proc))
        print(
            "PARALLEL_STAGE13_WORKER_START "
            + json.dumps(
                {
                    "group": group_name,
                    "conditions": group_conditions,
                    "worker_index": int(worker_index),
                    "physical_gpu_id": assigned_gpu_ids[worker_index],
                    "pid": int(proc.pid or -1),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )
        if worker_index + 1 < len(selected_groups):
            stagger_sec = int(os.environ.get("STAGE13_WORKER_START_STAGGER_SEC", PARALLEL_WORKER_START_STAGGER_SEC))
            if stagger_sec > 0:
                print(
                    "PARALLEL_STAGE13_STAGGER_SLEEP "
                    + json.dumps(
                        {
                            "after_group": group_name,
                            "seconds": stagger_sec,
                            "reason": "avoid simultaneous 7B model load memory spikes",
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    flush=True,
                )
                time.sleep(float(stagger_sec))

    for _group_name, proc in processes:
        proc.join()

    statuses: dict[str, dict[str, Any]] = {}
    while not status_queue.empty():
        status = status_queue.get()
        if isinstance(status, dict) and isinstance(status.get("group"), str):
            statuses[str(status["group"])] = status

    failures: list[dict[str, Any]] = []
    for group_name, proc in processes:
        status = statuses.get(group_name, {})
        if proc.exitcode != 0 or not bool(status.get("ok")):
            failures.append({"group": group_name, "return_code": int(proc.exitcode or -1), "error": status.get("error")})
            continue
        result_path = _analysis_results_path(group_name)
        if not result_path.is_file():
            failures.append({"group": group_name, "return_code": 0, "error": f"missing {result_path}"})
            continue

    if failures:
        raise RuntimeError("Parallel Stage 13 worker failure: " + json.dumps(failures, ensure_ascii=False, sort_keys=True))

    worker_payloads = [_safe_load_json_file(_analysis_results_path(group_name)) for group_name, _proc in processes]
    all_condition_summaries: dict[str, Any] = {}
    for payload in worker_payloads:
        condition_summaries = payload.get("condition_summaries", {})
        if isinstance(condition_summaries, dict):
            all_condition_summaries.update(condition_summaries)

    aggregator = ResultAggregator(_stabilize_config(_load_runtime_config(), 0))
    all_pairwise_comparisons: list[dict[str, Any]] = []
    for left_name, right_name in globals().get("AUTHORITATIVE_COMPARISON_PAIRS", []):
        left_summary = all_condition_summaries.get(left_name)
        right_summary = all_condition_summaries.get(right_name)
        if left_summary is None or right_summary is None:
            continue
        comparison = aggregator.paired_comparison(left_summary, right_summary)
        comparison["baseline_condition"] = left_name
        comparison["candidate_condition"] = right_name
        all_pairwise_comparisons.append(_json_ready(comparison))

    ranking = sorted(
        (
            {"condition": name, "primary_metric": float(summary["primary_metric"])}
            for name, summary in all_condition_summaries.items()
            if isinstance(summary, dict) and "primary_metric" in summary
        ),
        key=lambda item: item["primary_metric"],
    )
    merged_payload = {
        "schema_version": 4,
        "experiment_type": "stage13_same_round_h1_screening_parallel",
        "parallel_groups": {name: group_conditions for name, group_conditions in selected_groups},
        "assigned_gpu_ids": assigned_gpu_ids[:worker_count],
        "condition_summaries": _json_ready(all_condition_summaries),
        "pairwise_comparisons": _json_ready(all_pairwise_comparisons),
        "ranking": ranking,
        "best_condition": ranking[0]["condition"] if ranking else None,
        "primary_metric": float(ranking[0]["primary_metric"]) if ranking else float("inf"),
    }
    Path("analysis_results.json").write_text(
        json.dumps(merged_payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    Path("results.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "primary_metric": merged_payload["primary_metric"],
                "analysis_results_json_path": "analysis_results.json",
                "num_conditions_run": int(len(all_condition_summaries)),
                "ranking": ranking,
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print("PARALLEL_STAGE13_DONE " + json.dumps(_json_ready(merged_payload), ensure_ascii=False, sort_keys=True), flush=True)
    return True
'''
        stripped_helper = "\n" + helper_block.strip() + "\n\n"
        if "\ndef _resume_record_for_seed" in text:
            text = text.replace(
                "\ndef _resume_record_for_seed",
                stripped_helper + "def _resume_record_for_seed",
                1,
            )
        elif "\ndef _json_ready" in text:
            text = text.replace(
                "\ndef _json_ready",
                stripped_helper + "def _json_ready",
                1,
            )
        elif "\ndef _run_stage13_experiment" in text:
            text = text.replace(
                "\ndef _run_stage13_experiment",
                stripped_helper + "def _run_stage13_experiment",
                1,
            )
        else:
            text = text + stripped_helper

    text = text.replace(
        "if not isinstance(raw, dict):\n        return None\n    metric = _safe_float(raw.get(\"primary_metric\"))",
        "if isinstance(raw, dict):\n        payload = raw.get(\"record\") if isinstance(raw.get(\"record\"), dict) else raw\n        metric = _safe_float(payload.get(\"primary_metric\"))\n    else:\n        metric = _safe_float(raw)",
        1,
    )
    text = text.replace("def _run_stage13_experiment() -> None:", "def _run_stage13_experiment(output_suffix: str = \"\") -> None:", 1)
    text = text.replace(
        "    Path(\"analysis_results.json\").write_text(\n        json.dumps(results_payload, indent=2, ensure_ascii=False, sort_keys=True) + \"\\n\",\n        encoding=\"utf-8\",\n    )",
        "    analysis_results_path = _analysis_results_path(output_suffix)\n    analysis_results_path.write_text(\n        json.dumps(results_payload, indent=2, ensure_ascii=False, sort_keys=True) + \"\\n\",\n        encoding=\"utf-8\",\n    )",
        1,
    )
    text = text.replace(
        "\"analysis_results_json_path\": \"analysis_results.json\"",
        "\"analysis_results_json_path\": str(analysis_results_path)",
        1,
    )
    text = text.replace(
        "def main() -> None:\n    _run_stage13_experiment()",
        "def main() -> None:\n    if _run_parallel_stage13_if_requested():\n        return\n    _run_stage13_experiment()",
        1,
    )
    return text


def _ensure_stage13_plain_main_parallel_wrapper(main_text: str) -> str:
    """Wrap plain sequential Stage 13 main.py files in subprocess workers."""
    if "def main() -> None:" not in main_text:
        return main_text
    if "def _run_parallel_stage13_subprocess_if_requested" in main_text:
        return main_text

    text = main_text
    if "import sys" not in text:
        text = text.replace("import os\n", "import os\nimport sys\n", 1)
    if "import time" not in text:
        text = text.replace("import os\n", "import os\nimport time\n", 1)
    if "import shutil" not in text:
        text = text.replace("import os\n", "import os\nimport shutil\n", 1)
    if "import subprocess" not in text:
        text = text.replace("import os\n", "import os\nimport subprocess\n", 1)

    text = text.replace("def main() -> None:", "def _stage13_single_worker_main() -> None:", 1)
    helper_block = r'''
PARALLEL_WORKER_START_STAGGER_SEC = 75

def _parse_assigned_gpu_ids() -> list[str]:
    raw = os.environ.get("RC_ASSIGNED_GPU_IDS", "").strip()
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "").strip()
    if visible:
        return [item.strip() for item in visible.split(",") if item.strip()]
    if torch.cuda.is_available():
        return [str(idx) for idx in range(torch.cuda.device_count())]
    return []

def _stage13_selected_active_conditions() -> list[str]:
    base_conditions = ACTIVE_CONDITIONS if "ACTIVE_CONDITIONS" in globals() else REQUIRED_ACTIVE_CONDITIONS
    override = os.environ.get("EXPERIMENT_ACTIVE_CONDITIONS", "").strip()
    requested = [item.strip() for item in override.split(",") if item.strip()] if override else list(base_conditions)
    allowed = set(base_conditions)
    return [name for name in requested if name in allowed]

def _stage13_apply_worker_condition_override() -> None:
    selected = _stage13_selected_active_conditions()
    if "REQUIRED_ACTIVE_CONDITIONS" in globals():
        REQUIRED_ACTIVE_CONDITIONS[:] = selected
    if "ACTIVE_CONDITIONS" in globals():
        ACTIVE_CONDITIONS[:] = selected

def _partition_conditions_evenly(conditions: list[str], worker_count: int) -> list[tuple[str, list[str]]]:
    count = max(1, int(worker_count))
    base = len(conditions) // count
    extra = len(conditions) % count
    groups: list[tuple[str, list[str]]] = []
    start = 0
    for idx in range(count):
        size = base + (1 if idx < extra else 0)
        chunk = conditions[start : start + size]
        start += size
        if chunk:
            groups.append((f"group{idx + 1}_{chunk[0]}", chunk))
    return groups

def _parallel_worker_dir(group_name: str) -> Path:
    safe_name = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in group_name)
    return Path(f"_parallel_{safe_name}")

def _prepare_parallel_worker_dir(group_name: str) -> Path:
    worker_dir = _parallel_worker_dir(group_name)
    worker_dir.mkdir(parents=True, exist_ok=True)
    skip_names = {
        "results.json",
        "partial_results.json",
        "analysis_results.json",
        "analysis_results_merged.json",
    }
    for path in Path(".").iterdir():
        if not path.is_file() or path.name in skip_names:
            continue
        if path.suffix.lower() not in {".py", ".json", ".txt", ".yaml", ".yml", ".cfg", ".ini", ".sh"}:
            continue
        shutil.copy2(path, worker_dir / path.name)
    return worker_dir

def _load_worker_result(worker_dir: Path) -> dict:
    for name in ("results.json", "partial_results.json"):
        path = worker_dir / name
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return {}

def _merge_parallel_worker_payloads(
    selected_groups: list[tuple[str, list[str]]],
    assigned_gpu_ids: list[str],
    allow_partial: bool = False,
) -> dict:
    merged_metrics: dict[str, float] = {}
    merged_rows: list[dict] = []
    failures: list[dict] = []
    for group_name, _conditions in selected_groups:
        worker_dir = _parallel_worker_dir(group_name)
        payload = _load_worker_result(worker_dir)
        if not payload:
            failures.append({"group": group_name, "error": "missing worker results"})
            continue
        metrics = payload.get("metrics", {})
        if isinstance(metrics, dict):
            merged_metrics.update(metrics)
        rows = payload.get("results", [])
        if isinstance(rows, list):
            merged_rows.extend(row for row in rows if isinstance(row, dict))
    if failures and not allow_partial:
        raise RuntimeError("Parallel Stage 13 missing worker payloads: " + json.dumps(failures, ensure_ascii=False))

    by_condition: dict[str, list[float]] = {}
    for row in merged_rows:
        condition_name = str(row.get("condition_name") or row.get("condition_registry_name") or "").strip()
        if not condition_name:
            continue
        try:
            metric = float(row.get("primary_metric"))
        except (TypeError, ValueError):
            continue
        if math.isfinite(metric):
            by_condition.setdefault(condition_name, []).append(metric)
    ranking = sorted(
        (
            {"condition": name, "primary_metric": float(sum(values) / len(values))}
            for name, values in by_condition.items()
            if values
        ),
        key=lambda item: item["primary_metric"],
    )
    return {
        "status": "partial" if failures else "completed",
        "metrics": merged_metrics,
        "results": merged_rows,
        "completed_seed_count": int(len(merged_rows)),
        "num_conditions_run": int(len(by_condition)),
        "parallel_groups": {name: conditions for name, conditions in selected_groups},
        "assigned_gpu_ids": assigned_gpu_ids[: len(selected_groups)],
        "worker_failures": failures,
        "ranking": ranking,
        "primary_metric": ranking[0]["primary_metric"] if ranking else None,
    }

def _run_parallel_stage13_subprocess_if_requested() -> bool:
    if os.environ.get("STAGE13_PARALLEL_WORKER") == "1":
        return False
    if os.environ.get("STAGE13_DISABLE_PARALLEL") == "1":
        return False

    assigned_gpu_ids = _parse_assigned_gpu_ids()[:3]
    conditions = _stage13_selected_active_conditions()
    worker_count = min(len(assigned_gpu_ids), len(conditions), 3)
    if worker_count <= 1:
        return False

    selected_groups = _partition_conditions_evenly(conditions, worker_count)
    print(
        "PARALLEL_STAGE13_START "
        + json.dumps(
            {
                "assigned_gpu_ids": assigned_gpu_ids[:worker_count],
                "groups": {name: group_conditions for name, group_conditions in selected_groups},
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )

    processes: list[tuple[str, subprocess.Popen]] = []
    for worker_index, (group_name, group_conditions) in enumerate(selected_groups):
        worker_dir = _prepare_parallel_worker_dir(group_name)
        env = os.environ.copy()
        env["STAGE13_PARALLEL_WORKER"] = "1"
        env["EXPERIMENT_ACTIVE_CONDITIONS"] = ",".join(group_conditions)
        env["RC_ASSIGNED_GPU_IDS"] = str(assigned_gpu_ids[worker_index])
        env["CUDA_VISIBLE_DEVICES"] = str(worker_index)
        env["STAGE13_WORKER_GROUP"] = group_name
        proc = subprocess.Popen([sys.executable, "-u", "main.py"], cwd=str(worker_dir), env=env)
        processes.append((group_name, proc))
        print(
            "PARALLEL_STAGE13_WORKER_START "
            + json.dumps(
                {
                    "group": group_name,
                    "conditions": group_conditions,
                    "worker_index": int(worker_index),
                    "container_cuda_visible_devices": str(worker_index),
                    "physical_gpu_id": assigned_gpu_ids[worker_index],
                    "pid": int(proc.pid or -1),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )
        if worker_index + 1 < len(selected_groups):
            stagger_sec = int(os.environ.get("STAGE13_WORKER_START_STAGGER_SEC", PARALLEL_WORKER_START_STAGGER_SEC))
            if stagger_sec > 0:
                print(
                    "PARALLEL_STAGE13_STAGGER_SLEEP "
                    + json.dumps(
                        {"after_group": group_name, "seconds": stagger_sec},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    flush=True,
                )
                time.sleep(float(stagger_sec))

    failures: list[dict] = []
    for group_name, proc in processes:
        return_code = proc.wait()
        if return_code != 0:
            failures.append({"group": group_name, "return_code": int(return_code)})
    if failures:
        partial_payload = _merge_parallel_worker_payloads(selected_groups, assigned_gpu_ids, allow_partial=True)
        partial_payload["status"] = "partial"
        partial_payload["worker_failures"] = failures
        Path("partial_results.json").write_text(
            json.dumps(partial_payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        raise RuntimeError("Parallel Stage 13 worker failure: " + json.dumps(failures, ensure_ascii=False, sort_keys=True))

    merged_payload = _merge_parallel_worker_payloads(selected_groups, assigned_gpu_ids)
    Path("analysis_results.json").write_text(
        json.dumps(merged_payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    Path("partial_results.json").write_text(
        json.dumps(merged_payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    Path("results.json").write_text(
        json.dumps(merged_payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("PARALLEL_STAGE13_DONE " + json.dumps(merged_payload, ensure_ascii=False, sort_keys=True), flush=True)
    return True

def main() -> None:
    if os.environ.get("STAGE13_PARALLEL_WORKER") == "1":
        _stage13_apply_worker_condition_override()
        _stage13_single_worker_main()
        return
    if _run_parallel_stage13_subprocess_if_requested():
        return
    _stage13_single_worker_main()
'''
    marker = re.search(r'\nif __name__ == ["\']__main__["\']:\n\s+main\(\)\n?', text)
    if marker:
        text = text[: marker.start()] + "\n" + helper_block.strip() + "\n" + text[marker.start() :]
    else:
        text = text.rstrip() + "\n\n" + helper_block.strip() + "\n"
    return text


def _build_stage13_incremental_plan(
    *,
    stage_dir: Path,
    best_files: dict[str, str],
    candidate_files: dict[str, str],
    condition_coverage_hint: str,
) -> dict[str, Any]:
    config_text = candidate_files.get("config.py") or best_files.get("config.py") or ""
    registry = _parse_stage13_condition_registry(config_text)
    manual_active_conditions = _stage13_manual_redesign_active_conditions(stage_dir)
    declared_active_conditions = _parse_stage13_active_condition_names(
        config_text,
        candidate_files.get("main.py") or best_files.get("main.py") or "",
    )
    ordered_conditions = (
        manual_active_conditions
        or declared_active_conditions
        or [entry["condition_name"] for entry in registry]
    )
    family_by_condition = {
        entry["condition_name"]: entry.get("family", "")
        for entry in registry
    }
    expected_seeds = _parse_stage13_seed_plan(config_text)
    condition_seed_cache = _load_stage13_condition_seed_cache(stage_dir)

    incomplete_conditions = [
        name
        for name in ordered_conditions
        if not set(expected_seeds).issubset(set(condition_seed_cache.get(name, {}).keys()))
    ]
    all_expected_results_complete = bool(ordered_conditions and expected_seeds) and not incomplete_conditions

    changed_files = sorted(
        fname
        for fname in set(best_files) | set(candidate_files)
        if best_files.get(fname) != candidate_files.get(fname)
    )
    executable_changed = [
        fname
        for fname in changed_files
        if Path(fname).suffix in {".py", ".txt", ".cfg", ".ini", ".json", ".yaml", ".yml", ".sh"}
    ]
    if not executable_changed:
        if incomplete_conditions or (
            condition_coverage_hint.strip() and not all_expected_results_complete
        ):
            return {
                "active": True,
                "reason": "coverage_gap_replay",
                "changed_files": changed_files,
                "coverage_gap": True,
                "active_conditions": list(incomplete_conditions or ordered_conditions),
                "frozen_conditions": [
                    name for name in ordered_conditions if name not in set(incomplete_conditions)
                ],
                "resume_registry": condition_seed_cache,
                "reuse_conditions": sorted(condition_seed_cache.keys()),
            }
        return {
            "active": False,
            "reason": "no_executable_change",
            "changed_files": changed_files,
            "coverage_gap": False,
            "active_conditions": [],
            "frozen_conditions": ordered_conditions,
            "resume_registry": condition_seed_cache,
            "reuse_conditions": sorted(condition_seed_cache.keys()),
        }

    class_to_condition = {
        entry["class_name"]: entry["condition_name"] for entry in registry
    }
    active_conditions: list[str] = []
    shared_change = False
    for file_name in executable_changed:
        if file_name == "methods.py":
            affected, methods_shared_change = _stage13_affected_conditions_for_methods_change(
                best_files.get(file_name, ""),
                candidate_files.get(file_name, ""),
                class_to_condition,
            )
            if methods_shared_change:
                shared_change = True
                break
            active_conditions.extend(sorted(affected))
            continue
        if file_name in {"config.py", "main.py", "evaluate.py", "data.py", "setup.py", "requirements.txt"}:
            shared_change = True
            break
        shared_change = True
        break

    if shared_change:
        reusable_baselines = [
            name
            for name in ordered_conditions
            if family_by_condition.get(name) == "baseline"
            and name not in set(incomplete_conditions)
            and bool(condition_seed_cache.get(name))
        ]
        active_conditions = [
            name
            for name in ordered_conditions
            if name not in set(reusable_baselines)
        ]
        resume_registry = {
            name: seed_map
            for name, seed_map in condition_seed_cache.items()
            if name in set(reusable_baselines)
        }
        return {
            "active": True,
            "reason": "shared_execution_change",
            "changed_files": changed_files,
            "coverage_gap": bool(incomplete_conditions or condition_coverage_hint.strip()),
            "active_conditions": active_conditions,
            "frozen_conditions": reusable_baselines,
            "resume_registry": resume_registry,
            "reuse_conditions": sorted(resume_registry.keys()),
        }

    affected_ordered = [
        name for name in ordered_conditions if name in set(active_conditions)
    ]
    if not affected_ordered:
        affected_ordered = list(incomplete_conditions)
    frozen_conditions = [
        name for name in ordered_conditions if name not in set(affected_ordered)
    ]
    resume_registry = {
        name: seed_map
        for name, seed_map in condition_seed_cache.items()
        if name in set(frozen_conditions)
    }
    return {
        "active": True,
        "reason": "condition_scoped_refine",
        "changed_files": changed_files,
        "coverage_gap": bool(incomplete_conditions or condition_coverage_hint.strip()),
        "active_conditions": affected_ordered,
        "frozen_conditions": frozen_conditions,
        "resume_registry": resume_registry,
        "reuse_conditions": sorted(resume_registry.keys()),
    }


def _should_use_stage13_incremental_replay(
    *,
    incremental_refine_available: bool,
    interrupted_resume_project_dir: Path | None,
    iteration: int,
    preflight_incremental_plan: dict[str, Any],
    method_diagnosis_payload: dict[str, Any],
) -> bool:
    """Replay only when the current plan is still methodologically valid."""
    if bool(method_diagnosis_payload.get("baseline_coverage_gap")):
        return False
    return (
        (incremental_refine_available or interrupted_resume_project_dir is not None)
        and iteration == 1
        and (
            interrupted_resume_project_dir is not None
            or str(preflight_incremental_plan.get("reason") or "") in {
                "coverage_gap_replay",
                "run_local_replay",
            }
        )
    )


def _should_use_stage13_deterministic_baseline_replay(
    *,
    candidate_files: dict[str, str],
    method_diagnosis_payload: dict[str, Any],
    interrupted_resume_project_dir: Path | None,
    manual_redesign_active: bool = False,
) -> bool:
    """Reuse trusted Stage 13 code when a rerun needs evidence, not new code."""
    required_files = {"main.py", "config.py", "methods.py"}
    return (
        (
            interrupted_resume_project_dir is not None
            or (
                manual_redesign_active
                and not bool(method_diagnosis_payload.get("baseline_coverage_gap"))
            )
        )
        and required_files.issubset(set(candidate_files))
    )


def _validate_stage13_candidate_main(
    main_code: str,
    *,
    trusted_deterministic_replay: bool = False,
) -> CodeValidation:
    """Validate Stage 13 code while allowing pipeline-owned replay wrappers."""
    return validate_code(main_code, skip_security=trusted_deterministic_replay)


def _stage13_llm_response_is_context_overflow(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    return (
        "context overflow" in normalized
        or ("prompt too large" in normalized and "model" in normalized)
        or ("maximum context" in normalized and "exceeded" in normalized)
    )


def _notifications_enabled(config: RCConfig) -> bool:
    channel = str(getattr(config.notifications, "channel", "") or "").strip().lower()
    target = str(getattr(config.notifications, "target", "") or "").strip()
    return bool(config.openclaw_bridge.use_message or (target and channel not in {"", "console", "local"}))


def _classify_stage12_failure(message: str) -> tuple[str, bool]:
    text = (message or "").lower()
    if "dataset" in text or "data_ready" in text or "load_dataset" in text:
        return "dataset_prep", True
    if "dtype" in text or "bfloat16" in text or "float16" in text:
        return "dtype_mismatch", True
    if "out of memory" in text or "cuda out of memory" in text:
        return "oom", True
    if "autograd" in text or "backward through the graph" in text or "inplace" in text:
        return "autograd", True
    if "timeout" in text:
        return "timeout", True
    if "config" in text or "contract" in text or "preflight" in text:
        return "config_mismatch", True
    if "httpx" in text or "readtimeout" in text or "network" in text:
        return "network", True
    return "unknown", False


def _sandbox_wait_notifier(
    *,
    run_dir: Path,
    adapters: AdapterBundle,
    config: RCConfig,
    run_id: str,
    stage: Stage,
) -> callable:
    def _notify(subject: str, body: str) -> None:
        lowered = subject.strip().lower()
        action = (
            ControlAction.WAIT_FOR_RESOURCE
            if lowered.startswith("gpu-wait")
            else ControlAction.PROCEED
        )
        write_control_state(
            run_dir,
            run_id=run_id,
            current_stage=int(stage),
            current_stage_name=stage.name,
            current_substep=lowered or "sandbox_notify",
            current_action=action.value,
            waiting_reason=body if action == ControlAction.WAIT_FOR_RESOURCE else "",
            observers=stage_observer_snapshot(
                run_dir,
                stage=stage,
                run_id=run_id,
                current_action=action,
                status=StageStatus.RUNNING,
                substep=lowered or "sandbox_notify",
                waiting_reason=body if action == ControlAction.WAIT_FOR_RESOURCE else "",
            ),
        )
        event_type = "stage_signal"
        event_status = "info"
        lowered_body = body.strip()
        if lowered.startswith("gpu-wait-start") or lowered.startswith("gpu-wait-heartbeat"):
            event_type = "gpu_waiting"
            event_status = "warning"
        elif lowered.startswith("gpu-wait-resumed"):
            event_type = "gpu_ready"
        elif lowered.startswith("gpu-wait-timeout"):
            event_type = "gpu_wait_timeout"
            event_status = "error"
        elif lowered.startswith("gpu-wait-stopped"):
            event_type = "gpu_wait_stopped"
            event_status = "warning"
        append_supervisor_event(
            run_dir,
            event_type=event_type,
            status=event_status,
            summary=lowered_body.splitlines()[0] if lowered_body else subject,
            stage=int(stage),
            stage_name=stage.name,
            backend="sandbox",
            waiting_reason=body if action == ControlAction.WAIT_FOR_RESOURCE else "",
            alerts=["gpu:waiting"] if event_type == "gpu_waiting" else [],
            payload={
                "subject": subject,
                "run_id": run_id,
            },
        )
        if not _notifications_enabled(config):
            return
        try:
            adapters.message.notify(
                config.notifications.channel,
                f"{subject}",
                (
                    f"Run: {run_id}\n"
                    f"Stage {int(stage):02d} {stage.name}\n\n"
                    f"{body}"
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sandbox wait notification failed for %s: %s", subject, exc)

    return _notify


def _execute_resource_planning(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    exp_plan = _read_prior_artifact(run_dir, "exp_plan.yaml") or ""
    schedule: dict[str, Any] | None = None
    if llm is not None:
        _pm = prompts or PromptManager()
        _overlay = _get_evolution_overlay(run_dir, "resource_planning")
        sp = _pm.for_stage("resource_planning", evolution_overlay=_overlay, exp_plan=exp_plan)
        resp = _chat_with_prompt(
            llm,
            sp.system,
            sp.user,
            json_mode=sp.json_mode,
            max_tokens=sp.max_tokens,
        )
        parsed = _safe_json_loads(resp.content, {})
        if isinstance(parsed, dict):
            schedule = parsed
    if schedule is None or not _is_meaningful_schedule(schedule):
        schedule = _default_schedule(config, exp_plan)
    else:
        schedule.setdefault("schema_version", 1)
        schedule.setdefault("generated", _utcnow_iso())
        schedule.setdefault("execution_strategy", "single_gpu_serial")
        schedule.setdefault("gpu_wait_policy", "wait_for_idle_gpu_0_6")
        schedule.setdefault(
            "checkpoint_strategy",
            "resume_from_latest_successful_stage_artifact",
        )
    (stage_dir / "schedule.json").write_text(
        json.dumps(schedule, indent=2), encoding="utf-8"
    )
    return StageResult(
        stage=Stage.RESOURCE_PLANNING,
        status=StageStatus.DONE,
        artifacts=("schedule.json",),
        evidence_refs=("stage-11/schedule.json",),
    )


def _execute_experiment_run(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    from researchclaw.experiment.factory import create_sandbox
    from researchclaw.experiment.runner import ExperimentRunner
    from researchclaw.pipeline.runner import stop_requested

    schedule_text = _read_prior_artifact(run_dir, "schedule.json") or "{}"
    # Try multi-file experiment directory first, fall back to single file
    exp_dir_path = _read_prior_artifact(run_dir, "experiment/")
    code_text = ""
    if exp_dir_path and Path(exp_dir_path).is_dir():
        main_path = Path(exp_dir_path) / "main.py"
        if main_path.exists():
            try:
                code_text = main_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                code_text = ""
    if not code_text:
        code_text = _read_prior_artifact(run_dir, "experiment.py") or ""

    runs_dir = stage_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    mode = config.experiment.mode

    def _write_run_payload(payload: dict[str, Any]) -> None:
        run_id = str(payload.get("run_id") or "run-1")
        (runs_dir / f"{_safe_filename(run_id)}.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

    def _stage12_failure(
        error: str,
        *,
        artifacts: tuple[str, ...] = ("runs/", "runtime_observer.json"),
        run_payload: dict[str, Any] | None = None,
        preflight_errors: list[str] | None = None,
        preflight_warnings: list[str] | None = None,
    ) -> StageResult:
        failure_type, retryable = _classify_stage12_failure(error)
        if run_payload is not None:
            run_payload["failure_type"] = failure_type
            run_payload["retryable"] = retryable
        _write_stage12_runtime_observer(
            stage_dir=stage_dir,
            run_dir=run_dir,
            config=config,
            schedule_text=schedule_text,
            exp_dir=Path(exp_dir_path) if exp_dir_path and Path(exp_dir_path).is_dir() else None,
            preflight_errors=preflight_errors or [],
            preflight_warnings=preflight_warnings or [],
            run_payload=run_payload,
            status="failed",
        )
        return StageResult(
            stage=Stage.EXPERIMENT_RUN,
            status=StageStatus.FAILED,
            artifacts=artifacts,
            evidence_refs=tuple(f"stage-12/{a}" for a in artifacts),
            error=f"[{failure_type}] " + _augment_stage12_error(error, run_payload),
            decision="retry",
            control_hints={
                "failure_type": failure_type,
                "retryable": retryable,
            },
        )

    if exp_dir_path and Path(exp_dir_path).is_dir():
        project_files = sorted(Path(exp_dir_path).glob("*.py"))
        project_errors: list[str] = []
        if not project_files:
            project_errors.append("experiment/ contains no Python files")
        for src_file in project_files:
            validation = validate_code(src_file.read_text(encoding="utf-8"))
            if not validation.ok:
                project_errors.append(f"{src_file.name}: {validation.summary()}")
        if project_errors:
            payload = {
                "run_id": "run-1",
                "task_id": "sandbox-main",
                "status": "failed",
                "metrics": {},
                "elapsed_sec": 0.0,
                "stdout": "",
                "stderr": "; ".join(project_errors),
                "timed_out": False,
                "completed_at": _utcnow_iso(),
            }
            _write_run_payload(payload)
            return _stage12_failure(
                "Invalid Stage 10 experiment artifact: " + "; ".join(project_errors),
                run_payload=payload,
            )
    elif not code_text.strip():
        payload = {
            "run_id": "run-1",
            "task_id": "sandbox-main",
            "status": "failed",
            "metrics": {},
            "elapsed_sec": 0.0,
            "stdout": "",
            "stderr": "No executable experiment code found for Stage 12.",
            "timed_out": False,
            "completed_at": _utcnow_iso(),
        }
        _write_run_payload(payload)
        return _stage12_failure(
            "No executable experiment code found for Stage 12.",
            run_payload=payload,
        )

    if mode in ("sandbox", "docker"):
        # P7: Auto-install missing dependencies before subprocess sandbox
        if mode == "sandbox":
            _all_code = code_text
            if exp_dir_path and Path(exp_dir_path).is_dir():
                for _pyf in Path(exp_dir_path).glob("*.py"):
                    try:
                        _all_code += "\n" + _pyf.read_text(encoding="utf-8")
                    except (OSError, UnicodeDecodeError):
                        pass
            _ensure_sandbox_deps(_all_code, config.experiment.sandbox.python_path)

        sandbox = create_sandbox(
            config.experiment,
            runs_dir / "sandbox",
            notify_callback=_sandbox_wait_notifier(
                run_dir=run_dir,
                adapters=adapters,
                config=config,
                run_id=run_dir.name,
                stage=Stage.EXPERIMENT_RUN,
            ),
            stop_requested=lambda: stop_requested(run_dir),
        )
        # Use run_project for multi-file, run for single-file
        if exp_dir_path and Path(exp_dir_path).is_dir():
            preflight_errors, preflight_warnings = _stage12_preflight(
                stage_dir=stage_dir,
                run_dir=run_dir,
                exp_dir=Path(exp_dir_path),
                config=config,
                schedule_text=schedule_text,
            )
            _write_stage12_runtime_observer(
                stage_dir=stage_dir,
                run_dir=run_dir,
                config=config,
                schedule_text=schedule_text,
                exp_dir=Path(exp_dir_path),
                preflight_errors=preflight_errors,
                preflight_warnings=preflight_warnings,
                run_payload=None,
                status="preflight",
            )
            for warning in preflight_warnings:
                logger.warning("Stage 12 preflight: %s", warning)
            if preflight_errors:
                payload = {
                    "run_id": "run-1",
                    "task_id": "sandbox-main",
                    "status": "failed",
                    "metrics": {},
                    "elapsed_sec": 0.0,
                    "stdout": "",
                    "stderr": "; ".join(preflight_errors),
                    "timed_out": False,
                    "completed_at": _utcnow_iso(),
                }
                _write_run_payload(payload)
                return _stage12_failure(
                    "Stage 12 preflight failed: " + "; ".join(preflight_errors),
                    artifacts=("runs/", "preflight_report.json"),
                    run_payload=payload,
                    preflight_errors=preflight_errors,
                    preflight_warnings=preflight_warnings,
                )
            result = sandbox.run_project(
                Path(exp_dir_path), timeout_sec=config.experiment.time_budget_sec
            )
        else:
            result = sandbox.run(
                code_text, timeout_sec=config.experiment.time_budget_sec
            )
        # Try to read structured results.json from sandbox working dir
        structured_results: dict[str, Any] | None = None
        sandbox_project = runs_dir / "sandbox" / "_project"
        results_json_path = sandbox_project / "results.json"
        if results_json_path.exists():
            try:
                structured_results = json.loads(
                    results_json_path.read_text(encoding="utf-8")
                )
                # Copy results.json to runs dir for easy access
                (runs_dir / "results.json").write_text(
                    results_json_path.read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
            except (json.JSONDecodeError, OSError):
                structured_results = None

        # If sandbox metrics are empty, try to parse from stdout
        effective_metrics = result.metrics
        if not effective_metrics and result.stdout:
            effective_metrics = _parse_metrics_from_stdout(result.stdout)

        # Determine run status: completed / partial (timed out with data) / failed
        # R6-2: Detect stdout failure signals even when exit code is 0
        _stdout_has_failure = bool(
            result.stdout
            and not effective_metrics
            and any(
                sig in result.stdout
                for sig in ("FAIL:", "NaN/divergence", "Traceback (most recent")
            )
        )
        if result.returncode == 0 and not result.timed_out and not _stdout_has_failure:
            run_status = "completed"
        elif result.timed_out and effective_metrics:
            run_status = "partial"
            logger.warning(
                "Experiment timed out but captured %d partial metrics",
                len(effective_metrics),
            )
        else:
            run_status = "failed"
            if _stdout_has_failure:
                logger.warning(
                    "Experiment exited cleanly but stdout contains failure signals"
                )

        # P1: Warn if experiment completed suspiciously fast (trivially easy benchmark)
        if run_status == "completed" and result.elapsed_sec and result.elapsed_sec < 5.0:
            logger.warning(
                "Stage 12: Experiment completed in %.2fs — benchmark may be trivially easy. "
                "Consider increasing task difficulty.",
                result.elapsed_sec,
            )

        run_payload: dict[str, Any] = {
            "run_id": "run-1",
            "task_id": "sandbox-main",
            "status": run_status,
            "metrics": effective_metrics,
            "elapsed_sec": result.elapsed_sec,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timed_out": result.timed_out,
            "completed_at": _utcnow_iso(),
        }
        if structured_results is not None:
            run_payload["structured_results"] = structured_results
        # Auto-generate results.json from parsed metrics if sandbox didn't produce one
        if structured_results is None and effective_metrics:
            auto_results = {"source": "stdout_parsed", "metrics": effective_metrics}
            (runs_dir / "results.json").write_text(
                json.dumps(auto_results, indent=2), encoding="utf-8"
            )
            logger.info("Stage 12: Auto-generated results.json from stdout metrics (%d keys)", len(effective_metrics))
        _write_run_payload(run_payload)

        # R11-6: Time budget adequacy check
        if result.timed_out or (result.elapsed_sec and result.elapsed_sec > config.experiment.time_budget_sec * 0.9):
            # Parse stdout to estimate how many conditions/seeds completed
            _stdout = result.stdout or ""
            _completed_conditions = set()
            _completed_seeds = 0
            for _line in _stdout.splitlines():
                if "condition=" in _line and "seed=" in _line:
                    _completed_seeds += 1
                    _cond_match = re.match(r".*condition=(\S+)", _line)
                    if _cond_match:
                        _completed_conditions.add(_cond_match.group(1))
            _time_budget_warning = {
                "timed_out": result.timed_out,
                "elapsed_sec": result.elapsed_sec,
                "budget_sec": config.experiment.time_budget_sec,
                "conditions_completed": sorted(_completed_conditions),
                "total_seed_runs": _completed_seeds,
                "warning": (
                    f"Experiment used {result.elapsed_sec:.0f}s of "
                    f"{config.experiment.time_budget_sec}s budget. "
                    f"Only {len(_completed_conditions)} conditions completed "
                    f"({_completed_seeds} seed-runs). Consider increasing "
                    f"time_budget_sec for more complete results."
                ),
            }
            logger.warning(
                "Stage 12: %s", _time_budget_warning["warning"]
            )
            (stage_dir / "time_budget_warning.json").write_text(
                json.dumps(_time_budget_warning, indent=2), encoding="utf-8"
            )

        # FIX-8: Validate seed count from structured results
        if structured_results and isinstance(structured_results, dict):
            _sr_conditions = structured_results.get("conditions", structured_results.get("per_condition", {}))
            if isinstance(_sr_conditions, dict):
                for _cname, _cdata in _sr_conditions.items():
                    if isinstance(_cdata, dict):
                        _seeds_run = _cdata.get("seeds_run", _cdata.get("n_seeds", 0))
                        if isinstance(_seeds_run, (int, float)) and 0 < _seeds_run < 3:
                            logger.warning(
                                "Stage 12: Condition '%s' ran only %d seed(s) — "
                                "minimum 3 required for statistical validity",
                                _cname, int(_seeds_run),
                            )

        if run_status == "failed":
            reason = "Experiment run failed"
            if result.stderr:
                reason = result.stderr.splitlines()[-1][:500] or reason
            return _stage12_failure(reason, run_payload=run_payload)
        _write_stage12_runtime_observer(
            stage_dir=stage_dir,
            run_dir=run_dir,
            config=config,
            schedule_text=schedule_text,
            exp_dir=Path(exp_dir_path) if exp_dir_path and Path(exp_dir_path).is_dir() else None,
            preflight_errors=preflight_errors if exp_dir_path and Path(exp_dir_path).is_dir() else [],
            preflight_warnings=preflight_warnings if exp_dir_path and Path(exp_dir_path).is_dir() else [],
            run_payload=run_payload,
            status=run_status,
        )
    elif mode == "simulated":
        schedule = _safe_json_loads(schedule_text, {})
        tasks = schedule.get("tasks", []) if isinstance(schedule, dict) else []
        if not isinstance(tasks, list):
            tasks = []
        for idx, task in enumerate(tasks or [{"id": "task-1", "name": "simulated"}]):
            task_id = (
                str(task.get("id", f"task-{idx + 1}"))
                if isinstance(task, dict)
                else f"task-{idx + 1}"
            )
            payload = {
                "run_id": f"run-{idx + 1}",
                "task_id": task_id,
                "status": "simulated",
                "key_metrics": {
                    config.experiment.metric_key: round(0.3 + idx * 0.03, 4),
                    "secondary_metric": round(0.6 - idx * 0.04, 4),
                },
                "notes": "Simulated run result",
                "completed_at": _utcnow_iso(),
            }
            run_id = str(payload["run_id"])
            _write_run_payload(payload)
        _write_stage12_runtime_observer(
            stage_dir=stage_dir,
            run_dir=run_dir,
            config=config,
            schedule_text=schedule_text,
            exp_dir=Path(exp_dir_path) if exp_dir_path and Path(exp_dir_path).is_dir() else None,
            preflight_errors=[],
            preflight_warnings=[],
            run_payload=payload,
            status="simulated",
        )
    else:
        runner = ExperimentRunner(config.experiment, runs_dir / "workspace")
        history = runner.run_loop(code_text, run_id=f"exp-{run_dir.name}", llm=llm)
        runner.save_history(stage_dir / "experiment_history.json")
        any_success = False
        for item in history.results:
            payload = {
                "run_id": f"run-{item.iteration}",
                "task_id": item.run_id,
                "status": "completed" if item.error is None else "failed",
                "metrics": item.metrics,
                "primary_metric": item.primary_metric,
                "improved": item.improved,
                "kept": item.kept,
                "elapsed_sec": item.elapsed_sec,
                "error": item.error,
                "completed_at": _utcnow_iso(),
            }
            if item.error is None:
                any_success = True
            _write_run_payload(payload)
        if not any_success:
            return _stage12_failure("No successful experiment iterations completed.")
        _write_stage12_runtime_observer(
            stage_dir=stage_dir,
            run_dir=run_dir,
            config=config,
            schedule_text=schedule_text,
            exp_dir=Path(exp_dir_path) if exp_dir_path and Path(exp_dir_path).is_dir() else None,
            preflight_errors=[],
            preflight_warnings=[],
            run_payload=payload,
            status="completed",
        )
    return StageResult(
        stage=Stage.EXPERIMENT_RUN,
        status=StageStatus.DONE,
        artifacts=("runs/", "preflight_report.json", "runtime_observer.json"),
        evidence_refs=("stage-12/runs/", "stage-12/preflight_report.json", "stage-12/runtime_observer.json"),
    )


def _execute_iterative_refine(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    from researchclaw.experiment.factory import create_sandbox
    from researchclaw.experiment.validator import format_issues_for_llm, validate_code

    def _to_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            f = float(value)
            # BUG-EX-01: NaN/Inf block all future improvement detection
            if math.isnan(f) or math.isinf(f):
                return None
            return f
        except (TypeError, ValueError):
            return None

    # R10-Fix3: Skip iterative refinement in simulated mode (no real execution)
    if config.experiment.mode == "simulated":
        logger.info(
            "Stage 13: Skipping iterative refinement in simulated mode "
            "(no real code execution available)"
        )
        import shutil

        final_dir = stage_dir / "experiment_final"
        # Copy latest experiment code as final (directory or single file)
        copied = False
        for stage_num in (12, 10):
            src_dir = run_dir / f"stage-{stage_num:02d}" / "experiment"
            if src_dir.is_dir():
                if final_dir.exists():
                    shutil.rmtree(final_dir)
                shutil.copytree(src_dir, final_dir)
                copied = True
                break
            # Also check for single experiment.py
            src_file = run_dir / f"stage-{stage_num:02d}" / "experiment.py"
            if src_file.is_file():
                (stage_dir / "experiment_final.py").write_text(
                    src_file.read_text(encoding="utf-8"), encoding="utf-8"
                )
                copied = True
                break

        log: dict[str, Any] = {
            "generated": _utcnow_iso(),
            "mode": "simulated",
            "skipped": True,
            "skip_reason": "Iterative refinement not meaningful in simulated mode",
            "metric_key": config.experiment.metric_key,
        }
        (stage_dir / "refinement_log.json").write_text(
            json.dumps(log, indent=2), encoding="utf-8"
        )
        return StageResult(
            stage=Stage.ITERATIVE_REFINE,
            status=StageStatus.DONE,
            artifacts=("refinement_log.json",),
            evidence_refs=(),
        )

    metric_key = config.experiment.metric_key
    metric_direction = config.experiment.metric_direction

    # P9: Detect metric direction mismatch between config and experiment code.
    # The code-gen stage instructs experiments to print a line like:
    #   METRIC_DEF: primary_metric | direction=higher | desc=...
    # Log a warning if mismatch is detected, but trust the config value
    # (BUG-06 fix: no longer auto-override, since Stage 9 and 12 now
    # explicitly enforce config.metric_direction in prompts).
    _runs_dir_detect = _read_prior_artifact(run_dir, "runs/")
    if _runs_dir_detect and Path(_runs_dir_detect).is_dir():
        import re as _re_detect

        for _rf in sorted(Path(_runs_dir_detect).glob("*.json"))[:5]:
            try:
                _rp = _safe_json_loads(_rf.read_text(encoding="utf-8"), {})
                _stdout = _rp.get("stdout", "") if isinstance(_rp, dict) else ""
                _match = _re_detect.search(
                    r"METRIC_DEF:.*direction\s*=\s*(higher|lower)", _stdout
                )
                if _match:
                    _detected = _match.group(1)
                    _detected_dir = "maximize" if _detected == "higher" else "minimize"
                    if _detected_dir != metric_direction:
                        logger.warning(
                            "P9: Metric direction mismatch — config says '%s' but "
                            "experiment code declares 'direction=%s'. "
                            "Keeping config value '%s'. Code will be "
                            "corrected in next refinement cycle.",
                            metric_direction,
                            _detected,
                            metric_direction,
                        )
                    break
            except OSError:
                pass

    maximize = metric_direction == "maximize"

    def _is_better(candidate: float | None, current: float | None) -> bool:
        if candidate is None:
            return False
        if current is None:
            return True
        return candidate > current if maximize else candidate < current

    def _find_metric(metrics: dict[str, object], key: str) -> float | None:
        """R13-4: Find metric value with fuzzy key matching.

        Tries exact match first, then looks for aggregate keys that contain
        the metric name (e.g. 'primary_metric_mean' when key='primary_metric').
        """
        # Exact match
        val = _to_float(metrics.get(key))
        if val is not None:
            return val
        # Try aggregate/mean keys containing the metric name
        # Prefer keys ending with the metric name or containing '_mean'
        candidates: list[tuple[str, float]] = []
        for mk, mv in metrics.items():
            fv = _to_float(mv)
            if fv is None:
                continue
            if mk == key or mk.endswith(f"/{key}"):
                return fv  # Exact match via condition prefix
            if key in mk and ("mean" in mk or "avg" in mk):
                candidates.append((mk, fv))
            elif mk.endswith(f"_{key}") or mk.endswith(f"/{key}_mean"):
                candidates.append((mk, fv))
        if candidates:
            # Take the aggregate mean if available, otherwise first match
            for ck, cv in candidates:
                if "mean" in ck:
                    return cv
            return candidates[0][1]
        # Stage 13 multi-condition experiments may only persist condition
        # means, not a root-level primary_metric.  Use the best finite
        # condition mean as the iteration-level score so completed evidence is
        # not discarded as "no metrics".
        condition_means: list[tuple[str, float]] = []
        for mk, mv in metrics.items():
            if not isinstance(mk, str):
                continue
            if not (
                mk.endswith(f"/{key}_mean")
                or (key == "primary_metric" and mk.endswith("/primary_metric_mean"))
            ):
                continue
            fv = _to_float(mv)
            if fv is not None:
                condition_means.append((mk, fv))
        if condition_means:
            best_value: float | None = None
            for _, value in condition_means:
                if _is_better(value, best_value):
                    best_value = value
            return best_value
        # Last resort: if there's an "overall" or root-level aggregate
        for mk, mv in metrics.items():
            fv = _to_float(mv)
            if fv is not None and key in mk and "/" not in mk and "seed" not in mk:
                return fv
        return None

    requested_iterations = int(getattr(config.experiment, "max_iterations", 10) or 10)
    max_iterations = max(1, min(requested_iterations, 10))

    # BUG-57: Wall-clock time cap for the entire refinement stage.
    # Default: 3× the per-iteration time budget (e.g., 2400s → 7200s = 2h).
    import time as _time_bug57
    _refine_start_time = _time_bug57.monotonic()
    _per_iter_budget = int(getattr(config.experiment, "time_budget_sec", 2400) or 2400)
    _max_refine_wall_sec = int(
        getattr(config.experiment, "max_refine_duration_sec", 0) or 0
    ) or int(_per_iter_budget * 1.5)

    # --- Collect baseline metrics from prior runs ---
    runs_dir_path: Path | None = None
    runs_dir_text = _read_prior_artifact(run_dir, "runs/")
    if runs_dir_text:
        runs_dir_path = Path(runs_dir_text)

    run_summaries: list[str] = []
    recent_run_payloads: list[dict[str, Any]] = []
    baseline_metric: float | None = None
    if runs_dir_path is not None:
        for run_file in sorted(runs_dir_path.glob("*.json"))[:40]:
            payload = _safe_json_loads(run_file.read_text(encoding="utf-8"), {})
            if not isinstance(payload, dict):
                continue
            recent_run_payloads.append(dict(payload))
            # R5-5: Truncate stdout/stderr for context efficiency
            summary = dict(payload)
            if "stdout" in summary and isinstance(summary["stdout"], str):
                lines = summary["stdout"].splitlines()
                if len(lines) > 30:
                    summary["stdout"] = (
                        f"[...truncated {len(lines) - 30} lines...]\n"
                        + "\n".join(lines[-30:])
                    )
                if len(summary["stdout"]) > 2000:
                    summary["stdout"] = summary["stdout"][-2000:]
            if "stderr" in summary and isinstance(summary["stderr"], str):
                lines = summary["stderr"].splitlines()
                if len(lines) > 50:
                    summary["stderr"] = "\n".join(lines[-50:])
                if len(summary["stderr"]) > 2000:
                    summary["stderr"] = summary["stderr"][-2000:]
            run_summaries.append(json.dumps(summary, ensure_ascii=False))
            metrics = payload.get("metrics")
            if not isinstance(metrics, dict):
                metrics = (
                    payload.get("key_metrics")
                    if isinstance(payload.get("key_metrics"), dict)
                    else {}
                )
            metric_val = (
                _find_metric(metrics, metric_key)
                if isinstance(metrics, dict)
                else None
            )
            if metric_val is None:
                metric_val = _to_float(payload.get("primary_metric"))
            if _is_better(metric_val, baseline_metric):
                baseline_metric = metric_val

    _exp_plan_text = _read_prior_artifact(run_dir, "exp_plan.yaml") or ""
    _condition_coverage_hint = ""
    if _exp_plan_text and run_summaries:
        _all_stdout = " ".join(run_summaries)
        _has_condition_labels = "condition=" in _all_stdout
        if not _has_condition_labels and _exp_plan_text.strip():
            _condition_coverage_hint = (
                "\nCONDITION COVERAGE GAP DETECTED:\n"
                "The experiment plan specifies multiple conditions/treatments, "
                "but the output contains NO condition labels (no 'condition=...' in stdout).\n"
                "You MUST:\n"
                "1. Run ALL conditions/treatments from the experiment plan independently\n"
                "2. Label each metric output: `condition=<name> {metric_key}: <value>`\n"
                "3. Print a SUMMARY line comparing all conditions after completion\n"
                "This is the MOST IMPORTANT improvement — a single unlabeled metric stream "
                "cannot support any comparative conclusions.\n\n"
            )
            logger.info(
                "Stage 13: condition coverage gap detected, injecting multi-condition hint"
            )

    diagnostic_summary = _build_stage13_diagnostic_bundle(
        stage_dir=stage_dir,
        run_dir=run_dir,
        metric_key=metric_key,
        metric_direction=metric_direction,
        baseline_metric=baseline_metric,
        run_payloads=recent_run_payloads,
        exp_plan_text=_exp_plan_text,
        condition_coverage_hint=_condition_coverage_hint,
    )

    # --- Read experiment project (multi-file or single-file) ---
    # BUG-58: When PIVOT rolls back to Stage 13, prefer the best refined code
    # from a previous cycle (stage-13_vX/experiment_final/) over the original
    # unrefined code (stage-12/experiment/ or stage-10/experiment/).
    # Enhanced: try ALL versioned directories (latest first) with fallback chain.
    interrupted_resume_project_dir = _latest_stage13_partial_project_dir(stage_dir)
    versioned_resume_project_dir = (
        None
        if interrupted_resume_project_dir is not None
        else _latest_stage13_experiment_version_dir(stage_dir)
    )
    resume_replay_project_dir = interrupted_resume_project_dir or versioned_resume_project_dir
    incremental_project_dir = resume_replay_project_dir or stage_dir / "experiment"
    incremental_refine_available = incremental_project_dir.is_dir()

    exp_dir_text: str | None = None
    _prev_refine_dirs = sorted(
        run_dir.glob("stage-13_v*/experiment_final"),
        key=lambda p: p.parent.name,
        reverse=True,  # latest version first
    )
    # BUG-58 fix: Find the best version across ALL cycles (not just latest)
    _best_prev_metric: float | None = None
    _best_prev_dir: Path | None = None
    for _prd in _prev_refine_dirs:
        if not _prd.is_dir():
            continue
        _prd_log = _prd.parent / "refinement_log.json"
        if _prd_log.is_file():
            _prd_data = _safe_json_loads(
                _prd_log.read_text(encoding="utf-8"), {}
            )
            _prd_metric = _prd_data.get("best_metric") if isinstance(_prd_data, dict) else None
            if isinstance(_prd_metric, (int, float)) and _is_better(_prd_metric, _best_prev_metric):
                _best_prev_metric = _prd_metric
                _best_prev_dir = _prd
        elif _best_prev_dir is None:
            # No log but directory exists — use as fallback
            _best_prev_dir = _prd
    if _best_prev_dir is not None:
        exp_dir_text = str(_best_prev_dir)
        logger.info(
            "BUG-58: Recovered best refined code from PIVOT cycle: %s (metric=%s)",
            _best_prev_dir.parent.name,
            f"{_best_prev_metric:.4f}" if _best_prev_metric is not None else "N/A",
        )
    if interrupted_resume_project_dir is not None:
        exp_dir_text = str(interrupted_resume_project_dir)
        logger.info(
            "Stage 13: resuming interrupted partial experiment directly from %s",
            interrupted_resume_project_dir,
        )
    elif versioned_resume_project_dir is not None:
        exp_dir_text = str(versioned_resume_project_dir)
        logger.info(
            "Stage 13: resuming existing Stage 13 experiment directly from %s",
            versioned_resume_project_dir,
        )
    elif incremental_refine_available:
        exp_dir_text = str(incremental_project_dir)
        logger.info(
            "Stage 13: using run-local incremental refine project: %s",
            incremental_project_dir,
        )
    if not exp_dir_text:
        exp_dir_text = _read_prior_artifact(run_dir, "experiment/")
    best_files: dict[str, str] = {}
    if exp_dir_text and Path(exp_dir_text).is_dir():
        # BUG-EX-02: Load ALL text files (not just .py) — requirements.txt,
        # setup.py, config files are needed for Docker sandbox phases.
        for src_file in sorted(Path(exp_dir_text).iterdir()):
            if src_file.name in {
                "docker_container.json",
                "partial_results.json",
                "partial_seed_metrics_latest.json",
                "results.json",
                "sandbox_result.json",
                "sandbox_stdout.log",
                "sandbox_stderr.log",
            }:
                continue
            if src_file.name.startswith("analysis_results"):
                continue
            if src_file.is_file() and src_file.suffix in (
                ".py", ".txt", ".yaml", ".yml", ".json", ".cfg", ".ini", ".sh",
            ):
                try:
                    best_files[src_file.name] = src_file.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    pass  # skip binary files
    if not best_files:
        # Backward compat: single experiment.py
        original_code = _read_prior_artifact(run_dir, "experiment.py") or ""
        if original_code:
            best_files = {"main.py": original_code}

    # --- Detect if prior experiment timed out ---
    prior_timed_out = False
    prior_time_budget = config.experiment.time_budget_sec
    if runs_dir_path is not None:
        for run_file in sorted(runs_dir_path.glob("*.json"))[:5]:
            try:
                payload = _safe_json_loads(run_file.read_text(encoding="utf-8"), {})
                if isinstance(payload, dict) and payload.get("timed_out"):
                    prior_timed_out = True
                    break
            except OSError:
                pass

    best_metric = baseline_metric
    best_version = "experiment/"
    # BUG-58: Recover best_metric from best previous PIVOT cycle
    if _best_prev_metric is not None and _is_better(_best_prev_metric, best_metric):
        best_metric = _best_prev_metric
        logger.info(
            "BUG-58: Recovered best_metric=%.4f from previous PIVOT",
            best_metric,
        )
    no_improve_streak = 0
    consecutive_no_metrics = 0

    log: dict[str, Any] = {
        "generated": _utcnow_iso(),
        "mode": config.experiment.mode,
        "metric_key": metric_key,
        "metric_direction": metric_direction,
        "max_iterations_requested": requested_iterations,
        "max_iterations_executed": max_iterations,
        "baseline_metric": baseline_metric,
        "project_files": list(best_files.keys()),
        "diagnostic_bundle": "refine_diagnostic_bundle.json",
        "iterations": [],
        "converged": False,
        "stop_reason": "max_iterations_reached",
        "incremental_refine_available": incremental_refine_available,
    }
    if incremental_refine_available:
        log["incremental_project_dir"] = str(incremental_project_dir)

    method_diagnosis_summary, method_diagnosis_payload = _build_stage13_method_diagnosis(
        stage_dir=stage_dir,
        run_dir=run_dir,
        metric_key=metric_key,
        metric_direction=metric_direction,
        condition_coverage_hint=_condition_coverage_hint,
        config_text=best_files.get("config.py", ""),
    )
    log["method_diagnosis"] = "method_diagnosis.json"

    config_text = best_files.get("config.py", "")
    main_text = best_files.get("main.py", "")
    registry = _parse_stage13_condition_registry(config_text)
    stage15_refine_redesign = _ensure_stage13_refine_handoff_manual_redesign(
        run_dir=run_dir,
        stage_dir=stage_dir,
    )
    if stage15_refine_redesign is not None:
        log["stage15_refine_handoff"] = "manual_redesign.json"
    manual_active_conditions = _stage13_manual_redesign_active_conditions(stage_dir)
    declared_active_conditions = _parse_stage13_active_condition_names(
        config_text,
        main_text,
    )
    ordered_conditions = (
        manual_active_conditions
        or declared_active_conditions
        or [entry["condition_name"] for entry in registry]
    )
    expected_seeds = _parse_stage13_seed_plan(config_text)
    completed_seed_cache = _load_stage13_condition_seed_cache(stage_dir)
    cached_results_complete = bool(ordered_conditions and expected_seeds) and all(
        set(expected_seeds).issubset(set(completed_seed_cache.get(name, {}).keys()))
        for name in ordered_conditions
    )

    def _stage13_complete_seed_cache_metric() -> tuple[bool, str | None, float | None, dict[str, Any]]:
        current_cache = _load_stage13_condition_seed_cache(stage_dir)
        complete = bool(ordered_conditions and expected_seeds) and all(
            set(expected_seeds).issubset(set(current_cache.get(name, {}).keys()))
            for name in ordered_conditions
        )
        if not complete:
            return False, None, None, current_cache
        condition_means = {
            name: sum(float(value) for value in current_cache[name].values())
            / len(current_cache[name])
            for name in ordered_conditions
        }
        selected = _select_best_condition(
            ordered_conditions,
            condition_means,
            metric_direction,
        )
        best_condition = selected[0] if selected is not None else None
        best_condition_metric = selected[1] if selected is not None else None
        return True, best_condition, best_condition_metric, current_cache

    if cached_results_complete:
        condition_means = {
            name: sum(float(value) for value in completed_seed_cache[name].values())
            / len(completed_seed_cache[name])
            for name in ordered_conditions
        }
        best_cached = _select_best_condition(
            ordered_conditions,
            condition_means,
            metric_direction,
        )
        best_cached_condition = best_cached[0] if best_cached is not None else None
        best_cached_metric = best_cached[1] if best_cached is not None else None
        flattened_metrics = {
            f"{condition_name}_seed_{seed_idx}": metric
            for condition_name, seed_map in completed_seed_cache.items()
            for seed_idx, metric in seed_map.items()
        }
        log.update(
            {
                "iterations": [
                    {
                        "iteration": 0,
                        "version_dir": None,
                        "files": list(best_files.keys()),
                        "validation_ok": True,
                        "validation_summary": "cached_complete",
                        "repaired": False,
                        "metric": best_cached_metric,
                        "improved": False,
                        "cached_completion": True,
                        "incremental_plan": {
                            "active": False,
                            "reason": "all_expected_condition_seeds_complete",
                            "coverage_gap": False,
                            "active_conditions": [],
                            "frozen_conditions": ordered_conditions,
                            "reuse_conditions": sorted(completed_seed_cache.keys()),
                        },
                        "sandbox": {
                            "returncode": 0,
                            "metrics": flattened_metrics,
                            "elapsed_sec": 0.0,
                            "timed_out": False,
                            "stderr": "",
                            "stdout": "",
                        },
                    }
                ],
                "converged": True,
                "stop_reason": "cached_results_complete",
                "best_metric": best_cached_metric,
                "best_version": "experiment_final/",
                "final_version": "experiment_final/",
                "method_redesign_required": bool(
                    method_diagnosis_payload.get("method_redesign_required")
                ),
                "cached_completion": True,
                "cached_best_condition": best_cached_condition,
            }
        )
        if log["method_redesign_required"]:
            log["scientific_outcome"] = "targeted_method_redesign_required"
            log["redesign_reasons"] = method_diagnosis_payload.get(
                "redesign_reasons",
                [],
            )
        final_dir = stage_dir / "experiment_final"
        final_dir.mkdir(parents=True, exist_ok=True)
        for fname, code in best_files.items():
            (final_dir / fname).write_text(code, encoding="utf-8")
        if "main.py" in best_files:
            (stage_dir / "experiment_final.py").write_text(
                best_files["main.py"], encoding="utf-8"
            )
        completion_gate = _build_stage13_completion_gate(log)
        log["completion_gate"] = completion_gate
        (stage_dir / "refinement_log.json").write_text(
            json.dumps(log, indent=2), encoding="utf-8"
        )
        artifacts = (
            "refinement_log.json",
            "refine_diagnostic_bundle.json",
            "refine_diagnostic_bundle.md",
            "method_diagnosis.json",
            "method_diagnosis.md",
            "experiment_final/",
        )
        if completion_gate["ok"]:
            logger.info(
                "Stage 13: accepting complete cached results for %d condition(s) x %d seed(s)",
                len(ordered_conditions),
                len(expected_seeds),
            )
            return StageResult(
                stage=Stage.ITERATIVE_REFINE,
                status=StageStatus.DONE,
                artifacts=artifacts,
                evidence_refs=tuple(f"stage-13/{artifact}" for artifact in artifacts),
            )

    # --- Helper: write files to a directory ---
    def _write_project(target_dir: Path, project_files: dict[str, str]) -> None:
        target_dir.mkdir(parents=True, exist_ok=True)
        for fname, code in project_files.items():
            (target_dir / fname).write_text(code, encoding="utf-8")

    # --- Helper: format all files for LLM context ---
    def _files_to_context(project_files: dict[str, str]) -> str:
        parts = []
        for fname, code in sorted(project_files.items()):
            if fname.startswith("analysis_results"):
                continue
            parts.append(f"```filename:{fname}\n{code}\n```")
        return "\n\n".join(parts)

    if llm is None:
        logger.info("Stage 13: LLM unavailable, saving original experiment as final")
        final_dir = stage_dir / "experiment_final"
        _write_project(final_dir, best_files)
        # Backward compat
        if "main.py" in best_files:
            (stage_dir / "experiment_final.py").write_text(
                best_files["main.py"], encoding="utf-8"
            )
        log.update(
            {
                "converged": True,
                "stop_reason": "llm_unavailable",
                "best_metric": best_metric,
                "best_version": "experiment_final/",
                "iterations": [
                    {
                        "iteration": 0,
                        "version_dir": "experiment_final/",
                        "source": "fallback_original",
                        "metric": best_metric,
                    }
                ],
            }
        )
        (stage_dir / "refinement_log.json").write_text(
            json.dumps(log, indent=2), encoding="utf-8"
        )
        artifacts = (
            "refinement_log.json",
            "refine_diagnostic_bundle.json",
            "refine_diagnostic_bundle.md",
            "experiment_final/",
        )
        return StageResult(
            stage=Stage.ITERATIVE_REFINE,
            status=StageStatus.DONE,
            artifacts=artifacts,
            evidence_refs=tuple(f"stage-13/{a}" for a in artifacts),
        )

    _pm = prompts or PromptManager()
    timeout_refine_attempts = 0

    # P1: Track metrics history for saturation detection
    _metrics_history: list[float | None] = [baseline_metric]

    for iteration in range(1, max_iterations + 1):
        # BUG-57: Check wall-clock time before starting a new iteration
        _elapsed = _time_bug57.monotonic() - _refine_start_time
        if _elapsed > _max_refine_wall_sec:
            logger.warning(
                "Stage 13: Wall-clock time cap reached (%.0fs > %ds). "
                "Stopping refinement after %d iterations.",
                _elapsed, _max_refine_wall_sec, iteration - 1,
            )
            log["stop_reason"] = "wall_clock_time_cap"
            break
        logger.info("Stage 13: refinement iteration %d/%d (%.0fs elapsed, cap %ds)",
                    iteration, max_iterations, _elapsed, _max_refine_wall_sec)

        # P1: Detect metric saturation and inject difficulty upgrade hint
        _saturation_hint = ""
        _valid_metrics = [m for m in _metrics_history if m is not None]
        if len(_valid_metrics) >= 2:
            _last_two = _valid_metrics[-2:]
            _saturated = False
            # Use relative change rate instead of hard-coded thresholds
            _change_rate = abs(_last_two[-1] - _last_two[-2]) / max(abs(_last_two[-2]), 1e-8)
            if metric_direction == "minimize":
                _saturated = all(m <= 0.001 for m in _last_two) or (
                    _change_rate < 0.001 and _last_two[-1] < 0.01
                )
            else:
                _saturated = all(m >= 0.999 for m in _last_two) or (
                    _change_rate < 0.001 and _last_two[-1] > 0.99
                )
            if _saturated:
                _saturation_hint = (
                    "\n\nWARNING — BENCHMARK SATURATION DETECTED:\n"
                    "All methods achieve near-perfect scores, making the task too easy "
                    "to discriminate between methods.\n"
                    "YOU MUST increase benchmark difficulty in this iteration:\n"
                    "1. Increase the number of actions/decisions from 8 to at least 20\n"
                    "2. Increase the horizon from 12-18 to at least 50-100 steps\n"
                    "3. Increase noise level to at least 0.3-0.5\n"
                    "4. Add partial observability (agent cannot see full state)\n"
                    "5. Add delayed rewards (reward only at episode end)\n"
                    "6. Ensure random search achieves < 50% success rate\n"
                    "Without this change, the experiment produces meaningless results.\n"
                )
                logger.warning("Stage 13: metric saturation detected, injecting difficulty upgrade hint")

        preflight_incremental_plan = _build_stage13_incremental_plan(
            stage_dir=stage_dir,
            best_files=best_files,
            candidate_files=best_files,
            condition_coverage_hint=_condition_coverage_hint,
        )
        if (
            (incremental_refine_available or resume_replay_project_dir is not None)
            and iteration == 1
            and str(preflight_incremental_plan.get("reason") or "") == "no_executable_change"
        ):
            preflight_incremental_plan = dict(preflight_incremental_plan)
            preflight_incremental_plan.update(
                {
                    "active": True,
                    "reason": "run_local_replay",
                    "coverage_gap": False,
                }
            )
        use_incremental_replay = _should_use_stage13_incremental_replay(
            incremental_refine_available=incremental_refine_available,
            interrupted_resume_project_dir=resume_replay_project_dir,
            iteration=iteration,
            preflight_incremental_plan=preflight_incremental_plan,
            method_diagnosis_payload=method_diagnosis_payload,
        )
        use_deterministic_baseline_replay = (
            iteration == 1
            and not use_incremental_replay
            and _should_use_stage13_deterministic_baseline_replay(
                candidate_files=best_files,
                method_diagnosis_payload=method_diagnosis_payload,
                interrupted_resume_project_dir=resume_replay_project_dir,
                manual_redesign_active=(stage_dir / "manual_redesign.json").is_file(),
            )
        )
        if use_incremental_replay:
            candidate_files = dict(best_files)
            llm_change_summary: dict[str, Any] = {
                "redesign_goal": (
                    "resume_interrupted_partial_experiment"
                    if resume_replay_project_dir is not None
                    else "coverage_gap_replay"
                ),
                "substantive_method_change": False,
            }
            logger.info(
                "Stage 13 iteration %d: replaying current/partial project before "
                "requesting any new LLM rewrite",
                iteration,
            )
        elif use_deterministic_baseline_replay:
            candidate_files = dict(best_files)
            llm_change_summary = {
                "redesign_goal": "deterministic_full_baseline_grid_replay",
                "substantive_method_change": False,
            }
            logger.info(
                "Stage 13 iteration %d: rebuilding required baseline grid "
                "deterministically before Docker execution",
                iteration,
            )
        else:
            files_context = _files_to_context(best_files)
            # BUG-10 fix: anchor refinement to original experiment plan
            _exp_plan_anchor = ""
            if _exp_plan_text.strip():
                _exp_plan_anchor = (
                    "Original experiment plan (exp_plan.yaml):\n"
                    "```yaml\n" + _exp_plan_text[:4000] + "\n```\n"
                    "You MUST preserve ALL condition names from this plan.\n\n"
                )
            ip = _pm.sub_prompt(
                "iterative_improve",
                metric_key=metric_key,
                metric_direction=metric_direction,
                files_context=files_context,
                run_summaries=diagnostic_summary,
                condition_coverage_hint=_condition_coverage_hint,
                method_diagnosis=method_diagnosis_summary,
                topic=config.research.topic,
                exp_plan_anchor=_exp_plan_anchor,
            )
            governance_overlay = (
                build_phase_charter("iterative_refine")
                + "\n"
                + build_stage_skill_overlay(
                    config,
                    stage_name="iterative_refine",
                    context=diagnostic_summary[:3000],
                )
            )

            # --- Timeout-aware prompt injection ---
            user_prompt = governance_overlay + "\n" + ip.user + _saturation_hint
            if prior_timed_out and baseline_metric is None:
                timeout_refine_attempts += 1
                timeout_hint = (
                    f"\n\nCRITICAL: The experiment TIMED OUT after {prior_time_budget}s "
                    f"with NO results. You MUST drastically reduce the experiment scale:\n"
                    f"- Reduce total runs to ≤50\n"
                    f"- Reduce steps per run to ≤2000\n"
                    f"- Remove conditions that are not essential\n"
                    f"- Persist intermediate metrics after every seed/condition so partial data is captured\n"
                    f"- Do not add a soft 80% early-stop guard that skips later conditions\n"
                    f"- Time budget is {prior_time_budget}s — design to fit the full configured budget\n"
                )
                user_prompt = user_prompt + timeout_hint
                logger.warning(
                    "Stage 13: injecting timeout-aware prompt (attempt %d)",
                    timeout_refine_attempts,
                )

            response = _chat_with_prompt(
                llm,
                ip.system,
                user_prompt,
                max_tokens=ip.max_tokens or 8192,
            )
            candidate_files = dict(best_files)
            if _stage13_llm_response_is_context_overflow(response.content):
                log["llm_context_overflow_count"] = int(log.get("llm_context_overflow_count", 0)) + 1
                llm_change_summary = {
                    "redesign_goal": "llm_context_overflow",
                    "substantive_method_change": False,
                    "context_overflow": True,
                }
                logger.warning(
                    "Stage 13 iteration %d: LLM returned context-overflow text; "
                    "preserving current project instead of writing it as code",
                    iteration,
                )
            else:
                extracted_files = _extract_multi_file_blocks(response.content)
                # If LLM returns only single block, treat as main.py update
                if not extracted_files:
                    single_code = _extract_code_block(response.content)
                    if single_code.strip():
                        extracted_files = {"main.py": single_code}
                llm_change_summary = _extract_method_change_summary(response.content)
                # R8-2: Merge with best_files to preserve supporting modules
                # (e.g., graphs.py, game.py) that the LLM didn't rewrite
                if extracted_files:
                    candidate_files.update(extracted_files)
                # If LLM returned nothing at all, candidate_files == best_files (unchanged)

        # BUG-R6-02: Preserve entry point when LLM strips main() function.
        # The LLM often returns only class/function improvements without the
        # main() entry point, causing the script to exit with no output.
        _new_main = candidate_files.get("main.py", "")
        _old_main = best_files.get("main.py", "")
        if (
            _new_main
            and _old_main
            and "if __name__" not in _new_main
            and "if __name__" in _old_main
        ):
            # Extract the entry-point block from original main.py
            _ep_idx = _old_main.rfind("\ndef main(")
            if _ep_idx == -1:
                _ep_idx = _old_main.rfind("\nif __name__")
            if _ep_idx != -1:
                _entry_block = _old_main[_ep_idx:]
                candidate_files["main.py"] = _new_main.rstrip() + "\n\n" + _entry_block
                logger.info(
                    "Stage 13 iter %d: restored entry point stripped by LLM "
                    "(%d chars appended from original main.py)",
                    iteration,
                    len(_entry_block),
                )

        candidate_files = _enforce_stage13_required_baseline_grid(
            candidate_files,
            method_diagnosis_payload,
        )
        if "main.py" in candidate_files:
            candidate_files["main.py"] = _ensure_stage13_main_parallel_wrapper(
                candidate_files["main.py"]
            )

        incremental_plan = (
            preflight_incremental_plan
            if use_incremental_replay
            else _build_stage13_incremental_plan(
                stage_dir=stage_dir,
                best_files=best_files,
                candidate_files=candidate_files,
                condition_coverage_hint=_condition_coverage_hint,
            )
        )

        if not incremental_plan.get("active", False):
            iter_record = {
                "iteration": iteration,
                "version_dir": None,
                "files": list(candidate_files.keys()),
                "validation_ok": True,
                "validation_summary": "skipped",
                "repaired": False,
                "metric": None,
                "improved": False,
                "incremental_plan": incremental_plan,
                "skipped_reason": str(incremental_plan.get("reason") or "inactive"),
                "method_change_summary": llm_change_summary,
            }
            log["iterations"].append(iter_record)
            no_improve_streak += 1
            if no_improve_streak >= 2:
                log["converged"] = True
                log["stop_reason"] = "no_improvement_for_2_iterations"
            break

        method_redesign_gate_active = (
            bool(method_diagnosis_payload.get("method_redesign_required"))
            and not bool(incremental_plan.get("coverage_gap"))
            and not use_incremental_replay
            and not use_deterministic_baseline_replay
        )
        substantive_method_change = _stage13_has_substantive_method_change(
            best_files=best_files,
            candidate_files=candidate_files,
            llm_change_summary=llm_change_summary,
        )
        if method_redesign_gate_active and not substantive_method_change:
            version_dir = stage_dir / f"experiment_v{iteration}"
            _write_project(version_dir, candidate_files)
            iter_record = {
                "iteration": iteration,
                "version_dir": f"experiment_v{iteration}/",
                "files": list(candidate_files.keys()),
                "validation_ok": True,
                "validation_summary": "method_gate_skip",
                "repaired": False,
                "metric": None,
                "improved": False,
                "incremental_plan": incremental_plan,
                "method_change_summary": llm_change_summary,
                "skipped_reason": "method_redesign_required_without_substantive_change",
            }
            log["iterations"].append(iter_record)
            no_improve_streak += 1
            logger.info(
                "Stage 13 iteration %d: skipped real execution because method redesign "
                "was required but no substantive method change was detected",
                iteration,
            )
            if no_improve_streak >= 2:
                log["converged"] = True
                log["stop_reason"] = "no_improvement_for_2_iterations"
                break
            continue

        active_conditions = [
            name
            for name in incremental_plan.get("active_conditions", [])
            if isinstance(name, str) and name.strip()
        ]
        supports_resume_cache = (
            "_load_resume_seed_registry" in candidate_files.get("main.py", "")
            and "resume_seed_registry" in candidate_files.get("main.py", "")
        )
        supports_resume_cache = supports_resume_cache or (stage_dir / "manual_redesign.json").is_file()
        if active_conditions and "config.py" in candidate_files and not supports_resume_cache:
            candidate_files["config.py"] = _rewrite_stage13_active_conditions(
                candidate_files["config.py"],
                active_conditions,
            )
            if "main.py" in candidate_files:
                candidate_files["main.py"] = _rewrite_stage13_main_required_conditions(
                    candidate_files["main.py"],
                    active_conditions,
                )

        resume_registry = incremental_plan.get("resume_registry", {})
        existing_resume_registry = candidate_files.get("resume_seed_registry.json", "")
        if isinstance(resume_registry, dict) and not existing_resume_registry.strip():
            candidate_files["resume_seed_registry.json"] = json.dumps(
                _stage13_resume_registry_payload(
                    resume_registry,
                    project_files=candidate_files,
                    stage_dir=stage_dir,
                    iteration=iteration,
                ),
                indent=2,
                ensure_ascii=False,
            )
        elif isinstance(resume_registry, dict) and existing_resume_registry.strip():
            existing_payload = _safe_json_loads(existing_resume_registry, {})
            if isinstance(existing_payload, dict):
                existing_conditions = existing_payload.setdefault("conditions", {})
                if isinstance(existing_conditions, dict):
                    for condition_name, seed_map in resume_registry.items():
                        if not isinstance(seed_map, dict):
                            continue
                        target = existing_conditions.setdefault(str(condition_name), {})
                        if not isinstance(target, dict):
                            target = {}
                            existing_conditions[str(condition_name)] = target
                        for seed_idx, metric in seed_map.items():
                            target[str(seed_idx)] = metric
                    existing_payload["updated_from_partial_results"] = True
                    existing_payload["cache_policy"] = (
                        "freeze completed condition/seed results from results.json "
                        "and partial_results.json; continue from unfinished seeds"
                    )
                    existing_resume_registry = json.dumps(
                        existing_payload,
                        indent=2,
                        ensure_ascii=False,
                    )
            aligned_registry = _stage13_align_resume_registry_signature(
                existing_resume_registry,
                project_files=candidate_files,
                stage_dir=stage_dir,
                iteration=iteration,
            )
            if aligned_registry != existing_resume_registry:
                candidate_files["resume_seed_registry.json"] = aligned_registry
                logger.info(
                    "Stage 13 iteration %d: aligned run-local resume_seed_registry.json "
                    "to candidate config signature",
                    iteration,
                )
            logger.info(
                "Stage 13 iteration %d: preserving run-local resume_seed_registry.json",
                iteration,
            )

        # Validate main.py
        main_code = candidate_files.get("main.py", "")
        validation = _validate_stage13_candidate_main(
            main_code,
            trusted_deterministic_replay=(
                use_deterministic_baseline_replay or use_incremental_replay
            ),
        )
        issue_text = ""
        repaired = False

        if not validation.ok:
            issue_text = format_issues_for_llm(validation)
            logger.info(
                "Stage 13 iteration %d validation failed: %s",
                iteration,
                validation.summary(),
            )
            irp = _pm.sub_prompt(
                "iterative_repair",
                issue_text=issue_text,
                all_files_ctx=_files_to_context(candidate_files),
            )
            repair_response = _chat_with_prompt(llm, irp.system, irp.user)
            if _stage13_llm_response_is_context_overflow(repair_response.content):
                log["llm_context_overflow_count"] = int(log.get("llm_context_overflow_count", 0)) + 1
                logger.warning(
                    "Stage 13 iteration %d: repair LLM returned context-overflow text; "
                    "leaving candidate code unchanged",
                    iteration,
                )
            else:
                candidate_files["main.py"] = _extract_code_block(repair_response.content)
                candidate_files = _enforce_stage13_required_baseline_grid(
                    candidate_files,
                    method_diagnosis_payload,
                )
                candidate_files["main.py"] = _ensure_stage13_main_parallel_wrapper(
                    candidate_files["main.py"]
                )
                validation = validate_code(candidate_files["main.py"])
                repaired = True

        # Save version directory
        version_dir = stage_dir / f"experiment_v{iteration}"
        _write_project(version_dir, candidate_files)

        iter_record: dict[str, Any] = {
            "iteration": iteration,
            "version_dir": f"experiment_v{iteration}/",
            "files": list(candidate_files.keys()),
            "validation_ok": validation.ok,
            "validation_summary": validation.summary(),
            "repaired": repaired,
            "metric": None,
            "improved": False,
            "incremental_plan": incremental_plan,
            "method_change_summary": llm_change_summary,
        }
        if use_incremental_replay:
            iter_record["incremental_replay"] = True
        if issue_text:
            iter_record["validation_issues"] = issue_text

        metric_val = None  # R6-3: initialize before conditional block
        accept_runtime_fix_completion = False
        if validation.ok and config.experiment.mode in ("sandbox", "docker"):
            # P7: Ensure deps for refined code (subprocess sandbox only)
            if config.experiment.mode == "sandbox":
                _refine_code = "\n".join(candidate_files.values())
                _ensure_sandbox_deps(_refine_code, config.experiment.sandbox.python_path)

            sandbox_workdir = stage_dir / f"refine_sandbox_v{iteration}"
            if use_incremental_replay and (
                resume_replay_project_dir is not None
                or (stage_dir / "manual_redesign.json").is_file()
            ):
                # The interrupted project directory is the input snapshot. Use a
                # fresh execution directory so DockerSandbox does not treat the
                # source partial checkpoint or manual-redesign snapshot as a
                # completed staging result.
                sandbox_workdir = stage_dir / (
                    f"refine_sandbox_v{iteration}_resume_{int(_time.time())}"
                )
            sandbox = create_sandbox(
                config.experiment,
                sandbox_workdir,
                notify_callback=_sandbox_wait_notifier(
                    run_dir=run_dir,
                    adapters=adapters,
                    config=config,
                    run_id=run_dir.name,
                    stage=Stage.ITERATIVE_REFINE,
                ),
            )
            rerun = sandbox.run_project(
                version_dir,
                timeout_sec=config.experiment.time_budget_sec,
            )
            metric_val = _find_metric(rerun.metrics, metric_key)
            # R19-1: Store stdout (capped) so PAIRED lines survive for Stage 14
            _stdout_cap = rerun.stdout[:50000] if rerun.stdout else ""
            iter_record["sandbox"] = {
                "returncode": rerun.returncode,
                "metrics": rerun.metrics,
                "elapsed_sec": rerun.elapsed_sec,
                "timed_out": rerun.timed_out,
                "stderr": rerun.stderr[:2000] if rerun.stderr else "",
                "stdout": _stdout_cap,
            }
            iter_record["metric"] = metric_val

            # BUG-110: Parse ABLATION_CHECK lines from stdout
            if rerun.stdout:
                import re as _re_ablation
                _ablation_checks = _re_ablation.findall(
                    r"ABLATION_CHECK:\s*(\S+)\s+vs\s+(\S+)\s+outputs_differ=(True|False)",
                    rerun.stdout,
                )
                if _ablation_checks:
                    _identical_pairs = [
                        (c1, c2) for c1, c2, diff in _ablation_checks if diff == "False"
                    ]
                    iter_record["ablation_checks"] = [
                        {"cond1": c1, "cond2": c2, "differ": diff == "True"}
                        for c1, c2, diff in _ablation_checks
                    ]
                    if _identical_pairs:
                        _pairs_str = ", ".join(f"{c1} vs {c2}" for c1, c2 in _identical_pairs)
                        logger.warning(
                            "BUG-110: Identical ablation outputs detected: %s. "
                            "Ablation conditions may not be wired correctly.",
                            _pairs_str,
                        )
                        iter_record["ablation_identical"] = True

            # --- Track timeout in refine sandbox ---
            if rerun.timed_out:
                prior_timed_out = True
                timeout_refine_attempts += 1
                logger.warning(
                    "Stage 13 iteration %d: sandbox timed out after %.1fs",
                    iteration,
                    rerun.elapsed_sec,
                )
                # If still no metrics after timeout, use partial stdout metrics
                if not rerun.metrics and rerun.stdout:
                    from researchclaw.experiment.sandbox import parse_metrics as _parse_sb_metrics
                    partial = _parse_sb_metrics(rerun.stdout)
                    if partial:
                        iter_record["sandbox"]["metrics"] = partial
                        metric_val = _find_metric(partial, metric_key)
                        iter_record["metric"] = metric_val
                        logger.info(
                            "Stage 13 iteration %d: recovered %d partial metrics from timeout stdout",
                            iteration,
                            len(partial),
                        )

            # --- Detect runtime issues (NaN/Inf, stderr warnings) ---
            runtime_issues = _detect_runtime_issues(rerun)
            if runtime_issues:
                iter_record["runtime_issues"] = runtime_issues
                logger.info(
                    "Stage 13 iteration %d: runtime issues detected: %s",
                    iteration,
                    runtime_issues[:200],
                )
                # Attempt LLM repair with runtime context
                rrp = _pm.sub_prompt(
                    "iterative_repair",
                    issue_text=runtime_issues,
                    all_files_ctx=_files_to_context(candidate_files),
                )
                repair_resp = _chat_with_prompt(llm, rrp.system, rrp.user)
                repaired_files: dict[str, str] = {}
                if _stage13_llm_response_is_context_overflow(repair_resp.content):
                    log["llm_context_overflow_count"] = int(log.get("llm_context_overflow_count", 0)) + 1
                    logger.warning(
                        "Stage 13 iteration %d: runtime repair LLM returned "
                        "context-overflow text; preserving candidate files",
                        iteration,
                    )
                else:
                    repaired_files = _extract_multi_file_blocks(repair_resp.content)
                    if not repaired_files:
                        single = _extract_code_block(repair_resp.content)
                        if single.strip():
                            repaired_files = dict(candidate_files)
                            repaired_files["main.py"] = single
                if repaired_files:
                    # BUG-106 fix: merge instead of replace to preserve
                    # supporting modules (trainers.py, utils.py, etc.)
                    merged = dict(candidate_files)
                    merged.update(repaired_files)
                    merged = _enforce_stage13_required_baseline_grid(
                        merged,
                        method_diagnosis_payload,
                    )
                    if "main.py" in merged:
                        merged["main.py"] = _ensure_stage13_main_parallel_wrapper(
                            merged["main.py"]
                        )
                    candidate_files = merged
                    _write_project(version_dir, candidate_files)
                    # Re-run after runtime fix
                    sandbox2 = create_sandbox(
                        config.experiment,
                        stage_dir / f"refine_sandbox_v{iteration}_fix",
                        notify_callback=_sandbox_wait_notifier(
                            run_dir=run_dir,
                            adapters=adapters,
                            config=config,
                            run_id=run_dir.name,
                            stage=Stage.ITERATIVE_REFINE,
                        ),
                    )
                    rerun2 = sandbox2.run_project(
                        version_dir,
                        timeout_sec=config.experiment.time_budget_sec,
                    )
                    metric_val = _find_metric(rerun2.metrics, metric_key)
                    iter_record["sandbox_after_fix"] = {
                        "returncode": rerun2.returncode,
                        "metrics": rerun2.metrics,
                        "elapsed_sec": rerun2.elapsed_sec,
                        "timed_out": rerun2.timed_out,
                    }
                    iter_record["runtime_repaired"] = True
                    (
                        runtime_fix_results_complete,
                        fixed_best_condition,
                        fixed_best_metric,
                        fixed_seed_cache,
                    ) = _stage13_complete_seed_cache_metric()
                    if (
                        rerun2.returncode == 0
                        and not rerun2.timed_out
                        and runtime_fix_results_complete
                        and fixed_best_metric is not None
                    ):
                        metric_val = fixed_best_metric
                        accept_runtime_fix_completion = True
                        fixed_flattened_metrics = {
                            f"{condition_name}_seed_{seed_idx}": seed_metric
                            for condition_name, seed_map in fixed_seed_cache.items()
                            if isinstance(seed_map, dict)
                            for seed_idx, seed_metric in seed_map.items()
                        }
                        iter_record["sandbox_after_fix"]["metrics"] = {
                            **fixed_flattened_metrics,
                            **(
                                rerun2.metrics
                                if isinstance(rerun2.metrics, dict)
                                else {}
                            ),
                        }
                        iter_record["runtime_fix_cached_completion"] = True
                        iter_record["runtime_fix_best_condition"] = fixed_best_condition
                        iter_record["runtime_fix_completed_seed_count"] = int(
                            sum(
                                len(seed_map)
                                for seed_map in fixed_seed_cache.values()
                                if isinstance(seed_map, dict)
                            )
                        )
                        logger.info(
                            "Stage 13 iteration %d: accepting runtime-fix results "
                            "as complete (%d condition(s) x %d seed(s))",
                            iteration,
                            len(ordered_conditions),
                            len(expected_seeds),
                        )
                    iter_record["metric"] = metric_val

            if metric_val is not None:
                consecutive_no_metrics = 0
                # R6-1: Only count toward no_improve_streak when we have real metrics
                if _is_better(metric_val, best_metric):
                    best_metric = metric_val
                    best_files = dict(candidate_files)
                    best_version = f"experiment_v{iteration}/"
                    iter_record["improved"] = True
                    no_improve_streak = 0
                else:
                    no_improve_streak += 1
            else:
                consecutive_no_metrics += 1
        elif validation.ok and best_version == "experiment/":
            best_files = dict(candidate_files)
            best_version = f"experiment_v{iteration}/"

        # P1: Track metric for saturation detection
        _metrics_history.append(metric_val)

        log["iterations"].append(iter_record)

        if accept_runtime_fix_completion:
            log["converged"] = True
            log["stop_reason"] = "runtime_fix_results_complete"
            break

        if consecutive_no_metrics >= 3:
            log["stop_reason"] = "consecutive_no_metrics"
            logger.warning("Stage 13: Aborting after %d consecutive iterations without metrics", consecutive_no_metrics)
            break

        if no_improve_streak >= 2:
            log["converged"] = True
            log["stop_reason"] = "no_improvement_for_2_iterations"
            logger.info(
                "Stage 13 converged after %d iterations (no improvement streak=%d)",
                iteration,
                no_improve_streak,
            )
            break

    # Write final experiment directory
    final_dir = stage_dir / "experiment_final"
    _write_project(final_dir, best_files)
    # Backward compat: also write experiment_final.py (copy of main.py)
    if "main.py" in best_files:
        (stage_dir / "experiment_final.py").write_text(
            best_files["main.py"], encoding="utf-8"
        )

    log["best_metric"] = best_metric
    log["best_version"] = best_version
    log["final_version"] = "experiment_final/"
    final_method_diagnosis_summary, final_method_diagnosis_payload = _build_stage13_method_diagnosis(
        stage_dir=stage_dir,
        run_dir=run_dir,
        metric_key=metric_key,
        metric_direction=metric_direction,
        condition_coverage_hint=_condition_coverage_hint,
        config_text=best_files.get("config.py", ""),
    )
    log["method_diagnosis"] = "method_diagnosis.json"
    log["method_redesign_required"] = bool(
        final_method_diagnosis_payload.get("method_redesign_required")
    )
    if log["method_redesign_required"]:
        log["scientific_outcome"] = "targeted_method_redesign_required"
        log["redesign_reasons"] = final_method_diagnosis_payload.get(
            "redesign_reasons",
            [],
        )
    # BUG-110: Aggregate ablation check results across iterations
    _all_ablation_identical = any(
        iter_rec.get("ablation_identical", False)
        for iter_rec in log.get("iterations", [])
        if isinstance(iter_rec, dict)
    )
    if _all_ablation_identical:
        log["ablation_identical_warning"] = True
    completion_gate = _build_stage13_completion_gate(log)
    log["completion_gate"] = completion_gate
    (stage_dir / "refinement_log.json").write_text(
        json.dumps(log, indent=2), encoding="utf-8"
    )

    artifacts = [
        "refinement_log.json",
        "refine_diagnostic_bundle.json",
        "refine_diagnostic_bundle.md",
        "method_diagnosis.json",
        "method_diagnosis.md",
        "experiment_final/",
    ]
    artifacts.extend(
        entry["version_dir"]
        for entry in log["iterations"]
        if isinstance(entry, dict) and isinstance(entry.get("version_dir"), str)
    )
    if not completion_gate["ok"]:
        return StageResult(
            stage=Stage.ITERATIVE_REFINE,
            status=StageStatus.FAILED,
            artifacts=tuple(artifacts),
            evidence_refs=tuple(f"stage-13/{a}" for a in artifacts),
            error=(
                "Stage 13 completion gate failed: "
                + ", ".join(str(reason) for reason in completion_gate["reasons"])
            ),
            decision="retry",
            control_hints={
                "completion_gate_failed": True,
                "completion_gate": completion_gate,
            },
        )
    return StageResult(
        stage=Stage.ITERATIVE_REFINE,
        status=StageStatus.DONE,
        artifacts=tuple(artifacts),
        evidence_refs=tuple(f"stage-13/{a}" for a in artifacts),
    )
