"""Stage 10: Code generation."""

from __future__ import annotations

import ast
import json
import logging
import hashlib
import re
from pathlib import Path
from typing import Any

from researchclaw.adapters import AdapterBundle
from researchclaw.config import RCConfig
from researchclaw.experiment.validator import (
    CodeValidation,
    detect_non_code_response,
    format_issues_for_llm,
    validate_code,
)
from researchclaw.llm.client import LLMClient
from researchclaw.pipeline._domain import _detect_domain
from researchclaw.pipeline._helpers import (
    StageResult,
    _build_experiment_plan_summary,
    _chat_with_prompt,
    _compress_instruction_block,
    _ensure_sandbox_deps,
    _extract_code_block,
    _extract_multi_file_blocks,
    _extract_yaml_block,
    _get_evolution_overlay,
    _load_hardware_profile,
    _read_prior_artifact,
    _safe_json_loads,
    _utcnow_iso,
)
from researchclaw.pipeline.stages import Stage, StageStatus
from researchclaw.prompts import PromptManager

logger = logging.getLogger(__name__)

# Improvement G: Continuous-action environments that are incompatible with DQN
_CONTINUOUS_ENVS = {
    "pendulum", "halfcheetah", "hopper", "walker2d", "ant", "humanoid",
    "swimmer", "reacher", "invertedpendulum", "inverteddoublependulum",
    "mountaincarcontinuous", "lunarlander-continuous",
}


def _check_rl_compatibility(code: str) -> list[str]:
    """Detect DQN + continuous-action environment mismatches.

    Returns a list of error strings if incompatible combinations are found.
    """
    errors: list[str] = []
    code_lower = code.lower()
    has_dqn = "dqn" in code_lower
    if not has_dqn:
        return errors

    for env_name in _CONTINUOUS_ENVS:
        if env_name in code_lower:
            errors.append(
                f"RL COMPATIBILITY ERROR: DQN is used with continuous-action "
                f"environment '{env_name}'. DQN only works with DISCRETE action "
                f"spaces. Use SAC, TD3, or PPO instead."
            )
    return errors


def _sync_experiment_dir(exp_dir: Path, files: dict[str, str]) -> None:
    """Rewrite the experiment directory from the in-memory file set.

    This prevents stale or partially repaired files from surviving across
    regeneration / repair passes.
    """
    exp_dir.mkdir(parents=True, exist_ok=True)
    for old_item in exp_dir.iterdir():
        if old_item.is_file() and old_item.name not in files:
            old_item.unlink(missing_ok=True)
    for fname, code in files.items():
        (exp_dir / fname).write_text(code, encoding="utf-8")


def _effective_network_policy(config: RCConfig) -> str:
    """Return the effective network policy for code generation artifacts."""
    if config.experiment.mode == "docker":
        return config.experiment.docker.network_policy
    if config.experiment.mode == "sandbox":
        return "none"
    return "full"


def _load_benchmark_plan(run_dir: Path) -> dict[str, Any]:
    for s9_dir in sorted(run_dir.glob("stage-09*"), reverse=True):
        candidate = s9_dir / "benchmark_plan.json"
        if candidate.exists():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:  # noqa: BLE001
                logger.debug("Failed to load benchmark plan from %s", candidate, exc_info=True)
    return {}


def _detect_required_pip_packages(files: dict[str, str]) -> list[str]:
    """Infer non-builtin pip packages from generated files.

    This mirrors DockerSandbox auto-detection so Stage 10 validation uses the
    same contract as Stage 12 execution.
    """
    try:
        from researchclaw.experiment.docker_sandbox import (
            _BUILTIN_PACKAGES,
            _IMPORT_TO_PIP,
        )
    except Exception:  # noqa: BLE001
        return []

    import_re = re.compile(r"^\s*(?:import|from)\s+([\w.]+)", re.MULTILINE)
    local_modules = {
        name[:-3] for name in files if name.endswith(".py")
    }
    ignore_modules = {
        "__future__",
        "researchclaw",
        "experiment_config",
        "importlib",
        "pathlib",
        "typing",
        "dataclasses",
        "collections",
        "functools",
        "itertools",
        "json",
        "math",
        "os",
        "re",
        "sys",
        "time",
        "hashlib",
    }
    detected: list[str] = []
    for fname, text in files.items():
        if not fname.endswith(".py"):
            continue
        for match in import_re.finditer(text):
            top_module = match.group(1).split(".")[0]
            if (
                top_module in ignore_modules
                or top_module in _BUILTIN_PACKAGES
                or top_module in local_modules
            ):
                continue
            pip_name = _IMPORT_TO_PIP.get(top_module, top_module)
            if pip_name not in detected:
                detected.append(pip_name)
    return detected


def _sanitize_requirement_entries(entries: list[str]) -> list[str]:
    valid_pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[A-Za-z0-9_,.-]+\])?(?:[<>=!~]=?.*)?$")
    blocked = {
        "__future__",
        "importlib",
        "researchclaw",
        "experiment_config",
        "config",
    }
    cleaned: list[str] = []
    for raw in entries:
        item = raw.strip()
        if not item or item.startswith("#"):
            continue
        base = re.split(r"[<>=!~\[]", item, maxsplit=1)[0].strip()
        if not base or base in blocked:
            continue
        if not valid_pattern.match(item):
            continue
        if item not in cleaned:
            cleaned.append(item)
    return cleaned


def _compact_project_context_for_repair(
    files: dict[str, str],
    *,
    focus_file: str,
    focus_char_budget: int = 16000,
    summary_char_budget: int = 8000,
) -> str:
    parts: list[str] = []
    focus_code = files.get(focus_file, "")
    if focus_code:
        if len(focus_code) <= focus_char_budget:
            focus_payload = focus_code
        else:
            lines = focus_code.splitlines()
            head = "\n".join(lines[:160])
            tail = "\n".join(lines[-80:]) if len(lines) > 80 else ""
            signatures = re.findall(
                r"^(class\s+[A-Za-z_][A-Za-z0-9_]*.*|def\s+[A-Za-z_][A-Za-z0-9_]*\s*\(.*)",
                focus_code,
                re.MULTILINE,
            )
            signature_block = "\n".join(signatures[:120])
            focus_payload = (
                "# File head\n"
                f"{head}\n\n"
                "# Symbol signatures\n"
                f"{signature_block or '(none)'}\n"
            )
            if tail:
                focus_payload += f"\n# File tail\n{tail}\n"
            if len(focus_payload) > focus_char_budget:
                focus_payload = focus_payload[:focus_char_budget] + "\n# ... truncated ..."
        parts.append(f"```filename:{focus_file}\n{focus_payload}\n```")

    summary_lines: list[str] = []
    used = 0
    for fname in sorted(files):
        if fname == focus_file or not fname.endswith(".py"):
            continue
        code = files[fname]
        imports = re.findall(r"^(?:from|import)\s+([a-zA-Z_][\w.]*)", code, re.MULTILINE)
        line = (
            f"- {fname}: {len(code.splitlines())} lines; "
            f"imports={', '.join(imports[:6]) or 'none'}"
        )
        if used + len(line) + 1 > summary_char_budget:
            break
        summary_lines.append(line)
        used += len(line) + 1
    if summary_lines:
        parts.append("## Other Files Summary\n" + "\n".join(summary_lines))
    return "\n\n".join(parts)


def _extract_issue_filename(issue: str) -> str | None:
    match = re.search(r"\[([^\]]+\.py)\]", issue)
    if match:
        return match.group(1)
    match = re.search(r"\b([A-Za-z0-9_]+\.py)\b", issue)
    if match:
        return match.group(1)
    return None


def _extract_issue_symbols(issue: str) -> list[str]:
    symbols: list[str] = []
    for item in re.findall(r"'([A-Za-z_][A-Za-z0-9_]*)'", issue):
        if item not in symbols:
            symbols.append(item)
    return symbols


def _infer_issue_file_from_symbols(
    files: dict[str, str],
    issue: str,
) -> str | None:
    class_names = _extract_issue_symbols(issue)
    if not class_names:
        return None
    for fname, code in files.items():
        if not fname.endswith(".py"):
            continue
        if all(re.search(rf"^\s*class\s+{re.escape(name)}\b", code, re.MULTILINE) for name in class_names[:2]):
            return fname
    return None


def _is_auto_repairable_deep_issue(issue: str) -> bool:
    lower = issue.lower()
    if "shadows stdlib/pip" in lower:
        return False
    return True


def _auto_repairable_issue_set(issues: list[str]) -> set[str]:
    return {
        issue for issue in issues
        if any(
            kw in issue for kw in (
                "UnboundLocalError", "unregistered", "does not exist",
                "empty or trivial subclass", "does NOT override",
                "Import-usage mismatch", "NameError",
                "was removed", "ptp()",
                "copy-paste", "identical method signatures",
                "identical AST", "NOT a real ablation",
            )
        )
    }


def _group_deep_issues_by_file(
    files: dict[str, str],
    issues: list[str],
) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for issue in issues:
        fname = _extract_issue_filename(issue) or _infer_issue_file_from_symbols(files, issue)
        if not fname:
            continue
        grouped.setdefault(fname, []).append(issue)
    return grouped


def _collect_symbol_spans(code: str) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    spans: list[dict[str, Any]] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            spans.append(
                {
                    "name": node.name,
                    "kind": "class",
                    "start_line": node.lineno,
                    "end_line": getattr(node, "end_lineno", node.lineno),
                }
            )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            spans.append(
                {
                    "name": node.name,
                    "kind": "function",
                    "start_line": node.lineno,
                    "end_line": getattr(node, "end_lineno", node.lineno),
                }
            )
    return spans


def _extract_named_symbol_blocks(
    code: str,
    symbol_names: list[str],
    *,
    max_blocks: int = 6,
) -> list[dict[str, Any]]:
    if not symbol_names:
        return []
    lines = code.splitlines()
    spans = _collect_symbol_spans(code)
    blocks: list[dict[str, Any]] = []
    for symbol in symbol_names:
        for span in spans:
            if span["name"] != symbol:
                continue
            start = max(1, int(span["start_line"]) - 2)
            end = min(len(lines), int(span["end_line"]) + 2)
            blocks.append(
                {
                    "name": symbol,
                    "kind": span["kind"],
                    "start_line": start,
                    "end_line": end,
                    "code": "\n".join(lines[start - 1:end]),
                }
            )
            break
        if len(blocks) >= max_blocks:
            break
    return blocks


def _build_symbol_repair_context(
    files: dict[str, str],
    *,
    focus_file: str,
    issues: list[str],
) -> str:
    code = files.get(focus_file, "")
    if not code:
        return _compact_project_context_for_repair(files, focus_file=focus_file)

    lines = code.splitlines()
    header = "\n".join(lines[: min(len(lines), 80)])
    symbols: list[str] = []
    for issue in issues:
        for symbol in _extract_issue_symbols(issue):
            if symbol not in symbols:
                symbols.append(symbol)
    blocks = _extract_named_symbol_blocks(code, symbols)
    parts = [f"```filename:{focus_file}\n# File header\n{header}\n```"]
    if blocks:
        block_text = "\n\n".join(
            (
                f"### {block['kind']} {block['name']} "
                f"(lines {block['start_line']}-{block['end_line']})\n"
                f"```python\n{block['code']}\n```"
            )
            for block in blocks
        )
        parts.append("## Relevant Symbol Blocks\n" + block_text)
    else:
        parts.append(_compact_project_context_for_repair(files, focus_file=focus_file))

    summary_lines: list[str] = []
    for fname in sorted(files):
        if fname == focus_file or not fname.endswith(".py"):
            continue
        summary_lines.append(f"- {fname}: {len(files[fname].splitlines())} lines")
    if summary_lines:
        parts.append("## Other Files\n" + "\n".join(summary_lines[:6]))
    return "\n\n".join(parts)


def _file_issue_set(files: dict[str, str], focus_file: str) -> set[str]:
    from researchclaw.experiment.validator import deep_validate_files

    warnings = deep_validate_files(files)
    auto = _auto_repairable_issue_set(warnings)
    grouped = _group_deep_issues_by_file(files, list(auto))
    return set(grouped.get(focus_file, []))


def _extract_single_named_file(content: str, expected_name: str) -> str:
    if detect_non_code_response(content):
        return ""
    fenced = re.search(
        rf"```(?:filename:)?{re.escape(expected_name)}\s*\n(.*?)```",
        content,
        re.DOTALL,
    )
    if fenced:
        candidate = fenced.group(1).strip()
        if not detect_non_code_response(candidate):
            return candidate
    generic = re.search(r"```python\s*\n(.*?)```", content, re.DOTALL)
    if generic:
        candidate = generic.group(1).strip()
        if not detect_non_code_response(candidate):
            return candidate
    stripped = content.strip()
    if stripped.startswith(("from ", "import ", "class ", "def ", '"""')):
        return stripped
    return ""


def _maybe_add_requirements_file(
    files: dict[str, str],
    benchmark_plan: dict[str, Any],
    config: RCConfig,
) -> dict[str, str]:
    """Backfill requirements.txt when Stage 12 would auto-generate it anyway."""
    selected = benchmark_plan.get("selected_benchmarks", [])
    if not isinstance(selected, list):
        return files
    has_tier2 = any(
        isinstance(item, dict) and int(item.get("tier", 1)) >= 2
        for item in selected
    )
    if not has_tier2:
        return files
    if _effective_network_policy(config) in {"none", "pip_only"}:
        return files
    existing_requirements = str(files.get("requirements.txt", "") or "")
    explicit = str(benchmark_plan.get("requirements") or "").strip()
    detected = _detect_required_pip_packages(files)
    lines: list[str] = []
    if existing_requirements.strip():
        lines.extend(
            line.strip()
            for line in existing_requirements.splitlines()
            if line.strip()
        )
    if explicit:
        lines.extend(
            line.strip()
            for line in explicit.splitlines()
            if line.strip()
        )
    for pkg in detected:
        if pkg not in lines:
            lines.append(pkg)
    lines = _sanitize_requirement_entries(lines)
    if not lines:
        if existing_requirements.strip():
            updated = dict(files)
            updated.pop("requirements.txt", None)
            logger.info("Stage 10: removed invalid synthesized requirements.txt")
            return updated
        return files

    updated = dict(files)
    updated["requirements.txt"] = "\n".join(lines) + "\n"
    logger.info(
        "Stage 10: synthesized requirements.txt with %d package(s): %s",
        len(lines),
        lines,
    )
    return updated


def _maybe_add_setup_file(
    files: dict[str, str],
    benchmark_plan: dict[str, Any],
    config: RCConfig,
    *,
    previous_files: dict[str, str] | None = None,
) -> dict[str, str]:
    """Ensure Tier 2 dataset plans retain a runnable setup.py.

    Alignment regeneration often returns only the core Python files and drops
    support files such as setup.py. When that happens we preserve the previous
    setup.py or synthesize a minimal writable-cache variant.
    """
    selected = benchmark_plan.get("selected_benchmarks", [])
    if not isinstance(selected, list):
        return files
    tier2 = [
        item for item in selected
        if isinstance(item, dict) and int(item.get("tier", 1)) >= 2
    ]
    if not tier2:
        return files
    if _effective_network_policy(config) in {"none", "pip_only"}:
        return files
    if str(files.get("setup.py", "")).strip():
        return files

    if previous_files:
        prior_setup = str(previous_files.get("setup.py", "") or "").strip()
        if prior_setup:
            updated = dict(files)
            updated["setup.py"] = prior_setup + ("\n" if not prior_setup.endswith("\n") else "")
            logger.info("Stage 10: restored setup.py from previous file set")
            return updated

    updated = dict(files)
    updated["setup.py"] = (
        '"""Prepare writable cache directories for Tier 2 datasets."""\n\n'
        "import os\n\n"
        'DATA_DIR = "/workspace/data"\n'
        'HF_CACHE = os.path.join(DATA_DIR, "hf")\n'
        'HF_HOME = os.path.join(DATA_DIR, "hf_home")\n'
        'TRANSFORMERS_CACHE = os.path.join(HF_HOME, "transformers")\n'
        'HF_ASSETS_CACHE = os.path.join(HF_HOME, "assets")\n'
        'XDG_CACHE_HOME = os.path.join(DATA_DIR, "xdg_cache")\n\n'
        "def main() -> None:\n"
        "    for path in [DATA_DIR, HF_CACHE, HF_HOME, TRANSFORMERS_CACHE, HF_ASSETS_CACHE, XDG_CACHE_HOME]:\n"
        "        os.makedirs(path, exist_ok=True)\n"
        '    os.environ["HOME"] = DATA_DIR\n'
        '    os.environ["HF_HOME"] = HF_HOME\n'
        '    os.environ["HF_DATASETS_CACHE"] = HF_CACHE\n'
        '    os.environ["TRANSFORMERS_CACHE"] = TRANSFORMERS_CACHE\n'
        '    os.environ["HF_ASSETS_CACHE"] = HF_ASSETS_CACHE\n'
        '    os.environ["XDG_CACHE_HOME"] = XDG_CACHE_HOME\n'
        '    print("[setup] prepared writable dataset/cache roots")\n\n'
        'if __name__ == "__main__":\n'
        "    main()\n"
    )
    logger.info("Stage 10: synthesized fallback setup.py for Tier 2 datasets")
    return updated


def _tier2_dataset_errors(
    files: dict[str, str],
    benchmark_plan: dict[str, Any],
    config: RCConfig,
) -> list[str]:
    selected = benchmark_plan.get("selected_benchmarks", [])
    if not isinstance(selected, list):
        return []
    tier2 = [
        item for item in selected
        if isinstance(item, dict) and int(item.get("tier", 1)) >= 2
    ]
    if not tier2:
        return []

    names = [str(item.get("name", "unknown")) for item in tier2]
    policy = _effective_network_policy(config)
    mode = str(config.experiment.mode)
    errors: list[str] = []

    if policy in {"none", "pip_only"}:
        errors.append(
            "Benchmark plan selected Tier 2 downloadable datasets "
            f"{names}, but mode={mode} uses network_policy={policy}. "
            "These datasets are not reachable in this runtime."
        )
        return errors

    setup_code = files.get("setup.py", "")
    if not setup_code.strip():
        errors.append(
            "Tier 2 datasets were selected but setup.py is missing. "
            f"Required for dataset preparation: {names}."
        )
    requirements_text = files.get("requirements.txt", "")
    benchmark_requirements = str(benchmark_plan.get("requirements") or "").strip()
    detected_packages = _detect_required_pip_packages(files)
    if (benchmark_requirements or detected_packages) and not requirements_text.strip():
        errors.append(
            "Tier 2 dataset pipeline requires requirements.txt, but it was not generated."
        )
    return errors


def _collect_final_project_errors(
    files: dict[str, str],
    *,
    benchmark_plan: dict[str, Any] | None = None,
    config: RCConfig | None = None,
) -> list[str]:
    """Validate the final project snapshot before declaring Stage 10 done."""
    errors: list[str] = []
    if not files:
        return ["No generated files were produced."]
    if "main.py" not in files:
        errors.append("Missing required entry point file: main.py")
        return errors
    main_code = files.get("main.py", "")
    if not main_code.strip():
        errors.append("main.py is empty.")
        return errors
    for fname, code in sorted(files.items()):
        upstream_error = detect_non_code_response(code)
        if upstream_error:
            errors.append(f"{fname}: {upstream_error}")
            continue
        if not fname.endswith(".py"):
            continue
        validation = validate_code(code)
        if not validation.ok:
            errors.append(f"{fname}: {validation.summary()}")
    if benchmark_plan is not None and config is not None:
        errors.extend(_tier2_dataset_errors(files, benchmark_plan, config))
    return errors


def _execute_code_generation(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    exp_plan = _read_prior_artifact(run_dir, "exp_plan.yaml") or ""
    compact_exp_plan = _build_experiment_plan_summary(
        exp_plan,
        run_dir=run_dir,
        max_chars=4700,
    )
    metric = config.experiment.metric_key
    max_repair = 5  # BUG-14: Increased from 3 to give more chances for critical bugs
    files: dict[str, str] = {}
    validation_log: list[str] = []
    benchmark_plan_data = _load_benchmark_plan(run_dir)

    # --- Detect available packages for sandbox ---
    _pm = prompts or PromptManager()

    # --- Hardware-aware package hint ---
    hw_profile = _load_hardware_profile(run_dir)
    if config.experiment.mode in ("sandbox", "docker"):
        if config.experiment.mode == "docker":
            pkg_prefix = "docker mode"
            _net_policy = config.experiment.docker.network_policy
            _base_pkgs = (
                ", torchvision, torchaudio, matplotlib, seaborn, scipy, "
                "tqdm, torchdiffeq, gymnasium, networkx, PyYAML, Pillow, "
                "transformers, datasets, accelerate, peft, bitsandbytes, "
                "timm, einops, torchmetrics, h5py"
            )
            if _net_policy == "none":
                pkg_extras = _base_pkgs + " (ONLY pre-installed packages — NO pip install available)"
            elif _net_policy in ("setup_only", "pip_only"):
                pkg_extras = _base_pkgs + ", and additional pip-installable packages via requirements.txt"
            else:
                pkg_extras = _base_pkgs + ", and additional pip-installable packages (auto-detected from imports)"
        else:
            pkg_prefix = "sandbox mode"
            pkg_extras = ""
        if hw_profile and hw_profile.get("has_gpu"):
            gpu_type = hw_profile.get("gpu_type", "cuda")
            gpu_name = hw_profile.get("gpu_name", "GPU")
            tier = hw_profile.get("tier", "limited")
            if tier == "high":
                device_hint = f"torch.device('{gpu_type}')"
                pkg_hint = (
                    f"\nAVAILABLE PACKAGES ({pkg_prefix}): Python stdlib, numpy, torch, sklearn, scipy, pandas{pkg_extras}.\n"
                    f"GPU: {gpu_name} ({gpu_type}). You MAY use PyTorch with GPU acceleration.\n"
                    f"Use `device = {device_hint}` for tensor operations.\n"
                )
            else:  # limited (low VRAM NVIDIA or MPS)
                device_hint = f"torch.device('{gpu_type}')"
                pkg_hint = (
                    f"\nAVAILABLE PACKAGES ({pkg_prefix}): Python stdlib, numpy, torch, sklearn, scipy, pandas{pkg_extras}.\n"
                    f"GPU: {gpu_name} ({gpu_type}) — LIMITED performance.\n"
                    f"Use `device = {device_hint}` but design LIGHTWEIGHT experiments:\n"
                    f"- Small models (<1M parameters)\n"
                    f"- Few epochs (<=20)\n"
                    f"- Small datasets (<=10K samples)\n"
                    f"- Avoid large batch sizes\n"
                )
        else:
            pkg_hint = _pm.block("pkg_hint_sandbox")
    else:
        pkg_hint = ""

    # --- Compute budget hint ---
    time_budget_sec = config.experiment.time_budget_sec
    try:
        compute_budget = _pm.block("compute_budget").replace(
            "{time_budget_sec}", str(time_budget_sec)
        )
    except Exception:  # noqa: BLE001
        compute_budget = (
            f"\n## Compute Budget Constraint\n"
            f"- Total execution time limit: {time_budget_sec} seconds\n"
            f"- Design experiments that complete within this budget\n"
            f"- Checkpoint after every seed/condition; do not stop at 80% of budget\n"
        )

    # --- Dataset guidance + setup script + HP reporting (docker/sandbox modes) ---
    extra_guidance = ""
    _net_policy = getattr(getattr(config, "docker", None), "network_policy", "setup_only")
    if config.experiment.mode in ("sandbox", "docker"):
        _net_policy = (
            config.experiment.docker.network_policy
            if config.experiment.mode == "docker"
            else "none"  # sandbox mode has no network
        )
        if _net_policy == "none":
            # Network disabled: inject strict offline-only guidance
            try:
                extra_guidance += _pm.block("network_disabled_guidance")
            except Exception:  # noqa: BLE001
                pass
        elif _net_policy == "full":
            try:
                extra_guidance += _pm.block("dataset_guidance")
                extra_guidance += _pm.block("network_full_guidance")
            except Exception:  # noqa: BLE001
                pass
        else:
            # setup_only or pip_only — existing behavior
            try:
                extra_guidance += _pm.block("dataset_guidance")
            except Exception:  # noqa: BLE001
                pass
            if config.experiment.mode == "docker":
                try:
                    extra_guidance += _pm.block("setup_script_guidance")
                except Exception:  # noqa: BLE001
                    pass
        try:
            extra_guidance += _pm.block("hp_reporting")
        except Exception:  # noqa: BLE001
            pass
        # I-06: Multi-seed enforcement for all experiments
        try:
            extra_guidance += _pm.block("multi_seed_enforcement")
        except Exception:  # noqa: BLE001
            pass

    # --- BA: Inject BenchmarkAgent plan from Stage 9 ---
    if benchmark_plan_data:
        try:
            # Reconstruct the prompt block
            from researchclaw.agents.benchmark_agent.orchestrator import BenchmarkPlan
            _bp = BenchmarkPlan(
                selected_benchmarks=benchmark_plan_data.get("selected_benchmarks", []),
                selected_baselines=benchmark_plan_data.get("selected_baselines", []),
                data_loader_code=benchmark_plan_data.get("data_loader_code", ""),
                baseline_code=benchmark_plan_data.get("baseline_code", ""),
                experiment_notes=benchmark_plan_data.get("experiment_notes", ""),
            )
            _bp_block = _bp.to_prompt_block()
            if _bp_block:
                extra_guidance += (
                    "\n\n## BenchmarkAgent Selections (USE THESE)\n"
                    "The following datasets, baselines, and code snippets were "
                    "automatically selected and validated by the BenchmarkAgent. "
                    "You MUST use these selections in your experiment code.\n\n"
                    + _bp_block
                )
                logger.info(
                    "BA: Injected benchmark plan (%d benchmarks, %d baselines)",
                    len(_bp.selected_benchmarks), len(_bp.selected_baselines),
                )
        except Exception as _bp_exc:
            logger.debug("BA: Failed to load benchmark plan: %s", _bp_exc)

    # --- P2.2+P2.3: LLM training topic detection and guidance ---
    _llm_keywords = (
        "language model", "llm", "fine-tun", "lora", "qlora", "peft",
        "instruction tun", "rlhf", "dpo", "sft", "alignment",
        "transformer train", "causal lm", "chat model", "qwen", "llama",
        "mistral", "phi-", "gemma", "pretraining", "tokeniz",
    )
    topic_lower = config.research.topic.lower()
    is_llm_topic = any(kw in topic_lower for kw in _llm_keywords)

    # --- I-08: RL topic detection and step guidance ---
    _rl_keywords = (
        "reinforcement learning", "policy gradient", "ppo", "sac", "td3",
        "ddpg", "dqn", "a2c", "a3c", "mujoco", "locomotion", "continuous control",
        "reward shaping", "exploration", "multi-agent rl", "marl", "curriculum rl",
        "imitation learning", "inverse rl", "offline rl", "model-based rl",
        "actor-critic", "reinforce", "gym", "gymnasium",
    )
    is_rl_topic = any(kw in topic_lower for kw in _rl_keywords)
    if is_rl_topic:
        try:
            extra_guidance += _pm.block("rl_step_guidance")
        except Exception:  # noqa: BLE001
            pass

    # --- F-01: Framework API doc injection (auto-detected) ---
    try:
        from researchclaw.data import detect_frameworks, load_framework_docs
        _hypothesis_text = _read_prior_artifact(run_dir, "hypotheses.md") or ""
        _fw_ids = detect_frameworks(
            config.research.topic, _hypothesis_text, exp_plan or ""
        )
        if _fw_ids:
            _fw_docs = load_framework_docs(_fw_ids, max_chars=2500)
            if _fw_docs:
                extra_guidance += _fw_docs
                logger.info("F-01: Injected framework docs for: %s", _fw_ids)
    except Exception:  # noqa: BLE001
        logger.debug("F-01: Framework doc injection skipped", exc_info=True)

    if is_llm_topic and config.experiment.mode == "docker":
        try:
            extra_guidance += _pm.block("llm_training_guidance")
        except Exception:  # noqa: BLE001
            pass
        try:
            extra_guidance += _pm.block("llm_eval_guidance")
        except Exception:  # noqa: BLE001
            pass
        # P2.3: Warn if time budget is too short for LLM training
        if time_budget_sec < 3600:
            extra_guidance += (
                "\n## COMPUTE BUDGET WARNING\n"
                f"Current time_budget_sec={time_budget_sec} is likely TOO SHORT "
                f"for LLM fine-tuning. Typical LoRA training needs 1-4 hours. "
                f"Design a LIGHTWEIGHT experiment:\n"
                f"- Use a small dataset (<=5000 samples)\n"
                f"- Train for 1-3 epochs only\n"
                f"- Use small batch size (1-2) with gradient accumulation\n"
                f"- Use 4-bit quantization (QLoRA) to minimize memory\n"
                f"- Limit max_seq_length to 512-1024\n"
                f"- If possible, use a smaller model (<=7B parameters)\n"
            )

    # --- Domain-specific guidance injection for non-ML domains ---
    try:
        from researchclaw.domains.detector import detect_domain as _dd_s10, is_ml_domain as _is_ml_s10
        _dp = _dd_s10(topic=config.research.topic)
        if not _is_ml_s10(_dp):
            from researchclaw.domains.prompt_adapter import get_adapter as _ga
            _adapter = _ga(_dp)
            _blocks = _adapter.get_code_generation_blocks({})
            if _blocks.compute_budget:
                compute_budget = _blocks.compute_budget
            if _blocks.dataset_guidance:
                extra_guidance = _blocks.dataset_guidance + "\n" + extra_guidance
            if _blocks.code_generation_hints:
                extra_guidance += "\n" + _blocks.code_generation_hints
            if _blocks.output_format_guidance:
                extra_guidance += "\n" + _blocks.output_format_guidance
            logger.info("Injected domain-specific guidance for %s", _dp.domain_id)
    except Exception:  # noqa: BLE001
        logger.debug("Domain guidance injection skipped", exc_info=True)

    # BUG-R6-01: Add explicit implementation constraints to prevent LLM
    # from substituting unrelated DL models for lightweight algorithms.
    extra_guidance += (
        "\n\nIMPLEMENTATION CONSTRAINTS (MUST FOLLOW):\n"
        "- Implement EXACTLY the algorithm/method described in the topic.\n"
        "- Do NOT replace the stated method with a deep-learning proxy "
        "(e.g. ResNet, BERT, GPT, Gymnasium+SB3) unless the topic "
        "EXPLICITLY requires deep learning.\n"
        "- Prefer lightweight CPU-friendly libraries (numpy, scipy, "
        "sklearn, pandas) unless deep learning is inherent to the topic.\n"
        "- The experiment MUST be self-contained and runnable without GPU.\n"
    )
    prompt_instruction_bundle = _compress_instruction_block(
        pkg_hint + "\n" + compute_budget + "\n" + extra_guidance,
        max_chars=5200,
    )

    # --- Code generation: CodeAgent → Legacy single-shot ---
    _code_agent_active = False
    _code_max_tokens = 8192

    if config.experiment.code_agent.enabled and llm is not None:
        # ── F-02: Advanced Code Agent path ────────────────────────────────
        from researchclaw.pipeline.code_agent import CodeAgent as _CodeAgent
        from researchclaw.pipeline.runner import stop_requested as _stop_requested
        from researchclaw.pipeline.stage_impls._execution import (
            _sandbox_wait_notifier,
        )

        _ca_cfg = config.experiment.code_agent
        # Ensure we have a proper config object
        if not hasattr(_ca_cfg, "enabled"):
            from researchclaw.pipeline.code_agent import (
                CodeAgentConfig as _CAConfig,
            )
            _ca_cfg = _CAConfig()

        # Sandbox factory (only for sandbox/docker modes)
        _sandbox_factory = None
        if config.experiment.mode in ("sandbox", "docker"):
            from researchclaw.experiment.factory import (
                create_sandbox as _csb,
            )
            _sandbox_factory = _csb

        if any(
            config.llm.primary_model.startswith(p)
            for p in ("gpt-5", "o3", "o4")
        ):
            _code_max_tokens = 16384

        # ── Domain detection + Code Search for non-ML domains ──────────
        _domain_profile = None
        _code_search_result = None
        try:
            from researchclaw.domains.detector import detect_domain as _dd
            from researchclaw.domains.detector import is_ml_domain as _is_ml
            _domain_profile = _dd(topic=config.research.topic)
            logger.info(
                "CodeAgent: domain=%s (%s)",
                _domain_profile.display_name,
                _domain_profile.domain_id,
            )
            # Run code search for non-ML domains (ML has enough built-in knowledge)
            if not _is_ml(_domain_profile):
                try:
                    from researchclaw.agents.code_searcher import CodeSearchAgent
                    _cs_agent = CodeSearchAgent(llm=llm)
                    _code_search_result = _cs_agent.search(
                        topic=config.research.topic,
                        domain=_domain_profile,
                    )
                    if _code_search_result and _code_search_result.patterns.has_content:
                        logger.info(
                            "Code search: %d patterns, %d repos found",
                            len(_code_search_result.patterns.api_patterns),
                            len(_code_search_result.repos_found),
                        )
                except Exception:  # noqa: BLE001
                    logger.debug("Code search unavailable", exc_info=True)
        except Exception:  # noqa: BLE001
            logger.debug("Domain detection unavailable", exc_info=True)

        _agent = _CodeAgent(
            llm=llm,
            prompts=_pm,
            config=_ca_cfg,
            stage_dir=stage_dir,
            sandbox_factory=_sandbox_factory,
            experiment_config=config.experiment,
            domain_profile=_domain_profile,
            code_search_result=_code_search_result,
            sandbox_notify_callback=_sandbox_wait_notifier(
                run_dir=run_dir,
                adapters=adapters,
                config=config,
                run_id=run_dir.name,
                stage=Stage.CODE_GENERATION,
            ),
            sandbox_stop_requested=lambda: _stop_requested(run_dir),
        )
        _agent_result = _agent.generate(
            topic=config.research.topic,
            exp_plan=compact_exp_plan or exp_plan,
            metric=metric,
            pkg_hint=prompt_instruction_bundle,
            max_tokens=_code_max_tokens,
        )
        files = _agent_result.files
        _code_agent_active = True

        # Write agent artifacts
        (stage_dir / "code_agent_log.json").write_text(
            json.dumps(
                {
                    "log": _agent_result.validation_log,
                    "llm_calls": _agent_result.total_llm_calls,
                    "sandbox_runs": _agent_result.total_sandbox_runs,
                    "best_score": _agent_result.best_score,
                    "tree_nodes_explored": _agent_result.tree_nodes_explored,
                    "review_rounds": _agent_result.review_rounds,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        if _agent_result.architecture_spec:
            (stage_dir / "architecture_spec.yaml").write_text(
                _agent_result.architecture_spec, encoding="utf-8",
            )
        logger.info(
            "CodeAgent: %d LLM calls, %d sandbox runs, score=%.2f",
            _agent_result.total_llm_calls,
            _agent_result.total_sandbox_runs,
            _agent_result.best_score,
        )
    elif not _beast_mode_used and llm is not None:
        # ── Legacy single-shot generation ─────────────────────────────────
        topic = config.research.topic
        _md = config.experiment.metric_direction
        _md_hint = (
            f"`{_md}` — use direction={'lower' if _md == 'minimize' else 'higher'} "
            f"in METRIC_DEF. You MUST NOT use the opposite direction."
        )
        _overlay = _get_evolution_overlay(run_dir, "code_generation")
        sp = _pm.for_stage(
            "code_generation",
            evolution_overlay=_overlay,
            topic=topic,
            metric=metric,
            pkg_hint=prompt_instruction_bundle,
            exp_plan=compact_exp_plan or exp_plan,
            metric_direction_hint=_md_hint,
        )
        # R13-3: Use higher max_tokens for reasoning models (they consume tokens
        # for internal chain-of-thought). Retry once with even higher limit on empty.
        _code_max_tokens = sp.max_tokens or 8192
        if any(config.llm.primary_model.startswith(p) for p in ("gpt-5", "o3", "o4")):
            _code_max_tokens = max(_code_max_tokens, 16384)

        resp = _chat_with_prompt(
            llm,
            sp.system,
            sp.user,
            json_mode=sp.json_mode,
            max_tokens=_code_max_tokens,
        )
        files = _extract_multi_file_blocks(resp.content)
        if not files and not resp.content.strip():
            # Empty response — retry with higher token limit
            logger.warning(
                "R13-3: Empty LLM response for code_generation (len=%d, "
                "finish_reason=%s, tokens=%d). Retrying with 32768 tokens.",
                len(resp.content),
                resp.finish_reason,
                resp.total_tokens,
            )
            resp = _chat_with_prompt(
                llm,
                sp.system,
                sp.user,
                json_mode=sp.json_mode,
                max_tokens=32768,
            )
            files = _extract_multi_file_blocks(resp.content)
        if not files:
            logger.warning(
                "R13-2: _extract_multi_file_blocks returned empty. "
                "LLM response length=%d, first 300 chars: %s",
                len(resp.content),
                resp.content[:300],
            )

    # --- Fallback: generic numerical experiment ---
    if not files:
        files = {
            "main.py": (
                "import numpy as np\n"
                "\n"
                "np.random.seed(42)\n"
                "\n"
                "# Fallback experiment: parameter sweep on a synthetic objective\n"
                "# This runs when LLM code generation fails to produce valid code.\n"
                "dim = 10\n"
                "n_conditions = 3\n"
                "results = {}\n"
                "\n"
                "for cond_idx in range(n_conditions):\n"
                "    cond_name = f'condition_{cond_idx}'\n"
                "    scores = []\n"
                "    for seed in range(3):\n"
                "        rng = np.random.RandomState(seed + cond_idx * 100)\n"
                "        x = rng.randn(dim)\n"
                "        score = float(1.0 / (1.0 + np.sum(x ** 2)))\n"
                "        scores.append(score)\n"
                "    mean_score = float(np.mean(scores))\n"
                "    results[cond_name] = mean_score\n"
                f"    print(f'condition={{cond_name}} {metric}: {{mean_score:.6f}}')\n"
                "\n"
                "best = max(results, key=results.get)\n"
                f"print(f'{metric}: {{results[best]:.6f}}')\n"
            )
        }

    # --- Validate each file + auto-repair loop ---
    all_valid = True
    attempt = 0
    for fname, code in list(files.items()):
        # Skip non-Python files (requirements.txt, setup.py, etc.)
        if not fname.endswith(".py"):
            continue
        validation = validate_code(code)
        repair_attempt = 0
        while not validation.ok and llm is not None and repair_attempt < max_repair:
            repair_attempt += 1
            attempt += 1
            # Only send errors to the LLM — warnings don't block validation
            # and confuse the LLM into over-correcting (e.g. removing runtime imports)
            errors_only = type(validation)(
                issues=[i for i in validation.issues if i.severity == "error"]
            )
            issues_text = format_issues_for_llm(errors_only)
            validation_log.append(
                f"File {fname} attempt {repair_attempt}: {validation.summary()}"
            )
            logger.info(
                "Code validation failed for %s (attempt %d/%d): %s",
                fname,
                repair_attempt,
                max_repair,
                validation.summary(),
            )
            all_files_ctx = _compact_project_context_for_repair(
                files,
                focus_file=fname,
            )
            rp = _pm.sub_prompt(
                "code_repair",
                fname=fname,
                issues_text=issues_text,
                all_files_ctx=all_files_ctx,
            )
            resp = _chat_with_prompt(llm, rp.system, rp.user)
            _repaired = _extract_code_block(resp.content)
            upstream_error = detect_non_code_response(_repaired)
            if _repaired.strip() and not upstream_error:
                files[fname] = _repaired
            elif upstream_error:
                logger.warning(
                    "Repair attempt for %s returned non-code text; keeping prior file: %s",
                    fname,
                    upstream_error,
                )
                validation_log.append(
                    f"File {fname} attempt {repair_attempt}: upstream non-code response ignored"
                )
            else:
                logger.warning("Repair attempt returned empty code, keeping original")
            validation = validate_code(files[fname])
        if not validation.ok:
            all_valid = False
            # BUG-14: Log remaining issues prominently
            logger.warning(
                "Code validation FAILED for %s after %d repair attempts: %s",
                fname, max_repair, validation.summary(),
            )

    # Improvement G: RL algorithm-environment compatibility check
    for fname, code in list(files.items()):
        if not fname.endswith(".py"):
            continue
        _rl_errors = _check_rl_compatibility(code)
        if _rl_errors:
            for _rl_err in _rl_errors:
                logger.error("Stage 10: %s (in %s)", _rl_err, fname)
                validation_log.append(f"RL_COMPAT: {fname}: {_rl_err}")
            all_valid = False

    # BUG-14: Block on critical validation failures (syntax/import errors)
    if not all_valid:
        _has_critical = False
        for fname, code in files.items():
            _v = validate_code(code)
            if not _v.ok:
                for issue in _v.issues:
                    if issue.severity == "error" and issue.category in (
                        "syntax", "import",
                    ):
                        _has_critical = True
        if _has_critical:
            logger.error(
                "Stage 10: CRITICAL validation issues remain after %d repair "
                "attempts. Blocking stage.", max_repair,
            )
            (stage_dir / "validation_report.md").write_text(
                "# Code Validation Report\n\n"
                f"**Status**: BLOCKED — critical issues remain after {max_repair} repairs\n\n"
                + "\n".join(f"- {e}" for e in validation_log),
                encoding="utf-8",
            )
            return StageResult(
                stage=Stage.CODE_GENERATION,
                status=StageStatus.FAILED,
                artifacts=("validation_report.md",),
                evidence_refs=(),
            )

    # --- BUG-184: Cross-import validation — warn if a .py file imports a
    # local module that doesn't exist in the files dict.  This catches the
    # case where Beast Mode/CodeAgent produced an intermediate file that
    # got lost during repair iterations.
    _known_modules = {
        f.replace(".py", "") for f in files if f.endswith(".py")
    }
    _stdlib_and_common = {
        "os", "sys", "json", "math", "time", "copy", "re", "random", "hashlib", "importlib",
        "pathlib", "argparse", "logging", "collections", "functools",
        "itertools", "abc", "typing", "dataclasses", "enum", "io",
        "csv", "pickle", "glob", "shutil", "subprocess", "datetime",
        "numpy", "np", "torch", "torchvision", "gymnasium", "gym",
        "sklearn", "scipy", "pandas", "matplotlib", "PIL", "tqdm",
        "einops", "timm", "transformers", "datasets", "peft",
        "stable_baselines3",
    }
    for fname, code in list(files.items()):
        if not fname.endswith(".py"):
            continue
        for _m in re.findall(
            r"^(?:from|import)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
            code, re.MULTILINE,
        ):
            if (_m not in _known_modules
                    and _m not in _stdlib_and_common
                    and not _m.startswith("_")):
                logger.warning(
                    "BUG-184: %s imports '%s' which is not in generated "
                    "files — experiment may crash on import",
                    fname, _m,
                )

    # --- Write experiment directory ---
    exp_dir = stage_dir / "experiment"
    _sync_experiment_dir(exp_dir, files)

    # --- Write validation report ---
    if validation_log or not all_valid:
        report_lines = ["# Code Validation Report\n"]
        if all_valid:
            report_lines.append(f"**Status**: PASSED after {attempt} total repair(s)\n")
        else:
            report_lines.append(
                f"**Status**: FAILED after {attempt} total repair attempt(s)\n"
            )
        for entry in validation_log:
            report_lines.append(f"- {entry}")
        (stage_dir / "validation_report.md").write_text(
            "\n".join(report_lines), encoding="utf-8"
        )

    # --- R10-Fix6: Code complexity and quality check ---
    from researchclaw.experiment.validator import (
        auto_fix_unbound_locals,
        check_code_complexity,
        deep_validate_files,
    )

    # --- BUG-3 fix: Programmatic auto-fix for UnboundLocalError patterns ---
    _total_ub_fixes = 0
    for fname, code in list(files.items()):
        if fname.endswith(".py"):
            fixed_code, n_fixes = auto_fix_unbound_locals(code)
            if n_fixes > 0:
                files[fname] = fixed_code
                _sync_experiment_dir(exp_dir, files)
                _total_ub_fixes += n_fixes
                logger.info(
                    "Stage 10: auto-fixed %d UnboundLocalError risk(s) in %s",
                    n_fixes, fname,
                )
    if _total_ub_fixes:
        logger.info(
            "Stage 10: auto-fixed %d total UnboundLocalError risks", _total_ub_fixes
        )

    complexity_warnings: list[str] = []
    for fname, code in files.items():
        if fname.endswith(".py"):
            cw = check_code_complexity(code)
            for w in cw:
                complexity_warnings.append(f"[{fname}] {w}")
                logger.warning("Stage 10 code quality: [%s] %s", fname, w)

    # --- P1.1+P1.2: Deep quality analysis (class quality, scoping, API) ---
    deep_warnings = deep_validate_files(files)
    for w in deep_warnings:
        logger.warning("Stage 10 deep quality: %s", w)
    complexity_warnings.extend(deep_warnings)

    # --- P1.2: If critical deep issues found, attempt one repair cycle ---
    critical_deep = [w for w in deep_warnings if any(
        kw in w for kw in ("UnboundLocalError", "unregistered", "does not exist",
                           "empty or trivial subclass", "does NOT override",
                           "Import-usage mismatch", "NameError",
                           "was removed", "ptp()",
                           "copy-paste", "identical method signatures",
                           "identical AST", "NOT a real ablation",
                           "shadows stdlib/pip")
    )]
    if critical_deep and llm is not None:
        logger.info(
            "Stage 10: %d critical code issues found — triggering repair cycle",
            len(critical_deep),
        )
        before_auto_repairable = _auto_repairable_issue_set(critical_deep)
        repairable_issues = [
            issue for issue in critical_deep
            if _is_auto_repairable_deep_issue(issue)
        ]
        deferred_issues = [
            issue for issue in critical_deep
            if not _is_auto_repairable_deep_issue(issue)
        ]
        if deferred_issues:
            for issue in deferred_issues:
                logger.warning(
                    "Stage 10: deferred high-cost deep issue (manual/structural): %s",
                    issue,
                )
            complexity_warnings.append(
                "[REPAIR] Deferred high-cost deep issues: "
                + "; ".join(deferred_issues[:3])
            )

        issues_by_file = _group_deep_issues_by_file(files, repairable_issues)
        repaired_any = False
        fixed_total = 0
        try:
            for focus_file, file_issues in sorted(issues_by_file.items()):
                if focus_file not in files:
                    continue
                prior_code = files[focus_file]
                before_file_issues = _file_issue_set(files, focus_file)
                repair_prompt = (
                    "CRITICAL CODE QUALITY ISSUES FOUND FOR ONE FILE.\n\n"
                    f"## Target file\n{focus_file}\n\n"
                    "## Issues\n"
                    + "\n".join(f"- {w}" for w in file_issues)
                    + "\n\n## Rules\n"
                    "- Fix only the target file.\n"
                    "- Preserve public names and imports used by other files.\n"
                    "- nn.Linear/nn.Conv must be created in __init__(), not forward().\n"
                    "- Variables used after if/else must be defined before the branch.\n"
                    "- Use scipy.special.erf, not np.erf.\n"
                    "- Ablation/variant classes must have genuinely different logic.\n"
                    "- If two condition classes are copy-paste variants, rewrite the "
                    "target condition logic so outputs differ on the same input for a "
                    "meaningful algorithmic reason.\n"
                    "- Modify only the relevant classes/functions or the smallest "
                    "necessary code block in the target file.\n"
                    "- Preserve all unrelated code byte-for-byte where possible.\n"
                    "- Output ONLY the corrected target file in "
                    f"```filename:{focus_file}``` format.\n\n"
                    "## Project context\n"
                    + _build_symbol_repair_context(
                        files,
                        focus_file=focus_file,
                        issues=file_issues,
                    )
                )
                repair_resp = _chat_with_prompt(
                    llm,
                    _pm.system("code_generation"),
                    repair_prompt,
                    max_tokens=min(_code_max_tokens, 12288),
                )
                repaired = _extract_multi_file_blocks(repair_resp.content)
                if focus_file not in repaired:
                    single = _extract_single_named_file(repair_resp.content, focus_file)
                    if single:
                        repaired = {focus_file: single}
                if focus_file not in repaired:
                    logger.warning(
                        "Stage 10: deep repair produced no extractable %s",
                        focus_file,
                    )
                    continue
                candidate_files = dict(files)
                candidate_files[focus_file] = repaired[focus_file]
                candidate_validation = validate_code(candidate_files[focus_file])
                if not candidate_validation.ok:
                    logger.warning(
                        "Stage 10: rejected deep repair for %s due to validation failure: %s",
                        focus_file,
                        candidate_validation.summary(),
                    )
                    continue
                after_file_issues = _file_issue_set(candidate_files, focus_file)
                if len(after_file_issues) >= len(before_file_issues):
                    logger.warning(
                        "Stage 10: rejected deep repair for %s because issues did not improve "
                        "(before=%d, after=%d)",
                        focus_file,
                        len(before_file_issues),
                        len(after_file_issues),
                    )
                    continue
                files[focus_file] = repaired[focus_file]
                _sync_experiment_dir(exp_dir, files)
                repaired_any = repaired_any or files[focus_file] != prior_code

            if repaired_any:
                deep_warnings_after = deep_validate_files(files)
                after_auto_repairable = _auto_repairable_issue_set(deep_warnings_after)
                fixed_total = len(before_auto_repairable - after_auto_repairable)
                logger.info(
                    "Stage 10: Deep repair fixed %d/%d auto-repairable critical issues",
                    fixed_total, len(repairable_issues),
                )
                complexity_warnings.append(
                    f"[REPAIR] Deep repair fixed {fixed_total}/{len(repairable_issues)} "
                    "auto-repairable critical issues"
                )
        except Exception as exc:
            logger.debug("Deep repair failed: %s", exc)

    if complexity_warnings:
        health: dict[str, Any] = {}
        health["code_complexity_warnings"] = complexity_warnings
        (stage_dir / "code_complexity.json").write_text(
            json.dumps(health, indent=2), encoding="utf-8"
        )

    # --- P1.4: LLM Code Review (Stage 10.5) ---
    # Skip when CodeAgent is active — Phase 4 review already covers this.
    if llm is not None and not _code_agent_active:
        all_code_review = "\n\n".join(
            f"# --- {fname} ---\n{code}" for fname, code in files.items()
        )
        if len(all_code_review) > 12000:
            all_code_review = all_code_review[:12000] + "\n... [truncated]"
        review_prompt = (
            f"You are a senior researcher reviewing experiment code for a "
            f"research submission.\n\n"
            f"TOPIC: {config.research.topic}\n"
            f"EXPERIMENT PLAN:\n{(compact_exp_plan or exp_plan)[:4500]}\n\n"
            f"CODE:\n```python\n{all_code_review}\n```\n\n"
            f"Review the code and return JSON with this EXACT structure:\n"
            f'{{"score": <1-10>, "issues": ['
            f'{{"severity": "critical|major|minor", '
            f'"description": "...", "fix": "..."}}], '
            f'"verdict": "pass|needs_fix"}}\n\n'
            f"Check specifically:\n"
            f"1. Does each algorithm/method have a DISTINCT implementation? "
            f"(Not just renamed copies)\n"
            f"2. Are ablation conditions genuinely different from the main method?\n"
            f"3. Are loss functions / training loops mathematically correct?\n"
            f"4. Will the code actually run without errors? Check variable scoping, "
            f"API usage, tensor shape compatibility.\n"
            f"5. Is the code complex enough for a research paper? (Not trivial)\n"
            f"6. Are experimental conditions fairly compared (same seeds, data)?\n"
            f"7. If using pretrained models (EfficientNet, ResNet, ViT), are input "
            f"images resized to the model's expected size (e.g., 224x224)? CIFAR "
            f"images are 32x32 and MUST be resized for pretrained models.\n"
            f"8. Are imports consistent? `from X import Y` must use `Y()`, not `X.Y()`.\n"
        )
        try:
            review_resp = llm.chat(
                [{"role": "user", "content": review_prompt}],
                system="You are a meticulous ML code reviewer. Be strict.",
                max_tokens=2048,
            )
            # Extract JSON from LLM response (may be wrapped in markdown fences)
            _review_text = review_resp.content if hasattr(review_resp, "content") else str(review_resp)
            # Strip markdown JSON fences if present
            _review_text = _review_text.strip()
            if _review_text.startswith("```"):
                _lines = _review_text.splitlines()
                _start = 1 if _lines[0].strip().startswith("```") else 0
                _end = len(_lines) - 1 if _lines[-1].strip() == "```" else len(_lines)
                _review_text = "\n".join(_lines[_start:_end])
            review_data = _safe_json_loads(_review_text, {})
            if isinstance(review_data, dict):
                review_score = review_data.get("score", 0)
                review_verdict = review_data.get("verdict", "unknown")
                review_issues = review_data.get("issues", [])

                # Write review report
                review_report = {
                    "score": review_score,
                    "verdict": review_verdict,
                    "issues": review_issues,
                    "timestamp": _utcnow_iso(),
                }
                (stage_dir / "code_review.json").write_text(
                    json.dumps(review_report, indent=2), encoding="utf-8"
                )

                # If critical issues found and score low, attempt fix
                critical_issues = [
                    i for i in review_issues
                    if isinstance(i, dict)
                    and i.get("severity") == "critical"
                ]
                if critical_issues and review_score <= 4:
                    logger.warning(
                        "Stage 10 code review: score=%d, %d critical issues — "
                        "attempting fix",
                        review_score, len(critical_issues),
                    )
                    fix_descriptions = "\n".join(
                        f"- [{i.get('severity', '?')}] {i.get('description', '?')}: "
                        f"{i.get('fix', 'no fix suggested')}"
                        for i in critical_issues
                    )
                    fix_prompt = (
                        f"Code review found {len(critical_issues)} CRITICAL issues "
                        f"(score: {review_score}/10):\n{fix_descriptions}\n\n"
                        f"Fix ALL critical issues. Return complete corrected files "
                        f"using ```filename:xxx.py format.\n\n"
                        f"Current code:\n"
                        + "\n\n".join(
                            f"```filename:{f}\n{c}\n```" for f, c in files.items()
                        )
                    )
                    try:
                        fix_resp = _chat_with_prompt(
                            llm,
                            _pm.system("code_generation"),
                            fix_prompt,
                            max_tokens=_code_max_tokens,
                        )
                        fixed_files = _extract_multi_file_blocks(fix_resp.content)
                        if fixed_files and "main.py" in fixed_files:
                            files = fixed_files
                            _sync_experiment_dir(exp_dir, files)
                            logger.info(
                                "Stage 10: Code fixed after review "
                                "(was %d/10, %d critical issues)",
                                review_score, len(critical_issues),
                            )
                    except Exception as exc:
                        logger.debug("Review-fix failed: %s", exc)
        except Exception as exc:
            logger.debug("Code review failed: %s", exc)

    # --- FIX-3: Topic-experiment alignment check ---
    # BUG-171: Previous 8000-char truncation caused false-positive misalignment
    # for multi-file experiments (30-90K chars). LLM saw "[truncated]" and
    # concluded code was incomplete. Fix: build a structured summary that
    # includes file inventory + full main.py + per-file function/class headers.
    alignment_ok = True
    alignment_note = ""
    if llm is not None:
        # Build structured code summary for alignment check
        _file_inventory = []
        for _fn, _cd in files.items():
            _lines = _cd.count("\n") + 1
            _file_inventory.append(f"  {_fn}: {_lines} lines, {len(_cd)} chars")
        _inventory_block = "FILES GENERATED:\n" + "\n".join(_file_inventory)

        # BUG-179: Beast Mode may use a different entry point (e.g.
        # run_experiment.py).  Detect the actual entry point by scanning
        # for ``if __name__ == "__main__"`` in all files, preferring main.py.
        _entry_file = "main.py"
        if "main.py" not in files or not files.get("main.py", "").strip():
            for _fn, _cd in files.items():
                if 'if __name__' in _cd and '__main__' in _cd:
                    _entry_file = _fn
                    break
        elif files.get("main.py", ""):
            # main.py exists but may be a stub — if another file has the
            # real orchestration (more lines + __main__ guard), prefer it
            _main_lines = files["main.py"].count("\n")
            for _fn, _cd in files.items():
                if _fn == "main.py":
                    continue
                if ('if __name__' in _cd and '__main__' in _cd
                        and _cd.count("\n") > _main_lines * 1.5):
                    _entry_file = _fn
                    break

        _main_code = files.get(_entry_file, files.get("main.py", ""))
        _main_block = f"# --- {_entry_file} (FULL — entry point) ---\n{_main_code}"
        # Cap main.py at 12000 chars to stay within token budget
        if len(_main_block) > 12000:
            _main_block = _main_block[:12000] + "\n... [main.py truncated at 12000 chars]"

        # For other files, include imports + function/class signatures
        _other_summaries = []
        for _fn, _cd in files.items():
            if _fn == _entry_file:
                continue
            _sig_lines = []
            for _line in _cd.split("\n"):
                _stripped = _line.strip()
                if (_stripped.startswith("def ") or _stripped.startswith("class ")
                        or _stripped.startswith("async def ")
                        # BUG-209: Include import lines — they reveal which
                        # techniques/libraries are used (e.g. CosineAnnealingLR)
                        or _stripped.startswith("import ")
                        or _stripped.startswith("from ")):
                    _sig_lines.append(_line)
            if _sig_lines:
                _other_summaries.append(
                    f"# --- {_fn} (imports + signatures) ---\n"
                    + "\n".join(_sig_lines)
                )
            else:
                # Small file — include first 800 chars
                _preview = _cd[:800]
                if len(_cd) > 800:
                    _preview += f"\n... [{len(_cd) - 800} more chars]"
                _other_summaries.append(f"# --- {_fn} (preview) ---\n{_preview}")
        _other_block = "\n\n".join(_other_summaries)
        # Cap other summaries
        if len(_other_block) > 6000:
            _other_block = _other_block[:6000] + "\n... [other files truncated]"

        all_code_for_check = (
            f"{_inventory_block}\n\n{_main_block}\n\n{_other_block}"
        )
        align_prompt = (
            f"Research topic: {config.research.topic}\n\n"
            f"Experiment code:\n```python\n{all_code_for_check}\n```\n\n"
            "TASK: Evaluate whether this experiment code actually tests the "
            "stated research topic. Answer with JSON:\n"
            '{"aligned": true/false, "reason": "...", "suggestions": "..."}\n\n'
            "IMPORTANT: The code spans MULTIPLE files. The file inventory above "
            "shows ALL generated files. Only main.py is shown in full; other "
            "files show function/class signatures. Do NOT mark as misaligned "
            "just because helper files are summarized — they contain full "
            "implementations.\n\n"
            "Check specifically:\n"
            "- Does main.py orchestrate an experiment matching the topic?\n"
            "- Do the helper file signatures indicate relevant models/methods?\n"
            "- If the topic mentions a specific technique, is there evidence of "
            "its implementation (function names, class names, imports)?\n"
            "- Are the experimental conditions meaningfully different from each other?\n"
        )
        try:
            align_resp = llm.chat(
                [{"role": "user", "content": align_prompt}],
                system="You are a scientific code reviewer checking topic-experiment alignment.",
                max_tokens=1024,
            )
            align_data = _safe_json_loads(align_resp.content, {})
            if isinstance(align_data, dict) and not align_data.get("aligned", True):
                alignment_ok = False
                alignment_note = align_data.get("reason", "Misaligned")
                suggestions = align_data.get("suggestions", "")
                logger.warning(
                    "Stage 10: Topic-experiment MISALIGNMENT detected: %s",
                    alignment_note,
                )
                # BUG-R6-01: Allow up to 2 regeneration attempts with re-check.
                _max_regen = 2
                for _regen_attempt in range(1, _max_regen + 1):
                    logger.info(
                        "Stage 10: Alignment regen attempt %d/%d",
                        _regen_attempt, _max_regen,
                    )
                    regen_prompt = (
                        f"The experiment code you previously generated does NOT align "
                        f"with the research topic.\n\n"
                        f"TOPIC: {config.research.topic}\n"
                        f"MISALIGNMENT: {alignment_note}\n"
                        f"SUGGESTIONS: {suggestions}\n\n"
                        f"REGENERATE the experiment code to DIRECTLY test the stated "
                        f"topic. The code MUST implement the core technique described "
                        f"in the topic, not a generic proxy.\n\n"
                        f"CRITICAL CONSTRAINTS:\n"
                        f"- You MUST implement the EXACT algorithm/method from the topic.\n"
                        f"- Do NOT substitute a deep-learning proxy (ResNet, BERT, etc.) "
                        f"when the topic describes a tabular, bandit, or game-theoretic method.\n"
                        f"- Use ONLY lightweight CPU-friendly libraries (numpy, scipy, "
                        f"sklearn) unless the topic EXPLICITLY requires deep learning.\n"
                        f"- The experiment must be self-contained and runnable without GPU.\n\n"
                        f"{prompt_instruction_bundle}\n"
                        f"PLAN:\n{compact_exp_plan or exp_plan}\n\n"
                        f"Return multiple files using ```filename:xxx.py format."
                    )
                    regen_resp = _chat_with_prompt(
                        llm,
                        system=_pm.system("code_generation"),
                        user=regen_prompt,
                        max_tokens=_code_max_tokens,
                    )
                    regen_files = _extract_multi_file_blocks(regen_resp.content)
                    if not regen_files or "main.py" not in regen_files:
                        logger.warning(
                            "Stage 10: Regen attempt %d produced no main.py",
                            _regen_attempt,
                        )
                        continue
                    _previous_files = dict(files)
                    regen_files = _maybe_add_setup_file(
                        regen_files,
                        benchmark_plan_data,
                        config,
                        previous_files=_previous_files,
                    )
                    regen_files = _maybe_add_requirements_file(
                        regen_files,
                        benchmark_plan_data,
                        config,
                    )
                    files = regen_files
                    _sync_experiment_dir(exp_dir, files)
                    # Re-check alignment on regenerated code (BUG-171 fix)
                    _rc_inv = []
                    for _fn, _cd in files.items():
                        _rc_inv.append(f"  {_fn}: {_cd.count(chr(10))+1} lines")
                    _rc_main = files.get("main.py", "")
                    if len(_rc_main) > 12000:
                        _rc_main = _rc_main[:12000] + "\n... [truncated]"
                    _rc_sigs = []
                    for _fn, _cd in files.items():
                        if _fn == "main.py":
                            continue
                        # BUG-209: Include imports alongside signatures
                        _slines = [l for l in _cd.split("\n")
                                   if l.strip().startswith((
                                       "def ", "class ", "async def ",
                                       "import ", "from ",
                                   ))]
                        if _slines:
                            _rc_sigs.append(f"# {_fn} imports+signatures:\n" + "\n".join(_slines))
                    recheck_code = (
                        "FILES:\n" + "\n".join(_rc_inv) + "\n\n"
                        f"# main.py (FULL):\n{_rc_main}\n\n"
                        + "\n".join(_rc_sigs)
                    )
                    recheck_resp = llm.chat(
                        [{"role": "user", "content": (
                            f"Research topic: {config.research.topic}\n\n"
                            f"Experiment code:\n```python\n{recheck_code}\n```\n\n"
                            "TASK: Evaluate whether this experiment code actually tests "
                            "the stated research topic. Only main.py is shown in full; "
                            "other files show signatures only. Answer with JSON:\n"
                            '{"aligned": true/false, "reason": "...", "suggestions": "..."}\n'
                        )}],
                        system="You are a scientific code reviewer checking topic-experiment alignment.",
                        max_tokens=1024,
                    )
                    recheck_data = _safe_json_loads(recheck_resp.content, {})
                    if isinstance(recheck_data, dict) and recheck_data.get("aligned", False):
                        alignment_ok = True
                        alignment_note = f"Regenerated after alignment check (attempt {_regen_attempt})"
                        logger.info(
                            "Stage 10: Code aligned after regen attempt %d",
                            _regen_attempt,
                        )
                        break
                    else:
                        alignment_note = recheck_data.get("reason", alignment_note)
                        suggestions = recheck_data.get("suggestions", suggestions)
                        logger.warning(
                            "Stage 10: Regen attempt %d still misaligned: %s",
                            _regen_attempt, alignment_note,
                        )
        except Exception as exc:
            logger.debug("Alignment check failed: %s", exc)

    # --- FIX-7: Ablation distinctness check ---
    main_code = files.get("main.py", "")
    if llm is not None and main_code and "condition" in main_code.lower():
        try:
            ablation_prompt = (
                f"Examine this experiment code:\n```python\n{main_code[:6000]}\n```\n\n"
                "Check if any experimental conditions (methods/ablations) have "
                "IDENTICAL configurations (same hyperparameters, same code paths). "
                "Answer JSON: "
                '{"has_duplicates": true/false, "details": "which conditions are identical"}'
            )
            abl_resp = llm.chat(
                [{"role": "user", "content": ablation_prompt}],
                system="You are a code reviewer checking experimental conditions.",
                max_tokens=512,
            )
            abl_data = _safe_json_loads(abl_resp.content, {})
            if isinstance(abl_data, dict) and abl_data.get("has_duplicates"):
                logger.warning(
                    "Stage 10: Duplicate ablation conditions detected: %s",
                    abl_data.get("details", ""),
                )
                (stage_dir / "ablation_warning.json").write_text(
                    json.dumps(abl_data, indent=2), encoding="utf-8"
                )
                # --- Attempt ablation repair ---
                focus_file = _infer_issue_file_from_symbols(files, str(dup_details)) or (
                    "methods.py" if "methods.py" in files else "main.py"
                )
                dup_details = abl_data.get("details", "unknown")
                abl_repair_prompt = (
                    f"ABLATION REPAIR REQUIRED — duplicate conditions detected:\n"
                    f"{dup_details}\n\n"
                    f"Rewrite the ablation/variant conditions so each one is "
                    f"GENUINELY DIFFERENT. Concrete strategies:\n"
                    f"- 'no_<component>': REMOVE the component entirely "
                    f"(e.g., replace attention with mean pooling, remove a loss term)\n"
                    f"- 'reduced_capacity': HALVE hidden dimensions or layers\n"
                    f"- Different conditions MUST produce different outputs on the "
                    f"same input. Add a startup assertion that runs one forward pass "
                    f"per condition on identical input and prints:\n"
                    f"  ABLATION_CHECK: <cond1> vs <cond2> outputs_differ=True\n\n"
                    f"Fix only the target file `{focus_file}` unless another file "
                    f"is strictly required for import compatibility.\n"
                    f"Output the corrected `{focus_file}` using "
                    f"```filename:{focus_file}``` format.\n\n"
                    "Current code:\n"
                    f"{_compact_project_context_for_repair(files, focus_file=focus_file)}\n"
                )
                try:
                    abl_repair_resp = _chat_with_prompt(
                        llm,
                        _pm.system("code_generation"),
                        abl_repair_prompt,
                        max_tokens=_code_max_tokens,
                    )
                    repaired_files = _extract_multi_file_blocks(abl_repair_resp.content)
                    if focus_file not in repaired_files:
                        single = _extract_single_named_file(abl_repair_resp.content, focus_file)
                        if single:
                            repaired_files = {focus_file: single}
                    if repaired_files and focus_file in repaired_files:
                        files[focus_file] = repaired_files[focus_file]
                        _sync_experiment_dir(exp_dir, files)
                        logger.info(
                            "Stage 10: Ablation repair applied — "
                            "rewrote duplicate conditions in %s",
                            focus_file,
                        )
                except Exception as exc:
                    logger.debug("Ablation repair failed: %s", exc)
        except Exception as exc:
            logger.debug("Ablation validation skipped: %s", exc)

    # --- Final project validation + final sync ---
    files = _maybe_add_setup_file(
        files,
        benchmark_plan_data,
        config,
    )
    files = _maybe_add_requirements_file(files, benchmark_plan_data, config)
    _sync_experiment_dir(exp_dir, files)
    final_project_errors = _collect_final_project_errors(
        files,
        benchmark_plan=benchmark_plan_data,
        config=config,
    )
    if final_project_errors:
        logger.error(
            "Stage 10: final project snapshot is invalid: %s",
            "; ".join(final_project_errors),
        )
        report_path = stage_dir / "validation_report.md"
        report_body = [
            "# Code Validation Report",
            "",
            "**Status**: BLOCKED — final project snapshot is invalid",
            "",
        ]
        report_body.extend(f"- {item}" for item in final_project_errors)
        report_path.write_text("\n".join(report_body), encoding="utf-8")
        return StageResult(
            stage=Stage.CODE_GENERATION,
            status=StageStatus.FAILED,
            artifacts=("experiment/", "validation_report.md"),
            evidence_refs=("stage-10/experiment/", "stage-10/validation_report.md"),
            error="Final generated project is not executable.",
        )

    # --- Write spec ---
    file_list = ", ".join(f"`{f}`" for f in sorted(files.keys()))
    main_validation = validate_code(files.get("main.py", ""))
    _align_status = "ALIGNED" if alignment_ok else f"MISALIGNED: {alignment_note}"
    spec = f"""# Experiment Specification

## Topic
{config.research.topic}

## Project Structure
Multi-file experiment project with {len(files)} file(s): {file_list}

## Entry Point
`main.py` \u2014 executed directly via sandbox

## Outputs
- `main.py` emits metric lines in `name: value` format
- Primary metric key: `{metric}`

## Topic-Experiment Alignment
{_align_status}

## Constraints
- Time budget per run: {config.experiment.time_budget_sec}s
- Max iterations: {config.experiment.max_iterations}
- Self-contained execution (no external data, no network)
- Validated: {main_validation.summary()}

## Generated
{_utcnow_iso()}
"""
    (stage_dir / "experiment_spec.md").write_text(spec, encoding="utf-8")

    file_manifest = []
    for fname, content in sorted(files.items()):
        file_manifest.append(
            {
                "path": fname,
                "size_bytes": len(content.encode("utf-8")),
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            }
        )
    experiment_contract = {
        "schema_version": 1,
        "generated": _utcnow_iso(),
        "topic": config.research.topic,
        "entry_point": "main.py",
        "primary_metric": metric,
        "metric_direction": config.experiment.metric_direction,
        "time_budget_sec": config.experiment.time_budget_sec,
        "execution_mode": config.experiment.mode,
        "network_policy": (
            config.experiment.docker.network_policy
            if config.experiment.mode == "docker"
            else "none"
        ),
        "requires_setup_phase": "setup.py" in files,
        "requires_requirements_phase": "requirements.txt" in files,
        "output_files": ["results.json"],
        "supported_gpu_policy": "up_to_two_idle_gpus",
        "file_manifest": file_manifest,
    }
    (stage_dir / "experiment_contract.json").write_text(
        json.dumps(experiment_contract, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (stage_dir / "experiment_contract.meta.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact": "experiment_contract.json",
                "sha256": hashlib.sha256(
                    json.dumps(experiment_contract, sort_keys=True, ensure_ascii=False).encode("utf-8")
                ).hexdigest(),
                "generated": _utcnow_iso(),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    artifacts = ["experiment/", "experiment_spec.md", "experiment_contract.json", "experiment_contract.meta.json"]
    if (stage_dir / "validation_report.md").exists():
        artifacts.append("validation_report.md")

    # BUG-R6-01: Fail stage if alignment check detected persistent mismatch
    # after all regen attempts, instead of silently proceeding.
    if not alignment_ok:
        logger.error(
            "Stage 10: Persistent topic-experiment misalignment after all "
            "regen attempts. Failing stage. Reason: %s",
            alignment_note,
        )
        return StageResult(
            stage=Stage.CODE_GENERATION,
            status=StageStatus.FAILED,
            artifacts=tuple(artifacts),
            evidence_refs=tuple(f"stage-10/{a}" for a in artifacts),
            error=f"Topic-experiment misalignment: {alignment_note}",
        )

    return StageResult(
        stage=Stage.CODE_GENERATION,
        status=StageStatus.DONE,
        artifacts=tuple(artifacts),
        evidence_refs=tuple(f"stage-10/{a}" for a in artifacts),
    )
