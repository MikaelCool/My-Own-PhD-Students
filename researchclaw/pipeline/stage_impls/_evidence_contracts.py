"""Evidence-contract wrappers for existing pipeline stages."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from researchclaw.adapters import AdapterBundle
from researchclaw.config import RCConfig
from researchclaw.evidence.claims import build_claims_evidence_matrix
from researchclaw.lineage.ledger import LineageLedger
from researchclaw.llm.client import LLMClient
from researchclaw.pipeline._helpers import StageResult, _read_prior_artifact
from researchclaw.pipeline.stage_impls._analysis import _execute_research_decision as _base_research_decision
from researchclaw.pipeline.stage_impls._experiment_design import (
    _execute_experiment_design as _base_experiment_design,
)
from researchclaw.pipeline.stages import StageStatus
from researchclaw.prompts import PromptManager


def _append_unique(items: tuple[str, ...], additions: tuple[str, ...]) -> tuple[str, ...]:
    merged = list(items)
    for item in additions:
        if item not in merged:
            merged.append(item)
    return tuple(merged)


def _extract_claim_id(text: str, fallback: str) -> str:
    match = re.search(r"\bC\d+\b", text)
    return match.group(0) if match else fallback


def _build_evidence_ledger_from_claims(
    *,
    run_id: str,
    claims_payload: dict[str, Any],
    experiment_summary: dict[str, Any] | None = None,
) -> LineageLedger:
    """Build the formal evidence ledger for Stage 15 claim decisions."""
    ledger = LineageLedger(run_id=run_id)

    unsupported = claims_payload.get("unsupported_claims", [])
    if isinstance(unsupported, list):
        for idx, claim in enumerate(unsupported, start=1):
            claim_text = str(claim).strip()
            if not claim_text or claim_text.lower() == "none.":
                continue
            claim_id = _extract_claim_id(claim_text, f"U{idx}")
            ledger.add_unsupported_claim(
                evidence_id=f"unsupported-{idx}",
                claim_id=claim_id,
                summary=claim_text,
                source_artifact="stage-15/claims_from_results.json",
            )

    partial = claims_payload.get("partial_claims", [])
    if isinstance(partial, list):
        for idx, claim in enumerate(partial, start=1):
            claim_text = str(claim).strip()
            if not claim_text or claim_text.lower() == "none.":
                continue
            claim_id = _extract_claim_id(claim_text, f"P{idx}")
            ledger.add_negative_result(
                evidence_id=f"partial-negative-{idx}",
                claim_id=claim_id,
                summary=f"Partial or narrowed support requires claim calibration: {claim_text}",
                source_artifact="stage-15/claims_from_results.json",
            )

    summary = experiment_summary or {}
    runs = summary.get("runs", [])
    if isinstance(runs, list):
        for idx, run in enumerate(runs, start=1):
            if not isinstance(run, dict):
                continue
            status = str(run.get("status") or "").lower()
            run_id_value = str(run.get("run_id") or f"run-{idx}")
            if status in {"failed", "error", "timeout"}:
                ledger.add_failed_experiment(
                    evidence_id=f"failed-experiment-{idx}",
                    summary=str(run.get("error") or run.get("summary") or f"Experiment {run_id_value} failed."),
                    source_artifact="stage-14/experiment_summary.json",
                    failure_mode=str(run.get("failure_mode") or run.get("error") or status),
                    affected_claim_ids=[],
                )
                continue
            metrics = run.get("metrics") or {}
            if isinstance(metrics, dict):
                for metric_name, metric_value in metrics.items():
                    try:
                        value = float(metric_value)
                    except (TypeError, ValueError):
                        continue
                    if value < 0.5:
                        ledger.add_negative_result(
                            evidence_id=f"negative-metric-{idx}-{metric_name}",
                            claim_id="C1",
                            summary=f"Run {run_id_value} produced low {metric_name}={value:.6g}.",
                            source_artifact="stage-14/experiment_summary.json",
                            metric_name=str(metric_name),
                            metric_value=value,
                        )
                        break
    return ledger


def _execute_experiment_design(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    result = _base_experiment_design(stage_dir, run_dir, config, adapters, llm=llm, prompts=prompts)
    if result.status is not StageStatus.DONE:
        return result

    plan_path = stage_dir / "exp_plan.yaml"
    if not plan_path.is_file():
        return result
    plan = yaml.safe_load(plan_path.read_text(encoding="utf-8")) or {}
    if not isinstance(plan, dict):
        return result

    hypotheses = _read_prior_artifact(run_dir, "hypotheses.md") or ""
    matrix_md, payload, graph = build_claims_evidence_matrix(
        config.research.topic,
        hypotheses,
        plan,
        config.experiment.metric_key,
    )
    (stage_dir / "claims_evidence_matrix.md").write_text(matrix_md, encoding="utf-8")
    (stage_dir / "claims_evidence_matrix.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (stage_dir / "claims_evidence_matrix.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    (stage_dir / "claim_graph.mmd").write_text(graph, encoding="utf-8")

    return replace(
        result,
        artifacts=_append_unique(result.artifacts, ("claims_evidence_matrix.yaml", "claim_graph.mmd")),
        evidence_refs=_append_unique(
            result.evidence_refs,
            ("stage-09/claims_evidence_matrix.yaml", "stage-09/claim_graph.mmd"),
        ),
    )


def _execute_research_decision(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    result = _base_research_decision(stage_dir, run_dir, config, adapters, llm=llm, prompts=prompts)

    claims_path = stage_dir / "claims_from_results.json"
    if not claims_path.is_file():
        return result
    try:
        claims_payload = json.loads(claims_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return result
    if not isinstance(claims_payload, dict):
        return result

    experiment_summary_payload: dict[str, Any] = {}
    experiment_summary = _read_prior_artifact(run_dir, "experiment_summary.json") or ""
    if experiment_summary:
        try:
            parsed_summary = json.loads(experiment_summary)
            if isinstance(parsed_summary, dict):
                experiment_summary_payload = parsed_summary
        except json.JSONDecodeError:
            experiment_summary_payload = {}

    evidence_ledger = _build_evidence_ledger_from_claims(
        run_id=run_dir.name,
        claims_payload=claims_payload,
        experiment_summary=experiment_summary_payload,
    )
    (stage_dir / "evidence_ledger.json").write_text(
        json.dumps(evidence_ledger.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return replace(
        result,
        artifacts=_append_unique(result.artifacts, ("evidence_ledger.json",)),
        evidence_refs=_append_unique(result.evidence_refs, ("stage-15/evidence_ledger.json",)),
    )
