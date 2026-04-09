"""Project manager: project workspace CRUD, run tracking, and startup contracts."""

from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from researchclaw.dashboard.collector import DashboardCollector
from researchclaw.pipeline.stages import PHASE_MAP, Stage
from researchclaw.project.models import Project

logger = logging.getLogger(__name__)

_REGISTRY_FILE = "registry.json"
_STARTUP_CONTRACT_FILE = "startup_contract.json"
_PROJECT_BRIEF_FILE = "project_brief.md"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProjectManager:
    """Manage multiple research projects with independent workspaces and runs."""

    def __init__(self, projects_dir: str | Path) -> None:
        self.projects_dir = Path(projects_dir).expanduser().resolve()
        self.projects: dict[str, Project] = {}
        self._active: str | None = None
        self._load_registry()

    # persistence -----------------------------------------------------------------

    def _registry_path(self) -> Path:
        return self.projects_dir / _REGISTRY_FILE

    def _project_dir(self, name: str) -> Path:
        return self.projects_dir / name

    def _load_registry(self) -> None:
        path = self._registry_path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for entry in data.get("projects", []):
                proj = Project.from_dict(entry)
                self.projects[proj.name] = proj
            self._active = data.get("active")
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Failed to load project registry: %s", exc)

    def _save_registry(self) -> None:
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "active": self._active,
            "projects": [p.to_dict() for p in self.projects.values()],
        }
        self._registry_path().write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # workspace helpers ------------------------------------------------------------

    def project_root(self, name: str) -> Path:
        return self._project_dir(name)

    def startup_contract_path(self, name: str) -> Path:
        return self.project_root(name) / _STARTUP_CONTRACT_FILE

    def project_brief_path(self, name: str) -> Path:
        return self.project_root(name) / _PROJECT_BRIEF_FILE

    def read_startup_contract(self, name: str) -> dict[str, Any]:
        path = self.startup_contract_path(name)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def update_startup_contract(self, name: str, startup_contract: dict[str, Any]) -> None:
        project = self.get(name)
        normalized = startup_contract or {}
        project.startup_contract = normalized
        project.launch_mode = str(
            normalized.get("launch_mode") or project.launch_mode or "standard_full_run"
        )
        project.updated_at = _utcnow()
        self.startup_contract_path(name).write_text(
            json.dumps(normalized, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.project_brief_path(name).write_text(
            self._render_project_brief(project, normalized),
            encoding="utf-8",
        )
        self._save_registry()

    def list_workspace_files(self, name: str, limit: int = 200) -> list[dict[str, Any]]:
        project = self.get(name)
        root = Path(project.workspace_dir)
        files: list[dict[str, Any]] = []
        if not root.exists():
            return files
        ignored_prefixes = {".git", ".venv", "__pycache__"}
        for path in sorted(root.rglob("*")):
            rel = path.relative_to(root)
            if any(part in ignored_prefixes for part in rel.parts):
                continue
            if path.is_file():
                files.append(
                    {
                        "path": str(rel).replace("\\", "/"),
                        "size": path.stat().st_size,
                        "modified_at": datetime.fromtimestamp(
                            path.stat().st_mtime, tz=timezone.utc
                        ).isoformat(),
                    }
                )
            if len(files) >= limit:
                break
        return files

    def list_runs(self, name: str) -> list[dict[str, Any]]:
        project = self.get(name)
        collector = DashboardCollector(artifacts_dir=project.run_dir)
        return [snap.to_dict() for snap in collector.collect_all()]

    def get_run(self, name: str, run_id: str) -> dict[str, Any]:
        collector = DashboardCollector(artifacts_dir=self.get(name).run_dir)
        for snap in collector.collect_all():
            if snap.run_id == run_id:
                return snap.to_dict()
        raise KeyError(f"Unknown run '{run_id}' for project '{name}'")

    def latest_run(self, name: str) -> dict[str, Any] | None:
        runs = self.list_runs(name)
        return runs[0] if runs else None

    def latest_recoverable_run(self, name: str) -> dict[str, Any] | None:
        """Return the most recent run that has a resumable checkpoint."""
        project = self.get(name)
        run_root = Path(project.run_dir)
        if not run_root.exists():
            return None

        from researchclaw.pipeline.runner import read_checkpoint

        candidates: list[Path] = []
        if project.last_run_id:
            candidates.append(run_root / project.last_run_id)
        candidates.extend(sorted(run_root.glob("rc-*"), reverse=True))

        seen: set[str] = set()
        for candidate in candidates:
            if not candidate.is_dir() or candidate.name in seen:
                continue
            seen.add(candidate.name)
            next_stage = read_checkpoint(candidate)
            if next_stage is None:
                continue
            return {
                "run_id": candidate.name,
                "path": str(candidate),
                "from_stage": next_stage.name,
                "from_stage_num": int(next_stage),
            }
        return None

    # CRUD ------------------------------------------------------------------------

    def create(
        self,
        name: str,
        config_path: str,
        topic: str | None = None,
        *,
        title: str | None = None,
        startup_contract: dict[str, Any] | None = None,
        launch_mode: str = "standard_full_run",
    ) -> Project:
        """Create a new project with an independent directory and config copy."""
        if name in self.projects:
            raise ValueError(f"Project already exists: {name}")

        project_dir = self.projects_dir / name
        workspace_dir = project_dir / "workspace"
        project_dir.mkdir(parents=True, exist_ok=True)
        workspace_dir.mkdir(parents=True, exist_ok=True)

        src = Path(config_path).expanduser().resolve()
        if src.exists():
            dst = project_dir / "config.yaml"
            shutil.copy2(src, dst)
            stored_config = str(dst)
        else:
            stored_config = config_path

        run_dir = project_dir / "artifacts"
        run_dir.mkdir(parents=True, exist_ok=True)

        project = Project(
            name=name,
            title=title or name,
            config_path=stored_config,
            run_dir=str(run_dir),
            workspace_dir=str(project_dir),
            topic=topic or "",
            launch_mode=launch_mode,
            startup_contract=startup_contract or {},
        )
        self.projects[name] = project
        if self._active is None:
            self._active = name
        self.update_startup_contract(name, startup_contract or {"launch_mode": launch_mode})
        self._save_registry()
        logger.info("Created project: %s", name)
        return project

    def delete(self, name: str) -> None:
        """Remove project from registry. Does not delete project files on disk."""
        if name not in self.projects:
            raise KeyError(f"Unknown project: {name}")
        del self.projects[name]
        if self._active == name:
            self._active = next(iter(self.projects), None)
        self._save_registry()
        logger.info("Deleted project (registry only): %s", name)

    def get(self, name: str) -> Project:
        if name not in self.projects:
            raise KeyError(f"Unknown project: {name}")
        return self.projects[name]

    def list_all(self) -> list[Project]:
        return sorted(self.projects.values(), key=lambda p: p.created_at)

    def get_status(self) -> dict[str, Any]:
        projects = self.list_all()
        return {
            "total": len(projects),
            "active": self._active,
            "by_status": _count_by(projects, "status"),
            "projects": [
                {
                    "name": p.name,
                    "title": p.title,
                    "status": p.status,
                    "topic": p.topic,
                    "launch_mode": p.launch_mode,
                }
                for p in projects
            ],
        }

    # switching -------------------------------------------------------------------

    def switch(self, name: str) -> Project:
        if name not in self.projects:
            raise KeyError(f"Unknown project: {name}")
        self._active = name
        self._save_registry()
        return self.projects[name]

    @property
    def active(self) -> Project | None:
        if self._active and self._active in self.projects:
            return self.projects[self._active]
        return None

    # comparison ------------------------------------------------------------------

    def compare(self, name_a: str, name_b: str) -> dict[str, Any]:
        a = self.get(name_a)
        b = self.get(name_b)
        return {
            "project_a": {
                "name": a.name,
                "status": a.status,
                "topic": a.topic,
                "metrics": a.metrics,
            },
            "project_b": {
                "name": b.name,
                "status": b.status,
                "topic": b.topic,
                "metrics": b.metrics,
            },
            "metric_diff": _metric_diff(a.metrics, b.metrics),
        }

    # run lifecycle ----------------------------------------------------------------

    def start_run(self, name: str, run_id: str, *, launch_mode: str | None = None) -> str:
        project = self.get(name)
        project.status = "running"
        project.last_run_id = run_id
        project.updated_at = _utcnow()
        if launch_mode:
            project.launch_mode = launch_mode
        self._save_registry()
        return run_id

    def finish_run(
        self,
        name: str,
        status: str,
        metrics: dict[str, Any] | None = None,
        *,
        summary: str = "",
    ) -> None:
        project = self.get(name)
        project.status = status
        project.updated_at = _utcnow()
        if metrics:
            project.metrics = metrics
        if summary:
            project.latest_summary = summary
        self._save_registry()

    # view materialization ---------------------------------------------------------

    def materialize_details(self, name: str) -> dict[str, Any]:
        project = self.get(name)
        latest_run = self.latest_run(name)
        startup_contract = self.read_startup_contract(name)
        return {
            "project": project.to_dict(),
            "startup_contract": startup_contract,
            "latest_run": latest_run,
            "workspace_files": self.list_workspace_files(name, limit=120),
            "key_artifacts": _collect_key_artifacts(Path(project.run_dir)),
        }

    def materialize_canvas(self, name: str) -> dict[str, Any]:
        project = self.get(name)
        latest_run = self.latest_run(name)
        startup_contract = self.read_startup_contract(name)
        project_node_id = f"project:{project.name}"
        nodes: list[dict[str, Any]] = [
            {
                "id": project_node_id,
                "type": "project",
                "label": project.title or project.name,
                "layer": 0,
                "sort": 0,
                "meta": {
                    "topic": project.topic,
                    "launch_mode": project.launch_mode,
                    "status": project.status,
                },
            }
        ]
        edges: list[dict[str, Any]] = []

        contract_specs = _contract_canvas_nodes(startup_contract)
        for idx, spec in enumerate(contract_specs, start=1):
            node_id = f"contract:{idx}"
            nodes.append(
                {
                    "id": node_id,
                    "type": spec["type"],
                    "label": spec["label"],
                    "layer": 1,
                    "sort": idx,
                    "meta": spec["meta"],
                }
            )
            edges.append({"source": project_node_id, "target": node_id, "kind": "contract"})

        run_node_id: str | None = None
        latest_run_root: Path | None = None
        if latest_run:
            run_id = str(latest_run["run_id"])
            run_node_id = f"run:{run_id}"
            latest_run_root = Path(project.run_dir) / run_id
            nodes.append(
                {
                    "id": run_node_id,
                    "type": "run",
                    "label": run_id,
                    "layer": 1,
                    "sort": 90,
                    "meta": latest_run,
                }
            )
            edges.append({"source": project_node_id, "target": run_node_id, "kind": "run"})

        phase_stage_map = _group_stage_nodes(latest_run)
        previous_phase_id = run_node_id or project_node_id
        macro_groups = (
            ("Discovery Council", tuple(list(PHASE_MAP.items())[:3])),
            ("Innovation Forge", tuple(list(PHASE_MAP.items())[3:6])),
            ("Editorial Board", tuple(list(PHASE_MAP.items())[6:])),
        )
        phase_index = 0
        for macro_index, (macro_label, phase_entries) in enumerate(macro_groups, start=1):
            macro_node_id = f"macro:{macro_index}"
            macro_completed = sum(
                1
                for _, phase_stages in phase_entries
                for stage in phase_stages
                if int(stage) in phase_stage_map
            )
            macro_total = sum(len(phase_stages) for _, phase_stages in phase_entries)
            nodes.append(
                {
                    "id": macro_node_id,
                    "type": "phase",
                    "label": macro_label,
                    "layer": 2,
                    "sort": macro_index,
                    "meta": {"completed": macro_completed, "total": macro_total},
                }
            )
            edges.append({"source": previous_phase_id, "target": macro_node_id, "kind": "phase"})
            previous_phase_id = macro_node_id

            for phase_label, phase_stages in phase_entries:
                phase_index += 1
                phase_node_id = f"phase:{phase_index}"
                completed = sum(1 for stage in phase_stages if int(stage) in phase_stage_map)
                nodes.append(
                    {
                        "id": phase_node_id,
                        "type": "phase",
                        "label": phase_label.split(":", 1)[-1].strip(),
                        "layer": 3,
                        "sort": phase_index,
                        "meta": {
                            "phase_key": phase_label,
                            "completed": completed,
                            "total": len(phase_stages),
                        },
                    }
                )
                edges.append({"source": macro_node_id, "target": phase_node_id, "kind": "phase"})

                last_stage_node_id: str | None = None
                for stage in phase_stages:
                    stage_runs = phase_stage_map.get(int(stage), [])
                    if not stage_runs:
                        continue
                    stage_node_id = f"stage:{int(stage):02d}"
                    nodes.append(
                        {
                            "id": stage_node_id,
                            "type": "stage",
                            "label": _stage_canvas_label(stage),
                            "layer": 4,
                            "sort": int(stage),
                            "meta": {
                                "stage": int(stage),
                                "stage_name": stage.name.lower(),
                                "versions": stage_runs,
                            },
                        }
                    )
                    if last_stage_node_id is None:
                        edges.append({"source": phase_node_id, "target": stage_node_id, "kind": "phase_stage"})
                    else:
                        edges.append({"source": last_stage_node_id, "target": stage_node_id, "kind": "flow"})
                    last_stage_node_id = stage_node_id

        if latest_run_root is not None:
            artifact_specs = _run_canvas_artifacts(latest_run_root)
            for idx, artifact in enumerate(artifact_specs, start=1):
                node_id = f"artifact:{idx}"
                nodes.append(
                    {
                        "id": node_id,
                        "type": artifact["type"],
                        "label": artifact["label"],
                        "layer": 5,
                        "sort": idx,
                        "meta": artifact["meta"],
                    }
                )
                edges.append(
                    {
                        "source": artifact["source"],
                        "target": node_id,
                        "kind": artifact["edge_kind"],
                    }
                )

            for idx, decision in enumerate(_decision_canvas_nodes(latest_run_root), start=1):
                node_id = f"decision:{idx}"
                nodes.append(
                    {
                        "id": node_id,
                        "type": decision["type"],
                        "label": decision["label"],
                        "layer": 5,
                        "sort": 200 + idx,
                        "meta": decision["meta"],
                    }
                )
                edges.append({"source": decision["source"], "target": node_id, "kind": decision["edge_kind"]})
                if decision.get("rollback_target"):
                    edges.append(
                        {
                            "source": node_id,
                            "target": decision["rollback_target"],
                            "kind": "rollback",
                        }
                    )

        return {
            "meta": {
                "project_id": project.name,
                "title": project.title or project.name,
                "launch_mode": project.launch_mode,
                "topic": project.topic,
                "latest_run_id": latest_run["run_id"] if latest_run else None,
                "phases": [label.split(":", 1)[-1].strip() for label in PHASE_MAP],
            },
            "nodes": nodes,
            "edges": edges,
        }

    def materialize_studio(self, name: str) -> dict[str, Any]:
        project = self.get(name)
        latest_run = self.latest_run(name)
        recoverable_run = self.latest_recoverable_run(name)
        startup_contract = self.read_startup_contract(name)
        logs: list[str] = []
        if latest_run:
            run_dir = Path(project.run_dir) / latest_run["run_id"]
            log_path = run_dir / "pipeline.log"
            if log_path.exists():
                logs = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-120:]
        return {
            "project": project.to_dict(),
            "latest_run": latest_run,
            "logs": logs,
            "messages": _build_studio_messages(project, startup_contract, latest_run, logs),
            "timeline": _build_studio_timeline(project, latest_run),
            "controls": {
                "can_start": project.status != "running",
                "can_stop": project.status == "running",
                "can_continue": project.status != "running" and recoverable_run is not None,
                "launch_mode": project.launch_mode,
                "continue_run_id": recoverable_run["run_id"] if recoverable_run else None,
                "continue_from_stage": recoverable_run["from_stage"] if recoverable_run else None,
            },
        }

    @staticmethod
    def _render_project_brief(project: Project, startup_contract: dict[str, Any]) -> str:
        objectives = startup_contract.get("objectives") or []
        baseline_urls = startup_contract.get("baseline_urls") or []
        paper_urls = startup_contract.get("paper_urls") or []
        lines = [
            f"# {project.title or project.name}",
            "",
            f"- Project ID: `{project.name}`",
            f"- Topic: {project.topic or '(not set)'}",
            f"- Launch Mode: `{startup_contract.get('launch_mode', project.launch_mode)}`",
            f"- Research Intensity: `{startup_contract.get('research_intensity', 'balanced')}`",
            f"- Decision Policy: `{startup_contract.get('decision_policy', 'autonomous')}`",
            "",
            "## Goal",
            startup_contract.get("goal") or "(not set)",
            "",
            "## Objectives",
        ]
        if objectives:
            for item in objectives:
                lines.append(f"- {item}")
        else:
            lines.append("- (not set)")
        lines.extend(["", "## Baselines"])
        if baseline_urls:
            for item in baseline_urls:
                lines.append(f"- {item}")
        else:
            lines.append("- (not set)")
        lines.extend(["", "## References"])
        if paper_urls:
            for item in paper_urls:
                lines.append(f"- {item}")
        else:
            lines.append("- (not set)")
        lines.extend(["", "## Runtime Constraints", startup_contract.get("runtime_constraints") or "(not set)", ""])
        return "\n".join(lines)


def _count_by(projects: list[Project], attr: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for project in projects:
        value = getattr(project, attr, "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _metric_diff(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    all_keys = set(a) | set(b)
    diff: dict[str, Any] = {}
    for key in sorted(all_keys):
        va, vb = a.get(key), b.get(key)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            diff[key] = {"a": va, "b": vb, "delta": round(vb - va, 6)}
        else:
            diff[key] = {"a": va, "b": vb}
    return diff


def _collect_key_artifacts(run_root: Path) -> list[dict[str, Any]]:
    if not run_root.exists():
        return []
    prioritized = (
        "claims_evidence_matrix.md",
        "paper_score.json",
        "review_state.json",
        "phase1_handoff.md",
        "phase2_handoff.md",
        "paper_draft.md",
        "paper.tex",
        "verification_report.json",
    )
    found: list[dict[str, Any]] = []
    for pattern in prioritized:
        for path in sorted(run_root.rglob(pattern), reverse=True):
            found.append(
                {
                    "label": path.name,
                    "path": str(path.relative_to(run_root)).replace("\\", "/"),
                    "run_id": path.relative_to(run_root).parts[0] if len(path.relative_to(run_root).parts) > 1 else "",
                }
            )
            break
    return found


def _contract_canvas_nodes(startup_contract: dict[str, Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    goal = str(startup_contract.get("goal") or "").strip()
    if goal:
        nodes.append(
            {
                "type": "contract",
                "label": goal[:72],
                "meta": {"kind": "goal", "value": goal},
            }
        )

    for objective in [str(item).strip() for item in startup_contract.get("objectives", []) if str(item).strip()][:3]:
        nodes.append(
            {
                "type": "objective",
                "label": objective[:72],
                "meta": {"kind": "objective", "value": objective},
            }
        )

    for baseline in [str(item).strip() for item in startup_contract.get("baseline_urls", []) if str(item).strip()][:3]:
        nodes.append(
            {
                "type": "baseline",
                "label": _short_label(baseline),
                "meta": {"kind": "baseline", "value": baseline},
            }
        )

    for paper in [str(item).strip() for item in startup_contract.get("paper_urls", []) if str(item).strip()][:2]:
        nodes.append(
            {
                "type": "reference",
                "label": _short_label(paper),
                "meta": {"kind": "reference", "value": paper},
            }
        )

    runtime_constraints = str(startup_contract.get("runtime_constraints") or "").strip()
    if runtime_constraints:
        nodes.append(
            {
                "type": "constraint",
                "label": runtime_constraints[:72],
                "meta": {"kind": "constraint", "value": runtime_constraints},
            }
        )
    return nodes


def _group_stage_nodes(latest_run: dict[str, Any] | None) -> dict[int, list[str]]:
    if not latest_run:
        return {}
    grouped: dict[int, list[str]] = {}
    for stage_dir in latest_run.get("stages_completed", []):
        number = _extract_stage_number(stage_dir)
        if number is None:
            continue
        grouped.setdefault(number, []).append(stage_dir)
    return grouped


def _extract_stage_number(stage_dir: str) -> int | None:
    match = re.match(r"stage-(\d+)", stage_dir)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _stage_canvas_label(stage: Stage) -> str:
    return f"{int(stage):02d} {stage.name.replace('_', ' ').title()}"


def _run_canvas_artifacts(run_root: Path) -> list[dict[str, Any]]:
    prioritized = (
        ("goal.md", "artifact"),
        ("problem_anchor.md", "artifact"),
        ("claims_evidence_matrix.md", "artifact"),
        ("analysis.md", "artifact"),
        ("paper_draft.md", "artifact"),
        ("paper_revised.md", "artifact"),
        ("quality_report.json", "quality"),
        ("verification_report.json", "quality"),
        ("deliverables/manifest.json", "deliverable"),
    )
    artifacts: list[dict[str, Any]] = []
    for rel_path, artifact_type in prioritized:
        path = _find_latest_run_file(run_root, rel_path)
        if path is None:
            continue
        stage_number = _extract_stage_number(path.parent.name) or _extract_stage_number(path.parent.parent.name)
        source = f"stage:{stage_number:02d}" if stage_number is not None else f"run:{run_root.name}"
        artifacts.append(
            {
                "type": artifact_type,
                "label": path.name,
                "source": source,
                "edge_kind": "artifact",
                "meta": {
                    "path": str(path.relative_to(run_root)).replace("\\", "/"),
                    "stage": stage_number,
                },
            }
        )
    return artifacts


def _decision_canvas_nodes(run_root: Path) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    history_path = run_root / "decision_history.json"
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            history = []
        if isinstance(history, list):
            for entry in history[:4]:
                if not isinstance(entry, dict):
                    continue
                rollback_target = entry.get("rollback_target")
                target_node = None
                if isinstance(rollback_target, int):
                    target_node = f"stage:{rollback_target:02d}"
                elif isinstance(rollback_target, str) and rollback_target.isdigit():
                    target_node = f"stage:{int(rollback_target):02d}"
                nodes.append(
                    {
                        "type": "decision",
                        "label": str(entry.get("decision") or "decision").upper(),
                        "source": "stage:15",
                        "edge_kind": "decision",
                        "rollback_target": target_node,
                        "meta": entry,
                    }
                )

    review_state_path = _find_latest_run_file(run_root, "review_state.json")
    if review_state_path is not None:
        try:
            review_state = json.loads(review_state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            review_state = {}
        if isinstance(review_state, dict):
            label = f"Review {review_state.get('review_outcome') or review_state.get('status') or 'state'}"
            nodes.append(
                {
                    "type": "review",
                    "label": label[:72],
                    "source": "stage:18",
                    "edge_kind": "review",
                    "meta": review_state,
                }
            )
    return nodes


def _find_latest_run_file(run_root: Path, relative_name: str) -> Path | None:
    direct = run_root / relative_name
    if direct.exists():
        return direct
    matches = sorted(run_root.rglob(Path(relative_name).name), reverse=True)
    for path in matches:
        if path.is_file():
            return path
    return None


def _short_label(value: str) -> str:
    text = value.replace("\\", "/").rstrip("/")
    return Path(text).name or text[-48:]


def _build_studio_messages(
    project: Project,
    startup_contract: dict[str, Any],
    latest_run: dict[str, Any] | None,
    logs: list[str],
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []

    goal = str(startup_contract.get("goal") or project.topic or "").strip()
    objectives = [
        str(item).strip() for item in startup_contract.get("objectives", []) if str(item).strip()
    ]
    if goal or objectives:
        prompt = goal or project.topic or project.title or project.name
        if objectives:
            prompt += "\n\nObjectives:\n" + "\n".join(f"- {item}" for item in objectives[:4])
        messages.append(
            {
                "role": "user",
                "title": "Startup Contract",
                "content": prompt,
                "timestamp": project.created_at.isoformat(),
            }
        )

    if latest_run:
        run_summary = [
            f"Run: {latest_run.get('run_id') or 'n/a'}",
            f"Status: {latest_run.get('status') or project.status}",
            f"Stage: {latest_run.get('current_stage_name') or latest_run.get('current_stage') or 0}",
            f"Launch Mode: {project.launch_mode}",
        ]
        if project.latest_summary:
            run_summary.append("")
            run_summary.append(project.latest_summary)
        messages.append(
            {
                "role": "assistant",
                "title": "ResearchClaw",
                "content": "\n".join(run_summary),
                "timestamp": project.updated_at.isoformat(),
            }
        )

    if project.status == "running":
        messages.append(
            {
                "role": "system",
                "title": "System",
                "content": "Pipeline is active. You can monitor stage progress here or stop the run from Studio.",
                "timestamp": project.updated_at.isoformat(),
            }
        )
    elif project.status in {"completed", "done"}:
        messages.append(
            {
                "role": "system",
                "title": "System",
                "content": "Latest run has completed. Review artifacts, quality gates, and publication outputs before starting a new cycle.",
                "timestamp": project.updated_at.isoformat(),
            }
        )

    if logs:
        recent = [line.strip() for line in logs[-4:] if line.strip()]
        if recent:
            messages.append(
                {
                    "role": "assistant",
                    "title": "Recent Activity",
                    "content": "\n".join(recent),
                    "timestamp": project.updated_at.isoformat(),
                }
            )

    return messages


def _build_studio_timeline(
    project: Project,
    latest_run: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = [
        {
            "kind": "project",
            "title": "Project created",
            "description": project.title or project.name,
            "timestamp": project.created_at.isoformat(),
            "status": "completed",
        }
    ]

    if not latest_run:
        return timeline

    if latest_run.get("start_time"):
        timeline.append(
            {
                "kind": "run",
                "title": "Run started",
                "description": latest_run.get("run_id") or "",
                "timestamp": latest_run["start_time"],
                "status": "completed",
            }
        )

    for stage_dir in latest_run.get("stages_completed", []):
        number = _extract_stage_number(stage_dir)
        if number is None:
            continue
        try:
            stage = Stage(number)
            title = _stage_canvas_label(stage)
        except ValueError:
            title = stage_dir
        timeline.append(
            {
                "kind": "stage",
                "title": title,
                "description": stage_dir,
                "timestamp": latest_run.get("start_time") or project.updated_at.isoformat(),
                "status": "completed",
            }
        )

    timeline.append(
        {
            "kind": "status",
            "title": "Current status",
            "description": str(latest_run.get("status") or project.status),
            "timestamp": project.updated_at.isoformat(),
            "status": str(latest_run.get("status") or project.status),
        }
    )

    return timeline
