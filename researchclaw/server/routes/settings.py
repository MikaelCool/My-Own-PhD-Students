"""Settings API routes for the lightweight web workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from researchclaw.config import RCConfig
from researchclaw.server.app import _app_state

router = APIRouter(prefix="/api", tags=["settings"])


class SettingsUpdateRequest(BaseModel):
    yaml_text: str | None = None
    config: dict[str, Any] | None = None


@router.get("/settings")
async def get_settings() -> dict[str, Any]:
    config = _app_state.get("config")
    config_path = _app_state.get("config_path")
    return {
        "config": config.to_dict() if config else {},
        "config_path": str(config_path) if config_path else "",
        "yaml_text": Path(config_path).read_text(encoding="utf-8") if config_path else "",
    }


@router.post("/settings")
async def update_settings(req: SettingsUpdateRequest) -> dict[str, Any]:
    config_path = _app_state.get("config_path")
    if not config_path:
        raise HTTPException(status_code=500, detail="Config path unavailable")

    target = Path(config_path)
    try:
        if req.config is not None:
            parsed = req.config
            yaml_text = yaml.safe_dump(
                _yaml_ready(parsed),
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )
        elif req.yaml_text is not None:
            parsed = yaml.safe_load(req.yaml_text) or {}
            yaml_text = req.yaml_text
        else:
            raise ValueError("Either yaml_text or config is required")
        config = RCConfig.from_dict(parsed, project_root=target.parent, check_paths=False)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    target.write_text(yaml_text, encoding="utf-8")
    _app_state["config"] = config
    return {"status": "ok", "config": config.to_dict(), "yaml_text": yaml_text}


def _yaml_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _yaml_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_yaml_ready(item) for item in value]
    return value
