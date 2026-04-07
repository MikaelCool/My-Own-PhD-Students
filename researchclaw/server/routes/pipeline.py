"""Pipeline control API routes."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from researchclaw.config import RCConfig
from researchclaw.dashboard.collector import DashboardCollector
from researchclaw.project.manager import ProjectManager

logger = logging.getLogger(__name__)

import re as _re

_RUN_ID_RE = _re.compile(r"^rc-\d{8}-\d{6}-[a-f0-9]+$")


def _validated_run_dir(run_id: str) -> Path:
    if not _RUN_ID_RE.match(run_id):
        raise HTTPException(status_code=400, detail=f"Invalid run_id format: {run_id}")
    run_dir = Path("artifacts") / run_id
    if not run_dir.resolve().is_relative_to(Path("artifacts").resolve()):
        raise HTTPException(status_code=400, detail=f"Invalid run_id: {run_id}")
    return run_dir


router = APIRouter(prefix="/api", tags=["pipeline"])


class PipelineStartRequest(BaseModel):
    topic: str | None = None
    config_overrides: dict[str, Any] | None = None
    auto_approve: bool = True
    project_id: str | None = None
    startup_contract: dict[str, Any] | None = None
    launch_mode: str | None = None
    from_stage: str | None = None
    resume: bool = False


class PipelineStartResponse(BaseModel):
    run_id: str
    status: str
    output_dir: str
    project_id: str | None = None


_active_run: dict[str, Any] | None = None
_run_task: asyncio.Task[Any] | None = None


def _get_app_state() -> dict[str, Any]:
    from researchclaw.server.app import _app_state

    return _app_state


def _project_manager(config: RCConfig) -> ProjectManager:
    return ProjectManager(Path(config.multi_project.projects_dir))


def _resolve_config(base_config: RCConfig, req: PipelineStartRequest) -> RCConfig:
    config = base_config
    if req.project_id:
        manager = _project_manager(base_config)
        project = manager.get(req.project_id)
        config = RCConfig.load(project.config_path, check_paths=False)
    if req.topic:
        import dataclasses

        new_research = dataclasses.replace(config.research, topic=req.topic)
        config = dataclasses.replace(config, research=new_research)
    return config


def _resolve_run_dir(
    config: RCConfig,
    req: PipelineStartRequest,
    run_id: str,
) -> tuple[Path, ProjectManager | None]:
    if req.project_id:
        manager = _project_manager(config)
        project = manager.get(req.project_id)
        run_dir = Path(project.run_dir) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        if req.startup_contract:
            manager.update_startup_contract(
                req.project_id,
                {
                    **project.startup_contract,
                    **req.startup_contract,
                    "goal": req.startup_contract.get("goal", req.topic or project.topic),
                    "launch_mode": req.launch_mode or project.launch_mode,
                },
            )
        manager.start_run(req.project_id, run_id, launch_mode=req.launch_mode)
        _write_run_startup_contract(
            run_dir,
            {
                **project.startup_contract,
                **(req.startup_contract or {}),
                "goal": (req.startup_contract or {}).get("goal", req.topic or project.topic),
                "launch_mode": req.launch_mode or project.launch_mode,
            },
        )
        return run_dir, manager
    run_dir = _validated_run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_run_startup_contract(
        run_dir,
        {
            **(req.startup_contract or {}),
            "goal": (req.startup_contract or {}).get("goal", req.topic or config.research.topic),
            "launch_mode": req.launch_mode or "standard_full_run",
        },
    )
    return run_dir, None


def _write_run_startup_contract(run_dir: Path, startup_contract: dict[str, Any]) -> None:
    payload = dict(startup_contract or {})
    payload["launch_mode"] = str(payload.get("launch_mode") or "standard_full_run")
    (run_dir / "startup_contract.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _resolve_from_stage(
    req: PipelineStartRequest,
    run_dir: Path,
):
    from researchclaw.pipeline.runner import read_checkpoint
    from researchclaw.pipeline.stages import Stage

    if req.from_stage:
        try:
            return Stage[req.from_stage.upper()]
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"Unknown stage: {req.from_stage}") from exc

    launch_mode = (req.launch_mode or "standard_full_run").lower()
    if launch_mode == "review_only":
        return Stage.PEER_REVIEW
    if launch_mode == "rebuttal_revision":
        return Stage.PAPER_REVISION
    if launch_mode == "continue_existing_state" or req.resume:
        resumed = read_checkpoint(run_dir)
        if resumed is not None:
            return resumed
        for candidate in sorted(run_dir.parent.glob("rc-*"), reverse=True):
            if candidate == run_dir:
                continue
            resumed = read_checkpoint(candidate)
            if resumed is not None:
                return resumed
        return Stage.TOPIC_INIT
    return Stage.TOPIC_INIT


def _load_metrics(run_dir: Path) -> dict[str, Any]:
    collector = DashboardCollector(artifacts_dir=run_dir.parent)
    for snap in collector.collect_all():
        if snap.run_id == run_dir.name:
            return snap.metrics
    return {}


@router.post("/pipeline/start", response_model=PipelineStartResponse)
async def start_pipeline(req: PipelineStartRequest) -> PipelineStartResponse:
    global _active_run, _run_task

    if _active_run and _active_run.get("status") == "running":
        raise HTTPException(status_code=409, detail="A pipeline is already running")

    state = _get_app_state()
    base_config = state["config"]
    try:
        config = _resolve_config(base_config, req)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    import hashlib
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    topic_hash = hashlib.sha256(config.research.topic.encode()).hexdigest()[:6]
    run_id = f"rc-{ts}-{topic_hash}"
    try:
        run_dir, manager = _resolve_run_dir(config, req, run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    from_stage = _resolve_from_stage(req, run_dir)

    _active_run = {
        "run_id": run_id,
        "status": "running",
        "output_dir": str(run_dir),
        "topic": config.research.topic,
        "project_id": req.project_id,
        "launch_mode": req.launch_mode or "standard_full_run",
        "from_stage": from_stage.name,
    }

    async def _run_in_background() -> None:
        global _active_run
        try:
            from researchclaw.adapters import AdapterBundle
            from researchclaw.pipeline.runner import execute_pipeline

            kb_root = Path(config.knowledge_base.root) if config.knowledge_base.root else None
            if kb_root:
                kb_root.mkdir(parents=True, exist_ok=True)

            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: execute_pipeline(
                    run_dir=run_dir,
                    run_id=run_id,
                    config=config,
                    adapters=AdapterBundle(),
                    from_stage=from_stage,
                    auto_approve_gates=req.auto_approve,
                    stop_on_gate=not req.auto_approve,
                    skip_noncritical=True,
                    kb_root=kb_root,
                ),
            )
            done = sum(1 for item in results if item.status.value == "done")
            failed = sum(1 for item in results if item.status.value == "failed")
            final_status = "completed" if failed == 0 else "failed"
            if _active_run:
                _active_run["status"] = final_status
                _active_run["stages_done"] = done
                _active_run["stages_failed"] = failed
            if manager and req.project_id:
                summary = (
                    f"Launch mode: {req.launch_mode or 'standard_full_run'} | "
                    f"From: {from_stage.name} | Done: {done} | Failed: {failed}"
                )
                manager.finish_run(
                    req.project_id,
                    final_status,
                    _load_metrics(run_dir),
                    summary=summary,
                )
        except Exception as exc:
            logger.exception("Pipeline run failed")
            if _active_run:
                _active_run["status"] = "failed"
                _active_run["error"] = str(exc)
            if manager and req.project_id:
                manager.finish_run(req.project_id, "failed", summary=str(exc))

    _run_task = asyncio.create_task(_run_in_background())

    return PipelineStartResponse(
        run_id=run_id,
        status="running",
        output_dir=str(run_dir),
        project_id=req.project_id,
    )


@router.post("/pipeline/stop")
async def stop_pipeline() -> dict[str, str]:
    global _active_run, _run_task

    if not _run_task or not _active_run:
        raise HTTPException(status_code=404, detail="No pipeline is running")

    _run_task.cancel()
    _active_run["status"] = "stopped"
    project_id = _active_run.get("project_id")
    if project_id:
        manager = _project_manager(_get_app_state()["config"])
        manager.finish_run(project_id, "stopped", summary="Stopped from web workspace.")
    return {"status": "stopped"}


@router.get("/pipeline/status")
async def pipeline_status() -> dict[str, Any]:
    if not _active_run:
        return {"status": "idle"}
    return _active_run


@router.get("/pipeline/stages")
async def pipeline_stages() -> dict[str, Any]:
    from researchclaw.pipeline.stages import Stage

    stages = []
    for stage in Stage:
        stages.append(
            {
                "number": int(stage),
                "name": stage.name,
                "label": getattr(stage, "label", stage.name.replace("_", " ").title()),
                "phase": getattr(stage, "phase", ""),
            }
        )
    return {"stages": stages}


@router.get("/runs")
async def list_runs() -> dict[str, Any]:
    artifacts = Path("artifacts")
    runs: list[dict[str, Any]] = []
    if artifacts.exists():
        for directory in sorted(artifacts.iterdir(), reverse=True):
            if directory.is_dir() and directory.name.startswith("rc-"):
                info: dict[str, Any] = {"run_id": directory.name, "path": str(directory)}
                ckpt = directory / "checkpoint.json"
                if ckpt.exists():
                    try:
                        with ckpt.open() as handle:
                            info["checkpoint"] = json.load(handle)
                    except Exception:
                        pass
                runs.append(info)
    return {"runs": runs[:50]}


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    run_dir = _validated_run_dir(run_id)
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    info: dict[str, Any] = {"run_id": run_id, "path": str(run_dir)}
    ckpt = run_dir / "checkpoint.json"
    if ckpt.exists():
        try:
            with ckpt.open() as handle:
                info["checkpoint"] = json.load(handle)
        except Exception:
            pass

    stage_dirs = sorted([d.name for d in run_dir.iterdir() if d.is_dir() and d.name.startswith("stage-")])
    info["stages_completed"] = stage_dirs
    for pattern in ("paper.md", "paper.tex", "paper.pdf"):
        found = list(run_dir.rglob(pattern))
        if found:
            info[f"has_{pattern.split('.')[1]}"] = True
    return info


@router.get("/runs/{run_id}/metrics")
async def get_run_metrics(run_id: str) -> dict[str, Any]:
    run_dir = _validated_run_dir(run_id)
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    metrics: dict[str, Any] = {}
    results_file = run_dir / "results.json"
    if results_file.exists():
        try:
            with results_file.open() as handle:
                metrics = json.load(handle)
        except Exception:
            pass

    return {"run_id": run_id, "metrics": metrics}
