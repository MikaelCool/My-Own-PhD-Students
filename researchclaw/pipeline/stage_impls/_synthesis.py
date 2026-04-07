"""Stages 7-8: Synthesis and hypothesis generation."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from researchclaw.adapters import AdapterBundle
from researchclaw.config import RCConfig
from researchclaw.llm.client import LLMClient
from researchclaw.pipeline._helpers import (
    StageResult,
    _default_hypotheses,
    _get_evolution_overlay,
    _load_baseline_briefing,
    _multi_perspective_generate,
    _parse_jsonl_rows,
    _read_prior_artifact,
    _synthesize_perspectives,
    _utcnow_iso,
)
from researchclaw.pipeline.research_governor import (
    build_phase_charter,
    build_stage_skill_overlay,
    write_phase_handoff,
)
from researchclaw.pipeline.stages import Stage, StageStatus
from researchclaw.prompts import PromptManager

logger = logging.getLogger(__name__)


def _execute_synthesis(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    cards_path = _read_prior_artifact(run_dir, "cards/") or ""
    cards_context = ""
    if cards_path:
        snippets: list[str] = []
        for path in sorted(Path(cards_path).glob("*.md"))[:24]:
            snippets.append(path.read_text(encoding="utf-8"))
        cards_context = "\n\n".join(snippets)
    if llm is not None:
        _pm = prompts or PromptManager()
        _overlay = (
            _get_evolution_overlay(run_dir, "synthesis")
            + "\n"
            + build_phase_charter("synthesis")
            + "\n"
            + build_stage_skill_overlay(
                config,
                stage_name="synthesis",
                context=cards_context[:3000],
            )
        )
        sp = _pm.for_stage(
            "synthesis",
            evolution_overlay=_overlay,
            topic=config.research.topic,
            cards_context=cards_context,
            baseline_briefing=_load_baseline_briefing(config),
        )
        resp = llm.chat(
            [{"role": "user", "content": sp.user}],
            system=sp.system,
            max_tokens=sp.max_tokens or 8192,
        )
        synthesis_md = resp.content
    else:
        synthesis_md = f"""# Synthesis

## Cluster Overview
- Cluster A: Representation methods
- Cluster B: Training strategies
- Cluster C: Evaluation robustness

## Gap 1
Limited consistency across benchmark protocols.

## Gap 2
Under-reported failure behavior under distribution shift.

## Prioritized Opportunities
1. Unified experimental protocol
2. Robustness-aware evaluation suite

## Generated
{_utcnow_iso()}
"""
    (stage_dir / "synthesis.md").write_text(synthesis_md, encoding="utf-8")
    return StageResult(
        stage=Stage.SYNTHESIS,
        status=StageStatus.DONE,
        artifacts=("synthesis.md",),
        evidence_refs=("stage-07/synthesis.md",),
    )


def _execute_hypothesis_gen(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    synthesis = _read_prior_artifact(run_dir, "synthesis.md") or ""
    if llm is not None:
        _pm = prompts or PromptManager()
        from researchclaw.prompts import DEBATE_ROLES_HYPOTHESIS  # noqa: PLC0415

        # --- Multi-perspective debate ---
        perspectives_dir = stage_dir / "perspectives"
        variables = {"topic": config.research.topic, "synthesis": synthesis}
        perspectives = _multi_perspective_generate(
            llm, DEBATE_ROLES_HYPOTHESIS, variables, perspectives_dir
        )
        # BUG-S2: If all debate perspectives failed, fall back to defaults
        # instead of sending empty context to the LLM (pure hallucination).
        if not perspectives:
            logger.warning("All debate perspectives failed; using default hypotheses")
            hypotheses_md = _default_hypotheses(config.research.topic)
        else:
            # --- Synthesize into final hypotheses ---
            hypotheses_md = _synthesize_perspectives(
                llm, perspectives, "hypothesis_synthesize", _pm
            )
    else:
        hypotheses_md = _default_hypotheses(config.research.topic)
    (stage_dir / "hypotheses.md").write_text(hypotheses_md, encoding="utf-8")

    # --- Novelty check (non-blocking) ---
    novelty_artifacts: tuple[str, ...] = ()
    try:
        from researchclaw.literature.novelty import check_novelty  # noqa: PLC0415

        candidates_text = _read_prior_artifact(run_dir, "candidates.jsonl") or ""
        papers_seen = _parse_jsonl_rows(candidates_text) if candidates_text else []
        novelty_report = check_novelty(
            topic=config.research.topic,
            hypotheses_text=hypotheses_md,
            papers_already_seen=papers_seen,
            s2_api_key=getattr(config.llm, "s2_api_key", ""),
        )
        (stage_dir / "novelty_report.json").write_text(
            json.dumps(novelty_report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        novelty_artifacts = ("novelty_report.json",)
        logger.info(
            "Novelty check: score=%.3f  assessment=%s  recommendation=%s",
            novelty_report["novelty_score"],
            novelty_report["assessment"],
            novelty_report["recommendation"],
        )
    except Exception:  # noqa: BLE001
        logger.warning("Novelty check failed (non-blocking)", exc_info=True)

    write_phase_handoff(
        stage_dir / "phase1_handoff.md",
        "Phase 1 Handoff",
        {
            "Discovery Council Charter": build_phase_charter("hypothesis_gen"),
            "Synthesis": synthesis[:2500],
            "Hypotheses": hypotheses_md[:2500],
        },
    )

    return StageResult(
        stage=Stage.HYPOTHESIS_GEN,
        status=StageStatus.DONE,
        artifacts=("hypotheses.md", "phase1_handoff.md") + novelty_artifacts,
        evidence_refs=("stage-08/hypotheses.md",),
    )
