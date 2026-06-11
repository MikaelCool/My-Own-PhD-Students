from __future__ import annotations

import json
from pathlib import Path

from researchclaw.skills.schema import Skill


def test_trace_context_normalizes_event_and_hashes_artifacts(tmp_path: Path) -> None:
    from researchclaw.observability.tracing import TraceContext, hash_file

    artifact = tmp_path / "result.json"
    artifact.write_text('{"score": 0.91}\n', encoding="utf-8")

    ctx = TraceContext.start(run_id="run-1", stage=14, metadata={"model": "test-model"})
    event = ctx.event(
        "metric_extracted",
        payload={"metric": "accuracy"},
        model="gpt-test",
        prompt_version="prompt@1",
        latency_ms=123.4,
        token_input=10,
        token_output=20,
        cost_usd=0.03,
        artifact_paths=[artifact],
        decision_reason="objective metric found",
    )

    assert event["trace_id"] == ctx.trace_id
    assert event["span_id"] == ctx.span_id
    assert event["run_id"] == "run-1"
    assert event["stage"] == 14
    assert event["model"] == "gpt-test"
    assert event["prompt_version"] == "prompt@1"
    assert event["token_total"] == 30
    assert event["artifact_hashes"][str(artifact)] == hash_file(artifact)
    assert event["decision_reason"] == "objective metric found"


def test_supervisor_event_accepts_trace_context(tmp_path: Path) -> None:
    from researchclaw.observability.tracing import TraceContext
    from researchclaw.pipeline.control_state import append_supervisor_event, recent_supervisor_events

    ctx = TraceContext.start(run_id="run-2", stage=9)
    append_supervisor_event(
        tmp_path,
        event_type="approval_required",
        summary="experiment design needs review",
        payload={"trace": ctx.to_dict(), "prompt_version": "design@2"},
    )

    [event] = recent_supervisor_events(tmp_path)
    assert event["event_type"] == "approval_required"
    assert event["trace_id"] == ctx.trace_id
    assert event["span_id"] == ctx.span_id
    assert event["prompt_version"] == "design@2"


def test_lineage_ledger_validates_scientific_integrity(tmp_path: Path) -> None:
    from researchclaw.lineage.ledger import LineageLedger

    data_file = tmp_path / "dataset.jsonl"
    data_file.write_text('{"x": 1}\n', encoding="utf-8")

    ledger = LineageLedger(run_id="run-3")
    ledger.add_dataset(
        name="toy",
        version="v1",
        split="test",
        source="local",
        path=data_file,
        leakage_status="checked",
    )
    ledger.add_metric(
        name="accuracy",
        value=0.91,
        direction="maximize",
        source_artifact="stage-14/experiment_summary.json",
    )
    ledger.add_artifact(path=data_file, role="dataset", simulated=False)
    ledger.add_decision(
        decision_id="select-best",
        selected="branch-a",
        rejected=["branch-b"],
        selection_rule="maximize accuracy on held-out test split",
        human_reviewer="lyc",
    )

    assert ledger.validate() == []
    payload = ledger.to_dict()
    restored = LineageLedger.from_dict(payload)
    assert restored.run_id == "run-3"
    assert restored.datasets[0].sha256


def test_lineage_ledger_flags_untagged_simulation_and_missing_rules(tmp_path: Path) -> None:
    from researchclaw.lineage.ledger import LineageLedger

    artifact = tmp_path / "simulated.csv"
    artifact.write_text("score\n0.5\n", encoding="utf-8")

    ledger = LineageLedger(run_id="run-4")
    ledger.add_artifact(path=artifact, role="result", simulated=True, simulation_label="")
    ledger.add_metric(name="score", value=0.5, direction="", source_artifact=str(artifact))
    ledger.add_decision(decision_id="pick", selected="a", rejected=["b"], selection_rule="")

    messages = [issue.message for issue in ledger.validate()]
    assert any("simulated" in message for message in messages)
    assert any("metric direction" in message for message in messages)
    assert any("selection rule" in message for message in messages)


def test_benchmark_report_aggregates_objective_metrics() -> None:
    from researchclaw.bench.core import BenchmarkMetric, BenchmarkReport, BenchmarkResult, BenchmarkTask

    task = BenchmarkTask(
        task_id="stage14-basic",
        name="Stage 14 objective metric extraction",
        stage=14,
        required_metrics=("claim_evidence_coverage", "reproducibility"),
    )
    result = BenchmarkResult(
        task=task,
        metrics=[
            BenchmarkMetric("claim_evidence_coverage", 0.96, threshold=0.95, direction="maximize"),
            BenchmarkMetric("reproducibility", 0.82, threshold=0.8, direction="maximize"),
        ],
        cost_usd=1.5,
        elapsed_sec=30.0,
    )
    report = BenchmarkReport(results=[result])

    assert result.passed
    assert report.pass_rate == 1.0
    assert report.total_cost_usd == 1.5
    assert report.to_dict()["results"][0]["passed"] is True


def test_adaptive_policy_limits_multi_agent_to_parallel_low_coupling_tasks() -> None:
    from researchclaw.policy.orchestration import OrchestrationInput, choose_orchestration

    sequential = choose_orchestration(
        OrchestrationInput(
            stage=17,
            task_type="paper_draft",
            coupling="high",
            parallelizable=False,
            risk="medium",
            uncertainty="low",
            branch_budget=4,
        )
    )
    parallel = choose_orchestration(
        OrchestrationInput(
            stage=5,
            task_type="literature_screen",
            coupling="low",
            parallelizable=True,
            risk="low",
            uncertainty="medium",
            branch_budget=6,
        )
    )
    risky = choose_orchestration(
        OrchestrationInput(
            stage=9,
            task_type="experiment_design",
            coupling="medium",
            parallelizable=True,
            risk="high",
            uncertainty="high",
            branch_budget=3,
        )
    )

    assert sequential.mode == "centralized"
    assert parallel.mode == "parallel_multi_agent"
    assert risky.requires_human_review is True


def test_trajectory_exports_jsonl_process_rewards() -> None:
    from researchclaw.post_training.trajectory import Trajectory, Transition

    trajectory = Trajectory(run_id="run-5")
    trajectory.add(
        Transition(
            state={"stage": 14},
            action={"tool": "verify_claims"},
            artifact_refs=["stage-14/experiment_summary.json"],
            reward={"claim_grounding": 1.0, "cost_penalty": -0.1},
            cost={"tokens": 100, "usd": 0.02},
            next_state={"stage": 15},
            terminal=False,
        )
    )

    line = trajectory.to_jsonl().strip()
    decoded = json.loads(line)
    assert decoded["run_id"] == "run-5"
    assert decoded["reward_total"] == 0.9
    assert decoded["transitions"][0]["action"]["tool"] == "verify_claims"


def test_skill_matcher_uses_gain_cost_and_conflict_metadata() -> None:
    from researchclaw.skills.matcher import match_skills

    high_gain = Skill(
        name="high-gain-low-cost",
        description="verify claims",
        body="",
        metadata={
            "trigger-keywords": "claims,verify",
            "applicable-stages": "17",
            "priority": "5",
            "expected-gain": "high",
            "token-cost-band": "low",
            "control-category": "verification",
        },
    )
    costly = Skill(
        name="costly",
        description="verify claims",
        body="",
        metadata={
            "trigger-keywords": "claims,verify",
            "applicable-stages": "17",
            "priority": "1",
            "expected-gain": "medium",
            "token-cost-band": "high",
            "control-category": "verification",
        },
    )
    conflicting = Skill(
        name="conflicting",
        description="verify claims",
        body="",
        metadata={
            "trigger-keywords": "claims,verify",
            "applicable-stages": "17",
            "priority": "1",
            "expected-gain": "high",
            "token-cost-band": "low",
            "conflict-skills": "already-active",
            "control-category": "verification",
        },
    )

    matched = match_skills(
        [costly, conflicting, high_gain],
        "verify claims in paper draft",
        17,
        token_budget_band="low",
        active_skill_names={"already-active"},
        required_control_category="verification",
    )

    assert [skill.name for skill in matched[:2]] == ["high-gain-low-cost", "costly"]
