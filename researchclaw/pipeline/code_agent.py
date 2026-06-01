"""Advanced multi-phase code generation agent.

Phases
------
1. **Blueprint Planning** — produce deep implementation blueprint with
   per-file pseudocode, tensor shapes, and generation ordering.
2. **Sequential File Generation** — generate files one-by-one following
   the dependency order from the blueprint, with CodeMem summaries.
   Falls back to single-shot generation if blueprint parsing fails.
3. **Execution-in-the-Loop** — run in sandbox, feed errors back for repair.
4. **Solution Tree Search** — explore multiple candidate implementations,
   evaluate via sandbox, select the best (optional, higher cost).
5. **Multi-Agent Review** — coder-reviewer dialog for quality assurance.

Integration
-----------
``CodeAgent`` is instantiated inside ``_execute_code_generation`` in
``executor.py`` when ``config.experiment.code_agent.enabled`` is True.
It receives the same inputs (topic, exp_plan, metric, pkg_hint) and
returns ``CodeAgentResult`` with the generated files.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
import re
import tempfile
import time
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from researchclaw.experiment.validator import detect_non_code_response
from researchclaw.pipeline.control_state import write_code_agent_control_state
from researchclaw.pipeline.stages import Stage

logger = logging.getLogger(__name__)

_REVIEW_FULL_FILE_ORDER: tuple[str, ...] = ("main.py", "methods.py", "data.py", "evaluate.py", "config.py")
_REVIEW_FULL_FILE_CHAR_BUDGET = 12000
_SUMMARY_CHAR_BUDGET = 8000
_ISSUE_FOCUSED_FILE_CHAR_BUDGET = 14000
_ISSUE_FOCUSED_BLOCK_LIMIT = 4

def _summarize_stderr(stderr: str, *, max_chars: int = 600) -> str:
    text = (stderr or "").strip()
    if not text:
        return ""
    compact = re.sub(r"\s+", " ", text)
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3] + "..."


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CodeAgentConfig:
    """Configuration for the advanced code generation agent.

    All phases are independently toggleable.  The default profile enables
    Phases 1 (blueprint), 2 (sequential generation + exec-fix), and 5
    (review), which gives a large quality boost at moderate extra cost.
    Phase 4 (tree search) is opt-in because it multiplies both LLM and
    sandbox usage.
    """

    enabled: bool = True

    # Phase 1: Blueprint planning (deep implementation blueprint)
    architecture_planning: bool = True

    # Phase 2: Sequential file generation (generate files one-by-one
    # following dependency order from blueprint, with CodeMem summaries)
    sequential_generation: bool = True

    # Phase 2.5: Hard validation gates (AST-based)
    hard_validation: bool = True
    hard_validation_max_repairs: int = 4

    # Phase 3: Execution-in-the-loop
    exec_fix_max_iterations: int = 3
    exec_fix_timeout_sec: int = 180

    # Phase 4: Solution tree search (off by default)
    tree_search_enabled: bool = False
    tree_search_candidates: int = 3
    tree_search_max_depth: int = 2
    tree_search_eval_timeout_sec: int = 120

    # Phase 5: Multi-agent review dialog
    review_max_rounds: int = 2


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class SolutionNode:
    """One candidate solution in the search tree."""

    node_id: str
    files: dict[str, str]
    parent_id: str | None = None
    depth: int = 0
    # Evaluation
    runs_ok: bool = False
    returncode: int = -1
    evaluated: bool = False
    stdout: str = ""
    stderr: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    generation_method: str = "initial"


@dataclass
class CodeAgentResult:
    """Final output from the code agent."""

    files: dict[str, str]
    architecture_spec: str = ""
    validation_log: list[str] = field(default_factory=list)
    total_llm_calls: int = 0
    total_sandbox_runs: int = 0
    best_score: float = 0.0
    tree_nodes_explored: int = 0
    review_rounds: int = 0


# ---------------------------------------------------------------------------
# Sandbox protocol (structural typing — no import dependency)
# ---------------------------------------------------------------------------


class _SandboxResult(Protocol):  # pragma: no cover
    returncode: int
    stdout: str
    stderr: str
    elapsed_sec: float
    metrics: dict[str, object]
    timed_out: bool


class _SandboxLike(Protocol):  # pragma: no cover
    def run_project(
        self,
        project_dir: Path,
        *,
        entry_point: str = "main.py",
        timeout_sec: int = 300,
    ) -> Any: ...


# ---------------------------------------------------------------------------
# CodeAgent
# ---------------------------------------------------------------------------


class CodeAgent:
    """Multi-phase code generation agent.

    Parameters
    ----------
    llm : LLMClient
        The language model client to use for code generation.
    prompts : PromptManager
        Manages prompt templates.
    config : CodeAgentConfig
        Agent configuration (toggles, limits, timeouts).
    stage_dir : Path
        Working directory for this stage (e.g. ``run_dir/stage-10``).
    sandbox_factory : callable, optional
        ``(ExperimentConfig, Path) -> SandboxLike``.  Required for
        Phases 2 and 3.
    experiment_config : ExperimentConfig, optional
        Passed to ``sandbox_factory`` when creating sandboxes.
    """

    def __init__(
        self,
        llm: Any,
        prompts: Any,
        config: CodeAgentConfig,
        stage_dir: Path,
        sandbox_factory: Any | None = None,
        experiment_config: Any | None = None,
        domain_profile: Any | None = None,
        code_search_result: Any | None = None,
        sandbox_notify_callback: Any | None = None,
        sandbox_stop_requested: Any | None = None,
    ) -> None:
        self._llm = llm
        self._pm = prompts
        self._cfg = config
        self._stage_dir = stage_dir
        self._sandbox_factory = sandbox_factory
        self._exp_config = experiment_config
        self._domain_profile = domain_profile
        self._code_search_result = code_search_result
        self._sandbox_notify_callback = sandbox_notify_callback
        self._sandbox_stop_requested = sandbox_stop_requested
        self._calls = 0
        self._runs = 0
        self._log: list[str] = []
        self._sandbox: _SandboxLike | None = None
        self._state_path = self._stage_dir / "code_agent_state.json"
        self._recovery_dir = self._stage_dir / "code_agent_recovery"

    # ── Public API ────────────────────────────────────────────────────────

    def generate(
        self,
        topic: str,
        exp_plan: str,
        metric: str,
        pkg_hint: str,
        max_tokens: int = 8192,
    ) -> CodeAgentResult:
        """Execute all enabled phases and return generated files."""
        t0 = time.time()
        self._log_event("CodeAgent.generate() started")
        state = self._load_state()
        self._calls = max(self._calls, int(state.get("llm_calls", 0) or 0))
        self._runs = max(self._runs, int(state.get("sandbox_runs", 0) or 0))
        if state:
            self._log_event(
                "Resuming from state: "
                f"phase={state.get('phase')}, "
                f"substate={state.get('phase_substate')}, "
                f"next_action={state.get('next_action')}, "
                f"file_index={state.get('file_index')}, "
                f"current_file={state.get('current_file') or '-'}, "
                f"review_rounds={state.get('review_rounds_completed', 0)}, "
                f"files={len(self._files_from_state(state))}"
            )

        # Phase 1: Blueprint planning
        arch_spec = str(state.get("arch_spec", "") or "")
        blueprint = state.get("blueprint")
        if (
            self._cfg.architecture_planning
            and not arch_spec
        ):
            self._save_state(
                {
                    "phase": "blueprint",
                    "phase_substate": "generate",
                    "next_action": "run_blueprint_planning",
                    "blueprint_index": 0,
                    "file_index": -1,
                    "current_file": "",
                    "arch_spec": "",
                    "blueprint": None,
                    "files": {},
                    "review_rounds_completed": 0,
                }
            )
            arch_spec, blueprint = self._phase1_blueprint(
                topic, exp_plan, metric,
            )
            self._save_state(
                {
                    "phase": "blueprint_done",
                    "phase_substate": "done",
                    "next_action": "start_sequential_generation",
                    "blueprint_index": 1,
                    "file_index": -1,
                    "current_file": "",
                    "arch_spec": arch_spec,
                    "blueprint": blueprint,
                    "files": {},
                    "review_rounds_completed": 0,
                }
            )

        # Phase 2: Code generation
        nodes_explored = 0
        files = self._files_from_state(state)
        if self._cfg.tree_search_enabled and self._sandbox_factory:
            best, nodes_explored = self._phase3_tree_search(
                topic, exp_plan, metric, pkg_hint, arch_spec, max_tokens,
            )
        elif (
            self._cfg.sequential_generation
            and blueprint is not None
            and self._is_valid_blueprint(blueprint)
        ):
            # Sequential file generation following blueprint
            files = self._phase2_sequential_generate(
                topic, exp_plan, metric, pkg_hint, arch_spec, blueprint, files,
            )
            # Hard validation gates (E-03)
            if self._cfg.hard_validation:
                files = self._hard_validate_and_repair(
                    files, topic, exp_plan, metric, pkg_hint, arch_spec,
                )
            # Exec-fix loop
            files = self._exec_fix_loop(files)
            best = SolutionNode(
                node_id="sequential", files=files, runs_ok=True, score=1.0,
            )
        else:
            # Fallback: single-shot generation
            if self._cfg.sequential_generation and blueprint is None:
                self._log_event(
                    "  Sequential generation requested but blueprint "
                    "invalid — falling back to single-shot"
                )
            if not files:
                files = self._phase2_generate_and_fix(
                    topic, exp_plan, metric, pkg_hint, arch_spec, max_tokens,
                )
            # Hard validation gates (E-03) for single-shot too
            if self._cfg.hard_validation and files:
                files = self._hard_validate_and_repair(
                    files, topic, exp_plan, metric, pkg_hint, arch_spec,
                )
            best = SolutionNode(
                node_id="single", files=files,
                runs_ok=bool(files), score=1.0 if files else 0.0,
            )

        # Phase 5: Review dialog
        review_rounds = 0
        if self._cfg.review_max_rounds > 0:
            best.files, review_rounds = self._phase4_review(
                best.files, topic, exp_plan, metric,
            )

        elapsed = time.time() - t0
        self._log_event(
            f"CodeAgent.generate() done in {elapsed:.1f}s — "
            f"{self._calls} LLM calls, {self._runs} sandbox runs"
        )
        self._save_state(
            {
                "phase": "done",
                "arch_spec": arch_spec,
                "blueprint": blueprint,
                "files": best.files,
                "review_rounds_completed": review_rounds,
            }
        )

        return CodeAgentResult(
            files=best.files,
            architecture_spec=arch_spec,
            validation_log=list(self._log),
            total_llm_calls=self._calls,
            total_sandbox_runs=self._runs,
            best_score=best.score,
            tree_nodes_explored=nodes_explored,
            review_rounds=review_rounds,
        )

    # ── Phase 1: Blueprint Planning ──────────────────────────────────────

    def _phase1_blueprint(
        self, topic: str, exp_plan: str, metric: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Generate a deep implementation blueprint.

        Returns (raw_yaml_str, parsed_blueprint_dict_or_None).
        """
        self._log_event("Phase 1: Blueprint planning")

        sp = self._pm.sub_prompt(
            "architecture_planning",
            topic=topic,
            exp_plan=exp_plan,
            metric=metric,
        )

        # Inject domain context and code search results into blueprint prompt
        domain_context = self._build_domain_context()
        if domain_context:
            sp = type(sp)(
                system=sp.system,
                user=sp.user + "\n\n" + domain_context,
            )
            self._log_event("  Injected domain context into blueprint prompt")

        resp = self._chat(sp.system, sp.user, max_tokens=8192)

        # Extract YAML block from response
        arch_spec = resp.content
        yaml_match = re.search(r"```ya?ml\s*\n(.*?)```", arch_spec, re.DOTALL)
        if yaml_match:
            arch_spec = yaml_match.group(1).strip()

        self._log_event(f"  Blueprint spec: {len(arch_spec)} chars")

        # Parse YAML into structured blueprint
        blueprint = self._parse_blueprint(arch_spec)
        if blueprint:
            n_files = len(blueprint.get("files", []))
            self._log_event(f"  Parsed blueprint: {n_files} files")
        else:
            self._log_event("  WARNING: Could not parse blueprint YAML")

        return arch_spec, blueprint

    def _build_domain_context(self) -> str:
        """Build domain-specific context for injection into prompts.

        Includes:
        - Domain profile hints (file structure, libraries, evaluation)
        - Code search results (API patterns, reference code)
        """
        parts: list[str] = []

        # Domain profile context
        if self._domain_profile is not None:
            try:
                from researchclaw.domains.prompt_adapter import get_adapter
                adapter = get_adapter(self._domain_profile)
                blueprint_ctx = adapter.get_blueprint_context()
                if blueprint_ctx:
                    parts.append(
                        "# Domain-Specific Guidance\n" + blueprint_ctx
                    )
            except Exception:
                logger.debug("Failed to get domain context", exc_info=True)

        # Code search results
        if self._code_search_result is not None:
            try:
                prompt_ctx = self._code_search_result.to_prompt_context()
                if prompt_ctx:
                    parts.append(
                        "# Reference Code from GitHub\n"
                        "The following patterns were found in relevant open-source projects. "
                        "Use them as reference for API usage and project structure.\n\n"
                        + prompt_ctx
                    )
            except Exception:
                logger.debug("Failed to get code search context", exc_info=True)

        return "\n\n".join(parts)

    def _parse_blueprint(self, yaml_text: str) -> dict[str, Any] | None:
        """Parse blueprint YAML into a structured dict.

        BUG-178: LLM often includes Python type annotations in signature
        values (e.g. ``signature: (self, name: str) -> Config``).  The
        bare ``:`` breaks YAML parsing.  We quote unquoted signature
        values before parsing.
        """
        import yaml

        # Pre-process: sanitize values that contain Python type annotations,
        # unclosed quotes, or other patterns that break YAML parsing.
        import re as _bp_re
        sanitized_lines = []
        for line in yaml_text.split("\n"):
            stripped = line.lstrip()
            if not stripped or stripped.startswith("#"):
                sanitized_lines.append(line)
                continue

            # Skip lines that are pure list markers or block scalars
            if stripped.startswith(("- ", "---", "...")):
                # For list items like `- key: value`, extract after `- `
                if stripped.startswith("- ") and ":" in stripped[2:]:
                    inner = stripped[2:]
                else:
                    sanitized_lines.append(line)
                    continue
            elif ":" in stripped:
                inner = stripped
            else:
                sanitized_lines.append(line)
                continue

            # Find the YAML key separator (first `:` followed by space or EOL)
            m = _bp_re.search(r":\s", inner)
            if not m:
                sanitized_lines.append(line)
                continue

            val_part = inner[m.end():].strip()
            if not val_part:
                sanitized_lines.append(line)
                continue

            # Already properly quoted — skip
            if val_part.startswith(("'", "|", ">")):
                sanitized_lines.append(line)
                continue

            # Check if value needs quoting:
            # 1) Contains `:` or `->` (type annotations)
            # 2) Starts with `"` but doesn't end with `"` (unclosed quote)
            # 3) Contains `[` with `:` (e.g. dict[str, float])
            needs_quoting = False
            if val_part.startswith('"'):
                # Already quoted — check if properly closed
                if not val_part.endswith('"') or val_part.count('"') % 2 != 0:
                    needs_quoting = True  # unclosed or malformed quote
                else:
                    sanitized_lines.append(line)
                    continue
            elif ":" in val_part or "->" in val_part:
                needs_quoting = True

            if needs_quoting:
                # Strip any existing partial quotes, escape internal quotes
                clean = val_part.strip('"').replace('"', '\\"')
                # Remove inline comments (# ...) to avoid YAML issues
                comment_idx = clean.find("  #")
                if comment_idx >= 0:
                    clean = clean[:comment_idx].rstrip()
                indent = line[:len(line) - len(stripped)]
                prefix = stripped[:len(stripped) - len(inner)]  # e.g. "- "
                key_sep = inner[:m.end()]
                sanitized_lines.append(
                    f'{indent}{prefix}{key_sep}"{clean}"'
                )
            else:
                sanitized_lines.append(line)
        sanitized = "\n".join(sanitized_lines)

        for attempt_text in (sanitized, yaml_text):
            try:
                data = yaml.safe_load(attempt_text)
                if isinstance(data, dict) and "files" in data:
                    return data
            except Exception as exc:
                self._log_event(f"  Blueprint YAML parse error: {exc}")
        return None

    @staticmethod
    def _is_valid_blueprint(blueprint: dict[str, Any]) -> bool:
        """Check if a blueprint has the minimum required structure."""
        files = blueprint.get("files", [])
        if not files or not isinstance(files, list):
            return False
        # Need at least 2 files with generation_order
        has_order = sum(
            1 for f in files
            if isinstance(f, dict) and "generation_order" in f
        )
        return has_order >= 2

    # ── Phase 2a: Sequential File Generation ─────────────────────────────

    def _phase2_sequential_generate(
        self,
        topic: str,
        exp_plan: str,
        metric: str,
        pkg_hint: str,
        arch_spec: str,
        blueprint: dict[str, Any],
        existing_files: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Generate files one-by-one following blueprint dependency order."""
        self._log_event("Phase 2: Sequential generation (blueprint-guided)")

        generated_files: dict[str, str] = dict(existing_files or {})
        code_memory: dict[str, dict[str, Any]] = {}  # CodeMem summaries
        for fname, code in generated_files.items():
            code_memory[fname] = self._build_code_summary(fname, code)

        # Sort files by generation_order
        file_specs = blueprint.get("files", [])
        file_specs = [f for f in file_specs if isinstance(f, dict)]

        # Ensure generation_order exists; default to list position
        for i, fs in enumerate(file_specs):
            if "generation_order" not in fs:
                fs["generation_order"] = i + 1

        file_specs.sort(key=lambda f: f.get("generation_order", 99))
        state = self._load_state()
        resume_file = str(state.get("current_file", "") or "")
        resume_action = str(state.get("next_action", "") or "")
        start_pos = 0
        if state.get("phase") == "sequential_generation" and resume_file:
            for pos, file_spec in enumerate(file_specs):
                if file_spec.get("name") != resume_file:
                    continue
                if resume_action == "generate_next_file" and resume_file in generated_files:
                    start_pos = pos + 1
                else:
                    start_pos = pos
                self._log_event(
                    f"  Sequential resume target: {resume_file} "
                    f"(position {start_pos + 1}/{len(file_specs)})"
                )
                break

        for pos, file_spec in enumerate(file_specs[start_pos:], start=start_pos):
            file_name = file_spec.get("name", "")
            if not file_name:
                continue
            if file_name in generated_files:
                self._log_event(f"  Reusing generated file {file_name}")
                continue
            try:
                file_index = int(file_spec.get("generation_order", 0))
            except (TypeError, ValueError):
                file_index = 0

            self._log_event(
                f"  Generating {file_name} "
                f"(order={file_spec.get('generation_order')})"
            )
            self._save_state(
                {
                    "phase": "sequential_generation",
                    "phase_substate": "generate",
                    "next_action": "generate_file",
                    "blueprint_index": 1,
                    "file_index": pos,
                    "arch_spec": arch_spec,
                    "blueprint": blueprint,
                    "files": generated_files,
                    "current_file": file_name,
                    "review_rounds_completed": 0,
                }
            )

            # Build dependency context
            deps = file_spec.get("dependencies", [])
            dep_summaries = ""
            dep_code = ""

            for dep in deps:
                if isinstance(dep, str):
                    if dep in code_memory:
                        dep_summaries += (
                            f"\n### {dep} (summary)\n"
                            + json.dumps(code_memory[dep], indent=2)
                            + "\n"
                        )
                    if dep in generated_files:
                        dep_code += (
                            f"\n### {dep}\n```python\n"
                            + generated_files[dep]
                            + "\n```\n"
                        )

            if not dep_summaries:
                dep_summaries = "(no dependencies yet)"
            if not dep_code:
                dep_code = "(no dependencies yet)"

            # Generate this file via LLM
            file_spec_str = json.dumps(file_spec, indent=2, default=str)
            sp = self._pm.sub_prompt(
                "generate_single_file",
                file_name=file_name,
                file_spec=file_spec_str,
                blueprint=arch_spec,
                dependency_summaries=dep_summaries,
                dependency_code=dep_code,
                topic=topic,
                exp_plan=exp_plan[:4000],  # Truncate to avoid token overflow
                pkg_hint=pkg_hint,
            )
            resp = self._chat(sp.system, sp.user, max_tokens=8192)

            upstream_error = detect_non_code_response(resp.content)
            if upstream_error:
                self._log_event(
                    f"  WARNING: {file_name} generation returned non-code text: "
                    f"{upstream_error}"
                )
                continue

            # Extract code from response
            code = self._extract_single_file_code(resp.content, file_name)
            if not code:
                self._log_event(f"  WARNING: Empty code for {file_name}")
                continue

            generated_files[file_name] = code

            # Build CodeMem summary via AST
            code_memory[file_name] = self._build_code_summary(
                file_name, code,
            )
            self._save_state(
                {
                    "phase": "sequential_generation",
                    "phase_substate": "generate",
                    "next_action": "generate_next_file",
                    "blueprint_index": 1,
                    "file_index": pos,
                    "arch_spec": arch_spec,
                    "blueprint": blueprint,
                    "files": generated_files,
                    "current_file": file_name,
                    "review_rounds_completed": 0,
                }
            )

            self._log_event(
                f"  {file_name}: {len(code.split(chr(10)))} lines, "
                f"{len(code_memory[file_name].get('classes', []))} classes"
            )

        # Verify we have main.py
        if "main.py" not in generated_files:
            self._log_event("  WARNING: No main.py generated, promoting first file")
            if generated_files:
                first_key = next(iter(generated_files))
                generated_files["main.py"] = generated_files.pop(first_key)

        self._log_event(
            f"  Sequential generation complete: {len(generated_files)} files"
        )
        return generated_files

    @staticmethod
    def _extract_single_file_code(content: str, expected_name: str) -> str:
        """Extract Python code from LLM response for a single file."""
        if detect_non_code_response(content):
            return ""

        # Try to extract from ```python``` block
        m = re.search(r"```python\s*\n(.*?)```", content, re.DOTALL)
        if m:
            candidate = m.group(1).strip()
            if detect_non_code_response(candidate):
                return ""
            return candidate

        # Try ```filename:xxx.py block
        m = re.search(
            rf"```(?:filename:)?{re.escape(expected_name)}\s*\n(.*?)```",
            content, re.DOTALL,
        )
        if m:
            candidate = m.group(1).strip()
            if detect_non_code_response(candidate):
                return ""
            return candidate

        # If content looks like raw Python (starts with import/from/# or def)
        stripped = content.strip()
        if stripped and (
            stripped.startswith("import ")
            or stripped.startswith("from ")
            or stripped.startswith("#")
            or stripped.startswith("def ")
            or stripped.startswith("class ")
            or stripped.startswith('"""')
        ):
            return stripped

        return ""

    @staticmethod
    def _build_code_summary(
        filename: str, code: str,
    ) -> dict[str, Any]:
        """Build a CodeMem-style compressed summary via AST analysis."""
        summary: dict[str, Any] = {
            "filename": filename,
            "classes": [],
            "functions": [],
            "imports": [],
        }

        try:
            tree = ast.parse(code)
        except SyntaxError:
            summary["parse_error"] = True
            return summary

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = []
                for n in node.body:
                    if isinstance(n, ast.FunctionDef):
                        args = [a.arg for a in n.args.args if a.arg != "self"]
                        methods.append({
                            "name": n.name,
                            "args": args,
                        })
                summary["classes"].append({
                    "name": node.name,
                    "bases": [ast.unparse(b) for b in node.bases],
                    "methods": methods,
                })
            elif isinstance(node, ast.FunctionDef) and node.col_offset == 0:
                args = [a.arg for a in node.args.args]
                summary["functions"].append({
                    "name": node.name,
                    "args": args,
                })
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                try:
                    summary["imports"].append(ast.unparse(node))
                except Exception:
                    pass

        return summary

    # ── Phase 2.5: Hard Validation Gates (E-03) ─────────────────────────

    def _hard_validate_and_repair(
        self,
        files: dict[str, str],
        topic: str,
        exp_plan: str,
        metric: str,
        pkg_hint: str,
        arch_spec: str,
    ) -> dict[str, str]:
        """Run AST-based hard validation and repair critical issues.

        Critical issues trigger targeted file regeneration.  Non-critical
        issues are logged as warnings only.
        """
        self._log_event("Phase 2.5: Hard validation gates")
        self._save_state(
            {
                "phase": "hard_validation",
                "phase_substate": "validate",
                "next_action": "run_hard_validation",
                "blueprint_index": 1,
                "file_index": -1,
                "current_file": "",
                "files": files,
            }
        )

        state = self._load_state()
        start_attempt = 0
        if state.get("phase") == "hard_validation":
            saved_attempt = int(state.get("repair_attempt", 0) or 0)
            if state.get("next_action") == "repair_critical_issues":
                start_attempt = min(
                    saved_attempt + 1,
                    self._cfg.hard_validation_max_repairs,
                )
            else:
                start_attempt = saved_attempt
            self._log_event(
                f"  Hard validation resume attempt={start_attempt}"
            )

        for attempt in range(
            start_attempt,
            self._cfg.hard_validation_max_repairs + 1,
        ):
            files, local_fixes = self._apply_local_hard_validation_repairs(files)
            if local_fixes:
                self._save_state(
                    {
                        "phase": "hard_validation",
                        "phase_substate": "local_repair",
                        "next_action": "apply_local_repairs",
                        "repair_attempt": attempt,
                        "blueprint_index": 1,
                        "file_index": -1,
                        "current_file": "",
                        "files": files,
                    }
                )
                for change in local_fixes:
                    self._log_event(f"  LOCAL-REPAIR: {change}")

            critical, warnings = self._hard_validate(files)

            if critical:
                files, issue_local_fixes = self._apply_issue_specific_local_repairs(
                    files,
                    critical,
                )
                if issue_local_fixes:
                    self._save_state(
                        {
                            "phase": "hard_validation",
                            "phase_substate": "local_repair",
                            "next_action": "apply_issue_specific_local_repairs",
                            "repair_attempt": attempt,
                            "blueprint_index": 1,
                            "file_index": -1,
                            "current_file": "",
                            "files": files,
                        }
                    )
                    for change in issue_local_fixes:
                        self._log_event(f"  LOCAL-REPAIR: {change}")
                    critical, warnings = self._hard_validate(files)

            # Log warnings
            for w in warnings:
                self._log_event(f"  WARNING: {w}")

            if not critical:
                self._log_event(
                    f"  Hard validation passed "
                    f"({len(warnings)} warning(s), attempt {attempt})"
                )
                return files

            self._log_event(
                f"  Hard validation found {len(critical)} CRITICAL issue(s) "
                f"(attempt {attempt}/{self._cfg.hard_validation_max_repairs})"
            )
            for c in critical:
                self._log_event(f"  CRITICAL: {c}")

            if attempt >= self._cfg.hard_validation_max_repairs:
                self._log_event(
                    "  Max repair attempts reached — proceeding with warnings"
                )
                return files

            # Targeted repair: ask LLM to fix specific critical issues
            files = self._repair_critical_issues(
                files, critical, topic, exp_plan, metric, arch_spec,
            )
            self._save_state(
                {
                    "phase": "hard_validation",
                    "phase_substate": "repair",
                    "next_action": "repair_critical_issues",
                    "repair_attempt": attempt,
                    "blueprint_index": 1,
                    "file_index": -1,
                    "current_file": "",
                    "files": files,
                }
            )

        return files

    def _hard_validate(
        self, files: dict[str, str],
    ) -> tuple[list[str], list[str]]:
        """Run AST-based checks and classify as CRITICAL or WARNING.

        Returns (critical_issues, warning_issues).
        """
        critical: list[str] = []
        warnings: list[str] = []

        from researchclaw.experiment.validator import (
            check_class_quality,
            check_code_complexity,
            check_api_correctness,
            check_variable_scoping,
            validate_syntax,
        )

        # 1. Syntax check — always critical
        for fname, code in files.items():
            if not fname.endswith(".py"):
                continue
            syn = validate_syntax(code)
            if not syn.ok:
                for issue in syn.errors:
                    critical.append(
                        f"[{fname}] Syntax error: {issue.message} "
                        f"(line {issue.line})"
                    )

        # 2. Class quality — some are critical
        class_warns = check_class_quality(files)
        for w in class_warns:
            if "identical AST to parent" in w:
                critical.append(w)
            elif "NOT a real ablation" in w:
                critical.append(w)
            elif "creates nn.Module" in w and "inside forward()" in w:
                critical.append(w)
            elif "empty or trivial subclass" in w:
                # Critical: ablation classes must have real implementations
                critical.append(w)
            else:
                warnings.append(w)

        # 3. Code complexity — hardcoded metrics are critical
        for fname, code in files.items():
            if not fname.endswith(".py"):
                continue
            complexity_warns = check_code_complexity(code)
            for w in complexity_warns:
                if "hardcoded metric" in w.lower():
                    critical.append(f"[{fname}] {w}")
                elif "trivial computation" in w.lower():
                    critical.append(f"[{fname}] {w}")
                else:
                    warnings.append(f"[{fname}] {w}")

        # 4. API correctness — NameError-causing issues are critical
        for fname, code in files.items():
            if not fname.endswith(".py"):
                continue
            api_warns = check_api_correctness(code, fname)
            for w in api_warns:
                if "NameError" in w or "Import-usage mismatch" in w:
                    critical.append(w)
                elif "does not exist" in w:
                    critical.append(w)
                else:
                    warnings.append(w)

        # 5. Variable scoping — UnboundLocalError is critical
        for fname, code in files.items():
            if not fname.endswith(".py"):
                continue
            scope_warns = check_variable_scoping(code, fname)
            for w in scope_warns:
                if "UnboundLocalError" in w:
                    critical.append(w)
                else:
                    warnings.append(w)

        # 6. Cross-file import consistency — check local imports resolve
        known_modules = {
            fname.replace(".py", "")
            for fname in files
            if fname.endswith(".py")
        }
        for fname, code in files.items():
            if not fname.endswith(".py"):
                continue
            try:
                tree = ast.parse(code)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    mod_top = node.module.split(".")[0]
                    # Check if importing from a local module that exists
                    if mod_top in known_modules:
                        # Verify imported names exist in target file
                        target_file = f"{mod_top}.py"
                        if target_file in files and node.names:
                            target_code = files[target_file]
                            exported = self._list_top_level_names(target_code)
                            if not exported:
                                continue
                            for alias in node.names:
                                name = alias.name
                                if name != "*" and name not in exported:
                                    critical.append(
                                        f"[{fname}] ImportError: "
                                        f"'{name}' not defined in "
                                        f"'{target_file}' — will crash"
                                    )

        # 7. BUG-R41-04: main.py MUST have an `if __name__ == "__main__"` block
        #    and must call a training/experiment function — otherwise Docker runs
        #    the file and exits 0 with no output.
        main_code = files.get("main.py", "")
        if main_code:
            try:
                main_tree = ast.parse(main_code)
                has_main_guard = False
                for node in ast.walk(main_tree):
                    if isinstance(node, ast.If):
                        # Check for `if __name__ == "__main__"` pattern
                        test = node.test
                        if isinstance(test, ast.Compare):
                            left = test.left
                            if (
                                isinstance(left, ast.Name)
                                and left.id == "__name__"
                                and len(test.comparators) == 1
                            ):
                                comp = test.comparators[0]
                                if (
                                    isinstance(comp, ast.Constant)
                                    and comp.value == "__main__"
                                ):
                                    has_main_guard = True
                                    break
                if not has_main_guard:
                    critical.append(
                        "[main.py] Missing `if __name__ == \"__main__\":` block — "
                        "script will define functions/classes but never execute "
                        "training. Add a main guard that calls the experiment entry "
                        "point."
                    )
            except SyntaxError:
                pass  # Already caught by syntax check above

        return critical, warnings

    def _repair_critical_issues(
        self,
        files: dict[str, str],
        critical_issues: list[str],
        topic: str,
        exp_plan: str,
        metric: str,
        arch_spec: str,
    ) -> dict[str, str]:
        """Ask LLM to fix critical validation issues."""
        self._log_event("  Targeted repair for critical issues")

        # Identify which files need repair
        affected_files: set[str] = set()
        for issue in critical_issues:
            # Extract filename from issue string: [filename.py] ...
            m = re.match(r"\[([^\]]+\.py)\]", issue)
            if m:
                affected_files.add(m.group(1))
            else:
                # If no filename found, assume all files affected
                affected_files.update(
                    f for f in files if f.endswith(".py")
                )

        if not affected_files:
            affected_files.update(f for f in files if f.endswith(".py"))
        issues_by_file = self._group_issues_by_file(critical_issues, affected_files)
        merged = dict(files)
        repaired_files: set[str] = set()
        sys_prompt = self._pm.system("code_generation")

        for fname in sorted(affected_files):
            file_issues = issues_by_file.get(fname, [])
            if not file_issues:
                continue
            repaired_code = None
            code = merged.get(fname, "")
            if self._should_use_problem_block_repair(fname, code, file_issues):
                repaired_code = self._repair_file_by_problem_blocks(
                    merged,
                    fname,
                    file_issues,
                    arch_spec,
                )
            if repaired_code is None:
                repaired_code = self._repair_file_with_full_context(
                    merged,
                    fname,
                    file_issues,
                    arch_spec,
                    sys_prompt,
                )
            if repaired_code is not None and repaired_code != merged.get(fname):
                merged[fname] = repaired_code
                repaired_files.add(fname)

        if repaired_files:
            self._log_event(
                f"  Repair updated {len(repaired_files)} file(s): "
                f"{', '.join(sorted(repaired_files))}"
            )
            return merged

        self._log_event("  WARNING: Repair produced no extractable files")
        return files

    # ── Phase 2b: Single-Shot Generate + Exec-Fix (legacy) ───────────────

    def _phase2_generate_and_fix(
        self,
        topic: str,
        exp_plan: str,
        metric: str,
        pkg_hint: str,
        arch_spec: str,
        max_tokens: int,
    ) -> dict[str, str]:
        """Generate code in single shot, then iteratively fix via sandbox."""
        self._log_event("Phase 2: Single-shot generate + exec-fix")

        # Initial generation (uses the existing code_generation prompt)
        files = self._generate_code(
            topic, exp_plan, metric, pkg_hint, arch_spec, max_tokens,
        )
        if not files:
            self._log_event("  WARNING: empty generation, returning fallback")
            return files

        return self._exec_fix_loop(files)

    def _exec_fix_loop(self, files: dict[str, str]) -> dict[str, str]:
        """Run exec-fix loop if sandbox is available."""
        if not self._sandbox_factory or self._cfg.exec_fix_max_iterations <= 0:
            return files

        state = self._load_state()
        start_iter = 0
        if state.get("phase") == "exec_fix":
            saved_iter = int(state.get("exec_fix_iteration", 0) or 0)
            if state.get("next_action") == "runtime_repair":
                start_iter = min(saved_iter + 1, self._cfg.exec_fix_max_iterations)
            else:
                start_iter = saved_iter
            self._log_event(f"  Exec-fix resume iteration={start_iter}")

        for i in range(start_iter, self._cfg.exec_fix_max_iterations):
            self._save_state(
                {
                    "phase": "exec_fix",
                    "phase_substate": "run",
                    "next_action": "sandbox_run",
                    "blueprint_index": 1,
                    "file_index": -1,
                    "current_file": "",
                    "files": files,
                    "exec_fix_iteration": i,
                }
            )
            result = self._run_in_sandbox(files)
            if result.returncode == 0:
                self._log_event(f"  Exec-fix iter {i}: code runs OK")
                break

            self._log_event(
                f"  Exec-fix iter {i}: crashed (rc={result.returncode}), "
                f"stderr={len(result.stderr or '')} chars, "
                f"summary={_summarize_stderr(result.stderr)}"
            )
            files = self._fix_runtime_error(files, result)
            self._save_state(
                {
                    "phase": "exec_fix",
                    "phase_substate": "repair",
                    "next_action": "runtime_repair",
                    "blueprint_index": 1,
                    "file_index": -1,
                    "current_file": "",
                    "files": files,
                    "exec_fix_iteration": i,
                }
            )

        return files

    def _generate_code(
        self,
        topic: str,
        exp_plan: str,
        metric: str,
        pkg_hint: str,
        arch_spec: str,
        max_tokens: int,
    ) -> dict[str, str]:
        """Single code generation call with architecture spec injected."""
        # Inject architecture specification into the pkg_hint slot
        hint = pkg_hint
        if arch_spec:
            hint = (
                f"{pkg_hint}\n\n"
                "## ARCHITECTURE SPECIFICATION (follow this file and class structure)\n"
                f"{arch_spec}\n"
            )

        # BUG-004: Inject numerical stability requirements
        hint += (
            "\n\n## NUMERICAL STABILITY (MANDATORY)\n"
            "- Add gradient clipping: `torch.nn.utils.clip_grad_norm_(params, 1.0)`\n"
            "- After each optimizer step, check for NaN loss:\n"
            "  `if torch.isnan(loss): print('FAIL: NaN detected'); break`\n"
            "- When logging metrics, guard against NaN/Inf:\n"
            "  `v = float(val); v = 0.0 if (math.isnan(v) or math.isinf(v)) else v`\n"
            "- For RL: clip rewards to [-10, 10], use reward normalization\n"
        )

        sp = self._pm.for_stage(
            "code_generation",
            topic=topic,
            metric=metric,
            pkg_hint=hint,
            exp_plan=exp_plan,
        )
        resp = self._chat(sp.system, sp.user, max_tokens=max_tokens)

        files = self._extract_files(resp.content)
        if not files and resp.content.strip():
            # Retry with higher token budget
            self._log_event("  Empty extraction, retrying with 32768 tokens")
            resp = self._chat(sp.system, sp.user, max_tokens=32768)
            files = self._extract_files(resp.content)

        return files

    def _fix_runtime_error(
        self, files: dict[str, str], result: Any,
    ) -> dict[str, str]:
        """Fix a runtime error using targeted or full-file repair.

        E-05: Parse the error traceback to identify the failing file and
        line, then send only the affected file with a focused context
        window.  Falls back to full-file repair if parsing fails.
        """
        stderr_tail = (result.stderr or "")[-3000:]
        stdout_tail = "\n".join(
            (result.stdout or "").split("\n")[-50:]
        )

        # Try targeted repair first (E-05)
        error_loc = self._parse_error_location(stderr_tail, files)
        if error_loc:
            fname, lineno, error_msg = error_loc
            self._log_event(
                f"  Targeted repair: {fname}:{lineno} — {error_msg[:80]}"
            )
            fixed = self._targeted_file_repair(
                files, fname, lineno, error_msg, stderr_tail,
            )
            if fixed:
                return fixed

        # Fallback: full-file repair
        focus_target = (
            error_loc[0]
            if error_loc
            else ("main.py" if "main.py" in files else next(iter(files), "main.py"))
        )
        files_ctx = self._build_compact_project_context(
            files,
            focus_files={focus_target},
            full_file_order=[focus_target],
            full_budget=max(len(files.get(focus_target, "")) + 2000, 12000),
        )
        sp = self._pm.sub_prompt(
            "code_exec_fix",
            stderr=stderr_tail or "(empty)",
            stdout_tail=stdout_tail or "(empty)",
            returncode=str(result.returncode),
            files_context=files_ctx,
        )
        resp = self._chat(sp.system, sp.user, max_tokens=16384)

        fixed = self._extract_files(resp.content)
        if fixed:
            merged = dict(files)
            merged.update(fixed)
            return merged
        return files

    @staticmethod
    def _parse_error_location(
        stderr: str, files: dict[str, str],
    ) -> tuple[str, int, str] | None:
        """Parse Python traceback to find failing file and line.

        Returns (filename, line_number, error_message) or None.
        """
        known_files = set(files.keys())
        # Parse traceback lines: File "xxx.py", line NNN
        tb_pattern = re.compile(
            r'File "(?:[^"]*[/\\])?([^"]+\.py)", line (\d+)'
        )
        matches = list(tb_pattern.finditer(stderr))
        if not matches:
            return None

        # Find the last match that references one of our files
        for m in reversed(matches):
            fname = m.group(1)
            lineno = int(m.group(2))
            if fname in known_files:
                # Extract error message (last line of stderr)
                lines = stderr.strip().split("\n")
                error_msg = lines[-1] if lines else "Unknown error"
                return fname, lineno, error_msg

        return None

    def _targeted_file_repair(
        self,
        files: dict[str, str],
        target_file: str,
        error_line: int,
        error_msg: str,
        full_stderr: str,
    ) -> dict[str, str] | None:
        """Repair a single file with focused context around the error."""
        if target_file not in files:
            return None

        code = files[target_file]
        code_lines = code.split("\n")
        total_lines = len(code_lines)

        # Extract context window: ±30 lines around error
        window = 30
        start = max(0, error_line - window - 1)
        end = min(total_lines, error_line + window)
        context_lines = code_lines[start:end]

        # Number the lines for the LLM
        numbered = "\n".join(
            f"{start + i + 1:4d} | {line}"
            for i, line in enumerate(context_lines)
        )

        # Build compact dependency context (summaries only)
        dep_summaries = ""
        for fname, fcode in files.items():
            if fname != target_file and fname.endswith(".py"):
                summary = self._build_code_summary(fname, fcode)
                dep_summaries += (
                    f"\n### {fname}: "
                    f"{len(summary.get('classes', []))} classes, "
                    f"{len(summary.get('functions', []))} functions\n"
                )
                for cls in summary.get("classes", []):
                    methods = ", ".join(
                        m["name"] for m in cls.get("methods", [])
                    )
                    dep_summaries += (
                        f"  class {cls['name']}"
                        f"({', '.join(cls.get('bases', []))})"
                        f": [{methods}]\n"
                    )

        prompt = (
            f"Fix the runtime error in `{target_file}` at line {error_line}.\n\n"
            f"## Error\n```\n{error_msg}\n```\n\n"
            f"## Full Traceback (last 1500 chars)\n"
            f"```\n{full_stderr[-1500:]}\n```\n\n"
            f"## {target_file} (lines {start + 1}-{end})\n"
            f"```python\n{numbered}\n```\n\n"
            f"## Other Files in Project\n{dep_summaries}\n\n"
            f"## Full File ({target_file}, {total_lines} lines)\n"
            f"```python\n{code}\n```\n\n"
            f"Output the COMPLETE fixed `{target_file}` in "
            f"```filename:{target_file}``` format. Fix the root cause, "
            f"not just the symptom."
        )

        sys_prompt = (
            "You are a debugging expert. Fix the specific runtime error "
            "shown. Preserve experiment design and scientific methodology. "
            "Output the COMPLETE fixed file."
        )
        resp = self._chat(sys_prompt, prompt, max_tokens=16384)

        fixed = self._extract_files(resp.content)
        if not fixed:
            # Try extracting as single file
            code_match = re.search(
                r"```(?:python|filename:\S+)\s*\n(.*?)```",
                resp.content, re.DOTALL,
            )
            if code_match:
                candidate = code_match.group(1).strip()
                if not detect_non_code_response(candidate):
                    fixed = {target_file: candidate}

        if fixed and target_file in fixed:
            merged = dict(files)
            merged.update(fixed)
            self._log_event(
                f"  Targeted repair applied to {target_file} "
                f"({len(fixed[target_file].split(chr(10)))} lines)"
            )
            return merged

        return None

    # ── Phase 3: Solution Tree Search ─────────────────────────────────────

    def _phase3_tree_search(
        self,
        topic: str,
        exp_plan: str,
        metric: str,
        pkg_hint: str,
        arch_spec: str,
        max_tokens: int,
    ) -> tuple[SolutionNode, int]:
        """Explore multiple candidate solutions via tree search."""
        self._log_event("Phase 3: Solution tree search")
        all_nodes: list[SolutionNode] = []

        # Generate initial candidates
        n_cand = max(self._cfg.tree_search_candidates, 1)
        for k in range(n_cand):
            self._log_event(f"  Generating candidate {k + 1}/{n_cand}")
            files = self._generate_code(
                topic, exp_plan, metric, pkg_hint, arch_spec, max_tokens,
            )
            node = SolutionNode(
                node_id=f"gen-{k}",
                files=files,
                depth=0,
                generation_method="initial",
            )
            all_nodes.append(node)

        # Iterative evaluate-fix-branch loop
        for depth in range(self._cfg.tree_search_max_depth):
            # Evaluate unevaluated nodes
            for node in all_nodes:
                if not node.evaluated:
                    self._evaluate_node(node, metric)

            # Sort by score
            all_nodes.sort(key=lambda n: n.score, reverse=True)

            self._log_event(
                f"  Depth {depth}: {len(all_nodes)} nodes, "
                f"best={all_nodes[0].node_id} score={all_nodes[0].score:.2f}"
            )

            # If best runs OK, we're done
            if all_nodes[0].runs_ok:
                break

            # Generate fix variants for top-2 crashing candidates
            new_nodes: list[SolutionNode] = []
            for node in all_nodes[:2]:
                if not node.runs_ok:
                    fixed_files = self._fix_runtime_error(
                        node.files,
                        _SimpleResult(
                            returncode=node.returncode,
                            stdout=node.stdout,
                            stderr=node.stderr,
                        ),
                    )
                    new_node = SolutionNode(
                        node_id=f"{node.node_id}-fix{depth}",
                        files=fixed_files,
                        parent_id=node.node_id,
                        depth=depth + 1,
                        generation_method="fix",
                    )
                    new_nodes.append(new_node)

            all_nodes.extend(new_nodes)

        # Final evaluation of any remaining unevaluated nodes
        for node in all_nodes:
            if node.returncode == -1:
                self._evaluate_node(node, metric)

        all_nodes.sort(key=lambda n: n.score, reverse=True)
        best = all_nodes[0]
        self._log_event(
            f"  Tree search complete: best={best.node_id} "
            f"score={best.score:.2f}, explored {len(all_nodes)} nodes"
        )

        return best, len(all_nodes)

    def _evaluate_node(self, node: SolutionNode, metric_key: str) -> None:
        """Run a node's code in sandbox and update its score."""
        if not node.files:
            node.score = 0.0
            return

        result = self._run_in_sandbox(
            node.files,
            timeout_sec=self._cfg.tree_search_eval_timeout_sec,
        )
        node.evaluated = True
        node.returncode = result.returncode
        node.stdout = result.stdout
        node.stderr = result.stderr
        node.runs_ok = result.returncode == 0
        node.metrics = dict(result.metrics) if result.metrics else {}
        node.score = self._score_node(node, metric_key)

    @staticmethod
    def _score_node(node: SolutionNode, metric_key: str) -> float:
        """Score a solution node based on execution results."""
        score = 0.0
        if node.runs_ok:
            score += 1.0
        if node.stdout and len(node.stdout) > 100:
            score += 0.3  # produces meaningful output
        if node.metrics:
            score += 0.5
            if metric_key in node.metrics:
                score += 0.5
        if node.stderr and "Error" in node.stderr:
            score -= 0.2
        return max(score, 0.0)

    # ── Phase 5: Multi-Agent Review Dialog ────────────────────────────────

    def _phase4_review(
        self,
        files: dict[str, str],
        topic: str,
        exp_plan: str,
        metric: str,
    ) -> tuple[dict[str, str], int]:
        """Reviewer agent examines code; coder fixes critical issues."""
        self._log_event("Phase 4: Review dialog")

        state = self._load_state()
        rounds = int(state.get("review_rounds_completed", 0) or 0)
        start_round = rounds
        if state.get("phase") == "review":
            self._log_event(f"  Review resume round={start_round + 1}")
        for r in range(start_round, self._cfg.review_max_rounds):
            rounds = r + 1
            self._save_state(
                {
                    "phase": "review",
                    "phase_substate": "review",
                    "next_action": "review_round",
                    "blueprint_index": 1,
                    "file_index": -1,
                    "current_file": "",
                    "files": files,
                    "review_rounds_completed": r,
                }
            )
            files_ctx = self._build_review_context(files)

            sp = self._pm.sub_prompt(
                "code_reviewer",
                topic=topic,
                exp_plan=exp_plan,
                metric=metric,
                files_context=files_ctx,
            )
            try:
                resp = self._chat(sp.system, sp.user, max_tokens=2048)
            except Exception as exc:
                self._log_event(
                    f"  Review round {r + 1}: reviewer call failed, skipping ({exc})"
                )
                break

            review = self._parse_json(resp.content)
            if not isinstance(review, dict) or not review:
                self._log_event(
                    f"  Review round {r + 1}: could not parse JSON, skipping"
                )
                break

            verdict = review.get("verdict", "APPROVE")
            score = review.get("score", 10)
            critical = review.get("critical_issues", [])

            self._log_event(
                f"  Review round {r + 1}: verdict={verdict}, score={score}, "
                f"critical_issues={len(critical)}"
            )

            if verdict == "APPROVE" or not critical:
                break

            affected_files = {
                fname for fname in (
                    self._extract_issue_filename(issue) for issue in critical
                ) if fname
            }
            sys_prompt = self._pm.system("code_generation")
            issues_by_file = self._group_issues_by_file(
                critical,
                affected_files or {"main.py", "methods.py"},
            )
            fixed: dict[str, str] = {}
            for fname in sorted(issues_by_file):
                file_issues = issues_by_file.get(fname, [])
                if not file_issues or fname not in files:
                    continue
                repair_ctx = self._build_issue_focused_project_context(
                    files,
                    target_file=fname,
                    issues=file_issues,
                    full_budget=14000,
                )
                summarized_issues = "\n".join(
                    f"- {issue}" for issue in file_issues[:6]
                )
                fix_prompt = (
                    "A code reviewer found critical issues in one target file.\n"
                    "Fix only that file while preserving the experiment design.\n\n"
                    f"## Target File\n{fname}\n\n"
                    "## Critical Issues\n"
                    + summarized_issues
                    + f"\n\n## Project Context\n{repair_ctx}\n\n"
                    "Output ONLY the corrected target file in "
                    f"```filename:{fname}``` format."
                )
                try:
                    fix_resp = self._chat(sys_prompt, fix_prompt, max_tokens=8192)
                except Exception as exc:
                    self._log_event(
                        f"  Review round {r + 1}: repair call failed for {fname}, "
                        f"skipping ({exc})"
                    )
                    continue
                file_fixed = self._extract_files(fix_resp.content)
                if not file_fixed:
                    single = self._extract_single_file_code(fix_resp.content, fname)
                    if single:
                        file_fixed = {fname: single}
                if fname in file_fixed:
                    fixed[fname] = file_fixed[fname]

            if fixed:
                files = dict(files)
                files.update(fixed)
                self._save_state(
                    {
                        "phase": "review",
                        "phase_substate": "repair",
                        "next_action": "apply_review_fixes",
                        "blueprint_index": 1,
                        "file_index": -1,
                        "current_file": "",
                        "files": files,
                        "review_rounds_completed": rounds,
                    }
                )
            else:
                self._log_event(
                    f"  Review round {r + 1}: no repair files extracted, skipping"
                )

        return files, rounds

    # ── Helpers ────────────────────────────────────────────────────────────

    def _chat(self, system: str, user: str, max_tokens: int = 8192) -> Any:
        """Make an LLM call and track count."""
        self._calls += 1
        messages = [{"role": "user", "content": user}]
        return self._llm.chat(
            messages=messages,
            system=system,
            max_tokens=max_tokens,
        )

    def _get_or_create_sandbox(self) -> _SandboxLike:
        """Lazily create a single sandbox instance for all validation runs."""
        if self._sandbox is None:
            sandbox_dir = self._stage_dir / "agent_sandbox"
            sandbox_dir.mkdir(parents=True, exist_ok=True)
            try:
                self._sandbox = self._sandbox_factory(
                    self._exp_config, sandbox_dir,
                    notify_callback=self._sandbox_notify_callback,
                    stop_requested=self._sandbox_stop_requested,
                )
            except TypeError as exc:
                if "unexpected keyword argument" not in str(exc):
                    raise
                self._sandbox = self._sandbox_factory(self._exp_config, sandbox_dir)
        return self._sandbox

    def _run_in_sandbox(
        self,
        files: dict[str, str],
        timeout_sec: int | None = None,
    ) -> Any:
        """Write files to a temp directory and run in sandbox."""
        if not self._sandbox_factory:
            raise RuntimeError("No sandbox factory configured")

        self._runs += 1
        timeout = timeout_sec or self._cfg.exec_fix_timeout_sec

        # Write files to a numbered attempt directory
        run_dir = self._stage_dir / "agent_runs" / f"attempt_{self._runs:03d}"
        run_dir.mkdir(parents=True, exist_ok=True)
        for fname, code in files.items():
            fpath = (run_dir / fname).resolve()
            # BUG-CA-10: Prevent path traversal from LLM-generated filenames
            if not fpath.is_relative_to(run_dir.resolve()):
                self._log_event(f"  WARNING: Skipping path-traversal filename: {fname}")
                continue
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(code, encoding="utf-8")

        # Run using the sandbox
        sandbox = self._get_or_create_sandbox()
        try:
            result = sandbox.run_project(run_dir, timeout_sec=timeout)
        except Exception as exc:
            self._log_event(f"  Sandbox run failed: {exc}")
            result = _SimpleResult(
                returncode=1,
                stdout="",
                stderr=f"Sandbox exception: {exc}",
            )

        return result

    def _extract_files(self, content: str) -> dict[str, str]:
        """Extract multi-file code blocks from LLM output."""
        # Local import to avoid circular dependency with executor.py
        from researchclaw.pipeline.executor import _extract_multi_file_blocks

        extracted = _extract_multi_file_blocks(content)
        filtered: dict[str, str] = {}
        for fname, code in extracted.items():
            upstream_error = detect_non_code_response(code)
            if upstream_error:
                self._log_event(
                    f"  WARNING: Ignoring non-code response for {fname}: "
                    f"{upstream_error}"
                )
                continue
            filtered[fname] = code
        return filtered

    @staticmethod
    def _extract_issue_filename(issue: str) -> str | None:
        match = re.search(r"\[([^\]]+\.py)\]", issue)
        if match:
            return match.group(1)
        match = re.search(r"\b([A-Za-z0-9_]+\.py)\b", issue)
        if match:
            return match.group(1)
        return None

    def _group_issues_by_file(
        self,
        issues: list[str],
        affected_files: set[str],
    ) -> dict[str, list[str]]:
        grouped = {fname: [] for fname in affected_files}
        unscoped: list[str] = []
        for issue in issues:
            fname = self._extract_issue_filename(issue)
            if fname and fname in grouped:
                grouped[fname].append(issue)
            else:
                unscoped.append(issue)
        if unscoped:
            for fname in grouped:
                grouped[fname].extend(unscoped)
        return grouped

    def _apply_local_hard_validation_repairs(
        self,
        files: dict[str, str],
    ) -> tuple[dict[str, str], list[str]]:
        from researchclaw.experiment.validator import auto_fix_unbound_locals

        merged = dict(files)
        changes: list[str] = []
        for fname, code in files.items():
            if not fname.endswith(".py"):
                continue
            fixed_code, n_fixes = auto_fix_unbound_locals(code)
            if n_fixes > 0 and fixed_code != code:
                merged[fname] = fixed_code
                changes.append(
                    f"{fname}: initialized {n_fixes} branch-scoped variable(s) "
                    "to avoid UnboundLocalError"
                )
        return merged, changes

    def _apply_issue_specific_local_repairs(
        self,
        files: dict[str, str],
        critical_issues: list[str],
    ) -> tuple[dict[str, str], list[str]]:
        merged = dict(files)
        changes: list[str] = []
        seen: set[tuple[str, str]] = set()

        for issue in critical_issues:
            match = re.search(
                r"ImportError: '([^']+)' not defined in '([^']+\.py)'",
                issue,
            )
            if not match:
                continue
            missing_name = match.group(1)
            target_file = match.group(2)
            key = (target_file, missing_name)
            if key in seen:
                continue
            seen.add(key)
            target_code = merged.get(target_file)
            if not target_code:
                continue
            fixed_code, note = self._auto_fix_missing_export(
                target_file,
                target_code,
                missing_name,
            )
            if note and fixed_code != target_code:
                merged[target_file] = fixed_code
                changes.append(note)

        return merged, changes

    @staticmethod
    def _list_top_level_names(code: str) -> set[str]:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return set()

        names: set[str] = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names.add(node.target.id)
        return names

    def _auto_fix_missing_export(
        self,
        target_file: str,
        code: str,
        missing_name: str,
    ) -> tuple[str, str | None]:
        names = self._list_top_level_names(code)
        if missing_name in names:
            return code, None

        if missing_name != "CONDITION_CLASS_REGISTRY":
            return code, None

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return code, None

        condition_classes: list[str] = []
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            if node.name == "BaseConditionStrategy":
                continue
            base_names = {
                ast.unparse(base).split(".")[-1]
                for base in node.bases
                if hasattr(ast, "unparse")
            }
            if node.name.endswith("Condition") or "BaseConditionStrategy" in base_names:
                condition_classes.append(node.name)

        if not condition_classes:
            return code, None

        registry_lines = "\n".join(
            f'    "{name}": {name},'
            for name in condition_classes
        )
        export_lines = ", ".join(
            f'"{name}"'
            for name in ["CONDITION_CLASS_REGISTRY", *condition_classes]
        )
        suffix = (
            "\n\nCONDITION_CLASS_REGISTRY = {\n"
            f"{registry_lines}\n"
            "}\n"
            "__all__ = sorted(set(list(globals().get(\"__all__\", [])) + ["
            f"{export_lines}"
            "]))\n"
        )
        return (
            code.rstrip() + suffix,
            f"{target_file}: synthesized CONDITION_CLASS_REGISTRY export for local imports",
        )

    @staticmethod
    def _parse_issue_line_numbers(
        fname: str,
        issues: list[str],
    ) -> list[int]:
        line_numbers: list[int] = []
        pattern = re.compile(rf"\[{re.escape(fname)}:(\d+)\]")
        for issue in issues:
            line_numbers.extend(int(m.group(1)) for m in pattern.finditer(issue))
        return sorted(set(line_numbers))

    @staticmethod
    def _should_use_problem_block_repair(
        fname: str,
        code: str,
        issues: list[str],
    ) -> bool:
        line_count = len(code.splitlines())
        issue_lines = CodeAgent._parse_issue_line_numbers(fname, issues)
        return line_count >= 600 or len(issue_lines) >= 2 or len(issues) >= 4

    @staticmethod
    def _collect_symbol_spans(code: str) -> list[dict[str, Any]]:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []

        parents: dict[ast.AST, str] = {}
        spans: list[dict[str, Any]] = []

        class Visitor(ast.NodeVisitor):
            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                qualname = node.name
                parent_name = parents.get(node)
                if parent_name:
                    qualname = f"{parent_name}.{node.name}"
                spans.append(
                    {
                        "kind": "class",
                        "qualname": qualname,
                        "start_line": node.lineno,
                        "end_line": getattr(node, "end_lineno", node.lineno),
                    }
                )
                for child in node.body:
                    parents[child] = qualname
                self.generic_visit(node)

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                parent_name = parents.get(node)
                qualname = f"{parent_name}.{node.name}" if parent_name else node.name
                spans.append(
                    {
                        "kind": "function",
                        "qualname": qualname,
                        "start_line": node.lineno,
                        "end_line": getattr(node, "end_lineno", node.lineno),
                    }
                )
                for child in node.body:
                    parents[child] = qualname
                self.generic_visit(node)

            visit_AsyncFunctionDef = visit_FunctionDef

        for child in tree.body:
            parents[child] = ""
        Visitor().visit(tree)
        return spans

    def _build_problem_blocks(
        self,
        fname: str,
        code: str,
        issues: list[str],
    ) -> list[dict[str, Any]]:
        lines = code.splitlines()
        issue_lines = self._parse_issue_line_numbers(fname, issues)
        spans = self._collect_symbol_spans(code)
        blocks: list[dict[str, Any]] = []

        for line_no in issue_lines:
            containing = [
                span
                for span in spans
                if span["start_line"] <= line_no <= span["end_line"]
            ]
            if containing:
                best = min(
                    containing,
                    key=lambda span: span["end_line"] - span["start_line"],
                )
                block = dict(best)
            else:
                start_line = max(1, line_no - 12)
                end_line = min(len(lines), line_no + 20)
                block = {
                    "kind": "window",
                    "qualname": f"lines_{start_line}_{end_line}",
                    "start_line": start_line,
                    "end_line": end_line,
                }
            blocks.append(block)

        if not blocks:
            blocks.append(
                {
                    "kind": "file_head",
                    "qualname": "file_head",
                    "start_line": 1,
                    "end_line": min(len(lines), 220),
                }
            )

        blocks.sort(key=lambda item: (item["start_line"], item["end_line"]))
        merged_blocks: list[dict[str, Any]] = []
        for block in blocks:
            if not merged_blocks:
                merged_blocks.append(block)
                continue
            last = merged_blocks[-1]
            if block["start_line"] <= last["end_line"] + 3:
                last["end_line"] = max(last["end_line"], block["end_line"])
                last["qualname"] = f"{last['qualname']}|{block['qualname']}"
                if last["kind"] != block["kind"]:
                    last["kind"] = "mixed"
                continue
            merged_blocks.append(block)

        for block in merged_blocks:
            start = block["start_line"] - 1
            end = block["end_line"]
            block["code"] = "\n".join(lines[start:end])
        return merged_blocks

    def _repair_file_by_problem_blocks(
        self,
        files: dict[str, str],
        fname: str,
        issues: list[str],
        arch_spec: str,
    ) -> str | None:
        code = files.get(fname)
        if not code:
            return None

        blocks = self._build_problem_blocks(fname, code, issues)
        block_specs = "\n\n".join(
            (
                f"### Block {idx + 1}: {block['qualname']}\n"
                f"- kind: {block['kind']}\n"
                f"- replace lines: {block['start_line']}-{block['end_line']}\n"
                f"```python\n{block['code']}\n```"
            )
            for idx, block in enumerate(blocks)
        )
        prompt = (
            "Your generated code has CRITICAL issues. Repair ONLY the listed "
            "problem blocks and preserve the rest of the file byte-for-byte.\n\n"
            f"## Target File\n{fname}\n\n"
            "## Critical Issues Found\n"
            + "\n".join(f"- {issue}" for issue in issues)
            + "\n\n## Architecture Blueprint\n"
            + f"{arch_spec[:2500]}\n\n"
            "## File Import/Header Context\n"
            + self._format_repair_header_context(code)
            + "\n\n## Problem Blocks\n"
            + block_specs
            + "\n\n## Other Project Files (summaries)\n"
            + self._format_file_summaries(files, exclude={fname}, max_chars=_SUMMARY_CHAR_BUDGET)
            + "\n\n## Output Format\n"
            "Return ONLY a JSON array. Each item must be:\n"
            "{\"start_line\": int, \"end_line\": int, \"replacement\": \"full replacement source\"}\n"
            "Rules:\n"
            "1. Use the exact start_line/end_line values I provided.\n"
            "2. replacement must contain the complete corrected code for that block.\n"
            "3. Do not emit unchanged blocks.\n"
            "4. Do not emit markdown fences or explanations.\n"
        )
        resp = self._chat(self._pm.system("code_generation"), prompt, max_tokens=12288)
        replacements = self._parse_replacement_array(resp.content)
        if not replacements:
            return None
        return self._apply_line_replacements(code, replacements)

    def _repair_file_with_full_context(
        self,
        files: dict[str, str],
        fname: str,
        issues: list[str],
        arch_spec: str,
        sys_prompt: str,
    ) -> str | None:
        repair_ctx = self._build_issue_focused_project_context(
            files,
            target_file=fname,
            issues=issues,
        )
        prompt = (
            "Your generated code has CRITICAL issues that will cause "
            "runtime failures or invalid results. Fix the target file only.\n\n"
            f"## Target File\n{fname}\n\n"
            "## Critical Issues Found\n"
            + "\n".join(f"- {issue}" for issue in issues)
            + "\n\n## Architecture Blueprint\n"
            + f"{arch_spec[:2500]}\n\n"
            "## Repair Context\n"
            + repair_ctx
            + "\n\n## Rules\n"
            "1. Fix every listed issue for the target file.\n"
            "2. Preserve imports/contracts required by other files.\n"
            "3. Do NOT rewrite unrelated files.\n"
            "4. Output ONLY the corrected target file in ```filename:xxx.py``` format.\n"
        )
        resp = self._chat(sys_prompt, prompt, max_tokens=12288)
        fixed = self._extract_files(resp.content)
        if not fixed and fname in files:
            single = self._extract_single_file_code(resp.content, fname)
            if single:
                fixed = {fname: single}
        return fixed.get(fname) if fixed and fname in fixed else None

    @staticmethod
    def _format_repair_header_context(code: str) -> str:
        lines = code.splitlines()
        head = "\n".join(lines[: min(len(lines), 80)])
        return f"```python\n{head}\n```"

    @staticmethod
    def _parse_replacement_array(text: str) -> list[dict[str, Any]]:
        candidates = [text.strip()]
        fenced = re.search(r"```json\s*\n(.*?)```", text, re.DOTALL)
        if fenced:
            candidates.insert(0, fenced.group(1).strip())
        for candidate in candidates:
            if not candidate:
                continue
            try:
                parsed = json.loads(candidate)
            except (json.JSONDecodeError, ValueError, TypeError):
                continue
            if isinstance(parsed, list):
                valid_items: list[dict[str, Any]] = []
                for item in parsed:
                    if (
                        isinstance(item, dict)
                        and isinstance(item.get("start_line"), int)
                        and isinstance(item.get("end_line"), int)
                        and isinstance(item.get("replacement"), str)
                    ):
                        valid_items.append(item)
                if valid_items:
                    return valid_items
        return []

    @staticmethod
    def _apply_line_replacements(
        code: str,
        replacements: list[dict[str, Any]],
    ) -> str:
        lines = code.splitlines()
        ordered = sorted(
            replacements,
            key=lambda item: (int(item["start_line"]), int(item["end_line"])),
            reverse=True,
        )
        for item in ordered:
            start_line = max(1, int(item["start_line"]))
            end_line = max(start_line, int(item["end_line"]))
            replacement_lines = str(item["replacement"]).splitlines()
            lines[start_line - 1:end_line] = replacement_lines
        return "\n".join(lines) + ("\n" if code.endswith("\n") else "")

    def _build_issue_focused_project_context(
        self,
        files: dict[str, str],
        *,
        target_file: str,
        issues: list[str],
        full_budget: int = _ISSUE_FOCUSED_FILE_CHAR_BUDGET,
    ) -> str:
        code = files.get(target_file, "")
        if not code:
            return self._build_compact_project_context(
                files,
                focus_files={target_file},
                full_file_order=[target_file],
                full_budget=full_budget,
            )

        issue_block = "\n".join(f"- {issue}" for issue in issues[:8]) or "- (no explicit issues)"
        parts = [
            "## Target File Issues\n" + issue_block,
        ]
        remaining = max(full_budget, 0)

        if self._should_use_problem_block_repair(target_file, code, issues):
            blocks = self._build_problem_blocks(target_file, code, issues)
            rendered_blocks: list[str] = []
            for idx, block in enumerate(blocks[:_ISSUE_FOCUSED_BLOCK_LIMIT]):
                snippet = self._truncate_code_for_context(
                    target_file,
                    str(block.get("code") or ""),
                    max_chars=min(remaining, 3500),
                )
                rendered = (
                    f"### Problem Block {idx + 1}: {block['qualname']}\n"
                    f"- kind: {block['kind']}\n"
                    f"- lines: {block['start_line']}-{block['end_line']}\n"
                    f"```python\n{snippet}\n```"
                )
                rendered_blocks.append(rendered)
                remaining -= len(snippet)
                if remaining <= 2000:
                    break
            if rendered_blocks:
                parts.append("## Target File Focused Context\n" + "\n\n".join(rendered_blocks))
            parts.append("## Target File Header\n" + self._format_repair_header_context(code))
        else:
            snippet = self._truncate_code_for_context(
                target_file,
                code,
                max_chars=min(remaining, full_budget),
            )
            parts.append(f"```filename:{target_file}\n{snippet}\n```")
            remaining -= len(snippet)

        summaries = self._format_file_summaries(
            files,
            exclude={target_file},
            max_chars=_SUMMARY_CHAR_BUDGET,
        )
        if summaries:
            parts.append("## Other Files Summary\n" + summaries)
        return "\n\n".join(part for part in parts if part)

    def _build_review_context(self, files: dict[str, str]) -> str:
        focus = [fname for fname in _REVIEW_FULL_FILE_ORDER if fname in files]
        return self._build_compact_project_context(
            files,
            focus_files=set(focus),
            full_file_order=focus,
            full_budget=_REVIEW_FULL_FILE_CHAR_BUDGET,
        )

    def _truncate_code_for_context(
        self,
        fname: str,
        code: str,
        *,
        max_chars: int,
    ) -> str:
        if len(code) <= max_chars:
            return code
        lines = code.splitlines()
        head = "\n".join(lines[:140])
        tail = "\n".join(lines[-60:]) if len(lines) > 60 else ""
        summary = self._build_code_summary(fname, code)
        classes = "\n".join(
            f"class {cls.get('name', '?')}({', '.join(cls.get('bases', []))})"
            for cls in summary.get("classes", [])[:20]
        ) or "(no classes)"
        functions = "\n".join(
            f"def {fn.get('name', '?')}({', '.join(fn.get('args', []))})"
            for fn in summary.get("functions", [])[:30]
        ) or "(no functions)"
        payload = (
            "# File head\n"
            f"{head}\n\n"
            "# Class summary\n"
            f"{classes}\n\n"
            "# Function summary\n"
            f"{functions}\n"
        )
        if tail:
            payload += f"\n# File tail\n{tail}\n"
        if len(payload) > max_chars:
            payload = payload[:max_chars] + "\n# ... truncated ..."
        return payload

    def _build_compact_project_context(
        self,
        files: dict[str, str],
        *,
        focus_files: set[str] | None = None,
        full_file_order: list[str] | None = None,
        full_budget: int = _REVIEW_FULL_FILE_CHAR_BUDGET,
    ) -> str:
        focus = set(focus_files or set())
        ordered_focus = list(full_file_order or [])
        ordered_focus.extend(
            fname for fname in sorted(focus) if fname not in ordered_focus and fname in files
        )
        parts: list[str] = []
        remaining = max(full_budget, 0)
        for fname in ordered_focus:
            code = files.get(fname)
            if not code:
                continue
            if remaining <= 0:
                break
            snippet = self._truncate_code_for_context(
                fname,
                code,
                max_chars=remaining,
            )
            parts.append(f"```filename:{fname}\n{snippet}\n```")
            remaining -= len(snippet)
        summaries = self._format_file_summaries(
            files,
            exclude=set(ordered_focus),
            max_chars=_SUMMARY_CHAR_BUDGET,
        )
        if summaries:
            parts.append("## Other Files Summary\n" + summaries)
        return "\n\n".join(parts)

    @staticmethod
    def _format_selected_files(
        files: dict[str, str],
        selected: list[str],
    ) -> str:
        parts = []
        for fname in selected:
            code = files.get(fname)
            if not code:
                continue
            parts.append(f"```filename:{fname}\n{code}\n```")
        return "\n\n".join(parts)

    def _format_file_summaries(
        self,
        files: dict[str, str],
        *,
        exclude: set[str] | None = None,
        max_chars: int,
    ) -> str:
        excluded = exclude or set()
        parts: list[str] = []
        used = 0
        for fname in sorted(files):
            if fname in excluded or not fname.endswith(".py"):
                continue
            summary = self._build_code_summary(fname, files[fname])
            class_names = ", ".join(
                cls.get("name", "?") for cls in summary.get("classes", [])[:6]
            ) or "none"
            function_names = ", ".join(
                fn.get("name", "?") for fn in summary.get("functions", [])[:8]
            ) or "none"
            line = (
                f"- {fname}: {len(files[fname].splitlines())} lines; "
                f"classes={class_names}; functions={function_names}"
            )
            if used + len(line) + 1 > max_chars:
                break
            parts.append(line)
            used += len(line) + 1
        return "\n".join(parts) or "(no additional files)"

    @staticmethod
    def _format_files(files: dict[str, str]) -> str:
        """Format files for inclusion in a prompt."""
        parts = []
        for fname in sorted(files):
            parts.append(f"```filename:{fname}\n{files[fname]}\n```")
        return "\n\n".join(parts)

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any] | None:
        """Best-effort JSON extraction from LLM response.

        BUG-17: Always returns ``dict | None`` — never a bare string or list,
        which would cause ``.get()`` crashes in callers.
        """
        def _as_dict(val: Any) -> dict[str, Any] | None:
            return val if isinstance(val, dict) else None

        # Direct parse
        try:
            return _as_dict(json.loads(text))
        except (json.JSONDecodeError, ValueError):
            pass
        # ```json``` fenced block
        m = re.search(r"```json\s*\n(.*?)```", text, re.DOTALL)
        if m:
            try:
                return _as_dict(json.loads(m.group(1)))
            except (json.JSONDecodeError, ValueError):
                pass
        # First {...} object (supports up to 2 levels of nesting)
        m = re.search(
            r"\{[^{}]*(?:\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}[^{}]*)*\}",
            text, re.DOTALL,
        )
        if m:
            try:
                return _as_dict(json.loads(m.group(0)))
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    def _log_event(self, msg: str) -> None:
        """Log to both Python logger and the internal validation log."""
        logger.info("[CodeAgent] %s", msg)
        self._log.append(msg)

    def _load_state(self) -> dict[str, Any]:
        if not self._state_path.exists():
            return {}
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return {}
        if isinstance(data, dict):
            files = self._load_files_from_manifest(data.get("file_manifest"))
            if files:
                data["files"] = files
            data.setdefault("phase_substate", None)
            data.setdefault("next_action", None)
            data.setdefault("blueprint_index", None)
            data.setdefault("file_index", None)
            data.setdefault("current_file", "")
            data.setdefault("repair_attempt", None)
            data.setdefault("exec_fix_iteration", None)
            data.setdefault("review_rounds_completed", 0)
            data.setdefault("last_saved_at", None)
        return data if isinstance(data, dict) else {}

    def _save_state(self, updates: dict[str, Any]) -> None:
        state = self._load_state()
        state.update(deepcopy(updates))
        files = self._files_from_state(state)
        manifest = self._persist_recovery_files(files) if files else []
        state.pop("files", None)
        state["state_schema_version"] = 2
        state["file_manifest"] = manifest
        state["last_successful_persist_at"] = time.time()
        state["last_saved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        state["llm_calls"] = self._calls
        state["sandbox_runs"] = self._runs
        state["updated_at"] = time.time()
        self._atomic_write_json(self._state_path, state)
        stage = self._infer_stage()
        if stage is not None:
            write_code_agent_control_state(
                self._stage_dir.parent,
                stage=stage,
                phase=str(state.get("phase") or ""),
                phase_substate=str(state.get("phase_substate") or ""),
                next_action=str(state.get("next_action") or ""),
                current_file=str(state.get("current_file") or ""),
                file_index=state.get("file_index") if isinstance(state.get("file_index"), int) else None,
                blueprint_index=state.get("blueprint_index") if isinstance(state.get("blueprint_index"), int) else None,
                file_manifest=manifest,
            )

    def _infer_stage(self) -> Stage | None:
        stage_name = self._stage_dir.name
        if not stage_name.startswith("stage-"):
            return None
        try:
            return Stage(int(stage_name.split("-", 1)[1]))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _files_from_state(state: dict[str, Any]) -> dict[str, str]:
        files = state.get("files")
        if not isinstance(files, dict):
            return {}
        return {
            str(name): str(content)
            for name, content in files.items()
            if isinstance(name, str) and isinstance(content, str)
        }

    def _persist_recovery_files(self, files: dict[str, str]) -> list[dict[str, Any]]:
        self._recovery_dir.mkdir(parents=True, exist_ok=True)
        manifest: list[dict[str, Any]] = []
        for name, content in sorted(files.items()):
            target = (self._recovery_dir / name).resolve()
            if not target.is_relative_to(self._recovery_dir.resolve()):
                self._log_event(f"  WARNING: skipping recovery persist for unsafe path {name}")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            data = content.encode("utf-8")
            fd, tmp_path = tempfile.mkstemp(
                dir=str(target.parent),
                prefix=f".{target.name}.",
                suffix=".tmp",
            )
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(data)
                    fh.flush()
                    os.fsync(fh.fileno())
                Path(tmp_path).replace(target)
            except BaseException:
                Path(tmp_path).unlink(missing_ok=True)
                raise
            stat = target.stat()
            manifest.append(
                {
                    "name": name,
                    "path": str(target),
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
        return manifest

    def _load_files_from_manifest(
        self, manifest: Any,
    ) -> dict[str, str]:
        if not isinstance(manifest, list):
            return {}
        restored: dict[str, str] = {}
        base = self._recovery_dir.resolve()
        for entry in manifest:
            if not isinstance(entry, dict):
                return {}
            name = entry.get("name")
            path_str = entry.get("path")
            expected_hash = entry.get("sha256")
            expected_size = entry.get("size")
            if not all(isinstance(x, str) for x in (name, path_str, expected_hash)):
                return {}
            path = Path(path_str).resolve()
            if not path.exists() or not path.is_relative_to(base):
                return {}
            try:
                raw = path.read_bytes()
                stat = path.stat()
            except OSError:
                return {}
            if isinstance(expected_size, int) and stat.st_size != expected_size:
                return {}
            if hashlib.sha256(raw).hexdigest() != expected_hash:
                return {}
            restored[name] = raw.decode("utf-8")
        return restored

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
                fh.flush()
                os.fsync(fh.fileno())
            Path(tmp_path).replace(path)
        except BaseException:
            Path(tmp_path).unlink(missing_ok=True)
            raise


# ---------------------------------------------------------------------------
# Lightweight result stand-in for error plumbing
# ---------------------------------------------------------------------------


@dataclass
class _SimpleResult:
    """Minimal sandbox result for internal error plumbing."""

    returncode: int = 1
    stdout: str = ""
    stderr: str = ""
    elapsed_sec: float = 0.0
    metrics: dict[str, object] = field(default_factory=dict)
    timed_out: bool = False
