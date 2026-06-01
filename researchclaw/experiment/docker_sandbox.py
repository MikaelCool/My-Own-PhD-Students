"""Docker-based sandbox for experiment code execution with GPU passthrough.

Uses a single-container, three-phase execution model:
  Phase 0: pip install from requirements.txt (if present)
  Phase 1: Run setup.py for dataset downloads (if present)
  Phase 2: Run the experiment script (main.py)

All phases run in the same container, so pip-installed packages
persist into the experiment phase. Network can be disabled after
setup via iptables (``setup_only`` policy).
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from researchclaw.config import DockerSandboxConfig
from researchclaw.experiment.sandbox import (
    SandboxConfig,
    SandboxResult,
    SandboxNotifyCallback,
    StopRequestedCallback,
    parse_metrics,
    pick_idle_gpus,
    validate_entry_point,
    validate_entry_point_resolved,
    wait_for_idle_gpus,
)

logger = logging.getLogger(__name__)

_CONTAINER_COUNTER = 0
_counter_lock = threading.Lock()
_ROOT_LOW_SPACE_THRESHOLD_BYTES = 20 * 1024**3
_ROOT_LOW_SPACE_FALLBACK = Path("/data2/lyc/researchclaw_cache")


def _next_container_name() -> str:
    global _CONTAINER_COUNTER  # noqa: PLW0603
    with _counter_lock:
        _CONTAINER_COUNTER += 1
        return f"rc-exp-{_CONTAINER_COUNTER}-{os.getpid()}"


def _root_disk_free_bytes() -> int:
    """Return free bytes on the root filesystem."""
    return shutil.disk_usage("/").free


def _path_uses_root_filesystem(path: Path) -> bool:
    """Return whether ``path`` resolves onto the root filesystem.

    ``path`` may not exist yet, so walk up to the nearest existing ancestor
    before comparing device ids.
    """
    candidate = path.expanduser()
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    try:
        return candidate.stat().st_dev == Path("/").stat().st_dev
    except OSError:
        return False


def _effective_shared_cache_root(configured_root_raw: str) -> Path | None:
    """Resolve the shared cache root, preferring /data2 when root disk is low.

    Explicit configuration is still honored when it already points away from
    the root filesystem.  If the configured target is on the root filesystem,
    or no shared cache root is configured at all, low root-disk headroom takes
    precedence so new experiment runs do not fill the root volume.
    """
    configured_root = (
        Path(configured_root_raw).expanduser()
        if str(configured_root_raw or "").strip()
        else None
    )
    root_free_bytes = _root_disk_free_bytes()
    root_is_low = root_free_bytes < _ROOT_LOW_SPACE_THRESHOLD_BYTES
    configured_root_is_on_root = (
        configured_root is not None and _path_uses_root_filesystem(configured_root)
    )
    should_use_fallback = root_is_low and (
        configured_root is None or configured_root_is_on_root
    )

    if should_use_fallback:
        try:
            _ROOT_LOW_SPACE_FALLBACK.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning(
                "Root disk is low (%.2f GiB free), but failed to create shared cache "
                "fallback %s: %s",
                root_free_bytes / 1024**3,
                _ROOT_LOW_SPACE_FALLBACK,
                exc,
            )
            return configured_root
        logger.warning(
            "Root disk is low (%.2f GiB free); using shared cache fallback %s",
            root_free_bytes / 1024**3,
            _ROOT_LOW_SPACE_FALLBACK,
        )
        return _ROOT_LOW_SPACE_FALLBACK

    return configured_root


# Packages already in the Docker image — skip during auto-detect.
_BUILTIN_PACKAGES = {
    # PyTorch ecosystem
    "torch", "torchvision", "torchaudio", "torchdiffeq",
    # Scientific / ML
    "numpy", "scipy", "sklearn", "pandas", "matplotlib", "seaborn",
    "tqdm", "gymnasium", "networkx",
    # Extended ML ecosystem
    "timm", "einops", "torchmetrics", "albumentations", "kornia",
    "h5py", "tensorboard",
    # HuggingFace / LLM stack
    "transformers", "datasets", "accelerate", "peft", "trl",
    "bitsandbytes", "sentencepiece", "protobuf", "tokenizers",
    "safetensors", "evaluate",
    # Other pre-installed
    "yaml", "PIL", "mujoco",
    # Python stdlib
    "os", "sys", "math", "random", "json", "csv", "re", "time",
    "collections", "itertools", "functools", "pathlib", "typing",
    "dataclasses", "abc", "copy", "io", "logging", "argparse",
    "datetime", "hashlib", "pickle", "subprocess", "shutil",
    "tempfile", "warnings", "unittest", "contextlib", "operator",
    "string", "textwrap", "struct", "statistics", "glob", "signal",
    "urllib", "http", "email", "html", "xml",
    "__future__",
}

# Map import names to pip package names.
_IMPORT_TO_PIP = {
    "torchdiffeq": "torchdiffeq",
    "torch_geometric": "torch-geometric",
    "torchvision": "torchvision",
    "torchaudio": "torchaudio",
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
    "gym": "gymnasium",
    "ogb": "ogb",
    "dgl": "dgl",
    "lightning": "lightning",
    "pytorch_lightning": "pytorch-lightning",
    "wandb": "wandb",
    "optuna": "optuna",
}


def _host_user_args() -> list[str]:
    """Return ``docker run`` args to run as the host user when available.

    On POSIX we pass ``--user UID:GID`` so files written into the bind mount
    remain editable by the host user. Windows does not expose ``os.getuid`` /
    ``os.getgid``, so we skip the flag there instead of crashing before Docker
    is even invoked.
    """
    getuid = getattr(os, "getuid", None)
    getgid = getattr(os, "getgid", None)
    if callable(getuid) and callable(getgid):
        return ["--user", f"{getuid()}:{getgid()}"]
    return []


def _docker_gpu_device_spec(device_ids: tuple[int, ...]) -> str:
    """Return a Docker CLI GPU device request for explicit GPU ids.

    Docker 28 rejects multi-device specs such as ``device=2,3`` with
    ``cannot set both Count and DeviceIDs`` unless the device request is
    quoted exactly as the CLI documents.  Because we pass argv directly
    instead of going through a shell, the quote characters must be part of the
    argument value.
    """
    device_spec = ",".join(str(d) for d in device_ids)
    return f'"device={device_spec}"'


def _looks_like_docker_permission_error(output: str) -> bool:
    text = (output or "").lower()
    return (
        "permission denied while trying to connect to the docker daemon socket" in text
        or "got permission denied while trying to connect to the docker daemon socket" in text
    )


def _run_docker_command(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
    """Run a Docker CLI command, retrying through ``sg docker -c`` if needed.

    This handles the common case where the current process does not have the
    refreshed supplementary ``docker`` group, but the account is already a
    member of that group and can access Docker via ``sg docker -c ...``.
    """
    try:
        completed = subprocess.run(cmd, **kwargs)
    except FileNotFoundError:
        if cmd and cmd[0] == "docker" and shutil.which("sg"):
            return subprocess.run(["sg", "docker", "-c", shlex.join(cmd)], **kwargs)
        raise

    if cmd and cmd[0] == "docker" and shutil.which("sg"):
        stderr = completed.stderr if isinstance(completed.stderr, str | bytes) else ""
        stdout = completed.stdout if isinstance(completed.stdout, str | bytes) else ""
        if _looks_like_docker_permission_error(
            (stderr.decode("utf-8", errors="replace") if isinstance(stderr, bytes) else str(stderr))
            + "\n"
            + (stdout.decode("utf-8", errors="replace") if isinstance(stdout, bytes) else str(stdout))
        ):
            logger.info("Docker CLI permission denied; retrying via 'sg docker -c'")
            return subprocess.run(["sg", "docker", "-c", shlex.join(cmd)], **kwargs)

    return completed


class DockerSandbox:
    """Execute experiment code inside a Docker container.

    Same public API as :class:`ExperimentSandbox` so the pipeline can use
    either backend transparently.

    The container uses ``entrypoint.sh`` which runs three phases in sequence:
      0. ``pip install -r requirements.txt`` (if file present in /workspace)
      1. ``python3 setup.py`` (if file present in /workspace)
      2. ``python3 <entry_point>``

    Network policy controls when network is available:
      - ``"none"``:       No network at any point (``--network none``)
      - ``"setup_only"``: Network during Phase 0+1, disabled via iptables before Phase 2
      - ``"pip_only"``:   Network during Phase 0 only (legacy compat, same as setup_only)
      - ``"full"``:       Network available throughout all phases
    """

    def __init__(
        self,
        config: DockerSandboxConfig,
        workdir: Path,
        *,
        sandbox_config: SandboxConfig | None = None,
        notify_callback: SandboxNotifyCallback | None = None,
        stop_requested: StopRequestedCallback | None = None,
    ) -> None:
        self.config = config
        self.workdir = workdir.resolve()
        self.workdir.mkdir(parents=True, exist_ok=True)
        self._run_counter = 0
        self._sandbox_config = sandbox_config
        self._notify_callback = notify_callback
        self._stop_requested = stop_requested

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, code: str, *, timeout_sec: int = 300) -> SandboxResult:
        """Run a single Python code string inside a container."""
        self._run_counter += 1
        staging = self.workdir / f"_docker_run_{self._run_counter}"
        staging.mkdir(parents=True, exist_ok=True)

        script_path = staging / "main.py"
        script_path.write_text(code, encoding="utf-8")

        # Inject experiment harness
        self._inject_harness(staging)

        return self._execute(staging, entry_point="main.py", timeout_sec=timeout_sec)

    def run_project(
        self,
        project_dir: Path,
        *,
        entry_point: str = "main.py",
        timeout_sec: int = 300,
    ) -> SandboxResult:
        """Run a multi-file experiment project inside a container."""
        self._run_counter += 1
        staging = self.workdir / f"_docker_project_{self._run_counter}"
        if staging.exists():
            recovered = (
                self._recover_orphaned_execution(staging)
                or self._load_recovered_execution(staging)
            )
            if recovered is not None:
                logger.warning(
                    "Recovered completed Docker sandbox result from %s instead of "
                    "deleting the staging directory",
                    staging,
                )
                return recovered
            shutil.rmtree(staging)
        staging.mkdir(parents=True, exist_ok=True)

        # Pre-copy syntax validation — fail fast before any I/O
        err = validate_entry_point(entry_point)
        if err:
            return SandboxResult(
                returncode=-1, stdout="", stderr=err,
                elapsed_sec=0.0, metrics={},
            )

        # Inject harness first (immutable)
        self._inject_harness(staging)

        # Copy project files and subdirectories (skip harness overwrite)
        import shutil as _shutil
        for src_item in project_dir.iterdir():
            dest = staging / src_item.name
            if src_item.name == "experiment_harness.py":
                logger.warning(
                    "Project contains experiment_harness.py — skipping (immutable)"
                )
                continue
            if src_item.is_file():
                dest.write_bytes(src_item.read_bytes())
            elif src_item.is_dir() and not src_item.name.startswith((".", "__")):
                _shutil.copytree(src_item, dest, dirs_exist_ok=True)

        # Post-copy resolve check — catches symlink-based escapes
        err = validate_entry_point_resolved(staging, entry_point)
        if err:
            return SandboxResult(
                returncode=-1, stdout="", stderr=err,
                elapsed_sec=0.0, metrics={},
            )

        entry = staging / entry_point
        if not entry.exists():
            return SandboxResult(
                returncode=-1,
                stdout="",
                stderr=f"Entry point {entry_point} not found in project",
                elapsed_sec=0.0,
                metrics={},
            )

        return self._execute(staging, entry_point=entry_point, timeout_sec=timeout_sec)

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def check_docker_available() -> bool:
        """Return True if the Docker daemon is reachable."""
        try:
            cp = _run_docker_command(
                ["docker", "info"],
                capture_output=True,
                timeout=10,
                check=False,
            )
            return cp.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    @staticmethod
    def check_nvidia_runtime() -> bool:
        """Return True if the NVIDIA Container Toolkit is available."""
        try:
            cp = _run_docker_command(
                ["docker", "run", "--rm", "--gpus", "all",
                 "nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04",
                 "nvidia-smi"],
                capture_output=True,
                timeout=30,
                check=False,
            )
            return cp.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    @staticmethod
    def ensure_image(image: str) -> bool:
        """Return True if *image* exists locally (does NOT pull)."""
        try:
            cp = _run_docker_command(
                ["docker", "image", "inspect", image],
                capture_output=True,
                timeout=10,
                check=False,
            )
            return cp.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    @staticmethod
    def _inject_harness(target_dir: Path) -> None:
        harness_src = Path(__file__).parent / "harness_template.py"
        if harness_src.exists():
            dest = target_dir / "experiment_harness.py"
            dest.write_text(harness_src.read_text(encoding="utf-8"), encoding="utf-8")
            logger.debug("Injected experiment harness into %s", target_dir)
        else:
            logger.warning("Harness template not found at %s", harness_src)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _execute(
        self, staging_dir: Path, *, entry_point: str, timeout_sec: int
    ) -> SandboxResult:
        """Core execution: single container, three-phase via entrypoint.sh."""
        cfg = self.config
        container_name = _next_container_name()

        if not cfg.keep_containers:
            self._cleanup_rc_exp_containers(exclude={container_name})

        self._align_generated_time_budget(staging_dir, timeout_sec=timeout_sec)

        # Auto-generate requirements.txt if packages need installing
        if cfg.network_policy in ("pip_only", "setup_only", "full"):
            self._write_requirements_txt(staging_dir)

        self._prepare_workspace_dirs(staging_dir)
        selected_gpu_ids = self._select_gpu_ids_for_run()

        # Build the docker run command
        cmd = self._build_run_command(
            staging_dir,
            entry_point=entry_point,
            container_name=container_name,
            selected_gpu_ids=selected_gpu_ids,
            timeout_sec=timeout_sec,
        )

        start = time.monotonic()
        timed_out = False
        stdout = ""
        stderr = ""
        returncode = -1
        elapsed = 0.0
        self._write_container_metadata(
            staging_dir,
            container_name=container_name,
            selected_gpu_ids=selected_gpu_ids,
            command=cmd,
            timeout_sec=timeout_sec,
        )
        try:
            logger.debug("Docker run command: %s", cmd)
            completed = _run_docker_command(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
            stdout = completed.stdout
            stderr = completed.stderr
            returncode = completed.returncode
            elapsed = time.monotonic() - start
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            returncode = -1
            # Snapshot partial seed metrics before killing the container.
            self._snapshot_partial_results_from_container(
                container_name,
                staging_dir=staging_dir,
            )
            self._kill_container(container_name)
            elapsed = time.monotonic() - start
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - start
            stderr = f"Docker execution error: {exc}"
            self._write_execution_artifacts(
                staging_dir,
                container_name=container_name,
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
                elapsed=elapsed,
                timed_out=timed_out,
            )
            if not cfg.keep_containers:
                self._remove_container(container_name)
                self._cleanup_rc_exp_containers()
            return SandboxResult(
                returncode=-1,
                stdout=stdout,
                stderr=stderr,
                elapsed_sec=elapsed,
                metrics={},
            )

        self._write_execution_artifacts(
            staging_dir,
            container_name=container_name,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            elapsed=elapsed,
            timed_out=timed_out,
        )
        if not cfg.keep_containers:
            self._remove_container(container_name)
            self._cleanup_rc_exp_containers()

        # Parse metrics from stdout
        metrics = parse_metrics(stdout)

        # Try to read structured results.json from staging dir (volume-mounted)
        results_json_path = staging_dir / "results.json"
        if results_json_path.exists():
            try:
                structured = json.loads(
                    results_json_path.read_text(encoding="utf-8")
                )
                metrics.update(
                    {
                        key: value
                        for key, value in self._extract_structured_metrics(structured).items()
                        if key not in metrics
                    }
                )
                analysis_rel = structured.get("analysis_results_json_path")
                if isinstance(analysis_rel, str) and analysis_rel.strip():
                    analysis_path = staging_dir / analysis_rel
                    if analysis_path.exists():
                        analysis_payload = json.loads(
                            analysis_path.read_text(encoding="utf-8")
                        )
                        metrics.update(
                            {
                                key: value
                                for key, value in self._extract_structured_metrics(analysis_payload).items()
                                if key not in metrics
                            }
                        )
            except (json.JSONDecodeError, OSError):
                pass

        return SandboxResult(
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            elapsed_sec=elapsed,
            metrics=metrics,
            timed_out=timed_out,
        )

    @staticmethod
    def _to_finite_float(value: object) -> float | None:
        try:
            if value is None:
                return None
            out = float(value)
        except (TypeError, ValueError):
            return None
        if out != out or out in (float("inf"), float("-inf")):
            return None
        return out

    @staticmethod
    def _extract_structured_metrics(payload: object) -> dict[str, float]:
        """Flatten numeric metrics from ``results.json``.

        Stage 13 experiments often persist the reliable evidence as
        ``{"metrics": {"condition_seed_0": value, ...}}`` while stdout can be
        lost if the controller process disconnects from Docker.  This helper
        makes those result files first-class by flattening nested values and
        deriving per-condition means from seed-level metrics.
        """
        if not isinstance(payload, dict):
            return {}
        root = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else payload
        if not isinstance(root, dict):
            return {}

        metrics: dict[str, float] = {}

        condition_summaries = root.get("condition_summaries")
        if isinstance(condition_summaries, dict):
            for condition_name, summary in condition_summaries.items():
                if not isinstance(condition_name, str) or not isinstance(summary, dict):
                    continue
                for metric_key, metric_value in summary.items():
                    finite = DockerSandbox._to_finite_float(metric_value)
                    if finite is not None:
                        metrics[f"{condition_name}/{metric_key}"] = finite
                scalar_summary = summary.get("scalar_summary")
                if isinstance(scalar_summary, dict):
                    for metric_key, stats in scalar_summary.items():
                        if not isinstance(metric_key, str):
                            continue
                        if isinstance(stats, dict):
                            for stat_name, stat_value in stats.items():
                                finite = DockerSandbox._to_finite_float(stat_value)
                                if finite is not None and isinstance(stat_name, str):
                                    metrics[f"{condition_name}/{metric_key}_{stat_name}"] = finite
                        else:
                            finite = DockerSandbox._to_finite_float(stats)
                            if finite is not None:
                                metrics[f"{condition_name}/{metric_key}"] = finite

        def _walk(prefix: str, value: object) -> None:
            finite = DockerSandbox._to_finite_float(value)
            if finite is not None and prefix:
                metrics[prefix] = finite
                return
            if isinstance(value, dict):
                for child_key, child_value in value.items():
                    if not isinstance(child_key, str):
                        continue
                    child_prefix = f"{prefix}/{child_key}" if prefix else child_key
                    _walk(child_prefix, child_value)

        for key, value in root.items():
            if isinstance(key, str):
                _walk(key, value)

        grouped: dict[str, list[float]] = {}
        for key, value in list(metrics.items()):
            match = re.match(r"^(.+)_seed_\d+$", key)
            if match:
                grouped.setdefault(match.group(1), []).append(value)
                continue
            match = re.match(r"^(.+)/\d+/primary_metric$", key)
            if match:
                grouped.setdefault(match.group(1), []).append(value)

        for condition, values in grouped.items():
            finite_values = [v for v in values if DockerSandbox._to_finite_float(v) is not None]
            if not finite_values:
                continue
            mean_value = sum(finite_values) / len(finite_values)
            metrics.setdefault(f"{condition}/primary_metric_mean", mean_value)
            metrics.setdefault(f"{condition}/primary_metric_min", min(finite_values))
            metrics.setdefault(f"{condition}/primary_metric_max", max(finite_values))

        return metrics

    @staticmethod
    def _parse_docker_finished_at(value: str) -> float | None:
        if not value or value.startswith("0001-"):
            return None
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        if "." in normalized:
            head, tail = normalized.split(".", 1)
            tz_part = ""
            frac = tail
            for marker in ("+", "-"):
                if marker in tail:
                    frac, tz_part = tail.split(marker, 1)
                    tz_part = marker + tz_part
                    break
            normalized = f"{head}.{frac[:6].ljust(6, '0')}{tz_part}"
        try:
            return datetime.fromisoformat(normalized).timestamp()
        except ValueError:
            return None

    @classmethod
    def _recover_orphaned_execution(cls, staging_dir: Path) -> SandboxResult | None:
        """Recover a completed Docker run when the controller died first.

        ``docker run`` can continue after the ResearchClaw controller process
        loses its HTTP/OpenClaw session.  In that case the container writes
        ``results.json`` into the mounted staging directory, but
        ``sandbox_result.json`` is never produced because Python never resumes
        after ``subprocess.run``.  On resume, do not delete that evidence.
        """
        metadata_path = staging_dir / "docker_container.json"
        results_path = staging_dir / "results.json"
        if not metadata_path.is_file() or not results_path.is_file():
            return None
        if (staging_dir / "sandbox_result.json").exists():
            return None

        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(metadata, dict):
            return None
        container_name = str(metadata.get("container_name") or "").strip()
        if not container_name:
            return None

        try:
            inspect_cp = _run_docker_command(
                ["docker", "inspect", container_name],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return None
        if inspect_cp.returncode != 0:
            return None
        try:
            inspect_payload = json.loads(inspect_cp.stdout or "[]")
        except json.JSONDecodeError:
            return None
        if not inspect_payload or not isinstance(inspect_payload[0], dict):
            return None
        state = inspect_payload[0].get("State")
        if not isinstance(state, dict) or bool(state.get("Running")):
            return None

        returncode = int(state.get("ExitCode") if state.get("ExitCode") is not None else -1)
        created_at = DockerSandbox._to_finite_float(metadata.get("created_at_unix"))
        finished_at = cls._parse_docker_finished_at(str(state.get("FinishedAt") or ""))
        elapsed = (
            max(0.0, finished_at - created_at)
            if created_at is not None and finished_at is not None
            else 0.0
        )

        stdout = ""
        try:
            logs_cp = _run_docker_command(
                ["docker", "logs", container_name],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if logs_cp.returncode == 0:
                stdout = logs_cp.stdout or ""
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            stdout = ""

        try:
            structured = json.loads(results_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            structured = {}
        metrics = parse_metrics(stdout)
        metrics.update(
            {
                key: value
                for key, value in cls._extract_structured_metrics(structured).items()
                if key not in metrics
            }
        )

        cls._write_execution_artifacts(
            staging_dir,
            container_name=container_name,
            returncode=returncode,
            stdout=stdout,
            stderr="",
            elapsed=elapsed,
            timed_out=False,
            recovered=True,
        )
        return SandboxResult(
            returncode=returncode,
            stdout=stdout,
            stderr="",
            elapsed_sec=elapsed,
            metrics=metrics,
            timed_out=False,
        )

    @classmethod
    def _load_recovered_execution(cls, staging_dir: Path) -> SandboxResult | None:
        """Load a previously recovered orphan result on a later resume."""
        result_path = staging_dir / "sandbox_result.json"
        results_path = staging_dir / "results.json"
        if not result_path.is_file() or not results_path.is_file():
            return None
        try:
            result_payload = json.loads(result_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(result_payload, dict) or not result_payload.get("recovered_orphan"):
            return None

        stdout = ""
        stderr = ""
        try:
            stdout = (staging_dir / "sandbox_stdout.log").read_text(encoding="utf-8")
        except OSError:
            pass
        try:
            stderr = (staging_dir / "sandbox_stderr.log").read_text(encoding="utf-8")
        except OSError:
            pass
        try:
            structured = json.loads(results_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            structured = {}

        metrics = parse_metrics(stdout)
        metrics.update(
            {
                key: value
                for key, value in cls._extract_structured_metrics(structured).items()
                if key not in metrics
            }
        )
        return SandboxResult(
            returncode=int(result_payload.get("returncode", -1)),
            stdout=stdout,
            stderr=stderr,
            elapsed_sec=float(result_payload.get("elapsed_sec") or 0.0),
            metrics=metrics,
            timed_out=bool(result_payload.get("timed_out")),
        )

    @staticmethod
    def _write_container_metadata(
        staging_dir: Path,
        *,
        container_name: str,
        selected_gpu_ids: tuple[int, ...],
        command: list[str],
        timeout_sec: int,
    ) -> None:
        # A resumed/retried stage may reuse the same staging directory. Clear
        # stale execution artifacts before recording the new live container so
        # monitors never mistake an old result for the current run.
        for name in ("sandbox_stdout.log", "sandbox_stderr.log", "sandbox_result.json"):
            try:
                (staging_dir / name).unlink(missing_ok=True)
            except OSError:
                logger.exception("Failed to remove stale Docker artifact %s", staging_dir / name)
        payload = {
            "container_name": container_name,
            "selected_gpu_ids": list(selected_gpu_ids),
            "command": command,
            "timeout_sec": timeout_sec,
            "created_at_unix": time.time(),
        }
        try:
            (staging_dir / "docker_container.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            logger.exception("Failed to write docker container metadata in %s", staging_dir)

    @staticmethod
    def _write_execution_artifacts(
        staging_dir: Path,
        *,
        container_name: str,
        returncode: int,
        stdout: str,
        stderr: str,
        elapsed: float,
        timed_out: bool,
        recovered: bool = False,
    ) -> None:
        """Persist Docker execution evidence before any container cleanup.

        This is deliberately written into the mounted staging directory so a
        pipeline restart can diagnose or recover even when the controller
        process loses contact with Docker.
        """
        try:
            (staging_dir / "sandbox_stdout.log").write_text(
                stdout or "",
                encoding="utf-8",
            )
            (staging_dir / "sandbox_stderr.log").write_text(
                stderr or "",
                encoding="utf-8",
            )
            payload = {
                "container_name": container_name,
                "returncode": returncode,
                "elapsed_sec": elapsed,
                "timed_out": timed_out,
                "completed_at_unix": time.time(),
            }
            if recovered:
                payload["recovered_orphan"] = True
            (staging_dir / "sandbox_result.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            logger.exception("Failed to write Docker sandbox artifacts in %s", staging_dir)

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp.replace(path)

    @staticmethod
    def _parse_seed_metrics_from_text(text: str) -> tuple[dict[str, float], list[dict[str, object]]]:
        metrics: dict[str, float] = {}
        rows_by_key: dict[tuple[str, int], dict[str, object]] = {}
        for raw in (text or "").splitlines():
            line = raw.strip()
            match = re.search(
                r"condition=([^\s]+)\s+seed=(\d+)\s+primary_metric:\s*([0-9.eE+-]+)",
                line,
            )
            if not match:
                continue
            condition_name = match.group(1)
            seed = int(match.group(2))
            try:
                value = float(match.group(3))
            except ValueError:
                continue
            if value != value or value in (float("inf"), float("-inf")):
                continue
            metrics[f"{condition_name}_seed_{seed}"] = value
            rows_by_key[(condition_name, seed)] = {
                "condition_name": condition_name,
                "seed": seed,
                "primary_metric": value,
                "source": "docker_logs",
            }
        return metrics, [rows_by_key[key] for key in sorted(rows_by_key)]

    @classmethod
    def _snapshot_partial_results_from_container(
        cls,
        container_id_or_name: str,
        *,
        staging_dir: Path | None = None,
    ) -> None:
        """Persist completed per-seed metrics before killing a live container.

        Older generated experiments only wrote ``results.json`` at the end.
        During a UI stop or power maintenance window, the only durable evidence
        may be Docker stdout.  Snapshot it into the mounted workspace so Stage
        13 can build a resume registry and continue from the next unfinished
        seed.
        """
        target_dir = staging_dir
        if target_dir is None:
            try:
                inspect_cp = _run_docker_command(
                    ["docker", "inspect", container_id_or_name],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                inspect_cp = None
            if inspect_cp is not None and inspect_cp.returncode == 0:
                try:
                    payload = json.loads(inspect_cp.stdout or "[]")
                except json.JSONDecodeError:
                    payload = []
                if payload and isinstance(payload[0], dict):
                    mounts = payload[0].get("Mounts")
                    if isinstance(mounts, list):
                        for mount in mounts:
                            if not isinstance(mount, dict):
                                continue
                            if mount.get("Destination") == "/workspace" and mount.get("Source"):
                                target_dir = Path(str(mount["Source"]))
                                break
        if target_dir is None:
            return
        try:
            logs_cp = _run_docker_command(
                ["docker", "logs", container_id_or_name],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return
        if logs_cp.returncode != 0:
            return
        stdout = (logs_cp.stdout or "") + "\n" + (logs_cp.stderr or "")
        metrics, rows = cls._parse_seed_metrics_from_text(stdout)
        if not metrics and not rows:
            return
        payload = {
            "status": "partial",
            "source": "docker_logs_before_container_cleanup",
            "container": container_id_or_name,
            "saved_at_unix": time.time(),
            "metrics": metrics,
            "results": rows,
            "completed_seed_count": len(rows),
        }
        try:
            cls._atomic_write_json(target_dir / "partial_results.json", payload)
            if not (target_dir / "results.json").exists():
                cls._atomic_write_json(target_dir / "results.json", payload)
            logger.warning(
                "Snapshotted %d partial seed results from Docker logs into %s",
                len(rows),
                target_dir,
            )
        except OSError:
            logger.exception("Failed to snapshot partial Docker results into %s", target_dir)

    @staticmethod
    def _prepare_workspace_dirs(staging_dir: Path) -> None:
        """Pre-create writable cache/home directories in the bind mount.

        If these directories are first created inside the container by a root
        process, later host-user execution can fail with permission errors.
        Creating them on the host keeps ownership aligned with the host UID.
        """
        for rel in (
            ".home",
            ".cache",
            ".cache/torch",
            ".cache/matplotlib",
            ".cache/huggingface",
            ".cache/huggingface/assets",
            ".cache/huggingface/transformers",
            ".cache/huggingface/xet",
        ):
            (staging_dir / rel).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _align_generated_time_budget(staging_dir: Path, *, timeout_sec: int) -> None:
        """Align LLM-generated config defaults with the real sandbox timeout.

        Some generated experiment configs hardcode ``time_budget_hours = 24``
        even when ResearchClaw is configured for a longer run. That stale
        default can combine with ``harness.should_stop()`` checks and skip
        whole conditions before the actual sandbox timeout. We patch common
        generated assignment patterns before execution and also pass matching
        environment variables into Docker.
        """
        if timeout_sec <= 0:
            return
        budget_hours = max(1, int((timeout_sec + 3599) // 3600))
        assignment_re = re.compile(
            r"(?m)^(?P<prefix>\s*self\.time_budget_hours\s*:\s*[^=]+?=\s*)\d+(\s*(?:#.*)?)$"
        )
        simple_assignment_re = re.compile(
            r"(?m)^(?P<prefix>\s*self\.time_budget_hours\s*=\s*)\d+(\s*(?:#.*)?)$"
        )
        for py_file in staging_dir.rglob("*.py"):
            try:
                text = py_file.read_text(encoding="utf-8")
            except OSError:
                continue
            updated = assignment_re.sub(
                lambda m: f"{m.group('prefix')}{budget_hours}{m.group(2) or ''}",
                text,
            )
            updated = simple_assignment_re.sub(
                lambda m: f"{m.group('prefix')}{budget_hours}{m.group(2) or ''}",
                updated,
            )
            if updated != text:
                py_file.write_text(updated, encoding="utf-8")
                logger.info(
                    "Aligned generated time_budget_hours to %sh in %s",
                    budget_hours,
                    py_file,
                )
            DockerSandbox._patch_empty_summary_guard(py_file)

    @staticmethod
    def _patch_empty_summary_guard(py_file: Path) -> None:
        """Avoid crashing when a condition has no completed seed records.

        Generated Stage 13 code sometimes raises on an empty per-condition
        record list. That turns a recoverable partial run into a runtime
        failure. Patch the narrow known pattern into a skipped-condition summary
        with a worst-case finite metric so prior completed results still land.
        """
        try:
            text = py_file.read_text(encoding="utf-8")
        except OSError:
            return
        needle = 'raise RuntimeError("No finite primary_metric values available for summary.")'
        if needle not in text:
            return
        replacement = (
            'repaired["status"] = "skipped"\n'
            '        repaired["skip_reason"] = "skipped_due_to_time_budget_or_no_finite_primary_metric"\n'
            '        repaired["primary_metric"] = 1.0e12\n'
            '        repaired["primary_metric_mean"] = 1.0e12\n'
            '        repaired["primary_metric_std"] = 0.0\n'
            '        repaired["per_seed_records"] = _json_ready(per_seed_records)\n'
            '        return repaired'
        )
        updated = text.replace(needle, replacement)
        if updated != text:
            py_file.write_text(updated, encoding="utf-8")
            logger.info("Patched empty-summary guard in generated experiment file %s", py_file)

    def _build_run_command(
        self,
        staging_dir: Path,
        *,
        entry_point: str,
        container_name: str,
        selected_gpu_ids: tuple[int, ...],
        timeout_sec: int = 0,
    ) -> list[str]:
        """Build the ``docker run`` command list.

        The container uses ``entrypoint.sh`` which handles:
          Phase 0: pip install requirements.txt
          Phase 1: python3 setup.py
          Phase 2: python3 <entry_point>

        Network policy determines --network and RC_SETUP_ONLY_NETWORK env.
        """
        cfg = self.config
        cmd = [
            "docker", "run",
            "--name", container_name,
            "-v", f"{staging_dir}:/workspace",
            "-w", "/workspace",
            f"--memory={cfg.memory_limit_mb}m",
            f"--shm-size={cfg.shm_size_mb}m",
        ]

        # --- Network policy ---
        if cfg.network_policy == "none":
            # Fully isolated — no network at any point
            cmd.extend(["--network", "none"])
            cmd.extend(_host_user_args())
        elif cfg.network_policy in ("setup_only", "pip_only"):
            # Network during Phase 0+1, disabled via iptables before Phase 2.
            # Run as host user so experiment can write results.json to volume.
            # iptables requires NET_ADMIN but will gracefully degrade if
            # the user lacks root — network remains available but the code
            # has already been validated by the pipeline security check.
            cmd.extend(["-e", "RC_SETUP_ONLY_NETWORK=1"])
            cmd.extend(_host_user_args())
            cmd.extend(["--cap-add=NET_ADMIN"])
        elif cfg.network_policy == "full":
            # Full network throughout — for development/debugging
            cmd.extend(_host_user_args())

        shared_cache_root = _effective_shared_cache_root(cfg.shared_cache_root)

        # Mount pre-cached datasets.
        # When a shared cache root is configured, keep the whole data tree
        # writable under that root.  Generated setup code can create sibling
        # directories such as /workspace/data/hf_home before datasets are
        # materialized, so mounting only /workspace/data/hf is insufficient.
        if shared_cache_root is not None:
            shared_data_root = shared_cache_root / "data"
            (shared_data_root / "hf").mkdir(parents=True, exist_ok=True)
            cmd.extend(["-v", f"{shared_data_root}:/workspace/data:rw"])
            cmd.extend(["-e", "HF_DATASETS_CACHE=/workspace/data/hf"])
        else:
            # Priority: /opt/datasets (system) > ~/.cache/datasets (user)
            datasets_host = Path("/opt/datasets")
            user_datasets = Path.home() / ".cache" / "datasets"
            if datasets_host.is_dir():
                cmd.extend(["-v", f"{datasets_host}:/workspace/data:ro"])
            elif user_datasets.is_dir():
                cmd.extend(["-v", f"{user_datasets}:/workspace/data:rw"])
            else:
                # Create user-level cache so containers can download datasets
                user_datasets.mkdir(parents=True, exist_ok=True)
                cmd.extend(["-v", f"{user_datasets}:/workspace/data:rw"])

        # Mount HuggingFace cache under /workspace so the host UID:GID can
        # access it even when the image's /home/researcher is not traversable
        # for arbitrary host users. Prefer a shared cache root when configured;
        # otherwise keep the legacy hub-only bind mount.
        hf_mounted = False
        _hf_root_cache = "/workspace/.cache/huggingface"
        _hf_hub_cache = f"{_hf_root_cache}/hub"
        if shared_cache_root is not None:
            shared_hf_cache = shared_cache_root / "huggingface"
            shared_hf_cache.mkdir(parents=True, exist_ok=True)
            cmd.extend(["-v", f"{shared_hf_cache}:{_hf_root_cache}:rw"])
            cmd.extend(["-e", f"HF_HUB_CACHE={_hf_hub_cache}"])
            hf_mounted = True
        else:
            hf_home_env = os.environ.get("HF_HOME", "").strip()
            if hf_home_env:
                xdg_hf = Path(hf_home_env).resolve()
                host_hub_cache = xdg_hf if xdg_hf.name == "hub" else xdg_hf / "hub"
                if host_hub_cache.is_dir():
                    cmd.extend(["-v", f"{host_hub_cache}:{_hf_hub_cache}:rw"])
                    cmd.extend(["-e", f"HF_HUB_CACHE={_hf_hub_cache}"])
                    hf_mounted = True
            if not hf_mounted:
                hf_cache_host = Path.home() / ".cache" / "huggingface" / "hub"
                if hf_cache_host.is_dir():
                    cmd.extend(["-v", f"{hf_cache_host}:{_hf_hub_cache}:rw"])
                    cmd.extend(["-e", f"HF_HUB_CACHE={_hf_hub_cache}"])

        extra_mounts_raw = os.environ.get("RC_EXTRA_DOCKER_MOUNTS", "").strip()
        if extra_mounts_raw:
            for mount_spec in extra_mounts_raw.split(","):
                mount_spec = mount_spec.strip()
                if mount_spec:
                    cmd.extend(["-v", mount_spec])
        local_kv_models = Path("/data2/lyc/kv_models")
        if local_kv_models.is_dir():
            cmd.extend(["-v", f"{local_kv_models}:/workspace/data/kv_models:ro"])

        # BUG-107 fix: Set TORCH_HOME to writable location so torchvision
        # can download pretrained model weights (e.g., Inception-v3 for FID).
        if shared_cache_root is not None:
            shared_torch_cache = shared_cache_root / "torch"
            shared_torch_cache.mkdir(parents=True, exist_ok=True)
            cmd.extend(["-v", f"{shared_torch_cache}:/workspace/.cache/torch:rw"])
        cmd.extend(["-e", "TORCH_HOME=/workspace/.cache/torch"])

        # BUG-R52-03: Set HOME to a writable directory.  The container runs
        # as the host user (--user UID:GID) whose HOME defaults to "/" when
        # no matching passwd entry exists.  pip --user then fails with
        # "Permission denied: '/.local'".
        cmd.extend(["-e", "HOME=/workspace/.home"])
        cmd.extend(["-e", "XDG_CACHE_HOME=/workspace/.cache"])
        cmd.extend(["-e", "HF_HOME=/workspace/.cache/huggingface"])
        cmd.extend(["-e", "HF_DATASETS_CACHE=/workspace/data/hf"])
        cmd.extend(["-e", "HF_ASSETS_CACHE=/workspace/.cache/huggingface/assets"])
        cmd.extend(["-e", "TRANSFORMERS_CACHE=/workspace/.cache/huggingface/transformers"])
        cmd.extend(["-e", "MPLCONFIGDIR=/workspace/.cache/matplotlib"])
        if timeout_sec > 0:
            budget_hours = max(1, int((timeout_sec + 3599) // 3600))
            cmd.extend(["-e", f"EXPERIMENT_TIME_BUDGET_SEC={int(timeout_sec)}"])
            cmd.extend(["-e", f"EXPERIMENT_TIME_BUDGET_HOURS={budget_hours}"])

        # Pass HF token if available (for gated model downloads)
        hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        if hf_token:
            cmd.extend(["-e", f"HF_TOKEN={hf_token}"])

        # GPU passthrough
        if cfg.gpu_enabled:
            if selected_gpu_ids:
                cmd.extend(["--gpus", _docker_gpu_device_spec(selected_gpu_ids)])
                cmd.extend(["-e", f"RC_ASSIGNED_GPU_IDS={','.join(str(d) for d in selected_gpu_ids)}"])
                logger.info("Docker sandbox selected process-free GPUs %s for experiment run", list(selected_gpu_ids))
            elif cfg.gpu_device_ids:
                cmd.extend(["--gpus", _docker_gpu_device_spec(tuple(cfg.gpu_device_ids))])
            else:
                cmd.extend(["--gpus", "all"])

        # Image + entry point (passed as CMD arg to entrypoint.sh)
        cmd.append(cfg.image)
        cmd.append(entry_point)

        return cmd

    def _select_gpu_ids_for_run(self) -> tuple[int, ...]:
        cfg = self.config
        if not cfg.gpu_enabled:
            return tuple()
        if self._sandbox_config is not None and self._sandbox_config.gpu_auto_select:
            selected = wait_for_idle_gpus(
                self._sandbox_config,
                self._notify_callback,
                self._stop_requested,
            )
            if cfg.gpu_device_ids:
                allowed = set(cfg.gpu_device_ids)
                selected = tuple(gpu for gpu in selected if gpu in allowed)
            return selected
        if cfg.gpu_device_ids:
            idle = pick_idle_gpus(cfg.gpu_device_ids, limit=3)
            return tuple(idle) if idle else tuple(cfg.gpu_device_ids)
        return tuple()

    def _write_requirements_txt(self, staging_dir: Path) -> None:
        """Generate requirements.txt in staging dir from auto-detected imports
        and explicit pip_pre_install, unless one already exists (LLM-generated).
        """
        req_path = staging_dir / "requirements.txt"

        # If the LLM already generated a requirements.txt, respect it but
        # append any pip_pre_install packages not already listed.
        existing_reqs: set[str] = set()
        local_modules = {
            pyf.stem for pyf in staging_dir.rglob("*.py")
        }
        if req_path.exists():
            cleaned_lines: list[str] = []
            changed = False
            for line in req_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    # Extract package name (before any version specifier)
                    pkg = re.split(r"[><=!~\[]", line)[0].strip().lower()
                    if pkg in _BUILTIN_PACKAGES or pkg in local_modules:
                        changed = True
                        continue
                    existing_reqs.add(pkg)
                cleaned_lines.append(line)
            if changed:
                cleaned_text = "\n".join(cleaned_lines).rstrip()
                req_path.write_text(
                    (cleaned_text + "\n") if cleaned_text else "",
                    encoding="utf-8",
                )

        # Collect additional packages to install
        packages: list[str] = []

        # From config pip_pre_install
        for pkg in self.config.pip_pre_install:
            pkg_base = re.split(r"[><=!~\[]", pkg)[0].strip().lower()
            if pkg_base not in existing_reqs:
                packages.append(pkg)
                existing_reqs.add(pkg_base)

        # Auto-detect from imports
        if self.config.auto_install_deps:
            detected = self._detect_pip_packages(staging_dir)
            for pkg in detected:
                pkg_base = pkg.lower()
                if pkg_base not in existing_reqs:
                    packages.append(pkg)
                    existing_reqs.add(pkg_base)

        if not packages and not req_path.exists():
            return  # Nothing to install

        if packages:
            mode = "a" if req_path.exists() else "w"
            with open(req_path, mode, encoding="utf-8") as f:
                if mode == "a":
                    f.write("\n# Auto-detected by ResearchClaw\n")
                for pkg in packages:
                    f.write(pkg + "\n")
            logger.info("requirements.txt updated: %s", packages)

    @staticmethod
    def _detect_pip_packages(staging_dir: Path) -> list[str]:
        """Scan Python files for import statements and return pip package names."""
        import_re = re.compile(
            r"^\s*(?:import|from)\s+([\w.]+)", re.MULTILINE
        )
        # Exclude local project modules (any .py file in staging_dir, recursive)
        # BUG-DA8-13: Use rglob to also scan subdirectories
        local_modules = {
            pyf.stem for pyf in staging_dir.rglob("*.py")
        }
        detected: list[str] = []
        for pyf in staging_dir.rglob("*.py"):
            if pyf.name == "setup.py":
                continue  # Don't scan setup.py for experiment deps
            text = pyf.read_text(encoding="utf-8", errors="replace")
            for m in import_re.finditer(text):
                top_module = m.group(1).split(".")[0]
                if top_module in _BUILTIN_PACKAGES:
                    continue
                if top_module in getattr(sys, "stdlib_module_names", set()):
                    continue
                if top_module in local_modules:
                    continue  # Skip local project modules
                pip_name = _IMPORT_TO_PIP.get(top_module, top_module)
                if pip_name not in detected:
                    detected.append(pip_name)

        return detected

    @staticmethod
    def _kill_container(name: str) -> None:
        try:
            _run_docker_command(
                ["docker", "kill", name],
                capture_output=True,
                timeout=10,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    @staticmethod
    def _remove_container(name: str) -> None:
        try:
            _run_docker_command(
                ["docker", "rm", "-f", name],
                capture_output=True,
                timeout=10,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    @staticmethod
    def _cleanup_rc_exp_containers(exclude: set[str] | None = None) -> None:
        exclude = exclude or set()
        try:
            listed = _run_docker_command(
                ["docker", "ps", "-aq", "--filter", "name=rc-exp-"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return
        if listed.returncode != 0:
            return
        container_ids = [line.strip() for line in listed.stdout.splitlines() if line.strip()]
        for cid in container_ids:
            try:
                name_cp = _run_docker_command(
                    ["docker", "inspect", "--format", "{{.Name}}", cid],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                continue
            if name_cp.returncode != 0:
                continue
            name = name_cp.stdout.strip().lstrip("/")
            if not name.startswith("rc-exp-") or name in exclude:
                continue
            try:
                DockerSandbox._snapshot_partial_results_from_container(cid)
                _run_docker_command(
                    ["docker", "stop", "-t", "30", cid],
                    capture_output=True,
                    timeout=45,
                    check=False,
                )
                _run_docker_command(
                    ["docker", "rm", "-f", cid],
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
                logger.warning("Removed stale ResearchClaw experiment container: %s", name)
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                continue
