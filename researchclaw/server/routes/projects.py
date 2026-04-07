"""Project workspace API routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from researchclaw.project.manager import ProjectManager
from researchclaw.project.models import Project
from researchclaw.server.app import _app_state

router = APIRouter(prefix="/api", tags=["projects"])


class ProjectCreateRequest(BaseModel):
    project_id: str = Field(min_length=1)
    title: str | None = None
    topic: str = ""
    startup_contract: dict[str, Any] = Field(default_factory=dict)
    launch_mode: str = "standard_full_run"


def _get_project_manager() -> ProjectManager:
    config = _app_state["config"]
    return ProjectManager(Path(config.multi_project.projects_dir))


def _serialize_project(project: Project, manager: ProjectManager) -> dict[str, Any]:
    latest_run = manager.latest_run(project.name)
    payload = project.to_dict()
    payload["latest_run"] = latest_run
    return payload


@router.get("/projects")
async def list_projects() -> dict[str, Any]:
    manager = _get_project_manager()
    projects = [_serialize_project(project, manager) for project in manager.list_all()]
    return {"projects": projects}


@router.post("/projects")
async def create_project(req: ProjectCreateRequest) -> dict[str, Any]:
    manager = _get_project_manager()
    config_path = _app_state.get("config_path")
    if config_path is None:
        raise HTTPException(status_code=500, detail="Config path unavailable")
    try:
        project = manager.create(
            req.project_id,
            config_path=str(config_path),
            topic=req.topic,
            title=req.title,
            startup_contract={
                **req.startup_contract,
                "goal": req.startup_contract.get("goal", req.topic),
                "launch_mode": req.launch_mode,
            },
            launch_mode=req.launch_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"project": _serialize_project(project, manager)}


@router.get("/projects/{project_id}")
async def get_project(project_id: str) -> dict[str, Any]:
    manager = _get_project_manager()
    try:
        project = manager.get(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"project": _serialize_project(project, manager)}


@router.get("/projects/{project_id}/details")
async def get_project_details(project_id: str) -> dict[str, Any]:
    manager = _get_project_manager()
    try:
        return manager.materialize_details(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/projects/{project_id}/canvas")
async def get_project_canvas(project_id: str) -> dict[str, Any]:
    manager = _get_project_manager()
    try:
        return manager.materialize_canvas(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/projects/{project_id}/studio")
async def get_project_studio(project_id: str) -> dict[str, Any]:
    manager = _get_project_manager()
    try:
        return manager.materialize_studio(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/projects/{project_id}/runs")
async def list_project_runs(project_id: str) -> dict[str, Any]:
    manager = _get_project_manager()
    try:
        runs = manager.list_runs(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"project_id": project_id, "runs": runs}


@router.get("/projects/{project_id}/runs/{run_id}")
async def get_project_run(project_id: str, run_id: str) -> dict[str, Any]:
    manager = _get_project_manager()
    try:
        run = manager.get_run(project_id, run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"project_id": project_id, "run": run}


@router.get("/projects/{project_id}/files")
async def list_project_files(project_id: str) -> dict[str, Any]:
    manager = _get_project_manager()
    try:
        files = manager.list_workspace_files(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"project_id": project_id, "files": files}
