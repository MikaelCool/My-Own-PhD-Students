"""Tests for DockerSandbox — all mocked, no real Docker needed."""

from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from researchclaw.config import DockerSandboxConfig, ExperimentConfig, SandboxConfig
from researchclaw.experiment.docker_sandbox import (
    DockerSandbox,
    _effective_shared_cache_root,
    _next_container_name,
)
from researchclaw.experiment.factory import create_sandbox
from researchclaw.experiment.sandbox import SandboxResult, wait_for_idle_gpus


# ── SandboxResult contract ─────────────────────────────────────────────


def test_sandbox_result_fields():
    r = SandboxResult(
        returncode=0,
        stdout="primary_metric: 0.95\n",
        stderr="",
        elapsed_sec=1.2,
        metrics={"primary_metric": 0.95},
        timed_out=False,
    )
    assert r.returncode == 0
    assert r.metrics["primary_metric"] == 0.95
    assert r.timed_out is False


# ── DockerSandbox command building ─────────────────────────────────────


def test_build_run_command_network_none(tmp_path: Path):
    """network_policy='none' → --network none, --user UID:GID."""
    cfg = DockerSandboxConfig(network_policy="none")
    sandbox = DockerSandbox(cfg, tmp_path / "work")
    cmd = sandbox._build_run_command(
        tmp_path / "staging",
        entry_point="main.py",
        container_name="rc-test-1",
        selected_gpu_ids=(),
    )
    assert "docker" in cmd
    assert "--gpus" in cmd
    assert "--network" in cmd
    assert "none" in cmd
    assert "--memory=8192m" in cmd
    assert "--shm-size=2048m" in cmd
    assert cmd[-1] == "main.py"
    if hasattr(os, "getuid") and hasattr(os, "getgid"):
        assert "--user" in cmd
    else:
        assert "--user" not in cmd


def test_build_run_command_setup_only(tmp_path: Path):
    """Default network_policy='setup_only' → RC_SETUP_ONLY_NETWORK=1, --cap-add."""
    cfg = DockerSandboxConfig()  # default is setup_only
    sandbox = DockerSandbox(cfg, tmp_path / "work")
    cmd = sandbox._build_run_command(
        tmp_path / "staging",
        entry_point="main.py",
        container_name="rc-test-setup",
        selected_gpu_ids=(),
    )
    # Should set env var for setup-only network
    assert "-e" in cmd
    env_idx = [i for i, x in enumerate(cmd) if x == "-e"]
    env_values = [cmd[i + 1] for i in env_idx]
    assert "RC_SETUP_ONLY_NETWORK=1" in env_values
    # Should add NET_ADMIN capability
    assert "--cap-add=NET_ADMIN" in cmd
    # Should NOT have --network none (needs network for setup)
    network_indices = [i for i, x in enumerate(cmd) if x == "--network"]
    assert len(network_indices) == 0
    if hasattr(os, "getuid") and hasattr(os, "getgid"):
        assert "--user" in cmd
    else:
        assert "--user" not in cmd


def test_build_run_command_full_network(tmp_path: Path):
    """network_policy='full' → no --network none, has --user."""
    cfg = DockerSandboxConfig(network_policy="full")
    sandbox = DockerSandbox(cfg, tmp_path / "work")
    cmd = sandbox._build_run_command(
        tmp_path / "staging",
        entry_point="main.py",
        container_name="rc-test-full",
        selected_gpu_ids=(),
    )
    # No --network none
    network_indices = [i for i, x in enumerate(cmd) if x == "--network"]
    assert len(network_indices) == 0
    if hasattr(os, "getuid") and hasattr(os, "getgid"):
        assert "--user" in cmd
    else:
        assert "--user" not in cmd


def test_build_run_command_no_gpu(tmp_path: Path):
    cfg = DockerSandboxConfig(gpu_enabled=False, network_policy="none")
    sandbox = DockerSandbox(cfg, tmp_path / "work")
    cmd = sandbox._build_run_command(
        tmp_path / "staging",
        entry_point="main.py",
        container_name="rc-test-2",
        selected_gpu_ids=(),
    )
    assert "--gpus" not in cmd
    assert "--rm" not in cmd


def test_build_run_command_keeps_container_recoverable(tmp_path: Path):
    """Experiment containers must not auto-remove before logs can be recovered."""
    cfg = DockerSandboxConfig(network_policy="none")
    sandbox = DockerSandbox(cfg, tmp_path / "work")
    cmd = sandbox._build_run_command(
        tmp_path / "staging",
        entry_point="main.py",
        container_name="rc-test-recoverable",
        selected_gpu_ids=(),
    )
    assert "--rm" not in cmd


def test_build_run_command_exports_time_budget_env(tmp_path: Path):
    cfg = DockerSandboxConfig(network_policy="none")
    sandbox = DockerSandbox(cfg, tmp_path / "work")
    cmd = sandbox._build_run_command(
        tmp_path / "staging",
        entry_point="main.py",
        container_name="rc-test-budget",
        selected_gpu_ids=(),
        timeout_sec=432000,
    )
    env_values = [cmd[i + 1] for i, value in enumerate(cmd) if value == "-e"]
    assert "EXPERIMENT_TIME_BUDGET_SEC=432000" in env_values
    assert "EXPERIMENT_TIME_BUDGET_HOURS=120" in env_values


def test_build_run_command_without_getuid_getgid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Windows lacks os.getuid/getgid; Docker command construction must not crash."""
    monkeypatch.delattr(os, "getuid", raising=False)
    monkeypatch.delattr(os, "getgid", raising=False)
    cfg = DockerSandboxConfig()
    sandbox = DockerSandbox(cfg, tmp_path / "work")
    cmd = sandbox._build_run_command(
        tmp_path / "staging",
        entry_point="main.py",
        container_name="rc-test-win",
        selected_gpu_ids=(),
    )
    assert "docker" in cmd
    assert "--user" not in cmd


def test_build_run_command_specific_gpus(tmp_path: Path):
    cfg = DockerSandboxConfig(gpu_device_ids=(0, 2), network_policy="none")
    sandbox = DockerSandbox(cfg, tmp_path / "work")
    cmd = sandbox._build_run_command(
        tmp_path / "staging",
        entry_point="main.py",
        container_name="rc-test-3",
        selected_gpu_ids=(),
    )
    assert "--gpus" in cmd
    gpu_idx = cmd.index("--gpus")
    assert cmd[gpu_idx + 1] == '"device=0,2"'


def test_build_run_command_selected_multi_gpu_uses_quoted_device_request(tmp_path: Path):
    cfg = DockerSandboxConfig(network_policy="none")
    sandbox = DockerSandbox(cfg, tmp_path / "work")
    cmd = sandbox._build_run_command(
        tmp_path / "staging",
        entry_point="main.py",
        container_name="rc-test-selected-gpus",
        selected_gpu_ids=(2, 3),
    )
    gpu_idx = cmd.index("--gpus")
    env_values = [cmd[i + 1] for i, value in enumerate(cmd) if value == "-e"]
    assert cmd[gpu_idx + 1] == '"device=2,3"'
    assert "RC_ASSIGNED_GPU_IDS=2,3" in env_values


def test_wait_for_idle_gpus_starts_with_partial_allowed_set(monkeypatch: pytest.MonkeyPatch):
    cfg = SandboxConfig(
        gpu_required=True,
        gpu_allowed_ids=(0, 2, 4),
        gpu_wait_timeout_sec=1,
    )
    monkeypatch.setattr(
        "researchclaw.experiment.sandbox.pick_idle_gpus",
        lambda allowed_ids, limit=None: [0],
    )

    assert wait_for_idle_gpus(cfg) == (0,)


def test_wait_for_idle_gpus_returns_up_to_three_available(monkeypatch: pytest.MonkeyPatch):
    cfg = SandboxConfig(
        gpu_required=True,
        gpu_allowed_ids=(0, 2, 4, 6),
        gpu_wait_timeout_sec=1,
    )
    monkeypatch.setattr(
        "researchclaw.experiment.sandbox.pick_idle_gpus",
        lambda allowed_ids, limit=None: [0, 2, 4, 6][:limit],
    )

    assert wait_for_idle_gpus(cfg) == (0, 2, 4)


def test_build_run_command_mounts_hf_cache_writable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    hf_home = tmp_path / "hf-cache"
    hf_hub = hf_home / "hub"
    hf_hub.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HF_HOME", str(hf_home))
    monkeypatch.setattr(
        "researchclaw.experiment.docker_sandbox._root_disk_free_bytes",
        lambda: 21 * 1024**3,
    )
    cfg = DockerSandboxConfig(network_policy="none")
    sandbox = DockerSandbox(cfg, tmp_path / "work")
    cmd = sandbox._build_run_command(
        tmp_path / "staging",
        entry_point="main.py",
        container_name="rc-test-hf-cache",
        selected_gpu_ids=(),
    )
    mounts = [cmd[i + 1] for i, value in enumerate(cmd) if value == "-v"]
    assert f"{hf_hub}:/workspace/.cache/huggingface/hub:rw" in mounts


def test_build_run_command_mounts_shared_cache_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shared_root = tmp_path / "shared-cache"
    monkeypatch.setattr(
        "researchclaw.experiment.docker_sandbox._root_disk_free_bytes",
        lambda: 21 * 1024**3,
    )
    cfg = DockerSandboxConfig(network_policy="none", shared_cache_root=str(shared_root))
    sandbox = DockerSandbox(cfg, tmp_path / "work")
    cmd = sandbox._build_run_command(
        tmp_path / "staging",
        entry_point="main.py",
        container_name="rc-test-shared-cache",
        selected_gpu_ids=(),
    )
    mounts = [cmd[i + 1] for i, value in enumerate(cmd) if value == "-v"]
    env_pairs = [cmd[i + 1] for i, value in enumerate(cmd) if value == "-e"]

    assert f"{shared_root / 'huggingface'}:/workspace/.cache/huggingface:rw" in mounts
    assert f"{shared_root / 'data'}:/workspace/data:rw" in mounts
    assert f"{shared_root / 'torch'}:/workspace/.cache/torch:rw" in mounts
    assert "HF_DATASETS_CACHE=/workspace/data/hf" in env_pairs
    assert "HF_HUB_CACHE=/workspace/.cache/huggingface/hub" in env_pairs


def test_effective_shared_cache_root_falls_back_to_data2_when_root_disk_is_low(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured_root = tmp_path / "configured-root-cache"
    fallback_root = tmp_path / "data2" / "lyc" / "researchclaw_cache"
    monkeypatch.setattr(
        "researchclaw.experiment.docker_sandbox._ROOT_LOW_SPACE_FALLBACK",
        fallback_root,
    )
    monkeypatch.setattr(
        "researchclaw.experiment.docker_sandbox._root_disk_free_bytes",
        lambda: 19 * 1024**3,
    )
    monkeypatch.setattr(
        "researchclaw.experiment.docker_sandbox._path_uses_root_filesystem",
        lambda _path: True,
    )

    assert _effective_shared_cache_root(str(configured_root)) == fallback_root
    assert fallback_root.is_dir()


def test_build_run_command_uses_data2_fallback_when_root_disk_is_low_without_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fallback_root = tmp_path / "data2" / "lyc" / "researchclaw_cache"
    monkeypatch.setattr(
        "researchclaw.experiment.docker_sandbox._ROOT_LOW_SPACE_FALLBACK",
        fallback_root,
    )
    monkeypatch.setattr(
        "researchclaw.experiment.docker_sandbox._root_disk_free_bytes",
        lambda: 19 * 1024**3,
    )
    cfg = DockerSandboxConfig(network_policy="none")
    sandbox = DockerSandbox(cfg, tmp_path / "work")

    cmd = sandbox._build_run_command(
        tmp_path / "staging",
        entry_point="main.py",
        container_name="rc-test-low-root-fallback",
        selected_gpu_ids=(),
    )
    mounts = [cmd[i + 1] for i, value in enumerate(cmd) if value == "-v"]

    assert f"{fallback_root / 'data'}:/workspace/data:rw" in mounts
    assert fallback_root.is_dir()


def test_effective_shared_cache_root_preserves_non_root_config_when_root_disk_is_low(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured_root = tmp_path / "fast-disk-cache"
    fallback_root = tmp_path / "data2" / "lyc" / "researchclaw_cache"
    monkeypatch.setattr(
        "researchclaw.experiment.docker_sandbox._ROOT_LOW_SPACE_FALLBACK",
        fallback_root,
    )
    monkeypatch.setattr(
        "researchclaw.experiment.docker_sandbox._root_disk_free_bytes",
        lambda: 19 * 1024**3,
    )
    monkeypatch.setattr(
        "researchclaw.experiment.docker_sandbox._path_uses_root_filesystem",
        lambda _path: False,
    )

    assert _effective_shared_cache_root(str(configured_root)) == configured_root
    assert not fallback_root.exists()


# ── Harness injection ─────────────────────────────────────────────────


def test_harness_injection(tmp_path: Path):
    harness_src = Path(__file__).parent.parent / "researchclaw" / "experiment" / "harness_template.py"
    if not harness_src.exists():
        pytest.skip("harness_template.py not found")

    target = tmp_path / "project"
    target.mkdir()
    DockerSandbox._inject_harness(target)
    assert (target / "experiment_harness.py").exists()


def test_prepare_workspace_dirs_creates_writable_cache_layout(tmp_path: Path):
    staging = tmp_path / "staging"
    staging.mkdir()
    DockerSandbox._prepare_workspace_dirs(staging)
    for rel in [
        ".home",
        ".cache",
        ".cache/torch",
        ".cache/matplotlib",
        ".cache/huggingface",
        ".cache/huggingface/assets",
        ".cache/huggingface/transformers",
        ".cache/huggingface/xet",
    ]:
        assert (staging / rel).is_dir()


# ── Factory ────────────────────────────────────────────────────────────


def test_factory_returns_experiment_sandbox(tmp_path: Path):
    from researchclaw.experiment.sandbox import ExperimentSandbox

    config = ExperimentConfig(mode="sandbox")
    sandbox = create_sandbox(config, tmp_path / "work")
    assert isinstance(sandbox, ExperimentSandbox)


@patch("researchclaw.experiment.docker_sandbox.DockerSandbox.ensure_image", return_value=True)
@patch("researchclaw.experiment.docker_sandbox.DockerSandbox.check_docker_available", return_value=True)
def test_factory_returns_docker_sandbox(mock_avail, mock_image, tmp_path: Path):
    config = ExperimentConfig(mode="docker")
    sandbox = create_sandbox(config, tmp_path / "work")
    assert isinstance(sandbox, DockerSandbox)


@patch("researchclaw.experiment.docker_sandbox.DockerSandbox.check_docker_available", return_value=False)
def test_factory_falls_back_when_docker_unavailable(mock_avail, tmp_path: Path):
    config = ExperimentConfig(mode="docker")
    sandbox = create_sandbox(config, tmp_path / "work")
    # BUG-002: Should fall back to subprocess sandbox instead of raising
    from researchclaw.experiment.sandbox import ExperimentSandbox
    assert isinstance(sandbox, ExperimentSandbox)


@patch("researchclaw.experiment.docker_sandbox.DockerSandbox.ensure_image", return_value=False)
@patch("researchclaw.experiment.docker_sandbox.DockerSandbox.check_docker_available", return_value=True)
def test_factory_raises_when_image_missing(mock_avail, mock_image, tmp_path: Path):
    config = ExperimentConfig(mode="docker")
    with pytest.raises(RuntimeError, match="not found locally"):
        create_sandbox(config, tmp_path / "work")


# ── run() with mocked subprocess ──────────────────────────────────────


@patch("subprocess.run")
def test_docker_run_success(mock_run, tmp_path: Path):
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker", "run"],
        returncode=0,
        stdout="primary_metric: 0.85\n",
        stderr="",
    )
    cfg = DockerSandboxConfig(network_policy="none")
    sandbox = DockerSandbox(cfg, tmp_path / "work")
    result = sandbox.run("print('hello')", timeout_sec=60)

    assert result.returncode == 0
    assert result.metrics.get("primary_metric") == 0.85
    assert result.timed_out is False


@patch("subprocess.run")
def test_docker_run_timeout(mock_run, tmp_path: Path):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker run", timeout=10)
    cfg = DockerSandboxConfig(network_policy="none")
    sandbox = DockerSandbox(cfg, tmp_path / "work")
    result = sandbox.run("import time; time.sleep(999)", timeout_sec=10)

    assert result.timed_out is True
    assert result.returncode == -1


# ── Dep detection ─────────────────────────────────────────────────────


def test_detect_pip_packages(tmp_path: Path):
    (tmp_path / "main.py").write_text(
        "import torchdiffeq\nimport numpy\nfrom PIL import Image\n"
    )
    detected = DockerSandbox._detect_pip_packages(tmp_path)
    # torchdiffeq and PIL/Pillow are now in builtin → skipped
    # numpy should be skipped (builtin)
    assert "numpy" not in detected
    assert "torchdiffeq" not in detected


def test_detect_pip_packages_finds_unknown(tmp_path: Path):
    """Unknown packages should be detected."""
    (tmp_path / "main.py").write_text(
        "import some_new_package\nimport numpy\n"
    )
    detected = DockerSandbox._detect_pip_packages(tmp_path)
    assert "some_new_package" in detected
    assert "numpy" not in detected


def test_detect_pip_packages_skips_setup_py(tmp_path: Path):
    """setup.py should not be scanned for experiment deps."""
    (tmp_path / "setup.py").write_text("import some_setup_dep\n")
    (tmp_path / "main.py").write_text("import numpy\n")
    detected = DockerSandbox._detect_pip_packages(tmp_path)
    assert "some_setup_dep" not in detected


def test_detect_pip_packages_skips_future_import(tmp_path: Path):
    (tmp_path / "main.py").write_text("from __future__ import annotations\nimport numpy\n")
    detected = DockerSandbox._detect_pip_packages(tmp_path)
    assert "__future__" not in detected


def test_detect_pip_packages_maps_imports(tmp_path: Path):
    """Known import-to-pip mappings should be applied."""
    (tmp_path / "main.py").write_text(
        "import cv2\nimport wandb\n"
    )
    detected = DockerSandbox._detect_pip_packages(tmp_path)
    assert "opencv-python" in detected
    assert "wandb" in detected


def test_next_container_name_is_thread_safe():
    names: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        for _ in range(20):
            name = _next_container_name()
            with lock:
                names.append(name)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(names) == 100
    assert len(names) == len(set(names))


# ── requirements.txt generation ──────────────────────────────────────


def test_write_requirements_txt_from_auto_detect(tmp_path: Path):
    """Auto-detected packages should be written to requirements.txt."""
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "main.py").write_text("import wandb\nimport optuna\n")

    cfg = DockerSandboxConfig(auto_install_deps=True)
    sandbox = DockerSandbox(cfg, tmp_path / "work")
    sandbox._write_requirements_txt(staging)

    req_path = staging / "requirements.txt"
    assert req_path.exists()
    content = req_path.read_text()
    assert "wandb" in content
    assert "optuna" in content


def test_write_requirements_txt_with_pip_pre_install(tmp_path: Path):
    """pip_pre_install packages should be added to requirements.txt."""
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "main.py").write_text("import numpy\n")

    cfg = DockerSandboxConfig(pip_pre_install=("einops==0.8.0", "kornia"))
    sandbox = DockerSandbox(cfg, tmp_path / "work")
    sandbox._write_requirements_txt(staging)

    req_path = staging / "requirements.txt"
    assert req_path.exists()
    content = req_path.read_text()
    assert "einops==0.8.0" in content
    assert "kornia" in content


def test_write_requirements_txt_respects_existing(tmp_path: Path):
    """If LLM already generated requirements.txt, append only new packages."""
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "main.py").write_text("import numpy\n")
    (staging / "requirements.txt").write_text("wandb\n")

    cfg = DockerSandboxConfig(pip_pre_install=("wandb", "einops"))
    sandbox = DockerSandbox(cfg, tmp_path / "work")
    sandbox._write_requirements_txt(staging)

    content = (staging / "requirements.txt").read_text()
    # wandb already in existing file, should not be duplicated
    assert content.count("wandb") == 1
    # einops should be appended
    assert "einops" in content


def test_write_requirements_txt_filters_local_harness(tmp_path: Path):
    """LLM-generated requirements must not pip-install local project modules."""
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "main.py").write_text(
        "from experiment_harness import ExperimentHarness\n",
        encoding="utf-8",
    )
    (staging / "experiment_harness.py").write_text("# injected harness\n", encoding="utf-8")
    (staging / "requirements.txt").write_text(
        "experiment_harness\nnumpy\n",
        encoding="utf-8",
    )

    cfg = DockerSandboxConfig(network_policy="none", auto_install_deps=False)
    sandbox = DockerSandbox(cfg, tmp_path / "work")
    sandbox._write_requirements_txt(staging)

    assert (staging / "requirements.txt").read_text(encoding="utf-8") == ""


def test_align_generated_time_budget(tmp_path: Path):
    staging = tmp_path / "staging"
    staging.mkdir()
    config_py = staging / "config.py"
    config_py.write_text(
        "class Config:\n"
        "    def __init__(self):\n"
        "        self.time_budget_hours: int = 24\n",
        encoding="utf-8",
    )

    DockerSandbox._align_generated_time_budget(staging, timeout_sec=432000)

    assert "self.time_budget_hours: int = 120" in config_py.read_text(encoding="utf-8")


def test_patch_empty_summary_guard(tmp_path: Path):
    staging = tmp_path / "staging"
    staging.mkdir()
    main_py = staging / "main.py"
    main_py.write_text(
        "def _repair_summary_metrics(repaired, per_seed_records):\n"
        "    if not per_seed_records:\n"
        "        raise RuntimeError(\"No finite primary_metric values available for summary.\")\n",
        encoding="utf-8",
    )

    DockerSandbox._align_generated_time_budget(staging, timeout_sec=432000)

    text = main_py.read_text(encoding="utf-8")
    assert "skipped_due_to_time_budget_or_no_finite_primary_metric" in text
    assert "No finite primary_metric values available" not in text


def test_write_requirements_txt_no_packages(tmp_path: Path):
    """No requirements.txt if no packages needed."""
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "main.py").write_text("import numpy\n")

    cfg = DockerSandboxConfig()
    sandbox = DockerSandbox(cfg, tmp_path / "work")
    sandbox._write_requirements_txt(staging)

    assert not (staging / "requirements.txt").exists()


# ── Static checks (mocked) ────────────────────────────────────────────


@patch("subprocess.run")
def test_check_docker_available_true(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
    assert DockerSandbox.check_docker_available() is True


@patch("subprocess.run")
def test_check_docker_available_false(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=1)
    assert DockerSandbox.check_docker_available() is False


@patch("subprocess.run", side_effect=FileNotFoundError)
def test_check_docker_available_no_binary(mock_run):
    assert DockerSandbox.check_docker_available() is False


@patch("subprocess.run")
def test_ensure_image_true(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
    assert DockerSandbox.ensure_image("researchclaw/experiment:latest") is True


@patch("subprocess.run")
def test_ensure_image_false(mock_run):
    mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=1)
    assert DockerSandbox.ensure_image("nonexistent:latest") is False


# ── Default config values ────────────────────────────────────────────


def test_default_network_policy_is_setup_only():
    """Default network_policy should be 'setup_only', not 'none'."""
    cfg = DockerSandboxConfig()
    assert cfg.network_policy == "setup_only"


def test_default_auto_install_deps_enabled():
    cfg = DockerSandboxConfig()
    assert cfg.auto_install_deps is True


# ── Entry point path traversal validation ─────────────────────────────


@patch("researchclaw.experiment.docker_sandbox.subprocess.run")
def test_run_project_rejects_path_traversal(mock_run: MagicMock, tmp_path: Path):
    """run_project() must reject entry_point with '..' components."""
    project = tmp_path / "proj"
    project.mkdir()
    (project / "main.py").write_text("print('hi')")

    cfg = DockerSandboxConfig()
    work = tmp_path / "work"
    sandbox = DockerSandbox(cfg, work)
    # Create escape target so .exists() alone wouldn't catch it
    work.mkdir(parents=True, exist_ok=True)
    (work / "escape.py").write_text("print('escaped!')")

    result = sandbox.run_project(project, entry_point="../escape.py")

    assert result.returncode == -1
    assert ".." in result.stderr
    mock_run.assert_not_called()


@patch("researchclaw.experiment.docker_sandbox.subprocess.run")
def test_run_project_rejects_absolute_path(mock_run: MagicMock, tmp_path: Path):
    """run_project() must reject absolute entry_point paths."""
    project = tmp_path / "proj"
    project.mkdir()
    (project / "main.py").write_text("print('hi')")

    cfg = DockerSandboxConfig()
    sandbox = DockerSandbox(cfg, tmp_path / "work")
    result = sandbox.run_project(project, entry_point="/etc/passwd")

    assert result.returncode == -1
    lower = result.stderr.lower()
    assert (
        "relative" in lower
        or "absolute" in lower
        or "escapes staging directory" in lower
    )
    mock_run.assert_not_called()


# ── Container cleanup behavior ────────────────────────────────────────


@patch.object(DockerSandbox, "_remove_container")
@patch("subprocess.run")
def test_cleanup_on_normal_exit(mock_run: MagicMock, mock_remove: MagicMock, tmp_path: Path):
    """_remove_container is called on normal successful exit."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker", "run"], returncode=0, stdout="metric: 1.0\n", stderr="",
    )
    cfg = DockerSandboxConfig(network_policy="none")
    sandbox = DockerSandbox(cfg, tmp_path / "work")
    result = sandbox.run("print('ok')", timeout_sec=60)

    assert result.returncode == 0
    mock_remove.assert_called_once()


@patch.object(DockerSandbox, "_remove_container")
@patch.object(DockerSandbox, "_kill_container")
@patch("subprocess.run")
def test_cleanup_on_timeout(
    mock_run: MagicMock, mock_kill: MagicMock, mock_remove: MagicMock, tmp_path: Path,
):
    """Both _kill_container and _remove_container are called on timeout."""
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker run", timeout=10)
    cfg = DockerSandboxConfig(network_policy="none")
    sandbox = DockerSandbox(cfg, tmp_path / "work")
    result = sandbox.run("import time; time.sleep(999)", timeout_sec=10)

    assert result.timed_out is True
    mock_kill.assert_called_once()
    mock_remove.assert_called_once()


@patch.object(DockerSandbox, "_remove_container")
@patch("subprocess.run")
def test_cleanup_on_exception(mock_run: MagicMock, mock_remove: MagicMock, tmp_path: Path):
    """_remove_container is called even when subprocess.run raises an unexpected exception."""
    mock_run.side_effect = OSError("Docker daemon not responding")
    cfg = DockerSandboxConfig(network_policy="none")
    sandbox = DockerSandbox(cfg, tmp_path / "work")
    result = sandbox.run("print('hi')", timeout_sec=60)

    assert result.returncode == -1
    assert "Docker execution error" in result.stderr
    mock_remove.assert_called_once()


@patch("subprocess.run")
def test_execute_persists_recovery_artifacts(mock_run: MagicMock, tmp_path: Path):
    """Docker stdout/stderr/status are persisted before any optional cleanup."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker", "run"],
        returncode=0,
        stdout="primary_metric: 0.42\n",
        stderr="warning: test\n",
    )
    cfg = DockerSandboxConfig(network_policy="none", keep_containers=True)
    sandbox = DockerSandbox(cfg, tmp_path / "work")
    result = sandbox.run("print('ok')", timeout_sec=60)

    staging = tmp_path / "work" / "_docker_run_1"
    assert (staging / "docker_container.json").exists()
    assert (staging / "sandbox_stdout.log").read_text(encoding="utf-8") == "primary_metric: 0.42\n"
    assert (staging / "sandbox_stderr.log").read_text(encoding="utf-8") == "warning: test\n"

    payload = json.loads((staging / "sandbox_result.json").read_text(encoding="utf-8"))
    assert payload["returncode"] == 0
    assert payload["timed_out"] is False
    assert payload["container_name"].startswith("rc-exp-")
    assert result.metrics["primary_metric"] == 0.42


@patch.object(DockerSandbox, "_kill_container")
@patch("subprocess.run")
def test_timeout_persists_recovery_artifacts(
    mock_run: MagicMock, mock_kill: MagicMock, tmp_path: Path
):
    mock_run.side_effect = subprocess.TimeoutExpired(
        cmd="docker run",
        timeout=10,
        output="partial stdout",
        stderr="partial stderr",
    )
    cfg = DockerSandboxConfig(network_policy="none", keep_containers=True)
    sandbox = DockerSandbox(cfg, tmp_path / "work")
    result = sandbox.run("import time; time.sleep(999)", timeout_sec=10)

    staging = tmp_path / "work" / "_docker_run_1"
    payload = json.loads((staging / "sandbox_result.json").read_text(encoding="utf-8"))
    assert result.timed_out is True
    assert payload["timed_out"] is True
    assert (staging / "sandbox_stdout.log").read_text(encoding="utf-8") == "partial stdout"
    assert (staging / "sandbox_stderr.log").read_text(encoding="utf-8") == "partial stderr"
    mock_kill.assert_called_once()


def test_structured_results_metrics_include_condition_seed_means():
    metrics = DockerSandbox._extract_structured_metrics(
        {
            "metrics": {
                "qlora_fixed_seed_0": 0.61,
                "qlora_fixed_seed_1": 0.62,
                "probe_control_seed_0": 0.72,
                "probe_control_seed_1": 0.74,
                "probe_control": {"peak_vram_gb": 7.5},
            }
        }
    )

    assert metrics["qlora_fixed_seed_0"] == 0.61
    assert metrics["qlora_fixed/primary_metric_mean"] == pytest.approx(0.615)
    assert metrics["probe_control/primary_metric_mean"] == pytest.approx(0.73)
    assert metrics["probe_control/peak_vram_gb"] == 7.5


def test_run_project_recovers_orphaned_completed_container(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("print('new run should not start')\n", encoding="utf-8")

    work = tmp_path / "work"
    staging = work / "_docker_project_1"
    staging.mkdir(parents=True)
    (staging / "docker_container.json").write_text(
        json.dumps(
            {
                "container_name": "rc-exp-orphan",
                "selected_gpu_ids": [0],
                "command": ["docker", "run"],
                "timeout_sec": 432000,
                "created_at_unix": 1000.0,
            }
        ),
        encoding="utf-8",
    )
    (staging / "results.json").write_text(
        json.dumps(
            {
                "metrics": {
                    "qlora_fixed_seed_0": 0.61,
                    "qlora_fixed_seed_1": 0.63,
                }
            }
        ),
        encoding="utf-8",
    )

    calls: list[list[str]] = []

    def _fake_docker(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append(cmd)
        if cmd[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=json.dumps(
                    [
                        {
                            "State": {
                                "Running": False,
                                "ExitCode": 0,
                                "FinishedAt": "1970-01-01T00:20:00.000000000Z",
                            }
                        }
                    ]
                ),
                stderr="",
            )
        if cmd[:2] == ["docker", "logs"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="primary_metric: 0.62\n", stderr="")
        raise AssertionError(f"unexpected docker command: {cmd}")

    monkeypatch.setattr(
        "researchclaw.experiment.docker_sandbox._run_docker_command",
        _fake_docker,
    )

    cfg = DockerSandboxConfig(network_policy="none", keep_containers=True)
    sandbox = DockerSandbox(cfg, work)
    result = sandbox.run_project(project, timeout_sec=60)

    assert result.returncode == 0
    assert result.metrics["primary_metric"] == 0.62
    assert result.metrics["qlora_fixed/primary_metric_mean"] == pytest.approx(0.62)
    assert (staging / "sandbox_result.json").exists()
    payload = json.loads((staging / "sandbox_result.json").read_text(encoding="utf-8"))
    assert payload["recovered_orphan"] is True
    assert not any(cmd[:2] == ["docker", "run"] for cmd in calls)


def test_run_project_reuses_previously_recovered_orphan_result(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "main.py").write_text("print('new run should not start')\n", encoding="utf-8")

    work = tmp_path / "work"
    staging = work / "_docker_project_1"
    staging.mkdir(parents=True)
    (staging / "sandbox_stdout.log").write_text("", encoding="utf-8")
    (staging / "sandbox_stderr.log").write_text("", encoding="utf-8")
    (staging / "sandbox_result.json").write_text(
        json.dumps(
            {
                "container_name": "rc-exp-recovered",
                "returncode": 0,
                "elapsed_sec": 123.0,
                "timed_out": False,
                "recovered_orphan": True,
            }
        ),
        encoding="utf-8",
    )
    (staging / "results.json").write_text(
        json.dumps({"metrics": {"probe_control_seed_0": 0.72, "probe_control_seed_1": 0.74}}),
        encoding="utf-8",
    )

    cfg = DockerSandboxConfig(network_policy="none", keep_containers=True)
    sandbox = DockerSandbox(cfg, work)
    result = sandbox.run_project(project, timeout_sec=60)

    assert result.returncode == 0
    assert result.elapsed_sec == 123.0
    assert result.metrics["probe_control/primary_metric_mean"] == pytest.approx(0.73)


@patch.object(DockerSandbox, "_remove_container")
@patch.object(DockerSandbox, "_kill_container")
@patch("subprocess.run")
def test_keep_containers_skips_removal(
    mock_run: MagicMock, mock_kill: MagicMock, mock_remove: MagicMock, tmp_path: Path,
):
    """When keep_containers=True, _remove_container is never called."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=["docker", "run"], returncode=0, stdout="", stderr="",
    )
    cfg = DockerSandboxConfig(network_policy="none", keep_containers=True)
    sandbox = DockerSandbox(cfg, tmp_path / "work")
    sandbox.run("print('ok')", timeout_sec=60)

    mock_remove.assert_not_called()
