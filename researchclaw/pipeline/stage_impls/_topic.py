"""Stages 1-2: Topic initialization and problem decomposition."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from researchclaw.adapters import AdapterBundle
from researchclaw.config import RCConfig
from researchclaw.hardware import detect_hardware, ensure_torch_available
from researchclaw.llm.client import LLMClient
from researchclaw.pipeline._domain import _detect_domain
from researchclaw.pipeline._helpers import (
    StageResult,
    _build_startup_contract_block,
    _get_evolution_overlay,
    _load_baseline_briefing,
    _read_prior_artifact,
    _safe_json_loads,
    _utcnow_iso,
)
from researchclaw.pipeline.stages import Stage, StageStatus
from researchclaw.prompts import PromptManager

logger = logging.getLogger(__name__)


def _fallback_problem_anchor(
    topic: str,
    goal_text: str,
    problem_tree: str,
    baseline_briefing: str,
) -> str:
    baseline_present = "Yes" if baseline_briefing.strip() else "No"
    return f"""# Problem Anchor

## Core Question
Which algorithmic weakness in the current baseline family is most worth attacking for `{topic}`?

## Dominant Contribution
Deliver one main method contribution and at most two supporting innovations; avoid workflow or engineering polish as claimed novelty.

## Baseline Gap
- Baseline briefing provided: {baseline_present}
- The proposed work must identify a concrete failure mode, limiting assumption, or missing theoretical mechanism in the baseline.

## Proof Obligations
- State what must be shown theoretically or mechanistically.
- State what evidence would falsify the main claim.

## Experimental Obligations
- Reproduce baseline settings fairly before claiming gains.
- Compare against strong baselines on the same metrics and regimes.
- Include at least one failure-case or boundary-condition check.

## Non-Goals
- No pure system optimization, prompt tinkering, or infrastructure contributions.
- No broad superiority claims without direct evidence.

## Source Context
### Goal
{goal_text[:1400]}

### Problem Tree
{problem_tree[:1400]}

## Generated
{_utcnow_iso()}
"""


def _execute_topic_init(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    topic = config.research.topic
    domains = (
        ", ".join(config.research.domains) if config.research.domains else "general"
    )
    if llm is not None:
        _pm = prompts or PromptManager()
        _overlay = "\n".join(
            part
            for part in (
                _get_evolution_overlay(run_dir, "topic_init"),
                _build_startup_contract_block(run_dir, stage_name="topic_init"),
            )
            if part
        )
        sp = _pm.for_stage(
            "topic_init",
            evolution_overlay=_overlay,
            topic=topic,
            domains=domains,
            baseline_briefing=_load_baseline_briefing(config),
            project_name=config.project.name,
            quality_threshold=config.research.quality_threshold,
        )
        resp = llm.chat(
            [{"role": "user", "content": sp.user}],
            system=sp.system,
        )
        goal_md = resp.content
    else:
        goal_md = f"""# Research Goal

## Topic
{topic}

## Scope
Investigate the topic with emphasis on reproducible methods and measurable outcomes.

## SMART Goal
- Specific: Build a focused research plan for {topic}
- Measurable: Produce literature shortlist, hypotheses, experiment plan, and final paper
- Achievable: Complete through staged pipeline with gate checks
- Relevant: Aligned with project {config.project.name}
- Time-bound: Constrained by pipeline execution budget

## Constraints
- Quality threshold: {config.research.quality_threshold}
- Daily paper target: {config.research.daily_paper_count}

## Success Criteria
- At least 2 falsifiable hypotheses
- Executable experiment code and results analysis
- Revised paper passing quality gate

## Generated
{_utcnow_iso()}
"""
    (stage_dir / "goal.md").write_text(goal_md, encoding="utf-8")

    # --- Hardware detection (GPU / MPS / CPU) ---
    hw = detect_hardware()
    (stage_dir / "hardware_profile.json").write_text(
        json.dumps(hw.to_dict(), indent=2), encoding="utf-8"
    )
    if hw.warning:
        logger.warning("Hardware advisory: %s", hw.warning)
    else:
        logger.info("Hardware detected: %s (%s, %s MB VRAM)", hw.gpu_name, hw.gpu_type, hw.vram_mb)

    # --- Optionally ensure PyTorch is available ---
    if hw.has_gpu and config.experiment.mode == "sandbox":
        torch_ok = ensure_torch_available(config.experiment.sandbox.python_path, hw.gpu_type)
        if torch_ok:
            logger.info("PyTorch is available for sandbox experiments")
        else:
            logger.warning("PyTorch could not be installed; sandbox will use CPU-only packages")
    elif hw.has_gpu and config.experiment.mode == "docker":
        logger.info("Docker sandbox: PyTorch pre-installed in container image")

    return StageResult(
        stage=Stage.TOPIC_INIT,
        status=StageStatus.DONE,
        artifacts=("goal.md", "hardware_profile.json"),
        evidence_refs=("stage-01/goal.md", "stage-01/hardware_profile.json"),
    )


def _execute_problem_decompose(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    goal_text = _read_prior_artifact(run_dir, "goal.md") or ""
    baseline_briefing = _load_baseline_briefing(config)
    _pm = prompts or PromptManager()
    if llm is not None:
        _overlay = "\n".join(
            part
            for part in (
                _get_evolution_overlay(run_dir, "problem_decompose"),
                _build_startup_contract_block(run_dir, stage_name="problem_decompose"),
            )
            if part
        )
        sp = _pm.for_stage(
            "problem_decompose",
            evolution_overlay=_overlay,
            topic=config.research.topic,
            goal_text=goal_text,
            baseline_briefing=baseline_briefing,
        )
        resp = llm.chat(
            [{"role": "user", "content": sp.user}],
            system=sp.system,
        )
        body = resp.content
    else:
        body = f"""# Problem Decomposition

## Source
Derived from `goal.md` for topic: {config.research.topic}

## Sub-questions
1. Which problem settings and benchmarks define current SOTA?
2. Which methodological gaps remain unresolved?
3. Which hypotheses are testable under realistic constraints?
4. Which datasets and metrics best discriminate method quality?
5. Which failure modes can invalidate expected gains?

## Priority Ranking
1. Problem framing and benchmark setup
2. Gap identification and hypothesis formulation
3. Experiment and metric design
4. Failure analysis and robustness checks

## Risks
- Ambiguous task definition
- Dataset leakage or metric mismatch

## Generated
{_utcnow_iso()}
"""
    (stage_dir / "problem_tree.md").write_text(body, encoding="utf-8")

    if llm is not None:
        _anchor_overlay = "\n".join(
            part
            for part in (
                _get_evolution_overlay(run_dir, "problem_decompose"),
                _build_startup_contract_block(run_dir, stage_name="problem_decompose"),
            )
            if part
        )
        _anchor_prompt = _pm.for_stage(
            "problem_anchor",
            evolution_overlay=_anchor_overlay,
            topic=config.research.topic,
            goal_text=goal_text,
            problem_tree=body,
            baseline_briefing=baseline_briefing,
        )
        _anchor_resp = llm.chat(
            [{"role": "user", "content": _anchor_prompt.user}],
            system=_anchor_prompt.system,
        )
        problem_anchor = _anchor_resp.content
    else:
        problem_anchor = _fallback_problem_anchor(
            config.research.topic,
            goal_text,
            body,
            baseline_briefing,
        )
    (stage_dir / "problem_anchor.md").write_text(problem_anchor, encoding="utf-8")

    # IMP-35: Topic/title quality pre-evaluation
    # Quick LLM check: is the topic well-scoped for a conference paper?
    if llm is not None:
        try:
            _eval_resp = llm.chat(
                [
                    {
                        "role": "user",
                        "content": (
                            "Evaluate this research topic for a top ML conference paper. "
                            "Score 1-10 on: (a) novelty, (b) specificity, (c) feasibility. "
                            "If overall score < 5, suggest a refined topic.\n\n"
                            f"Topic: {config.research.topic}\n\n"
                            "Reply as JSON: {\"novelty\": N, \"specificity\": N, "
                            "\"feasibility\": N, \"overall\": N, \"suggestion\": \"...\"}"
                        ),
                    }
                ],
                system=(
                    f"You are a senior {_detect_domain(config.research.topic, config.research.domains)[1]} "
                    f"researcher evaluating research topic quality."
                ),
            )
            _eval_data = _safe_json_loads(_eval_resp.content, {})
            if isinstance(_eval_data, dict):
                overall = _eval_data.get("overall", 10)
                if isinstance(overall, (int, float)) and overall < 5:
                    logger.warning(
                        "IMP-35: Topic quality score %s/10 — consider refining: %s",
                        overall,
                        _eval_data.get("suggestion", ""),
                    )
                else:
                    logger.info("IMP-35: Topic quality score %s/10", overall)
                (stage_dir / "topic_evaluation.json").write_text(
                    json.dumps(_eval_data, indent=2), encoding="utf-8"
                )
        except Exception:  # noqa: BLE001
            logger.debug("IMP-35: Topic evaluation skipped (non-blocking)")

    return StageResult(
        stage=Stage.PROBLEM_DECOMPOSE,
        status=StageStatus.DONE,
        artifacts=("problem_tree.md", "problem_anchor.md"),
        evidence_refs=("stage-02/problem_tree.md", "stage-02/problem_anchor.md"),
    )
