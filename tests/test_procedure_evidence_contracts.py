from __future__ import annotations

import json
from pathlib import Path

import yaml


def test_skill_procedure_contract_validates_required_steps() -> None:
    from researchclaw.skills.schema import Skill

    skill = Skill.from_dict(
        {
            "id": "claim-audit",
            "description": "Audit claims against evidence",
            "procedure_contract": {
                "contract_id": "claim-audit-v1",
                "version": "1.0",
                "inputs": ["claims_evidence_matrix.json"],
                "outputs": ["claim_audit.json"],
                "steps": [
                    {
                        "id": "load-claims",
                        "instruction": "Load structured claims.",
                        "verification": "Every claim has a claim_id.",
                        "failure_modes": ["missing_claim_id"],
                    },
                    {
                        "id": "audit-support",
                        "instruction": "Compare each claim against evidence records.",
                        "verification": "Unsupported claims are marked unsupported.",
                        "failure_modes": ["unsupported_claim"],
                    },
                ],
            },
        }
    )

    assert skill.procedure_contract is not None
    assert skill.procedure_contract.step_ids == ["load-claims", "audit-support"]
    assert skill.validate_procedure_contract() == []
    payload = skill.to_dict()
    assert payload["procedure_contract"]["steps"][1]["failure_modes"] == ["unsupported_claim"]


def test_skill_procedure_contract_flags_prompt_only_guidelines() -> None:
    from researchclaw.skills.schema import Skill

    skill = Skill.from_dict(
        {
            "id": "weak-guideline",
            "description": "Only prompt text",
            "procedure_contract": {
                "contract_id": "weak-v1",
                "steps": [
                    {
                        "id": "think",
                        "instruction": "Think carefully.",
                    }
                ],
            },
        }
    )

    messages = [issue["message"] for issue in skill.validate_procedure_contract()]
    assert any("outputs" in message for message in messages)
    assert any("verification" in message for message in messages)


def test_claim_matrix_exports_json_yaml_and_mermaid_graph() -> None:
    from researchclaw.evidence.claims import build_claims_evidence_matrix

    md, payload, graph = build_claims_evidence_matrix(
        topic="compression post-training",
        hypotheses="H1: Sparse adapters improve reward retention under compression.",
        plan={
            "proposed_methods": ["SparseAdapter"],
            "baselines": ["LoRA"],
            "ablations": ["no sparsity"],
            "datasets": ["reward-bench"],
            "metrics": ["win_rate"],
        },
        metric_key="win_rate",
    )

    assert "Claims-Evidence Matrix" in md
    assert payload["schema_version"] == 1
    assert payload["claims"][0]["claim_id"] == "C1"
    assert payload["claims"][0]["status"] == "planned"
    assert "graph TD" in graph
    assert "C1" in graph
    assert "E_C1_1" in graph
    assert yaml.safe_load(yaml.safe_dump(payload, allow_unicode=True))["claims"][0]["claim"] == payload["claims"][0]["claim"]


def test_lineage_ledger_records_negative_failed_and_unsupported_evidence(tmp_path: Path) -> None:
    from researchclaw.lineage.ledger import LineageLedger

    failed_log = tmp_path / "failed.json"
    failed_log.write_text('{"error": "oom"}\n', encoding="utf-8")

    ledger = LineageLedger(run_id="run-evidence")
    ledger.add_negative_result(
        evidence_id="neg-1",
        claim_id="C1",
        summary="SparseAdapter did not outperform LoRA on reward-bench.",
        source_artifact="stage-14/analysis.md",
        metric_name="win_rate",
        metric_value=0.49,
    )
    ledger.add_failed_experiment(
        evidence_id="fail-1",
        summary="Ablation run failed with OOM.",
        source_artifact=failed_log,
        failure_mode="resource_exhausted",
        affected_claim_ids=["C1"],
    )
    ledger.add_unsupported_claim(
        evidence_id="unsupported-1",
        claim_id="C2",
        summary="SOTA wording has no matching baseline evidence.",
        source_artifact="stage-15/claims_from_results.json",
    )

    assert ledger.validate() == []
    payload = ledger.to_dict()
    assert [item["evidence_type"] for item in payload["evidence_events"]] == [
        "negative_result",
        "failed_experiment",
        "unsupported_claim",
    ]

    path = tmp_path / "ledger.json"
    ledger.write_json(path)
    restored = LineageLedger.read_json(path)
    assert restored.evidence_events[1].failure_mode == "resource_exhausted"


def test_research_decision_evidence_ledger_from_claims_payload() -> None:
    from researchclaw.pipeline.stage_impls._evidence_contracts import _build_evidence_ledger_from_claims

    ledger = _build_evidence_ledger_from_claims(
        run_id="run-stage-15",
        claims_payload={
            "unsupported_claims": ["C2: broad SOTA claim is not supported"],
            "partial_claims": ["C1 needs narrower scope"],
            "supported_claims": ["C0 is supported"],
        },
        experiment_summary={
            "runs": [
                {"run_id": "r1", "status": "failed", "error": "oom"},
                {"run_id": "r2", "status": "completed", "metrics": {"win_rate": 0.42}},
            ]
        },
    )

    evidence_types = [record.evidence_type for record in ledger.evidence_events]
    assert "unsupported_claim" in evidence_types
    assert "failed_experiment" in evidence_types
    assert "negative_result" in evidence_types
    assert ledger.validate() == []
