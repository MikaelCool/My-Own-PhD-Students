from __future__ import annotations

import json
import logging
import math
import re
import time as _time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from researchclaw.adapters import AdapterBundle
from researchclaw.config import RCConfig
from researchclaw.hardware import HardwareProfile, detect_hardware, ensure_torch_available, is_metric_name
from researchclaw.llm import create_llm_client
from researchclaw.llm.client import LLMClient
from researchclaw.prompts import PromptManager
from researchclaw.pipeline.stages import (
    NEXT_STAGE,
    Stage,
    StageStatus,
    TransitionEvent,
    TransitionOutcome,
    advance,
    gate_required,
)
from researchclaw.pipeline.contracts import CONTRACTS, StageContract
from researchclaw.experiment.validator import (
    CodeValidation,
    format_issues_for_llm,
    validate_code,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain detection (extracted to _domain.py)
# ---------------------------------------------------------------------------
from researchclaw.pipeline._domain import (  # noqa: E402
    _DOMAIN_KEYWORDS,
    _detect_domain,
    _is_ml_domain,
)


# ---------------------------------------------------------------------------
# Shared helpers (extracted to _helpers.py)
# ---------------------------------------------------------------------------
from researchclaw.pipeline._helpers import (  # noqa: E402
    StageResult,
    _METACLAW_SKILLS_DIR,
    _SANDBOX_SAFE_PACKAGES,
    _STOP_WORDS,
    _build_context_preamble,
    _build_fallback_queries,
    _chat_with_prompt,
    _collect_experiment_results,
    _collect_json_context,
    _default_hypotheses,
    _default_paper_outline,
    _default_quality_report,
    _detect_runtime_issues,
    _ensure_sandbox_deps,
    _extract_code_block,
    _extract_multi_file_blocks,
    _extract_paper_title,
    _extract_topic_keywords,
    _extract_yaml_block,
    _find_prior_file,
    _generate_framework_diagram_prompt,
    _generate_neurips_checklist,
    _get_evolution_overlay,
    _load_hardware_profile,
    _multi_perspective_generate,
    _parse_jsonl_rows,
    _parse_metrics_from_stdout,
    _read_prior_artifact,
    _safe_filename,
    _safe_json_loads,
    _synthesize_perspectives,
    _topic_constraint_block,
    _utcnow_iso,
    _write_jsonl,
    _write_stage_meta,
    reconcile_figure_refs,
)

# ---------------------------------------------------------------------------
# Stages 1-2 (extracted to stage_impls/_topic.py)
# ---------------------------------------------------------------------------
from researchclaw.pipeline.stage_impls._topic import (  # noqa: E402
    _execute_topic_init,
    _execute_problem_decompose,
)

# ---------------------------------------------------------------------------
# Stages 3-6 (extracted to stage_impls/_literature.py)
# ---------------------------------------------------------------------------
from researchclaw.pipeline.stage_impls._literature import (  # noqa: E402
    _execute_search_strategy,
    _execute_literature_collect,
    _execute_literature_screen,
    _execute_knowledge_extract,
    _expand_search_queries,
)

# ---------------------------------------------------------------------------
# Stages 7-8 (extracted to stage_impls/_synthesis.py)
# ---------------------------------------------------------------------------
from researchclaw.pipeline.stage_impls._synthesis import (  # noqa: E402
    _execute_synthesis,
    _execute_hypothesis_gen,
)

# ---------------------------------------------------------------------------
# Stage 9 (extracted to stage_impls/_experiment_design.py)
# ---------------------------------------------------------------------------
from researchclaw.pipeline.stage_impls._experiment_design import (  # noqa: E402
    _execute_experiment_design,
)

# ---------------------------------------------------------------------------
# Stage 10 (extracted to stage_impls/_code_generation.py)
# ---------------------------------------------------------------------------
from researchclaw.pipeline.stage_impls._code_generation import (  # noqa: E402
    _execute_code_generation,
)

# ---------------------------------------------------------------------------
# Stages 11-13 (extracted to stage_impls/_execution.py)
# ---------------------------------------------------------------------------
from researchclaw.pipeline.stage_impls._execution import (  # noqa: E402
    _execute_resource_planning,
    _execute_experiment_run,
    _execute_iterative_refine,
)

# ---------------------------------------------------------------------------
# Stages 14-15 (extracted to stage_impls/_analysis.py)
# ---------------------------------------------------------------------------
from researchclaw.pipeline.stage_impls._analysis import (  # noqa: E402
    _execute_result_analysis,
    _parse_decision,
    _execute_research_decision,
)

# ---------------------------------------------------------------------------
# Stages 16-17 (extracted to stage_impls/_paper_writing.py)
# ---------------------------------------------------------------------------
from researchclaw.pipeline.stage_impls._paper_writing import (  # noqa: E402
    _execute_paper_outline,
    _execute_paper_draft,
    _collect_raw_experiment_metrics,
    _write_paper_sections,
    _validate_draft_quality,
    _review_compiled_pdf,
    _check_ablation_effectiveness,
    _detect_result_contradictions,
    _BULLET_LENIENT_SECTIONS,
    _BALANCE_SECTIONS,
)

# ---------------------------------------------------------------------------
# Stages 18-23 (extracted to stage_impls/_review_publish.py)
# ---------------------------------------------------------------------------
from researchclaw.pipeline.stage_impls._review_publish import (  # noqa: E402
    _execute_peer_review,
    _execute_paper_revision,
    _execute_quality_gate,
    _execute_knowledge_archive,
    _execute_export_publish,
    _execute_citation_verify,
    _sanitize_fabricated_data,
    _collect_experiment_evidence,
    _check_citation_relevance,
    _remove_bibtex_entries,
    _remove_citations_from_text,
)


_STAGE_EXECUTORS: dict[Stage, Callable[..., StageResult]] = {
    Stage.TOPIC_INIT: _execute_topic_init,
    Stage.PROBLEM_DECOMPOSE: _execute_problem_decompose,
    Stage.SEARCH_STRATEGY: _execute_search_strategy,
    Stage.LITERATURE_COLLECT: _execute_literature_collect,
    Stage.LITERATURE_SCREEN: _execute_literature_screen,
    Stage.KNOWLEDGE_EXTRACT: _execute_knowledge_extract,
    Stage.SYNTHESIS: _execute_synthesis,
    Stage.HYPOTHESIS_GEN: _execute_hypothesis_gen,
    Stage.EXPERIMENT_DESIGN: _execute_experiment_design,
    Stage.CODE_GENERATION: _execute_code_generation,
    Stage.RESOURCE_PLANNING: _execute_resource_planning,
    Stage.EXPERIMENT_RUN: _execute_experiment_run,
    Stage.ITERATIVE_REFINE: _execute_iterative_refine,
    Stage.RESULT_ANALYSIS: _execute_result_analysis,
    Stage.RESEARCH_DECISION: _execute_research_decision,
    Stage.PAPER_OUTLINE: _execute_paper_outline,
    Stage.PAPER_DRAFT: _execute_paper_draft,
    Stage.PEER_REVIEW: _execute_peer_review,
    Stage.PAPER_REVISION: _execute_paper_revision,
    Stage.QUALITY_GATE: _execute_quality_gate,
    Stage.KNOWLEDGE_ARCHIVE: _execute_knowledge_archive,
    Stage.EXPORT_PUBLISH: _execute_export_publish,
    Stage.CITATION_VERIFY: _execute_citation_verify,
}

_STAGE_NOTIFICATION_GUIDANCE: dict[Stage, dict[str, tuple[str, ...]]] = {
    Stage.TOPIC_INIT: {
        "done": (
            "Locked the research topic, scope, and operating constraints.",
        ),
        "innovation": (
            "Front-loads topic constraints so later novelty claims stay grounded.",
        ),
        "advantages": (
            "Reduces scope drift before literature and experiment work begin.",
        ),
    },
    Stage.PROBLEM_DECOMPOSE: {
        "done": (
            "Decomposed the topic into sub-problems, questions, and anchors.",
        ),
        "innovation": (
            "Turns a vague idea into testable problem slices instead of one broad prompt.",
        ),
        "advantages": (
            "Improves downstream search coverage and experiment alignment.",
        ),
    },
    Stage.SEARCH_STRATEGY: {
        "done": (
            "Prepared the literature search plan and source priority.",
        ),
        "innovation": (
            "Prioritizes curated knowledge sources before loose seed files.",
        ),
        "advantages": (
            "Raises relevance and lowers noise in the collected evidence base.",
        ),
    },
    Stage.LITERATURE_COLLECT: {
        "done": (
            "Collected papers, notes, and seed documents into a unified pool.",
        ),
        "innovation": (
            "Blends Zotero, Obsidian, and local seeds into one intake path.",
        ),
        "advantages": (
            "Produces a stronger evidence base for novelty and baseline analysis.",
        ),
    },
    Stage.LITERATURE_SCREEN: {
        "done": (
            "Screened candidate literature for relevance and quality.",
        ),
        "innovation": (
            "Applies stage gates before weak sources contaminate later reasoning.",
        ),
        "advantages": (
            "Improves citation quality and reduces hallucinated framing.",
        ),
    },
    Stage.KNOWLEDGE_EXTRACT: {
        "done": (
            "Extracted structured facts, methods, and limitations from the literature.",
        ),
        "innovation": (
            "Converts papers into reusable knowledge blocks instead of raw text.",
        ),
        "advantages": (
            "Makes synthesis, gap finding, and hypothesis generation more reliable.",
        ),
    },
    Stage.SYNTHESIS: {
        "done": (
            "Synthesized literature into gaps, tensions, and candidate directions.",
        ),
        "innovation": (
            "Forces explicit gap articulation before claiming contribution.",
        ),
        "advantages": (
            "Improves novelty quality and prevents shallow topic rewording.",
        ),
    },
    Stage.HYPOTHESIS_GEN: {
        "done": (
            "Generated hypotheses and candidate contribution directions.",
        ),
        "innovation": (
            "Pushes the pipeline toward testable claims instead of generic ideas.",
        ),
        "advantages": (
            "Gives later experiment design a concrete claim structure to validate.",
        ),
    },
    Stage.EXPERIMENT_DESIGN: {
        "done": (
            "Designed the experiment plan, baselines, ablations, and success criteria.",
        ),
        "innovation": (
            "Uses a claims-evidence matrix to bind novelty to measurable support.",
        ),
        "advantages": (
            "Makes unsupported contributions easier to catch before paper writing.",
        ),
    },
    Stage.CODE_GENERATION: {
        "done": (
            "Generated executable experiment code and supporting files.",
        ),
        "innovation": (
            "Keeps generated code tied to the validated experiment plan.",
        ),
        "advantages": (
            "Improves implementation consistency and reduces off-topic experiments.",
        ),
    },
    Stage.RESOURCE_PLANNING: {
        "done": (
            "Estimated runtime, compute needs, and execution strategy.",
        ),
        "innovation": (
            "Matches experiment ambition to practical compute constraints early.",
        ),
        "advantages": (
            "Reduces failed runs caused by unrealistic resource assumptions.",
        ),
    },
    Stage.EXPERIMENT_RUN: {
        "done": (
            "Executed the experiment suite and collected primary metrics.",
        ),
        "innovation": (
            "Uses real execution results instead of paper-only speculation.",
        ),
        "advantages": (
            "Creates the evidence base needed for trustworthy analysis.",
        ),
    },
    Stage.ITERATIVE_REFINE: {
        "done": (
            "Refined the implementation and reran experiments based on failures or weak results.",
        ),
        "innovation": (
            "Closes the loop between runtime feedback and code updates.",
        ),
        "advantages": (
            "Improves robustness and gives the method another chance to beat baselines.",
        ),
    },
    Stage.RESULT_ANALYSIS: {
        "done": (
            "Analyzed experiment outputs and converted results into claims.",
        ),
        "innovation": (
            "Checks whether results genuinely support the proposed contribution.",
        ),
        "advantages": (
            "Catches weak evidence before it gets baked into the paper draft.",
        ),
    },
    Stage.RESEARCH_DECISION: {
        "done": (
            "Decided whether to proceed, refine, or pivot.",
        ),
        "innovation": (
            "Allows the pipeline to downgrade or rework claims when evidence is weak.",
        ),
        "advantages": (
            "Prevents low-quality ideas from cruising into the writing stage unchecked.",
        ),
    },
    Stage.PAPER_OUTLINE: {
        "done": (
            "Outlined the manuscript structure and evidence flow.",
        ),
        "innovation": (
            "Aligns paper structure with verified evidence and contribution logic.",
        ),
        "advantages": (
            "Makes the final draft easier to revise under reviewer pressure.",
        ),
    },
    Stage.PAPER_DRAFT: {
        "done": (
            "Drafted the paper from the validated experiment and analysis artifacts.",
        ),
        "innovation": (
            "Keeps the manuscript grounded in stage outputs rather than free-form generation.",
        ),
        "advantages": (
            "Reduces fabricated claims and improves traceability to evidence.",
        ),
    },
    Stage.PEER_REVIEW: {
        "done": (
            "Ran a reviewer-style audit over the current paper state.",
        ),
        "innovation": (
            "Scores the draft against venue-aware review expectations.",
        ),
        "advantages": (
            "Makes revision needs visible before final export.",
        ),
    },
    Stage.PAPER_REVISION: {
        "done": (
            "Revised the manuscript based on review findings.",
        ),
        "innovation": (
            "Treats reviewer comments as structured work items instead of vague feedback.",
        ),
        "advantages": (
            "Improves paper quality in a measurable loop rather than one-shot writing.",
        ),
    },
    Stage.QUALITY_GATE: {
        "done": (
            "Checked whether the draft clears the configured quality bar.",
        ),
        "innovation": (
            "Uses score thresholds and venue expectations as explicit gates.",
        ),
        "advantages": (
            "Stops weak drafts from being exported as if they were submission-ready.",
        ),
    },
    Stage.KNOWLEDGE_ARCHIVE: {
        "done": (
            "Archived artifacts, lessons, and reusable run knowledge.",
        ),
        "innovation": (
            "Preserves operational learning instead of throwing run history away.",
        ),
        "advantages": (
            "Improves future runs through memory and reusable skills.",
        ),
    },
    Stage.EXPORT_PUBLISH: {
        "done": (
            "Packaged deliverables and exported the paper for external use.",
        ),
        "innovation": (
            "Converts the internal markdown-first workflow into final publication assets.",
        ),
        "advantages": (
            "Produces a cleaner handoff for Overleaf, review, and release workflows.",
        ),
    },
    Stage.CITATION_VERIFY: {
        "done": (
            "Verified citation integrity and pruned low-confidence references.",
        ),
        "innovation": (
            "Adds a final citation sanity check after writing and export.",
        ),
        "advantages": (
            "Reduces the risk of fabricated or irrelevant references in the final paper.",
        ),
    },
}


def _notify_enabled(config: RCConfig) -> bool:
    channel = str(getattr(config.notifications, "channel", "") or "").strip().lower()
    target = str(getattr(config.notifications, "target", "") or "").strip()
    return bool(config.openclaw_bridge.use_message or (target and channel not in {"", "console", "local"}))


def _safe_notify(
    adapters: AdapterBundle,
    config: RCConfig,
    *,
    subject: str,
    body: str,
) -> None:
    if not _notify_enabled(config):
        return
    try:
        adapters.message.notify(config.notifications.channel, subject, body)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Notification failed for %s: %s", subject, exc)


def _read_textish_artifact(path: Path) -> str:
    if path.suffix.lower() in {".md", ".txt", ".yaml", ".yml", ".json"}:
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""
    return ""


def _extract_markdownish_lines(text: str, *, keywords: tuple[str, ...], limit: int) -> list[str]:
    seen: set[str] = set()
    matches: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        normalized = line.lstrip("#*-0123456789. ").strip()
        if len(normalized) < 12 or len(normalized) > 180:
            continue
        lower = normalized.lower()
        if keywords and not any(keyword in lower for keyword in keywords):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        matches.append(normalized)
        if len(matches) >= limit:
            break
    return matches


def _artifact_snippets(stage_dir: Path, artifacts: tuple[str, ...], *, limit: int = 2) -> list[str]:
    snippets: list[str] = []
    for artifact in artifacts:
        text = _read_textish_artifact(stage_dir / artifact)
        if not text:
            continue
        snippets.extend(
            _extract_markdownish_lines(
                text,
                keywords=(),
                limit=max(1, limit - len(snippets)),
            )
        )
        if len(snippets) >= limit:
            break
    return snippets[:limit]


def _signal_lines(
    stage_dir: Path,
    artifacts: tuple[str, ...],
    *,
    keywords: tuple[str, ...],
    limit: int = 2,
) -> list[str]:
    lines: list[str] = []
    for artifact in artifacts:
        text = _read_textish_artifact(stage_dir / artifact)
        if not text:
            continue
        lines.extend(
            _extract_markdownish_lines(
                text,
                keywords=keywords,
                limit=max(1, limit - len(lines)),
            )
        )
        if len(lines) >= limit:
            break
    return lines[:limit]


def _build_stage_completion_body(
    *,
    stage: Stage,
    stage_dir: Path,
    run_id: str,
    result: StageResult,
    duration_sec: float,
) -> str:
    guidance = _STAGE_NOTIFICATION_GUIDANCE.get(stage, {})
    artifact_list = ", ".join(result.artifacts[:4]) if result.artifacts else "no explicit artifacts"
    what_done = list(guidance.get("done", (f"Completed {stage.name.lower()} and wrote stage outputs.",)))
    what_done.extend(_artifact_snippets(stage_dir, result.artifacts))
    innovations = list(guidance.get("innovation", ("Strengthened the novelty/evidence loop for this stage.",)))
    innovations.extend(
        _signal_lines(
            stage_dir,
            result.artifacts,
            keywords=("novel", "innovation", "contribution", "hypothesis", "claim", "gap", "baseline", "venue"),
        )
    )
    advantages = list(guidance.get("advantages", ("Improved pipeline traceability and execution quality.",)))
    advantages.extend(
        _signal_lines(
            stage_dir,
            result.artifacts,
            keywords=("advantage", "benefit", "improv", "outperform", "score", "quality", "evidence", "coverage", "robust"),
        )
    )
    what_done = list(dict.fromkeys(what_done))[:3]
    innovations = list(dict.fromkeys(innovations))[:3]
    advantages = list(dict.fromkeys(advantages))[:3]
    body_lines = [
        f"Run: {run_id}",
        f"Stage {int(stage):02d} {stage.name} completed in {duration_sec:.2f}s.",
        f"Artifacts: {artifact_list}",
        f"Decision: {result.decision}",
        "",
        "What was done:",
    ]
    body_lines.extend(f"- {line}" for line in what_done)
    body_lines.append("")
    body_lines.append("Innovation:")
    body_lines.extend(f"- {line}" for line in innovations)
    body_lines.append("")
    body_lines.append("Advantages:")
    body_lines.extend(f"- {line}" for line in advantages)
    return "\n".join(body_lines)


def _build_stage_failure_body(
    *,
    stage: Stage,
    run_id: str,
    result: StageResult,
) -> str:
    return "\n".join(
        [
            f"Run: {run_id}",
            f"Stage {int(stage):02d} {stage.name} failed.",
            f"Decision: {result.decision}",
            f"Error: {result.error or 'unknown error'}",
        ]
    )


def execute_stage(
    stage: Stage,
    *,
    run_dir: Path,
    run_id: str,
    config: RCConfig,
    adapters: AdapterBundle,
    auto_approve_gates: bool = False,
) -> StageResult:
    """Execute one pipeline stage, validate outputs, and apply gate logic."""

    stage_dir = run_dir / f"stage-{int(stage):02d}"
    stage_dir.mkdir(parents=True, exist_ok=True)
    _t_health_start = _time.monotonic()
    contract: StageContract = CONTRACTS[stage]

    if contract.input_files:
        for input_file in contract.input_files:
            found = _read_prior_artifact(run_dir, input_file)
            if found is None:
                result = StageResult(
                    stage=stage,
                    status=StageStatus.FAILED,
                    artifacts=(),
                    error=f"Missing input: {input_file} (required by {stage.name})",
                    decision="retry",
                )
                _write_stage_meta(stage_dir, stage, run_id, result)
                return result

    bridge = config.openclaw_bridge
    if config.notifications.on_stage_start:
        _safe_notify(
            adapters,
            config,
            subject=f"stage-{int(stage):02d}-start",
            body=f"Starting {stage.name}",
        )
    if bridge.use_memory:
        adapters.memory.append("stages", f"{run_id}:{int(stage)}:running")

    llm = None
    try:
        if config.llm.provider == "acp":
            llm = create_llm_client(config)
        else:
            candidate = LLMClient.from_rc_config(config)
            if candidate.config.base_url and candidate.config.api_key:
                llm = candidate
    except Exception as _llm_exc:  # noqa: BLE001
        logger.warning("LLM client creation failed: %s", _llm_exc)
        llm = None

    try:
        _ = advance(stage, StageStatus.PENDING, TransitionEvent.START)
        executor = _STAGE_EXECUTORS[stage]
        prompts = PromptManager(config.prompts.custom_file or None)  # type: ignore[attr-defined]
        try:
            result = executor(
                stage_dir, run_dir, config, adapters, llm=llm, prompts=prompts
            )
        except TypeError as exc:
            if "unexpected keyword argument 'prompts'" not in str(exc):
                raise
            result = executor(stage_dir, run_dir, config, adapters, llm=llm)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Stage %s failed", stage.name)
        result = StageResult(
            stage=stage,
            status=StageStatus.FAILED,
            artifacts=(),
            error=str(exc),
            decision="retry",
        )

    if result.status == StageStatus.DONE:
        for output_file in contract.output_files:
            if output_file.endswith("/"):
                path = stage_dir / output_file.rstrip("/")
                if not path.is_dir() or not any(path.iterdir()):
                    result = StageResult(
                        stage=stage,
                        status=StageStatus.FAILED,
                        artifacts=result.artifacts,
                        error=f"Missing output directory: {output_file}",
                        decision="retry",
                        evidence_refs=result.evidence_refs,
                    )
                    break
            else:
                path = stage_dir / output_file
                if not path.exists() or path.stat().st_size == 0:
                    result = StageResult(
                        stage=stage,
                        status=StageStatus.FAILED,
                        artifacts=result.artifacts,
                        error=f"Missing or empty output: {output_file}",
                        decision="retry",
                        evidence_refs=result.evidence_refs,
                    )
                    break

    # --- MetaClaw PRM quality gate evaluation ---
    try:
        mc_bridge = getattr(config, "metaclaw_bridge", None)
        if (
            mc_bridge
            and getattr(mc_bridge, "enabled", False)
            and result.status == StageStatus.DONE
        ):
            mc_prm = getattr(mc_bridge, "prm", None)
            if mc_prm and getattr(mc_prm, "enabled", False):
                prm_stages = getattr(mc_prm, "gate_stages", (5, 9, 15, 20))
                if int(stage) in prm_stages:
                    from researchclaw.metaclaw_bridge.prm_gate import ResearchPRMGate

                    prm_gate = ResearchPRMGate.from_bridge_config(mc_prm)
                    if prm_gate is not None:
                        # Read stage output for PRM evaluation
                        output_text = ""
                        for art in result.artifacts:
                            art_path = stage_dir / art
                            if art_path.exists() and art_path.is_file():
                                try:
                                    output_text += art_path.read_text(encoding="utf-8")[:4000]
                                except (UnicodeDecodeError, OSError):
                                    pass
                        if output_text:
                            prm_score = prm_gate.evaluate_stage(int(stage), output_text)
                            logger.info(
                                "MetaClaw PRM score for stage %d: %.1f",
                                int(stage),
                                prm_score,
                            )
                            # Write PRM score to stage health
                            import json as _prm_json

                            prm_report = {
                                "stage": int(stage),
                                "prm_score": prm_score,
                                "model": prm_gate.model,
                                "votes": prm_gate.votes,
                            }
                            (stage_dir / "prm_score.json").write_text(
                                _prm_json.dumps(prm_report, indent=2),
                                encoding="utf-8",
                            )
                            # If PRM score is -1 (fail), mark stage as failed
                            if prm_score == -1.0:
                                logger.warning(
                                    "MetaClaw PRM rejected stage %d output",
                                    int(stage),
                                )
                                result = StageResult(
                                    stage=result.stage,
                                    status=StageStatus.FAILED,
                                    artifacts=result.artifacts,
                                    error="PRM quality gate: output below quality threshold",
                                    decision="retry",
                                    evidence_refs=result.evidence_refs,
                                )
    except Exception:  # noqa: BLE001
        logger.warning("MetaClaw PRM evaluation failed (non-blocking)")

    if gate_required(stage, config.security.hitl_required_stages):
        if auto_approve_gates:
            if bridge.use_memory:
                adapters.memory.append("gates", f"{run_id}:{int(stage)}:auto-approved")
        else:
            result = StageResult(
                stage=result.stage,
                status=StageStatus.BLOCKED_APPROVAL,
                artifacts=result.artifacts,
                error=result.error,
                decision="block",
                evidence_refs=result.evidence_refs,
            )
            if config.notifications.on_gate_required:
                _safe_notify(
                    adapters,
                    config,
                    subject=f"gate-{int(stage):02d}",
                    body=f"Approval required for {stage.name}",
                )

    if bridge.use_memory:
        adapters.memory.append("stages", f"{run_id}:{int(stage)}:{result.status.value}")

    _write_stage_meta(stage_dir, stage, run_id, result)

    _t_health_end = _time.monotonic()
    stage_health = {
        "stage_id": f"{int(stage):02d}-{stage.name.lower()}",
        "run_id": run_id,
        "duration_sec": round(_t_health_end - _t_health_start, 2),
        "status": result.status.value,
        "artifacts_count": len(result.artifacts),
        "error": result.error,
        "timestamp": _utcnow_iso(),
    }
    try:
        (stage_dir / "stage_health.json").write_text(
            json.dumps(stage_health, indent=2), encoding="utf-8"
        )
    except OSError:
        pass

    if result.status == StageStatus.DONE and config.notifications.on_stage_complete:
        _safe_notify(
            adapters,
            config,
            subject=f"stage-{int(stage):02d}-complete",
            body=_build_stage_completion_body(
                stage=stage,
                stage_dir=stage_dir,
                run_id=run_id,
                result=result,
                duration_sec=stage_health["duration_sec"],
            ),
        )
    elif result.status == StageStatus.FAILED and config.notifications.on_stage_fail:
        _safe_notify(
            adapters,
            config,
            subject=f"stage-{int(stage):02d}-fail",
            body=_build_stage_failure_body(stage=stage, run_id=run_id, result=result),
        )

    return result
