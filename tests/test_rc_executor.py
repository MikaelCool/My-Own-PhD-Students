# pyright: reportPrivateUsage=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnusedCallResult=false, reportAttributeAccessIssue=false, reportUnknownLambdaType=false
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from researchclaw.adapters import AdapterBundle, WebhookMessageAdapter
from researchclaw.config import RCConfig
from researchclaw.pipeline import executor as rc_executor
from researchclaw.pipeline._helpers import _chat_with_prompt
from researchclaw.pipeline.stage_impls import _analysis as rc_analysis
from researchclaw.pipeline.stages import Stage, StageStatus


class FakeLLMClient:
    def __init__(self, response_text: str = "mock response"):
        self.response_text: str = response_text
        self.calls: list[list[dict[str, str]]] = []

    def chat(self, messages: list[dict[str, str]], **kwargs: object):
        _ = kwargs
        self.calls.append(messages)
        from researchclaw.llm.client import LLMResponse

        return LLMResponse(content=self.response_text, model="fake-model")


class FakeLLMClientWithConfig(FakeLLMClient):
    def __init__(self, response_text: str = "mock response"):
        super().__init__(response_text=response_text)
        self.config: SimpleNamespace = SimpleNamespace(
            base_url="http://fake", api_key="fake-key"
        )


class SequenceLLMClient(FakeLLMClient):
    def __init__(self, responses: list[str]):
        super().__init__(response_text=responses[0] if responses else "mock response")
        self._responses = list(responses)

    def chat(self, messages: list[dict[str, str]], **kwargs: object):
        self.calls.append(messages)
        from researchclaw.llm.client import LLMResponse

        if self._responses:
            content = self._responses.pop(0)
        else:
            content = self.response_text
        return LLMResponse(content=content, model="fake-model")


@pytest.fixture()
def rc_config(tmp_path: Path) -> RCConfig:
    data = {
        "project": {"name": "rc-test", "mode": "docs-first"},
        "research": {
            "topic": "test-driven science",
            "domains": ["ml", "systems"],
            "daily_paper_count": 2,
            "quality_threshold": 8.2,
        },
        "runtime": {"timezone": "UTC"},
        "notifications": {
            "channel": "local",
            "on_stage_start": True,
            "on_stage_fail": False,
            "on_gate_required": True,
        },
        "knowledge_base": {"backend": "markdown", "root": str(tmp_path / "kb")},
        "openclaw_bridge": {"use_memory": True, "use_message": True},
        "llm": {
            "provider": "openai-compatible",
            "base_url": "http://localhost:1234/v1",
            "api_key_env": "RC_TEST_KEY",
            "api_key": "inline-test-key",
            "primary_model": "fake-model",
            "fallback_models": [],
        },
        "security": {"hitl_required_stages": [5, 9, 20]},
        "experiment": {"mode": "sandbox"},
    }
    return RCConfig.from_dict(data, project_root=tmp_path, check_paths=False)


@pytest.fixture()
def adapters() -> AdapterBundle:
    return AdapterBundle()


@pytest.fixture()
def run_dir(tmp_path: Path) -> Path:
    path = tmp_path / "run"
    path.mkdir()
    return path


def _write_prior_artifact(
    run_dir: Path, stage_num: int, filename: str, content: str
) -> None:
    stage_dir = run_dir / f"stage-{stage_num:02d}"
    stage_dir.mkdir(parents=True, exist_ok=True)
    (stage_dir / filename).write_text(content, encoding="utf-8")


def test_executor_map_has_23_entries() -> None:
    executor_map = getattr(rc_executor, "EXECUTOR_MAP", rc_executor._STAGE_EXECUTORS)
    assert len(executor_map) == 23


def test_every_stage_member_has_matching_executor() -> None:
    executor_map = getattr(rc_executor, "EXECUTOR_MAP", rc_executor._STAGE_EXECUTORS)
    assert set(executor_map.keys()) == set(Stage)


def test_stage_result_dataclass_fields() -> None:
    result = rc_executor.StageResult(
        stage=Stage.TOPIC_INIT, status=StageStatus.DONE, artifacts=("goal.md",)
    )
    assert result.stage == Stage.TOPIC_INIT
    assert result.status == StageStatus.DONE
    assert result.artifacts == ("goal.md",)
    assert result.error is None
    assert result.decision == "proceed"
    assert result.evidence_refs == ()
    assert result.control_hints == {}


def test_utcnow_iso_returns_valid_iso_timestamp() -> None:
    ts = rc_executor._utcnow_iso()
    assert ts.endswith("+00:00")
    assert "T" in ts


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("before\n```yaml\na: 1\n```\nafter", "a: 1"),
        ("```yml\nkey: value\n```", "key: value"),
        ("```\nplain: true\n```", "plain: true"),
        ("  x: y  ", "x: y"),
    ],
)
def test_extract_yaml_block_variants(text: str, expected: str) -> None:
    assert rc_executor._extract_yaml_block(text) == expected


@pytest.mark.parametrize(
    ("payload", "default", "expected"),
    [
        ('{"ok": true}', {"fallback": True}, {"ok": True}),
        ("[1, 2, 3]", {"fallback": True}, [1, 2, 3]),
        ("not-json", {"fallback": True}, {"fallback": True}),
    ],
)
def test_safe_json_loads_valid_and_invalid(payload: str, default, expected) -> None:
    assert rc_executor._safe_json_loads(payload, default) == expected


def test_adapter_bundle_uses_webhook_message_adapter_for_lark(tmp_path: Path) -> None:
    config = RCConfig.from_dict(
        {
            "project": {"name": "notify-test", "mode": "docs-first"},
            "research": {"topic": "test topic"},
            "runtime": {"timezone": "UTC"},
            "notifications": {
                "channel": "lark",
                "target": "https://example.invalid/hook",
                "secret": "top-secret",
            },
            "knowledge_base": {"backend": "markdown", "root": str(tmp_path / "kb")},
            "openclaw_bridge": {"use_message": False},
            "llm": {
                "provider": "openai-compatible",
                "base_url": "http://localhost:1234/v1",
                "api_key_env": "RC_TEST_KEY",
                "api_key": "inline-test-key",
                "primary_model": "fake-model",
            },
            "experiment": {"mode": "simulated"},
        },
        project_root=tmp_path,
        check_paths=False,
    )

    bundle = AdapterBundle.from_config(config)

    assert isinstance(bundle.message, WebhookMessageAdapter)
    assert bundle.message.channel == "lark"
    assert bundle.message.target == "https://example.invalid/hook"
    assert bundle.message.secret == "top-secret"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a/b", "a_b"),
        ("a\\b", "a_b"),
        ("../secret", "__secret"),
        ("name with spaces!.md", "name_with_spaces_.md"),
        ("", "unnamed"),
    ],
)
def test_safe_filename_sanitization(raw: str, expected: str) -> None:
    assert rc_executor._safe_filename(raw) == expected


def test_safe_filename_truncates_to_100_chars() -> None:
    raw = "x" * 120
    cleaned = rc_executor._safe_filename(raw)
    assert len(cleaned) == 100
    assert cleaned == "x" * 100


def test_execute_stage_sends_stage_complete_summary_notification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = RCConfig.from_dict(
        {
            "project": {"name": "notify-test", "mode": "docs-first"},
            "research": {"topic": "test topic"},
            "runtime": {"timezone": "UTC"},
            "notifications": {
                "channel": "local",
                "on_stage_start": True,
                "on_stage_complete": True,
                "on_stage_fail": True,
                "on_gate_required": True,
            },
            "knowledge_base": {"backend": "markdown", "root": str(tmp_path / "kb")},
            "openclaw_bridge": {"use_message": True, "use_memory": False},
            "llm": {
                "provider": "openai-compatible",
                "base_url": "http://localhost:1234/v1",
                "api_key_env": "RC_TEST_KEY",
                "api_key": "inline-test-key",
                "primary_model": "fake-model",
            },
            "security": {"hitl_required_stages": [5, 9, 20]},
            "experiment": {"mode": "simulated"},
        },
        project_root=tmp_path,
        check_paths=False,
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    adapters = AdapterBundle()

    def fake_executor(stage_dir, _run_dir, _config, _adapters, **_kwargs):
        (stage_dir / "goal.md").write_text(
            "# Goal\n- Baseline-aware scope locked\n- Novel contribution target defined\n- Quality improves via early scoping\n",
            encoding="utf-8",
        )
        (stage_dir / "goal_brief.md").write_text(
            "- Brief goal summary\n",
            encoding="utf-8",
        )
        (stage_dir / "hardware_profile.json").write_text(
            json.dumps({"device": "cpu"}),
            encoding="utf-8",
        )
        return rc_executor.StageResult(
            stage=Stage.TOPIC_INIT,
            status=StageStatus.DONE,
            artifacts=("goal.md", "goal_brief.md", "hardware_profile.json"),
        )

    monkeypatch.setitem(rc_executor._STAGE_EXECUTORS, Stage.TOPIC_INIT, fake_executor)

    result = rc_executor.execute_stage(
        Stage.TOPIC_INIT,
        run_dir=run_dir,
        run_id="run-notify",
        config=config,
        adapters=adapters,
    )

    assert result.status == StageStatus.DONE
    assert len(adapters.message.calls) == 2
    assert adapters.message.calls[0][1] == "stage-01-start"
    assert adapters.message.calls[1][1] == "stage-01-complete"
    completion_body = adapters.message.calls[1][2]
    assert "What was done:" in completion_body
    assert "Innovation:" in completion_body
    assert "Advantages:" in completion_body
    assert "Baseline-aware scope locked" in completion_body


def test_execute_stage_writes_run_control_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = RCConfig.from_dict(
        {
            "project": {"name": "control-state-test", "mode": "docs-first"},
            "research": {"topic": "test topic"},
            "runtime": {"timezone": "UTC"},
            "notifications": {
                "channel": "local",
                "on_stage_start": True,
                "on_stage_complete": False,
                "on_stage_fail": False,
                "on_gate_required": True,
            },
            "knowledge_base": {"backend": "markdown", "root": str(tmp_path / "kb")},
            "openclaw_bridge": {"use_message": True, "use_memory": False},
            "llm": {
                "provider": "openai-compatible",
                "base_url": "http://localhost:1234/v1",
                "api_key_env": "RC_TEST_KEY",
                "api_key": "inline-test-key",
                "primary_model": "fake-model",
            },
        },
        project_root=tmp_path,
        check_paths=False,
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    def fake_executor(stage_dir, _run_dir, _config, _adapters, **_kwargs):
        (stage_dir / "goal.md").write_text("# ok\n", encoding="utf-8")
        (stage_dir / "goal_brief.md").write_text("- ok\n", encoding="utf-8")
        (stage_dir / "hardware_profile.json").write_text(
            json.dumps({"device": "cpu"}),
            encoding="utf-8",
        )
        return rc_executor.StageResult(
            stage=Stage.TOPIC_INIT,
            status=StageStatus.DONE,
            artifacts=("goal.md", "goal_brief.md", "hardware_profile.json"),
        )

    original = rc_executor._STAGE_EXECUTORS[Stage.TOPIC_INIT]
    monkeypatch.setitem(rc_executor._STAGE_EXECUTORS, Stage.TOPIC_INIT, fake_executor)
    try:
        rc_executor.execute_stage(
            Stage.TOPIC_INIT,
            run_dir=run_dir,
            run_id="run-exec-control",
            config=config,
            adapters=AdapterBundle(),
        )
    finally:
        monkeypatch.setitem(rc_executor._STAGE_EXECUTORS, Stage.TOPIC_INIT, original)

    control_state = cast(
        dict[str, Any],
        json.loads((run_dir / "run_control_state.json").read_text(encoding="utf-8")),
    )
    assert control_state["current_stage"] == int(Stage.TOPIC_INIT)
    assert control_state["current_substep"] == "stage_complete"
    assert control_state["active_session_backend"] == "openai-compatible"
    assert control_state["latest_stage_result"]["status"] == StageStatus.DONE.value
    assert control_state["observers"]["artifact_integrity"]["artifact_count"] == 3


def test_build_stage_failure_body_includes_observer_summary(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run_control_state.json").write_text(
        json.dumps(
            {
                "current_stage": 12,
                "current_stage_name": "EXPERIMENT_RUN",
                "current_substep": "stage_complete",
                "waiting_reason": "",
                "observers": {
                    "stage_progress": {
                        "current_stage": 12,
                        "current_stage_name": "EXPERIMENT_RUN",
                        "current_substep": "stage_complete",
                        "status": "failed",
                        "waiting_reason": "",
                    },
                    "session_health": {"backend": "openai-compatible"},
                    "resource_state": {"waiting": False, "waiting_reason": ""},
                    "risk_flags": ["stage_failed"],
                },
            }
        ),
        encoding="utf-8",
    )
    stage12_dir = run_dir / "stage-12"
    stage12_dir.mkdir()
    (stage12_dir / "runtime_observer.json").write_text(
        json.dumps(
            {
                "dataset_readiness": {
                    "status": "blocked",
                    "summary": "Dataset preparation is blocked by preflight errors.",
                },
                "gpu_availability": {"status": "ready", "summary": "Process-free GPUs detected."},
                "runtime_watchdog": {"status": "failed", "summary": "Stage 12 failed before exhausting the time budget."},
            }
        ),
        encoding="utf-8",
    )

    body = rc_executor._build_stage_failure_body(
        stage=Stage.EXPERIMENT_RUN,
        run_dir=run_dir,
        run_id="run-fail-summary",
        result=rc_executor.StageResult(
            stage=Stage.EXPERIMENT_RUN,
            status=StageStatus.FAILED,
            artifacts=(),
            error="boom",
            decision="retry",
        ),
    )

    assert "Focus: Dataset preparation is blocked by preflight errors." in body
    assert "Alerts: dataset:blocked" in body


def test_safe_notify_failure_writes_supervisor_event(
    rc_config: RCConfig,
    run_dir: Path,
) -> None:
    adapters = AdapterBundle()

    def _fail_notify(channel: str, subject: str, body: str) -> str:
        _ = channel, subject, body
        raise RuntimeError("webhook timed out")

    adapters.message.notify = _fail_notify  # type: ignore[method-assign]

    rc_executor._safe_notify(
        adapters,
        rc_config,
        subject="stage-10-fail",
        body="boom",
        run_dir=run_dir,
    )

    control_state = json.loads((run_dir / "run_control_state.json").read_text(encoding="utf-8"))
    assert control_state["notification_state"]["last_status"] == "failed"
    run_index = json.loads((run_dir / "run_index.json").read_text(encoding="utf-8"))
    supervisor_events = [
        item for item in run_index["events"] if item.get("event") == "supervisor_event"
    ]
    assert supervisor_events
    latest = supervisor_events[-1]
    assert latest["event_type"] == "notification_failed"
    assert latest["error"] == "webhook timed out"
    assert "notification_failed" in latest["alerts"]


def test_write_backend_health_snapshot_records_session_switch(run_dir: Path) -> None:
    fake_llm = SimpleNamespace(
        describe_backend_health=lambda: {
            "selected_backend": "openclaw_gateway",
            "backend_order": ["openclaw_gateway", "acp_named_session", "acp_exec"],
            "gateway_healthy": True,
            "named_sessions_usable": False,
            "session_ready": False,
            "degraded": False,
        }
    )
    rc_executor.write_control_state(
        run_dir,
        active_session_backend="acp:codex",
        current_stage=int(Stage.CODE_GENERATION),
        current_stage_name=Stage.CODE_GENERATION.name,
    )

    rc_executor._write_backend_health_snapshot(
        run_dir=run_dir,
        run_id="run-backend",
        stage=Stage.CODE_GENERATION,
        config=SimpleNamespace(llm=SimpleNamespace(provider="acp")),
        llm=fake_llm,
    )

    control_state = json.loads((run_dir / "run_control_state.json").read_text(encoding="utf-8"))
    assert control_state["active_session_backend"] == "openclaw_gateway"
    assert control_state["session_backend_state"]["gateway_healthy"] is True
    run_index = json.loads((run_dir / "run_index.json").read_text(encoding="utf-8"))
    supervisor_events = [
        item for item in run_index["events"] if item.get("event") == "supervisor_event"
    ]
    assert supervisor_events[-1]["event_type"] == "session_switched"
    assert supervisor_events[-1]["from_backend"] == "acp:codex"
    assert supervisor_events[-1]["to_backend"] == "openclaw_gateway"


def test_execute_stage_gate_block_writes_human_review_supervisor_event(
    rc_config: RCConfig,
    run_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_prior_artifact(run_dir, 4, "candidates.jsonl", '{"title": "paper"}\n')

    def fake_executor(
        stage_dir: Path,
        run_dir_arg: Path,
        config: RCConfig,
        adapters: AdapterBundle,
        *,
        llm: object = None,
        prompts: object = None,
    ) -> rc_executor.StageResult:
        _ = stage_dir, run_dir_arg, config, adapters, llm, prompts
        (stage_dir / "screening.json").write_text("{}", encoding="utf-8")
        return rc_executor.StageResult(
            stage=Stage.LITERATURE_SCREEN,
            status=StageStatus.DONE,
            artifacts=("screening.json",),
        )

    original = rc_executor._STAGE_EXECUTORS[Stage.LITERATURE_SCREEN]
    monkeypatch.setitem(
        rc_executor._STAGE_EXECUTORS,
        Stage.LITERATURE_SCREEN,
        fake_executor,
    )
    try:
        result = rc_executor.execute_stage(
            Stage.LITERATURE_SCREEN,
            run_dir=run_dir,
            run_id="run-gate-block",
            config=rc_config,
            adapters=AdapterBundle(),
            auto_approve_gates=False,
        )
    finally:
        monkeypatch.setitem(rc_executor._STAGE_EXECUTORS, Stage.LITERATURE_SCREEN, original)

    assert result.status == StageStatus.BLOCKED_APPROVAL
    run_index = json.loads((run_dir / "run_index.json").read_text(encoding="utf-8"))
    supervisor_events = [
        item for item in run_index["events"] if item.get("event") == "supervisor_event"
    ]
    assert supervisor_events[-1]["event_type"] == "human_review_needed"
    assert supervisor_events[-1]["stage"] == int(Stage.LITERATURE_SCREEN)
    assert "human_review_needed" in supervisor_events[-1]["alerts"]


def test_execute_stage_failed_quality_gate_writes_supervisor_event(
    rc_config: RCConfig,
    run_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_prior_artifact(run_dir, 19, "paper_revised.md", "# Revised Paper\n")

    def fake_executor(
        stage_dir: Path,
        run_dir_arg: Path,
        config: RCConfig,
        adapters: AdapterBundle,
        *,
        llm: object = None,
        prompts: object = None,
    ) -> rc_executor.StageResult:
        _ = stage_dir, run_dir_arg, config, adapters, llm, prompts
        (stage_dir / "quality_report.json").write_text("{}", encoding="utf-8")
        return rc_executor.StageResult(
            stage=Stage.QUALITY_GATE,
            status=StageStatus.FAILED,
            artifacts=("quality_report.json",),
            error="novelty score below threshold",
            decision="rollback",
        )

    original = rc_executor._STAGE_EXECUTORS[Stage.QUALITY_GATE]
    monkeypatch.setitem(
        rc_executor._STAGE_EXECUTORS,
        Stage.QUALITY_GATE,
        fake_executor,
    )
    try:
        result = rc_executor.execute_stage(
            Stage.QUALITY_GATE,
            run_dir=run_dir,
            run_id="run-quality-block",
            config=rc_config,
            adapters=AdapterBundle(),
            auto_approve_gates=True,
        )
    finally:
        monkeypatch.setitem(rc_executor._STAGE_EXECUTORS, Stage.QUALITY_GATE, original)

    assert result.status == StageStatus.FAILED
    run_index = json.loads((run_dir / "run_index.json").read_text(encoding="utf-8"))
    supervisor_events = [
        item for item in run_index["events"] if item.get("event") == "supervisor_event"
    ]
    assert supervisor_events[-1]["event_type"] == "quality_gate_blocked"
    assert supervisor_events[-1]["status"] == "error"
    assert supervisor_events[-1]["decision"] == "rollback"
    assert supervisor_events[-1]["error"] == "novelty score below threshold"


def test_build_context_preamble_basic_fields(
    rc_config: RCConfig, run_dir: Path
) -> None:
    text = rc_executor._build_context_preamble(rc_config, run_dir)
    assert "## Research Context" in text
    assert "test-driven science" in text
    assert "ml, systems" in text


def test_build_context_preamble_includes_selected_prior_artifacts(
    rc_config: RCConfig, run_dir: Path
) -> None:
    _write_prior_artifact(run_dir, 1, "goal.md", "goal content")
    _write_prior_artifact(run_dir, 8, "hypotheses.md", "hyp content")
    _write_prior_artifact(run_dir, 7, "synthesis.md", "synth content")
    text = rc_executor._build_context_preamble(
        rc_config,
        run_dir,
        include_goal=True,
        include_hypotheses=True,
        include_synthesis=True,
    )
    assert "### Goal" in text
    assert "goal content" in text
    assert "### Hypotheses" in text
    assert "hyp content" in text
    assert "### Synthesis" in text
    assert "synth content" in text


def test_build_context_preamble_includes_anchor_claims_and_matrix(
    rc_config: RCConfig, run_dir: Path
) -> None:
    _write_prior_artifact(run_dir, 2, "problem_anchor.md", "anchor content")
    _write_prior_artifact(run_dir, 9, "claims_evidence_matrix.md", "matrix content")
    _write_prior_artifact(run_dir, 15, "claims_from_results.md", "claim gate content")
    text = rc_executor._build_context_preamble(
        rc_config,
        run_dir,
        include_problem_anchor=True,
        include_claim_matrix=True,
        include_claims=True,
    )
    assert "### Problem Anchor" in text
    assert "anchor content" in text
    assert "### Claims-Evidence Matrix" in text
    assert "matrix content" in text
    assert "### Claims From Results" in text
    assert "claim gate content" in text


def test_build_context_preamble_preserves_late_phase2_missing_experiments(
    rc_config: RCConfig, run_dir: Path
) -> None:
    filler = ("Background paragraph.\n\n" * 120).strip()
    _write_prior_artifact(
        run_dir,
        15,
        "phase2_handoff.md",
        (
            f"# Phase 2 Handoff\n\n{filler}\n\n"
            "### Exact missing experiments that would unblock the paper\n"
            "1. Run `cheap_proxy_controller`, `probe_control`, and `adalora_like_budget` "
            "under matched settings.\n"
        ),
    )

    text = rc_executor._build_context_preamble(rc_config, run_dir)

    assert "### Phase 2 Handoff" in text
    assert "Exact missing experiments that would unblock the paper" in text
    assert "cheap_proxy_controller" in text
    assert "adalora_like_budget" in text


def test_build_context_preamble_compact_preserves_late_phase2_missing_experiments(
    rc_config: RCConfig, run_dir: Path
) -> None:
    filler = ("Background paragraph.\n\n" * 120).strip()
    _write_prior_artifact(
        run_dir,
        15,
        "phase2_handoff.md",
        (
            f"# Phase 2 Handoff\n\n{filler}\n\n"
            "### Exact missing experiments that would unblock the paper\n"
            "1. Run `cheap_proxy_controller`, `probe_control`, and `adalora_like_budget` "
            "under matched settings.\n"
        ),
    )

    text = rc_executor._build_context_preamble(rc_config, run_dir, compact=True)

    assert "### Phase 2 Handoff" in text
    assert "Exact missing experiments that would unblock the paper" in text
    assert "cheap_proxy_controller" in text
    assert "adalora_like_budget" in text


def test_build_context_preamble_includes_startup_contract_and_launch_mode(
    rc_config: RCConfig, run_dir: Path
) -> None:
    (run_dir / "startup_contract.json").write_text(
        json.dumps(
            {
                "goal": "audit the existing paper and revise only where evidence is weak",
                "launch_mode": "rebuttal_revision",
                "objectives": ["address reviewer concerns", "preserve validated claims"],
            }
        ),
        encoding="utf-8",
    )
    text = rc_executor._build_context_preamble(rc_config, run_dir)
    assert "## Startup Contract" in text
    assert "rebuttal_revision" in text
    assert "address reviewer concerns" in text


def test_read_prior_artifact_finds_newest_file(run_dir: Path) -> None:
    _write_prior_artifact(run_dir, 1, "goal.md", "old")
    _write_prior_artifact(run_dir, 3, "goal.md", "new")
    found = rc_executor._read_prior_artifact(run_dir, "goal.md")
    assert found == "new"


def test_read_prior_artifact_finds_directory_path(run_dir: Path) -> None:
    cards_dir = run_dir / "stage-06" / "cards"
    cards_dir.mkdir(parents=True)
    (cards_dir / "card-1.json").write_text("{}", encoding="utf-8")
    found = rc_executor._read_prior_artifact(run_dir, "cards/")
    assert found == str(cards_dir)


def test_read_prior_artifact_returns_none_when_not_found(run_dir: Path) -> None:
    assert rc_executor._read_prior_artifact(run_dir, "missing.md") is None


def test_read_best_analysis_prefers_best_file(run_dir: Path) -> None:
    """BUG-225: _read_best_analysis prefers analysis_best.md at run root."""
    from researchclaw.pipeline._helpers import _read_best_analysis

    # Create degenerate analysis in stage-14 and best at run root
    s14 = run_dir / "stage-14"
    s14.mkdir(parents=True)
    (s14 / "analysis.md").write_text("Degenerate analysis", encoding="utf-8")
    (run_dir / "analysis_best.md").write_text("Best analysis", encoding="utf-8")

    result = _read_best_analysis(run_dir)
    assert result == "Best analysis"


def test_read_best_analysis_falls_back_to_prior_artifact(run_dir: Path) -> None:
    """BUG-225: Falls back to _read_prior_artifact when no analysis_best.md."""
    from researchclaw.pipeline._helpers import _read_best_analysis

    s14 = run_dir / "stage-14"
    s14.mkdir(parents=True)
    (s14 / "analysis.md").write_text("Only analysis", encoding="utf-8")

    result = _read_best_analysis(run_dir)
    assert result == "Only analysis"


def test_read_best_analysis_returns_empty_when_none(run_dir: Path) -> None:
    """BUG-225: Returns empty string when no analysis exists at all."""
    from researchclaw.pipeline._helpers import _read_best_analysis

    result = _read_best_analysis(run_dir)
    assert result == ""


def test_write_stage_meta_writes_expected_json(run_dir: Path) -> None:
    stage_dir = run_dir / "stage-01"
    stage_dir.mkdir()
    result = rc_executor.StageResult(
        stage=Stage.TOPIC_INIT,
        status=StageStatus.DONE,
        artifacts=("goal.md",),
        decision="proceed",
        evidence_refs=("stage-01/goal.md",),
    )
    rc_executor._write_stage_meta(stage_dir, Stage.TOPIC_INIT, "run-abc", result)
    payload = cast(
        dict[str, Any],
        json.loads((stage_dir / "decision.json").read_text(encoding="utf-8")),
    )
    assert payload["stage_id"] == "01-topic_init"
    assert payload["run_id"] == "run-abc"
    assert payload["status"] == "done"
    assert payload["decision"] == "proceed"
    assert payload["output_artifacts"] == ["goal.md"]
    assert payload["evidence_refs"] == ["stage-01/goal.md"]
    assert payload["next_stage"] == 2
    assert re.match(r"\d{4}-\d{2}-\d{2}T", payload["ts"])


def test_execute_stage_creates_stage_dir_writes_artifacts_and_meta(
    monkeypatch: pytest.MonkeyPatch,
    run_dir: Path,
    rc_config: RCConfig,
    adapters: AdapterBundle,
) -> None:
    fake_llm = FakeLLMClientWithConfig("# Goal\n\nMocked goal body")
    monkeypatch.setattr(
        "researchclaw.pipeline.executor.LLMClient.from_rc_config",
        lambda _config: fake_llm,
    )

    result = rc_executor.execute_stage(
        Stage.TOPIC_INIT,
        run_dir=run_dir,
        run_id="run-1",
        config=rc_config,
        adapters=adapters,
        auto_approve_gates=True,
    )

    assert result.status == StageStatus.DONE
    assert "goal.md" in result.artifacts
    assert "hardware_profile.json" in result.artifacts
    assert (run_dir / "stage-01").is_dir()
    assert (
        (run_dir / "stage-01" / "goal.md")
        .read_text(encoding="utf-8")
        .startswith("# Goal")
    )
    assert (run_dir / "stage-01" / "hardware_profile.json").exists()
    assert len(fake_llm.calls) == 1

    decision = cast(
        dict[str, Any],
        json.loads(
            (run_dir / "stage-01" / "decision.json").read_text(encoding="utf-8")
        ),
    )
    assert decision["run_id"] == "run-1"
    assert decision["status"] == "done"
    assert decision["output_artifacts"] == [
        "goal.md",
        "goal_brief.md",
        "hardware_profile.json",
    ]


def test_execute_stage_contract_validation_missing_output_file_marks_failed(
    monkeypatch: pytest.MonkeyPatch,
    run_dir: Path,
    rc_config: RCConfig,
    adapters: AdapterBundle,
) -> None:
    def bad_executor(
        _stage_dir: Path,
        _run_dir: Path,
        _config: RCConfig,
        _adapters: AdapterBundle,
        *,
        llm: object = None,
    ):
        _ = llm
        return rc_executor.StageResult(
            stage=Stage.TOPIC_INIT, status=StageStatus.DONE, artifacts=("goal.md",)
        )

    monkeypatch.setitem(rc_executor._STAGE_EXECUTORS, Stage.TOPIC_INIT, bad_executor)
    result = rc_executor.execute_stage(
        Stage.TOPIC_INIT,
        run_dir=run_dir,
        run_id="run-2",
        config=rc_config,
        adapters=adapters,
        auto_approve_gates=True,
    )
    assert result.status == StageStatus.FAILED
    assert "Missing or empty output: goal.md" in (result.error or "")


def test_execute_stage_contract_validation_missing_output_directory_marks_failed(
    monkeypatch: pytest.MonkeyPatch,
    run_dir: Path,
    rc_config: RCConfig,
    adapters: AdapterBundle,
) -> None:
    _write_prior_artifact(run_dir, 5, "shortlist.jsonl", '{"title": "x"}')

    def bad_executor(
        _stage_dir: Path,
        _run_dir: Path,
        _config: RCConfig,
        _adapters: AdapterBundle,
        *,
        llm: object = None,
    ):
        _ = llm
        return rc_executor.StageResult(
            stage=Stage.KNOWLEDGE_EXTRACT,
            status=StageStatus.DONE,
            artifacts=("cards/",),
        )

    monkeypatch.setitem(
        rc_executor._STAGE_EXECUTORS, Stage.KNOWLEDGE_EXTRACT, bad_executor
    )
    result = rc_executor.execute_stage(
        Stage.KNOWLEDGE_EXTRACT,
        run_dir=run_dir,
        run_id="run-3",
        config=rc_config,
        adapters=adapters,
        auto_approve_gates=True,
    )
    assert result.status == StageStatus.FAILED
    assert "Missing output directory: cards/" in (result.error or "")


def test_execute_stage_missing_required_input_returns_failed(
    run_dir: Path,
    rc_config: RCConfig,
    adapters: AdapterBundle,
) -> None:
    result = rc_executor.execute_stage(
        Stage.PROBLEM_DECOMPOSE,
        run_dir=run_dir,
        run_id="run-4",
        config=rc_config,
        adapters=adapters,
        auto_approve_gates=True,
    )
    assert result.status == StageStatus.FAILED
    assert "Missing input: goal.md" in (result.error or "")


def test_execute_stage_gate_behavior_auto_approve_true_keeps_done(
    monkeypatch: pytest.MonkeyPatch,
    run_dir: Path,
    rc_config: RCConfig,
    adapters: AdapterBundle,
) -> None:
    _write_prior_artifact(run_dir, 4, "candidates.jsonl", '{"title": "paper"}')

    def good_executor(
        stage_dir: Path,
        _run_dir: Path,
        _config: RCConfig,
        _adapters: AdapterBundle,
        *,
        llm: object = None,
        **_kwargs: object,
    ):
        _ = llm
        (stage_dir / "shortlist.jsonl").write_text(
            '{"title": "paper"}\n', encoding="utf-8"
        )
        return rc_executor.StageResult(
            stage=Stage.LITERATURE_SCREEN,
            status=StageStatus.DONE,
            artifacts=("shortlist.jsonl",),
        )

    monkeypatch.setitem(
        rc_executor._STAGE_EXECUTORS, Stage.LITERATURE_SCREEN, good_executor
    )
    result = rc_executor.execute_stage(
        Stage.LITERATURE_SCREEN,
        run_dir=run_dir,
        run_id="run-5",
        config=rc_config,
        adapters=adapters,
        auto_approve_gates=True,
    )
    assert result.status == StageStatus.DONE
    memory_entries = getattr(adapters.memory, "entries", [])
    assert any(
        ns == "gates" and "auto-approved" in content for ns, content in memory_entries
    )


def test_execute_stage_gate_behavior_auto_approve_false_blocks(
    monkeypatch: pytest.MonkeyPatch,
    run_dir: Path,
    rc_config: RCConfig,
    adapters: AdapterBundle,
) -> None:
    _write_prior_artifact(run_dir, 4, "candidates.jsonl", '{"title": "paper"}')

    def good_executor(
        stage_dir: Path,
        _run_dir: Path,
        _config: RCConfig,
        _adapters: AdapterBundle,
        *,
        llm: object = None,
        **_kwargs: object,
    ):
        _ = llm
        (stage_dir / "shortlist.jsonl").write_text(
            '{"title": "paper"}\n', encoding="utf-8"
        )
        return rc_executor.StageResult(
            stage=Stage.LITERATURE_SCREEN,
            status=StageStatus.DONE,
            artifacts=("shortlist.jsonl",),
        )

    monkeypatch.setitem(
        rc_executor._STAGE_EXECUTORS, Stage.LITERATURE_SCREEN, good_executor
    )
    result = rc_executor.execute_stage(
        Stage.LITERATURE_SCREEN,
        run_dir=run_dir,
        run_id="run-6",
        config=rc_config,
        adapters=adapters,
        auto_approve_gates=False,
    )
    assert result.status == StageStatus.BLOCKED_APPROVAL
    assert result.decision == "block"
    message_calls = getattr(adapters.message, "calls", [])
    assert message_calls
    assert "Approval required" in message_calls[-1][2]


def test_execute_stage_llm_client_creation_error_falls_back_without_crash(
    monkeypatch: pytest.MonkeyPatch,
    run_dir: Path,
    rc_config: RCConfig,
    adapters: AdapterBundle,
) -> None:
    def boom(_config: RCConfig):
        raise RuntimeError("llm init failed")

    monkeypatch.setattr("researchclaw.pipeline.executor.LLMClient.from_rc_config", boom)
    result = rc_executor.execute_stage(
        Stage.TOPIC_INIT,
        run_dir=run_dir,
        run_id="run-7",
        config=rc_config,
        adapters=adapters,
        auto_approve_gates=True,
    )
    assert result.status == StageStatus.DONE
    assert (run_dir / "stage-01" / "goal.md").exists()


def test_execute_stage_executor_exception_returns_failed(
    monkeypatch: pytest.MonkeyPatch,
    run_dir: Path,
    rc_config: RCConfig,
    adapters: AdapterBundle,
) -> None:
    def raising_executor(
        _stage_dir: Path,
        _run_dir: Path,
        _config: RCConfig,
        _adapters: AdapterBundle,
        *,
        llm: object = None,
        **_kwargs: object,
    ):
        _ = llm
        raise RuntimeError("stage exploded")

    monkeypatch.setitem(
        rc_executor._STAGE_EXECUTORS, Stage.TOPIC_INIT, raising_executor
    )
    result = rc_executor.execute_stage(
        Stage.TOPIC_INIT,
        run_dir=run_dir,
        run_id="run-8",
        config=rc_config,
        adapters=adapters,
        auto_approve_gates=True,
    )
    assert result.status == StageStatus.FAILED
    assert result.decision == "retry"
    assert "stage exploded" in (result.error or "")


@pytest.mark.parametrize(
    "stage",
    [
        Stage.TOPIC_INIT,
        Stage.PROBLEM_DECOMPOSE,
        Stage.SEARCH_STRATEGY,
        Stage.LITERATURE_COLLECT,
        Stage.LITERATURE_SCREEN,
        Stage.KNOWLEDGE_EXTRACT,
        Stage.SYNTHESIS,
        Stage.HYPOTHESIS_GEN,
        Stage.EXPERIMENT_DESIGN,
        Stage.CODE_GENERATION,
    ],
)
def test_stage_executor_mapping_values_are_callable(stage: Stage) -> None:
    assert callable(rc_executor._STAGE_EXECUTORS[stage])


class TestStageHealth:
    def test_stage_health_json_written(self, tmp_path: Path) -> None:
        from researchclaw.pipeline.executor import execute_stage
        from researchclaw.pipeline.stages import Stage

        config = RCConfig.load(
            Path(__file__).parent.parent / "config.researchclaw.example.yaml",
            check_paths=False,
        )
        result = execute_stage(
            Stage.TOPIC_INIT,
            run_dir=tmp_path,
            run_id="test-health",
            config=config,
            adapters=AdapterBundle(),
            auto_approve_gates=True,
        )
        health_path = tmp_path / "stage-01" / "stage_health.json"
        assert result is not None
        assert health_path.exists()

    def test_stage_health_has_required_fields(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock, patch

        from researchclaw.pipeline.executor import execute_stage
        from researchclaw.pipeline.stages import Stage

        config = RCConfig.load(
            Path(__file__).parent.parent / "config.researchclaw.example.yaml",
            check_paths=False,
        )

        with patch("researchclaw.pipeline.executor.LLMClient") as mock_llm_cls:
            mock_client = MagicMock()
            mock_client.chat.return_value = MagicMock(
                content='{"topic": "test", "research_questions": ["q1"]}'
            )
            mock_llm_cls.from_rc_config.return_value = mock_client

            execute_stage(
                Stage.TOPIC_INIT,
                run_dir=tmp_path,
                run_id="test-health-fields",
                config=config,
                adapters=AdapterBundle(),
                auto_approve_gates=True,
            )

        health_path = tmp_path / "stage-01" / "stage_health.json"
        if health_path.exists():
            data = json.loads(health_path.read_text(encoding="utf-8"))
            assert "stage_id" in data
            assert "run_id" in data
            assert "duration_sec" in data
            assert "status" in data
            assert "timestamp" in data
            assert data["duration_sec"] >= 0


    def test_stage_health_duration_positive(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock, patch

        from researchclaw.pipeline.executor import execute_stage
        from researchclaw.pipeline.stages import Stage

        config = RCConfig.load(
            Path(__file__).parent.parent / "config.researchclaw.example.yaml",
            check_paths=False,
        )

        with patch("researchclaw.pipeline.executor.LLMClient") as mock_llm_cls:
            mock_client = MagicMock()
            mock_client.chat.return_value = MagicMock(
                content='{"topic": "test", "sub_problems": []}'
            )
            mock_llm_cls.from_rc_config.return_value = mock_client

            execute_stage(
                Stage.TOPIC_INIT,
                run_dir=tmp_path,
                run_id="test-duration",
                config=config,
                adapters=AdapterBundle(),
                auto_approve_gates=True,
            )

        health_path = tmp_path / "stage-01" / "stage_health.json"
        if health_path.exists():
            data = json.loads(health_path.read_text(encoding="utf-8"))
            assert data["duration_sec"] >= 0

# Contracts import for Stage 13/22 preservation features.
from researchclaw.pipeline.contracts import CONTRACTS


class TestIterativeRefine:
    def _prepare_refine_inputs(self, run_dir: Path) -> None:
        _write_prior_artifact(
            run_dir,
            10,
            "experiment.py",
            (
                "import random\n"
                "random.seed(42)\n"
                "for i in range(5):\n"
                "    print(f'val_loss: {0.5 - i*0.05:.4f}')\n"
            ),
        )
        (run_dir / "stage-12" / "runs").mkdir(parents=True, exist_ok=True)
        _write_prior_artifact(
            run_dir,
            12,
            "runs/run-1.json",
            json.dumps(
                {
                    "run_id": "run-1",
                    "status": "completed",
                    "metrics": {"val_loss": 0.35},
                }
            ),
        )

    def test_refine_simulated_mode_skips(
        self,
        run_dir: Path,
        rc_config: RCConfig,
        adapters: AdapterBundle,
    ) -> None:
        """R10-Fix3: Simulated mode should skip iterative refinement entirely."""
        self._prepare_refine_inputs(run_dir)
        stage_dir = run_dir / "stage-13"
        stage_dir.mkdir(parents=True, exist_ok=True)
        # Force simulated mode to test the skip behavior
        import copy
        sim_cfg = copy.deepcopy(rc_config)
        object.__setattr__(sim_cfg.experiment, "mode", "simulated")

        result = rc_executor._execute_iterative_refine(
            stage_dir,
            run_dir,
            sim_cfg,
            adapters,
            llm=None,
        )

        payload = json.loads(
            (stage_dir / "refinement_log.json").read_text(encoding="utf-8")
        )
        assert payload["skipped"] is True
        assert payload["mode"] == "simulated"
        assert result.status == StageStatus.DONE
        # Original code should be copied as final
        assert (stage_dir / "experiment_final.py").exists()

    def test_refine_no_llm_saves_original_as_final(
        self,
        run_dir: Path,
        rc_config: RCConfig,
        adapters: AdapterBundle,
    ) -> None:
        self._prepare_refine_inputs(run_dir)
        stage_dir = run_dir / "stage-13"
        stage_dir.mkdir(parents=True, exist_ok=True)

        result = rc_executor._execute_iterative_refine(
            stage_dir,
            run_dir,
            rc_config,
            adapters,
            llm=None,
        )

        original_code = (run_dir / "stage-10" / "experiment.py").read_text(
            encoding="utf-8"
        )
        final_code = (stage_dir / "experiment_final.py").read_text(encoding="utf-8")
        assert original_code == final_code
        payload = json.loads(
            (stage_dir / "refinement_log.json").read_text(encoding="utf-8")
        )
        assert payload["stop_reason"] == "llm_unavailable"
        assert result.status == StageStatus.DONE

    def test_refine_with_llm_generates_improved_code(
        self,
        run_dir: Path,
        rc_config: RCConfig,
        adapters: AdapterBundle,
    ) -> None:
        self._prepare_refine_inputs(run_dir)
        stage_dir = run_dir / "stage-13"
        stage_dir.mkdir(parents=True, exist_ok=True)
        llm = FakeLLMClient(
            "```python\n"
            "import random\n"
            "random.seed(42)\n"
            "for i in range(10):\n"
            "    print(f'val_loss: {0.4 - i*0.03:.4f}')\n"
            "```"
        )

        rc_executor._execute_iterative_refine(
            stage_dir, run_dir, rc_config, adapters, llm=llm
        )

        assert (stage_dir / "experiment_v1").is_dir()
        assert (stage_dir / "experiment_final.py").exists()
        payload = json.loads(
            (stage_dir / "refinement_log.json").read_text(encoding="utf-8")
        )
        assert isinstance(payload.get("iterations"), list)
        assert payload["iterations"]

    def test_refine_converges_after_no_improvement(
        self,
        tmp_path: Path,
        run_dir: Path,
        adapters: AdapterBundle,
    ) -> None:
        import sys

        self._prepare_refine_inputs(run_dir)
        stage_dir = run_dir / "stage-13"
        stage_dir.mkdir(parents=True, exist_ok=True)

        sandbox_data = {
            "project": {"name": "rc-test", "mode": "docs-first"},
            "research": {
                "topic": "test-driven science",
                "domains": ["ml", "systems"],
                "daily_paper_count": 2,
                "quality_threshold": 8.2,
            },
            "runtime": {"timezone": "UTC"},
            "notifications": {
                "channel": "local",
                "on_stage_start": True,
                "on_stage_fail": False,
                "on_gate_required": True,
            },
            "knowledge_base": {"backend": "markdown", "root": str(tmp_path / "kb")},
            "openclaw_bridge": {"use_memory": True, "use_message": True},
            "llm": {
                "provider": "openai-compatible",
                "base_url": "http://localhost:1234/v1",
                "api_key_env": "RC_TEST_KEY",
                "api_key": "inline-test-key",
                "primary_model": "fake-model",
                "fallback_models": [],
            },
            "security": {"hitl_required_stages": [5, 9, 20]},
            "experiment": {
                "mode": "sandbox",
                "time_budget_sec": 30,
                "max_iterations": 3,
                "metric_key": "val_loss",
                "metric_direction": "minimize",
                "sandbox": {
                    "python_path": sys.executable,
                    "gpu_required": False,
                    "max_memory_mb": 1024,
                },
            },
        }
        sandbox_config = RCConfig.from_dict(
            sandbox_data,
            project_root=tmp_path,
            check_paths=False,
        )
        llm = FakeLLMClient(
            "```python\nfor _ in range(3):\n    print('val_loss: 0.5000')\n```"
        )

        rc_executor._execute_iterative_refine(
            stage_dir,
            run_dir,
            sandbox_config,
            adapters,
            llm=llm,
        )

        payload = json.loads(
            (stage_dir / "refinement_log.json").read_text(encoding="utf-8")
        )
        assert payload["converged"] is True
        assert payload["stop_reason"] == "no_improvement_for_2_iterations"

    def test_refine_artifacts_include_version_files(
        self,
        run_dir: Path,
        rc_config: RCConfig,
        adapters: AdapterBundle,
    ) -> None:
        self._prepare_refine_inputs(run_dir)
        stage_dir = run_dir / "stage-13"
        stage_dir.mkdir(parents=True, exist_ok=True)
        llm = FakeLLMClient(
            "```python\n"
            "import random\n"
            "random.seed(42)\n"
            "for i in range(10):\n"
            "    print(f'val_loss: {0.4 - i*0.03:.4f}')\n"
            "```"
        )

        result = rc_executor._execute_iterative_refine(
            stage_dir,
            run_dir,
            rc_config,
            adapters,
            llm=llm,
        )

        assert "refinement_log.json" in result.artifacts
        assert "experiment_final/" in result.artifacts
        assert any(
            artifact.startswith("experiment_v") and artifact.endswith("/")
            for artifact in result.artifacts
        )

    def test_refine_fails_completion_gate_when_no_valid_metric(
        self,
        run_dir: Path,
        rc_config: RCConfig,
        adapters: AdapterBundle,
    ) -> None:
        self._prepare_refine_inputs(run_dir)
        stage_dir = run_dir / "stage-13"
        stage_dir.mkdir(parents=True, exist_ok=True)
        llm = FakeLLMClient("```python\nthis is not valid python\n```")

        result = rc_executor._execute_iterative_refine(
            stage_dir,
            run_dir,
            rc_config,
            adapters,
            llm=llm,
        )

        payload = json.loads(
            (stage_dir / "refinement_log.json").read_text(encoding="utf-8")
        )
        assert result.status == StageStatus.FAILED
        assert result.decision == "retry"
        assert payload["completion_gate"]["ok"] is False
        assert "best_metric_missing" in payload["completion_gate"]["reasons"]

    def test_refine_sandbox_mode_runs_code(
        self,
        tmp_path: Path,
        run_dir: Path,
        adapters: AdapterBundle,
    ) -> None:
        import sys

        self._prepare_refine_inputs(run_dir)
        stage_dir = run_dir / "stage-13"
        stage_dir.mkdir(parents=True, exist_ok=True)

        sandbox_data = {
            "project": {"name": "rc-test", "mode": "docs-first"},
            "research": {
                "topic": "test-driven science",
                "domains": ["ml", "systems"],
                "daily_paper_count": 2,
                "quality_threshold": 8.2,
            },
            "runtime": {"timezone": "UTC"},
            "notifications": {
                "channel": "local",
                "on_stage_start": True,
                "on_stage_fail": False,
                "on_gate_required": True,
            },
            "knowledge_base": {"backend": "markdown", "root": str(tmp_path / "kb")},
            "openclaw_bridge": {"use_memory": True, "use_message": True},
            "llm": {
                "provider": "openai-compatible",
                "base_url": "http://localhost:1234/v1",
                "api_key_env": "RC_TEST_KEY",
                "api_key": "inline-test-key",
                "primary_model": "fake-model",
                "fallback_models": [],
            },
            "security": {"hitl_required_stages": [5, 9, 20]},
            "experiment": {
                "mode": "sandbox",
                "time_budget_sec": 30,
                "max_iterations": 3,
                "metric_key": "val_loss",
                "metric_direction": "minimize",
                "sandbox": {
                    "python_path": sys.executable,
                    "gpu_required": False,
                    "max_memory_mb": 1024,
                },
            },
        }
        sandbox_config = RCConfig.from_dict(
            sandbox_data,
            project_root=tmp_path,
            check_paths=False,
        )
        llm = FakeLLMClient(
            "```python\n"
            "import random\n"
            "random.seed(42)\n"
            "for i in range(10):\n"
            "    print(f'val_loss: {0.4 - i*0.03:.4f}')\n"
            "```"
        )

        rc_executor._execute_iterative_refine(
            stage_dir,
            run_dir,
            sandbox_config,
            adapters,
            llm=llm,
        )

        payload = json.loads(
            (stage_dir / "refinement_log.json").read_text(encoding="utf-8")
        )
        assert any(
            "sandbox" in iteration for iteration in payload.get("iterations", [])
        )

    def test_refine_incremental_replay_skips_first_llm_rewrite(
        self,
        tmp_path: Path,
        run_dir: Path,
        adapters: AdapterBundle,
    ) -> None:
        import sys

        self._prepare_refine_inputs(run_dir)
        stage_dir = run_dir / "stage-13"
        resume_dir = stage_dir / "experiment"
        resume_dir.mkdir(parents=True, exist_ok=True)
        (resume_dir / "main.py").write_text(
            (
                "from helper import cached_metric\n"
                "print(f'val_loss: {cached_metric():.4f}')\n"
            ),
            encoding="utf-8",
        )
        (resume_dir / "helper.py").write_text(
            "def cached_metric() -> float:\n    return 0.1234\n",
            encoding="utf-8",
        )
        (resume_dir / "resume_seed_registry.json").write_text(
            json.dumps(
                {
                    "conditions": {
                        "cheap_proxy_controller": {
                            "0": {"primary_metric": 0.1234}
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        data = {
            "project": {"name": "rc-test", "mode": "docs-first"},
            "research": {
                "topic": "test-driven science",
                "domains": ["ml", "systems"],
                "daily_paper_count": 2,
                "quality_threshold": 8.2,
            },
            "runtime": {"timezone": "UTC"},
            "notifications": {
                "channel": "local",
                "on_stage_start": True,
                "on_stage_fail": False,
                "on_gate_required": True,
            },
            "knowledge_base": {"backend": "markdown", "root": str(tmp_path / "kb")},
            "openclaw_bridge": {"use_memory": True, "use_message": True},
            "llm": {
                "provider": "openai-compatible",
                "base_url": "http://localhost:1234/v1",
                "api_key_env": "RC_TEST_KEY",
                "api_key": "inline-test-key",
                "primary_model": "fake-model",
                "fallback_models": [],
            },
            "security": {"hitl_required_stages": [5, 9, 20]},
            "experiment": {
                "mode": "sandbox",
                "time_budget_sec": 30,
                "max_iterations": 1,
                "metric_key": "val_loss",
                "metric_direction": "minimize",
                "sandbox": {
                    "python_path": sys.executable,
                    "gpu_required": False,
                    "max_memory_mb": 1024,
                },
            },
        }
        sandbox_config = RCConfig.from_dict(
            data,
            project_root=tmp_path,
            check_paths=False,
        )
        llm = FakeLLMClient("```python\nraise RuntimeError('llm rewrite should be skipped')\n```")

        rc_executor._execute_iterative_refine(
            stage_dir,
            run_dir,
            sandbox_config,
            adapters,
            llm=llm,
        )

        assert len(llm.calls) == 0
        payload = json.loads(
            (stage_dir / "refinement_log.json").read_text(encoding="utf-8")
        )
        assert payload["incremental_refine_available"] is True
        assert payload["iterations"][0]["incremental_replay"] is True
        assert payload["iterations"][0]["incremental_plan"]["reason"] == "run_local_replay"
        assert (stage_dir / "experiment_v1" / "helper.py").exists()
        assert (
            stage_dir / "experiment_v1" / "resume_seed_registry.json"
        ).exists()
        main_code = (stage_dir / "experiment_v1" / "main.py").read_text(
            encoding="utf-8"
        )
        assert "cached_metric" in main_code

    def test_build_stage13_incremental_plan_skips_when_no_change(
        self,
        tmp_path: Path,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        stage_dir = tmp_path / "stage-13"
        stage_dir.mkdir(parents=True)
        results_dir = stage_dir / "refine_sandbox_v1" / "_docker_project_1"
        results_dir.mkdir(parents=True)
        (results_dir / "results.json").write_text(
            json.dumps(
                {
                    "metrics": {
                        "full_finetuning_seed_0": 0.71,
                        "full_finetuning_seed_1": 0.72,
                        "full_finetuning_seed_2": 0.73,
                        "qlora_fixed_seed_0": 0.61,
                        "qlora_fixed_seed_1": 0.62,
                        "qlora_fixed_seed_2": 0.63,
                    }
                }
            ),
            encoding="utf-8",
        )
        config_text = (
            'register("full_finetuning", "FullFineTuningCondition", "baseline", False, False, [])\n'
            'register("qlora_fixed", "QLoRACondition", "baseline", True, False, [])\n'
            'self.screening_seeds: list[int] = [0, 1, 2]\n'
            'self.active_condition_names: list[str] = ["full_finetuning", "qlora_fixed"]\n'
        )
        best_files = {"config.py": config_text, "main.py": "print('ok')\n"}
        plan = rc_execution_impl._build_stage13_incremental_plan(
            stage_dir=stage_dir,
            best_files=best_files,
            candidate_files=dict(best_files),
            condition_coverage_hint="",
        )
        assert plan["active"] is False
        assert plan["reason"] == "no_executable_change"

    def test_stage13_incremental_replay_is_blocked_by_baseline_coverage_gap(
        self,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        assert rc_execution_impl._should_use_stage13_incremental_replay(
            incremental_refine_available=True,
            interrupted_resume_project_dir=Path("/tmp/interrupted"),
            iteration=1,
            preflight_incremental_plan={"reason": "coverage_gap_replay"},
            method_diagnosis_payload={"baseline_coverage_gap": True},
        ) is False

    def test_stage13_incremental_replay_still_handles_interrupted_resume_without_gap(
        self,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        assert rc_execution_impl._should_use_stage13_incremental_replay(
            incremental_refine_available=True,
            interrupted_resume_project_dir=Path("/tmp/interrupted"),
            iteration=1,
            preflight_incremental_plan={"reason": "coverage_gap_replay"},
            method_diagnosis_payload={"baseline_coverage_gap": False},
        ) is True

    def test_stage13_parallel_wrapper_supports_plain_main_entrypoint(
        self,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        main_text = (
            "from __future__ import annotations\n\n"
            "import json\n"
            "import os\n"
            "from pathlib import Path\n\n"
            "REQUIRED_ACTIVE_CONDITIONS: list[str] = [\n"
            '    "lora_fixed",\n'
            '    "probe_control",\n'
            '    "cheap_proxy_controller",\n'
            "]\n\n"
            "def main() -> None:\n"
            "    print(REQUIRED_ACTIVE_CONDITIONS)\n\n"
            'if __name__ == "__main__":\n'
            "    main()\n"
        )

        wrapped = rc_execution_impl._ensure_stage13_main_parallel_wrapper(main_text)

        assert "def _stage13_single_worker_main() -> None:" in wrapped
        assert "def _run_parallel_stage13_subprocess_if_requested() -> bool:" in wrapped
        assert "PARALLEL_STAGE13_START" in wrapped
        assert "CUDA_VISIBLE_DEVICES" in wrapped
        assert 'env["CUDA_VISIBLE_DEVICES"] = str(worker_index)' in wrapped
        assert 'if __name__ == "__main__":\n    main()' in wrapped

    def test_stage13_parallel_wrapper_uses_container_local_cuda_indices(
        self,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        main_text = (
            "from __future__ import annotations\n\n"
            "import json\n"
            "import os\n"
            "import torch\n"
            "from pathlib import Path\n\n"
            "ACTIVE_CONDITIONS: list[str] = [\n"
            '    "lora_fixed",\n'
            '    "dora",\n'
            "]\n\n"
            "def _json_ready(value: Any) -> Any:\n"
            "    return value\n\n"
            "def _run_stage13_experiment(output_suffix: str = '') -> None:\n"
            "    print(output_suffix)\n\n"
            "def main() -> None:\n"
            "    _run_stage13_experiment()\n\n"
            'if __name__ == "__main__":\n'
            "    main()\n"
        )

        wrapped = rc_execution_impl._ensure_stage13_main_parallel_wrapper(main_text)

        assert 'os.environ["CUDA_VISIBLE_DEVICES"] = str(worker_index)' in wrapped
        assert '"physical_gpu_id": str(assigned_gpu_id)' in wrapped

    def test_stage13_baseline_grid_is_forced_into_regenerated_project(
        self,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        candidate_files = {
            "config.py": (
                "class ExperimentConfig:\n"
                "    def __init__(self) -> None:\n"
                "        self.active_condition_names: list[str] = [\n"
                '            "lora_fixed",\n'
                '            "qlora_fixed",\n'
                '            "probe_control",\n'
                "        ]\n"
                '        self.precision: str = "float32"\n'
                "        self.condition_registry = []\n"
                "    def validate(self) -> None:\n"
                "        if len(self.condition_registry) > 8:\n"
                '            raise ValueError("Active condition count must be <= 8.")\n'
            ),
            "main.py": (
                "REQUIRED_ACTIVE_CONDITIONS: list[str] = [\n"
                '    "lora_fixed",\n'
                '    "qlora_fixed",\n'
                '    "probe_control",\n'
                "]\n"
                'config.precision = "float32"\n'
                'os.environ.setdefault("EXPERIMENT_PRECISION", "float32")\n'
            ),
        }
        diagnosis_payload = {
            "baseline_coverage_gap": True,
            "required_baseline_conditions": [
                "lora_fixed",
                "lora_fixed_matched_rank",
                "dora",
                "pissa_init",
                "milora_init",
                "lora_ga_init",
                "sensitivity_lora",
                "full_finetuning",
                "lora_fa",
                "adalora_like_budget",
                "qlora_fixed",
            ],
            "missing_active_conditions": ["dora", "lora_fa", "adalora_like_budget"],
        }

        enforced = rc_execution_impl._enforce_stage13_required_baseline_grid(
            dict(candidate_files),
            diagnosis_payload,
        )

        main_text = enforced["main.py"]
        config_text = enforced["config.py"]
        for condition_name in [
            "lora_fixed_matched_rank",
            "dora",
            "pissa_init",
            "milora_init",
            "lora_ga_init",
            "sensitivity_lora",
            "full_finetuning",
            "lora_fa",
            "adalora_like_budget",
            "cheap_proxy_controller",
            "exact_svd_oracle_controller",
            "falcon_qb_init_plus_cheap_proxy",
        ]:
            assert condition_name in main_text
            assert condition_name in config_text
        assert "Active condition count must be <= 8" not in config_text
        assert 'self.precision: str = "bf16"' in config_text
        assert 'config.precision = "bf16"' in main_text
        assert 'os.environ.setdefault("EXPERIMENT_PRECISION", "bf16")' in main_text
        assert '"float32"' not in main_text

    def test_stage13_bf16_precision_is_forced_without_baseline_gap(
        self,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        enforced = rc_execution_impl._enforce_stage13_required_baseline_grid(
            {
                "config.py": 'self.precision: str = "float32"\n',
                "main.py": (
                    'config.precision = "float32"\n'
                    'os.environ.setdefault("EXPERIMENT_PRECISION", "float32")\n'
                ),
            },
            {"baseline_coverage_gap": False},
        )

        assert 'self.precision: str = "bf16"' in enforced["config.py"]
        assert 'config.precision = "bf16"' in enforced["main.py"]
        assert 'os.environ.setdefault("EXPERIMENT_PRECISION", "bf16")' in enforced["main.py"]

    def test_stage13_full_ft_uses_stateless_optimizer_without_baseline_gap(
        self,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        enforced = rc_execution_impl._enforce_stage13_required_baseline_grid(
            {
                "methods.py": (
                    "class NumpyAdamW:\n"
                    "    def __init__(\n"
                    "        self,\n"
                    "        params: list[nn.Parameter],\n"
                    "        lr: float,\n"
                    "        betas: tuple[float, float] = (0.9, 0.999),\n"
                    "        eps: float = 1.0e-8,\n"
                    "        weight_decay: float = 0.0,\n"
                    "        max_grad_norm: float = 1.0,\n"
                    "    ) -> None:\n"
                    "        self.max_grad_norm = float(max_grad_norm)\n"
                    "        self.state: dict[int, dict[str, Any]] = {}\n"
                    "    def step(self) -> None:\n"
                    "        for param in self.params:\n"
                    "            grad = torch.nan_to_num(param.grad.detach(), nan=0.0, posinf=0.0, neginf=0.0)\n"
                    "            param_id = id(param)\n"
                ),
                "evaluate.py": (
                    "    def _optimizer_for_model(self, model: BackboneWithAdapters) -> NumpyAdamW:\n"
                    "        lr = float(self.config.learning_rate_full_ft) if str(model.mode) == \"full_ft\" else float(self.config.learning_rate_peft)\n"
                    "        return NumpyAdamW(\n"
                    "            [param for param in model.parameters() if param.requires_grad],\n"
                    "            lr=lr,\n"
                    "            weight_decay=float(self.config.weight_decay),\n"
                    "            max_grad_norm=float(self.config.max_grad_norm),\n"
                    "        )\n"
                ),
            },
            {"baseline_coverage_gap": False},
        )

        assert "use_moments: bool = True" in enforced["methods.py"]
        assert "if not self.use_moments:" in enforced["methods.py"]
        assert "use_moments = str(model.mode) != \"full_ft\"" in enforced["evaluate.py"]
        assert "use_moments=use_moments" in enforced["evaluate.py"]

    def test_stage13_adapter_weights_align_to_bf16_activation_dtype(
        self,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        enforced = rc_execution_impl._enforce_stage13_required_baseline_grid(
            {
                "methods.py": (
                    "class DoRALinear(nn.Module):\n"
                    "    def forward(self, x: torch.Tensor) -> torch.Tensor:\n"
                    "        scaled_weight = self.base_linear.weight.float() * self.magnitude\n"
                    "        return F.linear(x, scaled_weight, self.base_linear.bias)\n"
                ),
            },
            {"baseline_coverage_gap": False},
        )

        assert "scaled_weight = scaled_weight.to(dtype=x.dtype, device=x.device)" in enforced["methods.py"]
        assert "bias = self.base_linear.bias" in enforced["methods.py"]
        assert "return F.linear(x, scaled_weight, bias)" in enforced["methods.py"]

    def test_stage13_adapter_dtype_alignment_preserves_dora_branch_indent(
        self,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        enforced = rc_execution_impl._enforce_stage13_required_baseline_grid(
            {
                "methods.py": (
                    "class LoRALinear(nn.Module):\n"
                    "    def forward(self, x: torch.Tensor) -> torch.Tensor:\n"
                    "        if self.use_dora and self.dora_magnitude is not None:\n"
                    "            weight = self.base_linear.weight + self.delta_weight()\n"
                    "            scaled_weight = weight * self.dora_magnitude.unsqueeze(1)\n"
                    "            return F.linear(x, scaled_weight, self.base_linear.bias)\n"
                    "        base = self.base_linear(x)\n"
                    "        return base\n"
                ),
            },
            {"baseline_coverage_gap": False},
        )

        methods_text = enforced["methods.py"]
        assert "            scaled_weight = scaled_weight.to(dtype=x.dtype, device=x.device)" in methods_text
        assert "            return F.linear(x, scaled_weight, bias)" in methods_text
        assert "        return F.linear(x, scaled_weight, bias)" not in methods_text.splitlines()

    def test_stage13_adapter_dtype_alignment_repairs_polluted_partial_code(
        self,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        enforced = rc_execution_impl._enforce_stage13_required_baseline_grid(
            {
                "methods.py": (
                    "class LoRALinear(nn.Module):\n"
                    "    def forward(self, x: torch.Tensor) -> torch.Tensor:\n"
                    "        if self.use_dora and self.dora_magnitude is not None:\n"
                    "            scaled_weight = self.base_linear.weight\n"
                    "            scaled_weight = scaled_weight.to(dtype=x.dtype, device=x.device)\n"
                    "        bias = self.base_linear.bias\n"
                    "        if bias is not None:\n"
                    "            bias = bias.to(dtype=x.dtype, device=x.device)\n"
                    "        return F.linear(x, scaled_weight, bias)\n"
                    "        base = self.base_linear(x)\n"
                    "        return base\n"
                ),
            },
            {"baseline_coverage_gap": False},
        )

        lines = enforced["methods.py"].splitlines()
        assert "            bias = self.base_linear.bias" in lines
        assert "            return F.linear(x, scaled_weight, bias)" in lines
        assert "        bias = self.base_linear.bias" not in lines
        assert "        return F.linear(x, scaled_weight, bias)" not in lines

    def test_stage13_missing_related_work_baselines_are_injected(
        self,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        candidate_files = {
            "config.py": (
                "    def build_condition_registry(self) -> list[dict[str, object]]:\n"
                "        registry: list[dict[str, object]] = []\n"
                "        def register(name, class_name, family, quantized, adaptive, datasets):\n"
                "            registry.append({'name': name, 'class_name': class_name})\n"
                '        register("sensitivity_lora", "SensitivityLoRACondition", "recent_baseline", False, True, [])\n'
                "        active_names = list(self.active_condition_names)\n"
                "        return [entry for entry in registry if entry['name'] in set(active_names)]\n"
            ),
            "methods.py": (
                "class FixedLoRACondition: pass\n"
                "class SensitivityLoRACondition(FixedLoRACondition): pass\n"
                "class FalconQBPreparationMixin: pass\n"
                "CONDITION_CLASS_REGISTRY: dict[str, object] = {\n"
                '    "sensitivity_lora": SensitivityLoRACondition,\n'
                "}\n"
            ),
        }

        enforced = rc_execution_impl._enforce_stage13_required_baseline_grid(
            candidate_files,
            {
                "baseline_coverage_gap": True,
                "missing_registered_conditions": ["lora_fa", "adalora_like_budget"],
            },
        )

        assert 'register("lora_fa", "LoRAFACondition"' in enforced["config.py"]
        assert 'register("adalora_like_budget", "AdaLoRALikeBudgetCondition"' in enforced["config.py"]
        assert "class LoRAFACondition" in enforced["methods.py"]
        assert "class AdaLoRALikeBudgetCondition" in enforced["methods.py"]
        assert '"lora_fa": LoRAFACondition' in enforced["methods.py"]
        assert '"adalora_like_budget": AdaLoRALikeBudgetCondition' in enforced["methods.py"]

    def test_stage13_interrupted_resume_uses_deterministic_full_grid_replay(
        self,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        assert rc_execution_impl._should_use_stage13_deterministic_baseline_replay(
            candidate_files={
                "main.py": "print('main')\n",
                "config.py": "class Config: pass\n",
                "methods.py": "class Method: pass\n",
            },
            method_diagnosis_payload={"baseline_coverage_gap": True},
            interrupted_resume_project_dir=Path("/tmp/interrupted"),
        ) is True
        assert rc_execution_impl._should_use_stage13_deterministic_baseline_replay(
            candidate_files={"main.py": "print('main')\n"},
            method_diagnosis_payload={"baseline_coverage_gap": True},
            interrupted_resume_project_dir=Path("/tmp/interrupted"),
        ) is False
        assert rc_execution_impl._should_use_stage13_deterministic_baseline_replay(
            candidate_files={
                "main.py": "print('main')\n",
                "config.py": "class Config: pass\n",
                "methods.py": "class Method: pass\n",
            },
            method_diagnosis_payload={"baseline_coverage_gap": False},
            interrupted_resume_project_dir=Path("/tmp/interrupted"),
        ) is True
        assert rc_execution_impl._should_use_stage13_deterministic_baseline_replay(
            candidate_files={
                "main.py": "print('main')\n",
                "config.py": "class Config: pass\n",
                "methods.py": "class Method: pass\n",
            },
            method_diagnosis_payload={"baseline_coverage_gap": True},
            interrupted_resume_project_dir=None,
        ) is False

    def test_stage13_manual_redesign_replays_recovered_best_code_without_llm(
        self,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        assert rc_execution_impl._should_use_stage13_deterministic_baseline_replay(
            candidate_files={
                "main.py": "print('main')\n",
                "config.py": "class Config: pass\n",
                "methods.py": "class Method: pass\n",
            },
            method_diagnosis_payload={"baseline_coverage_gap": False},
            interrupted_resume_project_dir=None,
            manual_redesign_active=True,
        ) is True

    def test_stage13_latest_experiment_version_is_resume_source(
        self,
        tmp_path: Path,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        stage_dir = tmp_path / "stage-13"
        (stage_dir / "experiment_v1").mkdir(parents=True)
        (stage_dir / "experiment_v2").mkdir(parents=True)
        (stage_dir / "experiment_v1" / "main.py").write_text("v1\n", encoding="utf-8")
        (stage_dir / "experiment_v2" / "main.py").write_text("v2\n", encoding="utf-8")

        assert (
            rc_execution_impl._latest_stage13_experiment_version_dir(stage_dir)
            == stage_dir / "experiment_v2"
        )

    def test_stage13_trusted_deterministic_replay_skips_wrapper_security_scan(
        self,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        validation = rc_execution_impl._validate_stage13_candidate_main(
            "import subprocess\nsubprocess.Popen(['echo', 'ok'])\n",
            trusted_deterministic_replay=True,
        )

        assert validation.ok is True

    def test_stage13_parallel_worker_partial_checkpoint_resumes_from_root_project(
        self,
        tmp_path: Path,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        stage_dir = tmp_path / "stage-13"
        worker_dir = stage_dir / "refine_sandbox_v1" / "_docker_project_1" / "_parallel_group2_dora"
        worker_dir.mkdir(parents=True)
        root_dir = worker_dir.parent
        (root_dir / "main.py").write_text("print('root')\n", encoding="utf-8")
        (worker_dir / "main.py").write_text("print('worker')\n", encoding="utf-8")
        (worker_dir / "partial_results.json").write_text(
            json.dumps(
                {
                    "status": "partial",
                    "results": [
                        {
                            "condition_name": "dora",
                            "seed": 1,
                            "primary_metric": 0.42,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        assert rc_execution_impl._latest_stage13_partial_project_dir(stage_dir) == root_dir
        assert rc_execution_impl._load_stage13_condition_seed_cache(stage_dir) == {
            "dora": {1: 0.42}
        }

    def test_stage13_parallel_wrapper_persists_partial_payload_before_failure(
        self,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        wrapped = rc_execution_impl._ensure_stage13_main_parallel_wrapper(
            "import os\n"
            "import json\n"
            "import math\n"
            "from pathlib import Path\n"
            "ACTIVE_CONDITIONS = ['a', 'b']\n"
            "def main() -> None:\n"
            "    pass\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        )

        assert "allow_partial: bool = False" in wrapped
        assert "worker_failures" in wrapped
        assert "_merge_parallel_worker_payloads(selected_groups, assigned_gpu_ids, allow_partial=True)" in wrapped

    def test_stage13_detects_context_overflow_instead_of_treating_it_as_code(
        self,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        assert rc_execution_impl._stage13_llm_response_is_context_overflow(
            "Context overflow: prompt too large for the model. Try /reset."
        )

    def test_stage13_stage15_refine_handoff_invalidates_completed_cache(
        self,
        tmp_path: Path,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        run_dir = tmp_path / "run"
        stage_dir = run_dir / "stage-13"
        stage15_dir = run_dir / "stage-15"
        results_dir = stage_dir / "refine_sandbox_v1" / "_docker_project_1"
        results_dir.mkdir(parents=True)
        stage15_dir.mkdir(parents=True)
        (stage15_dir / "decision_structured.json").write_text(
            json.dumps({"decision": "refine"}),
            encoding="utf-8",
        )
        (stage15_dir / "phase2_handoff.md").write_text(
            (
                "**REFINE**\n\n"
                "### 最关键的 3 个补实验\n"
                "1. 公平同版本核心重跑: `lora_fixed`, `qlora_fixed`, "
                "`cheap_proxy_controller`, `probe_control`, "
                "`exact_svd_oracle_controller`.\n"
                "2. QB-init × controller 二因素消融: QB init + cheap proxy.\n"
                "3. 严格 H1 matched-budget 对照.\n"
            ),
            encoding="utf-8",
        )
        (results_dir / "results.json").write_text(
            json.dumps(
                {
                    "metrics": {
                        "lora_fixed_seed_0": 0.1,
                        "lora_fixed_seed_1": 0.1,
                        "lora_fixed_seed_2": 0.1,
                    }
                }
            ),
            encoding="utf-8",
        )

        payload = rc_execution_impl._ensure_stage13_refine_handoff_manual_redesign(
            run_dir=run_dir,
            stage_dir=stage_dir,
        )

        assert payload is not None
        assert payload["source_stage"] == 15
        assert payload["cache_policy"] == "invalidate_existing_stage13_cache_for_refine_handoff"
        assert "lora_fixed" in payload["active_conditions"]
        assert "falcon_qb_init_plus_cheap_proxy" in payload["active_conditions"]
        assert (stage_dir / "manual_redesign.json").is_file()
        assert rc_execution_impl._load_stage13_condition_seed_cache(stage_dir) == {}
        assert (results_dir / "results.json").is_file()

    def test_stage13_manual_redesign_active_conditions_reads_json_payload(
        self,
        tmp_path: Path,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        stage_dir = tmp_path / "stage-13"
        stage_dir.mkdir(parents=True)
        (stage_dir / "manual_redesign.json").write_text(
            json.dumps({"active_conditions": ["probe_control", "cheap_proxy_controller"]}),
            encoding="utf-8",
        )

        assert rc_execution_impl._stage13_manual_redesign_active_conditions(stage_dir) == [
            "probe_control",
            "cheap_proxy_controller",
        ]

    def test_stage13_manual_redesign_complete_results_survive_later_partial_checkpoint(
        self,
        tmp_path: Path,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        stage_dir = tmp_path / "stage-13"
        stage_dir.mkdir(parents=True)
        manual = stage_dir / "manual_redesign.json"
        manual.write_text(
            json.dumps({"active_conditions": ["lora_fixed", "falcon_qb_activation_rank"]}),
            encoding="utf-8",
        )
        complete_dir = stage_dir / "refine_sandbox_v1_resume_complete" / "_docker_project_1"
        complete_dir.mkdir(parents=True)
        (complete_dir / "results.json").write_text(
            json.dumps(
                {
                    "status": "completed",
                    "results": [
                        {"condition_name": "lora_fixed", "seed": 0, "primary_metric": 0.24},
                        {"condition_name": "lora_fixed", "seed": 1, "primary_metric": 0.25},
                        {"condition_name": "lora_fixed", "seed": 2, "primary_metric": 0.26},
                        {
                            "condition_name": "falcon_qb_activation_rank",
                            "seed": 0,
                            "primary_metric": 0.20,
                        },
                        {
                            "condition_name": "falcon_qb_activation_rank",
                            "seed": 1,
                            "primary_metric": 0.19,
                        },
                        {
                            "condition_name": "falcon_qb_activation_rank",
                            "seed": 2,
                            "primary_metric": 0.18,
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        later_partial_dir = (
            stage_dir / "refine_sandbox_v1_resume_later_partial" / "_docker_project_1"
        )
        later_partial_dir.mkdir(parents=True)
        (later_partial_dir / "partial_results.json").write_text(
            json.dumps(
                {
                    "status": "partial",
                    "results": [
                        {"condition_name": "lora_fixed", "seed": 0, "primary_metric": 0.24}
                    ],
                }
            ),
            encoding="utf-8",
        )
        os.utime(manual, (100.0, 100.0))
        os.utime(complete_dir / "results.json", (200.0, 200.0))
        os.utime(later_partial_dir / "partial_results.json", (300.0, 300.0))

        cache = rc_execution_impl._load_stage13_condition_seed_cache(stage_dir)

        assert sorted(cache) == ["falcon_qb_activation_rank", "lora_fixed"]
        assert sorted(cache["lora_fixed"]) == [0, 1, 2]
        assert sorted(cache["falcon_qb_activation_rank"]) == [0, 1, 2]

    def test_stage13_manual_redesign_keeps_newer_partial_resume_cache(
        self,
        tmp_path: Path,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        stage_dir = tmp_path / "stage-13"
        worker_dir = stage_dir / "refine_sandbox_v2" / "_docker_project_2"
        worker_dir.mkdir(parents=True)
        manual_path = stage_dir / "manual_redesign.json"
        manual_path.write_text(
            json.dumps({"active_conditions": ["probe_control"]}),
            encoding="utf-8",
        )
        partial_path = worker_dir / "partial_results.json"
        partial_path.write_text(
            json.dumps(
                {
                    "status": "partial",
                    "results": [
                        {
                            "condition_name": "probe_control",
                            "seed": 1,
                            "primary_metric": 0.42,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        newer = manual_path.stat().st_mtime + 5.0
        os.utime(partial_path, (newer, newer))

        assert rc_execution_impl._load_stage13_condition_seed_cache(stage_dir) == {
            "probe_control": {1: 0.42}
        }


    def test_build_stage13_incremental_plan_freezes_unaffected_baselines(
        self,
        tmp_path: Path,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        stage_dir = tmp_path / "stage-13"
        stage_dir.mkdir(parents=True)
        results_dir = stage_dir / "refine_sandbox_v1" / "_docker_project_1"
        results_dir.mkdir(parents=True)
        (results_dir / "results.json").write_text(
            json.dumps(
                {
                    "metrics": {
                        "full_finetuning_seed_0": 0.71,
                        "full_finetuning_seed_1": 0.72,
                        "full_finetuning_seed_2": 0.73,
                        "qlora_fixed_seed_0": 0.61,
                        "qlora_fixed_seed_1": 0.62,
                        "qlora_fixed_seed_2": 0.63,
                    }
                }
            ),
            encoding="utf-8",
        )
        config_text = (
            'register("full_finetuning", "FullFineTuningCondition", "baseline", False, False, [])\n'
            'register("qlora_fixed", "QLoRACondition", "baseline", True, False, [])\n'
            'register("probe_control", "ProbeControlCondition", "proposed", False, True, [])\n'
            'self.screening_seeds: list[int] = [0, 1, 2]\n'
            'self.active_condition_names: list[str] = ["full_finetuning", "qlora_fixed", "probe_control"]\n'
        )
        best_methods = (
            "class FullFineTuningCondition:\n    pass\n\n"
            "class QLoRACondition:\n    pass\n\n"
            "class ProbeControlCondition:\n    def maybe_update_rank(self):\n        return 1\n"
        )
        candidate_methods = (
            "class FullFineTuningCondition:\n    pass\n\n"
            "class QLoRACondition:\n    pass\n\n"
            "class ProbeControlCondition:\n    def maybe_update_rank(self):\n        return 2\n"
        )
        plan = rc_execution_impl._build_stage13_incremental_plan(
            stage_dir=stage_dir,
            best_files={"config.py": config_text, "methods.py": best_methods, "main.py": "print('ok')\n"},
            candidate_files={"config.py": config_text, "methods.py": candidate_methods, "main.py": "print('ok')\n"},
            condition_coverage_hint="",
        )
        assert plan["active"] is True
        assert plan["reason"] == "condition_scoped_refine"
        assert plan["active_conditions"] == ["probe_control"]
        assert sorted(plan["frozen_conditions"]) == ["full_finetuning", "qlora_fixed"]
        assert sorted(plan["resume_registry"].keys()) == ["full_finetuning", "qlora_fixed"]

    def test_build_stage13_incremental_plan_freezes_completed_baselines_on_shared_change(
        self,
        tmp_path: Path,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        stage_dir = tmp_path / "stage-13"
        stage_dir.mkdir(parents=True)
        results_dir = stage_dir / "refine_sandbox_v1" / "_docker_project_1"
        results_dir.mkdir(parents=True)
        (results_dir / "results.json").write_text(
            json.dumps(
                {
                    "metrics": {
                        "full_finetuning_seed_0": 0.71,
                        "full_finetuning_seed_1": 0.72,
                        "full_finetuning_seed_2": 0.73,
                        "qlora_fixed_seed_0": 0.61,
                        "qlora_fixed_seed_1": 0.62,
                        "qlora_fixed_seed_2": 0.63,
                    }
                }
            ),
            encoding="utf-8",
        )
        config_text = (
            'register("full_finetuning", "FullFineTuningCondition", "baseline", False, False, [])\n'
            'register("qlora_fixed", "QLoRACondition", "baseline", True, False, [])\n'
            'register("probe_control", "ProbeControlCondition", "proposed", False, True, [])\n'
            'register("cheap_proxy_controller", "CheapProxyControlCondition", "ablation", False, False, [])\n'
            'self.screening_seeds: list[int] = [0, 1, 2]\n'
            'self.active_condition_names: list[str] = ["full_finetuning", "qlora_fixed", "probe_control", "cheap_proxy_controller"]\n'
        )
        best_files = {
            "config.py": config_text,
            "main.py": "def main():\n    return 'old'\n",
            "methods.py": "class ProbeControlCondition:\n    pass\n",
        }
        candidate_files = {
            "config.py": config_text,
            "main.py": "def main():\n    return 'new'\n",
            "methods.py": "class ProbeControlCondition:\n    pass\n",
        }
        plan = rc_execution_impl._build_stage13_incremental_plan(
            stage_dir=stage_dir,
            best_files=best_files,
            candidate_files=candidate_files,
            condition_coverage_hint="",
        )
        assert plan["active"] is True
        assert plan["reason"] == "shared_execution_change"
        assert plan["active_conditions"] == ["probe_control", "cheap_proxy_controller"]
        assert sorted(plan["frozen_conditions"]) == ["full_finetuning", "qlora_fixed"]
        assert sorted(plan["resume_registry"].keys()) == ["full_finetuning", "qlora_fixed"]

    def test_build_stage13_method_diagnosis_requires_advantage_redesign(
        self,
        tmp_path: Path,
        run_dir: Path,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        stage_dir = run_dir / "stage-13"
        stage_dir.mkdir(parents=True, exist_ok=True)
        exp_dir = stage_dir / "experiment"
        exp_dir.mkdir(parents=True, exist_ok=True)
        config_text = (
            'register("full_finetuning", "FullFineTuningCondition", "baseline", False, False, [])\n'
            'register("qlora_fixed", "QLoRACondition", "baseline", True, False, [])\n'
            'register("probe_control", "ProbeControlCondition", "proposed", False, True, [])\n'
            "self.max_steps_screening: int = 60\n"
            "self.probe_interval: int = 20\n"
            "self.screening_seeds: list[int] = [0, 1, 2]\n"
        )
        (exp_dir / "config.py").write_text(config_text, encoding="utf-8")
        (exp_dir / "methods.py").write_text(
            (
                "def resize_rank_basic():\n    return 1\n\n"
                "def resize_rank_state_consistent():\n    return 1\n"
            ),
            encoding="utf-8",
        )
        sandbox_results = stage_dir / "refine_sandbox_v1" / "_docker_project_1"
        sandbox_results.mkdir(parents=True, exist_ok=True)
        (sandbox_results / "results.json").write_text(
            json.dumps(
                {
                    "metrics": {
                        "qlora_fixed_seed_0": 0.61,
                        "qlora_fixed_seed_1": 0.62,
                        "qlora_fixed_seed_2": 0.63,
                        "probe_control_seed_0": 0.72,
                        "probe_control_seed_1": 0.73,
                        "probe_control_seed_2": 0.74,
                    }
                }
            ),
            encoding="utf-8",
        )
        _write_prior_artifact(
            run_dir,
            8,
            "hypotheses.md",
            (
                "Hypothesis: the RSVD controller should reduce peak VRAM and "
                "wall-clock overhead while preserving quality and rank efficiency."
            ),
        )
        _write_prior_artifact(
            run_dir,
            9,
            "experiment_adequacy_report.json",
            json.dumps({"verdict": "ready_for_gate", "score": 11}),
        )

        summary, payload = rc_execution_impl._build_stage13_method_diagnosis(
            stage_dir=stage_dir,
            run_dir=run_dir,
            metric_key="val_loss",
            metric_direction="minimize",
            condition_coverage_hint="",
            config_text=config_text,
        )

        assert payload["method_redesign_required"] is True
        assert payload["strongest_baseline"]["condition"] == "qlora_fixed"
        assert payload["strongest_non_baseline"]["condition"] == "probe_control"
        assert "too short for adaptive control" in summary

    def test_build_stage13_method_diagnosis_flags_missing_baseline_coverage(
        self,
        run_dir: Path,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        stage_dir = run_dir / "stage-13"
        stage_dir.mkdir(parents=True, exist_ok=True)
        exp_dir = stage_dir / "experiment"
        exp_dir.mkdir(parents=True, exist_ok=True)
        config_text = (
            'register("lora_fixed", "LoRACondition", "baseline", False, False, [])\n'
            'register("qlora_fixed", "QLoRACondition", "baseline", False, False, [])\n'
            'register("probe_control", "ProbeControlCondition", "proposed", False, False, [])\n'
            "self.max_steps_screening: int = 160\n"
            "self.probe_interval: int = 20\n"
            "self.screening_seeds: list[int] = [0, 1, 2]\n"
            'self.active_condition_names: list[str] = ["lora_fixed", "qlora_fixed", "probe_control"]\n'
        )
        (exp_dir / "config.py").write_text(config_text, encoding="utf-8")
        _write_prior_artifact(
            run_dir,
            9,
            "benchmark_plan.json",
            json.dumps(
                {
                    "selected_baselines": [
                        {"condition": "lora_fixed"},
                        {"condition": "lora_fixed_matched_rank"},
                        {"condition": "dora"},
                        {"condition": "pissa_init"},
                        {"condition": "milora_init"},
                        {"condition": "lora_ga_init"},
                        {"condition": "sensitivity_lora"},
                    ],
                    "stage13_alignment": {
                        "active_conditions": [
                            "lora_fixed",
                            "lora_fixed_matched_rank",
                            "dora",
                            "pissa_init",
                            "milora_init",
                            "lora_ga_init",
                            "sensitivity_lora",
                        ]
                    },
                }
            ),
        )
        _write_prior_artifact(
            run_dir,
            15,
            "claims_from_results.md",
            (
                "## Missing Evidence\n"
                "- At minimum: LoRA, QLoRA, AdaLoRA, DoRA, LoRA-FA under matched settings.\n"
            ),
        )
        _write_prior_artifact(
            run_dir,
            6,
            "related_work_map.md",
            "GRIT\nLoRA-Squeeze\nLoRA-drop\nID-LoRA\nSECURA\nPLoP\n",
        )

        summary, payload = rc_execution_impl._build_stage13_method_diagnosis(
            stage_dir=stage_dir,
            run_dir=run_dir,
            metric_key="val_loss",
            metric_direction="minimize",
            condition_coverage_hint="",
            config_text=config_text,
        )

        assert payload["baseline_coverage_gap"] is True
        assert "lora_fixed_matched_rank" in payload["missing_active_conditions"]
        assert "dora" in payload["missing_active_conditions"]
        assert "adalora_like_budget" in payload["missing_registered_conditions"]
        assert "lora_fa" in payload["missing_registered_conditions"]
        assert "GRIT" in payload["related_work_comparators"]
        assert "LoRA-Squeeze" in payload["related_work_comparators"]
        assert "same-round baseline coverage is incomplete" in summary
        assert "related-work comparators require explicit coverage or exclusion" in summary

    def test_stage13_completion_gate_accepts_measured_max_iteration_stop(
        self,
    ) -> None:
        from researchclaw.pipeline.stage_impls import _execution as rc_execution_impl

        gate = rc_execution_impl._build_stage13_completion_gate(
            {
                "best_metric": 0.62,
                "converged": False,
                "stop_reason": "max_iterations_reached",
                "iterations": [
                    {
                        "metric": 0.62,
                        "incremental_plan": {
                            "active_conditions": ["qlora_fixed", "probe_control"],
                        },
                        "sandbox": {
                            "returncode": 0,
                            "metrics": {
                                "qlora_fixed_seed_0": 0.61,
                                "probe_control_seed_0": 0.72,
                            },
                        },
                    }
                ],
            }
        )

        assert gate["ok"] is True
        assert "non_converged_stop:max_iterations_reached" not in gate["reasons"]

    def test_refine_skips_rerun_when_redesign_required_but_change_is_not_substantive(
        self,
        tmp_path: Path,
        run_dir: Path,
        adapters: AdapterBundle,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import sys

        stage_dir = run_dir / "stage-13"
        exp_dir = stage_dir / "experiment"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "main.py").write_text(
            "def main():\n    print('val_loss: 0.9')\n\nif __name__ == '__main__':\n    main()\n",
            encoding="utf-8",
        )
        (exp_dir / "config.py").write_text(
            (
                'register("full_finetuning", "FullFineTuningCondition", "baseline", False, False, [])\n'
                'register("qlora_fixed", "QLoRACondition", "baseline", True, False, [])\n'
                'register("probe_control", "ProbeControlCondition", "proposed", False, True, [])\n'
                "self.max_steps_screening: int = 60\n"
                "self.probe_interval: int = 20\n"
                "self.screening_seeds: list[int] = [0, 1, 2]\n"
                'self.active_condition_names: list[str] = ["full_finetuning", "qlora_fixed", "probe_control"]\n'
            ),
            encoding="utf-8",
        )
        (exp_dir / "methods.py").write_text(
            (
                "class ProbeControlCondition:\n"
                "    def run(self):\n"
                "        return 'old'\n\n"
                "def resize_rank_basic():\n"
                "    return 1\n\n"
                "def resize_rank_state_consistent():\n"
                "    return 1\n"
            ),
            encoding="utf-8",
        )
        sandbox_results = stage_dir / "refine_sandbox_v1" / "_docker_project_1"
        sandbox_results.mkdir(parents=True, exist_ok=True)
        (sandbox_results / "results.json").write_text(
            json.dumps(
                {
                    "metrics": {
                        "full_finetuning_seed_0": 0.71,
                        "full_finetuning_seed_1": 0.72,
                        "full_finetuning_seed_2": 0.73,
                        "qlora_fixed_seed_0": 0.61,
                        "qlora_fixed_seed_1": 0.62,
                        "qlora_fixed_seed_2": 0.63,
                        "probe_control_seed_0": 0.72,
                        "probe_control_seed_1": 0.73,
                        "probe_control_seed_2": 0.74,
                    }
                }
            ),
            encoding="utf-8",
        )
        _write_prior_artifact(
            run_dir,
            8,
            "hypotheses.md",
            (
                "Hypothesis: RSVD control should reduce peak VRAM and wall-clock "
                "time while preserving quality."
            ),
        )
        _write_prior_artifact(
            run_dir,
            9,
            "experiment_adequacy_report.json",
            json.dumps({"verdict": "ready_for_gate", "score": 11}),
        )

        sandbox_data = {
            "project": {"name": "rc-test", "mode": "docs-first"},
            "research": {
                "topic": "test-driven science",
                "domains": ["ml", "systems"],
                "daily_paper_count": 2,
                "quality_threshold": 8.2,
            },
            "runtime": {"timezone": "UTC"},
            "notifications": {
                "channel": "local",
                "on_stage_start": True,
                "on_stage_fail": False,
                "on_gate_required": True,
            },
            "knowledge_base": {"backend": "markdown", "root": str(tmp_path / "kb")},
            "openclaw_bridge": {"use_memory": True, "use_message": True},
            "llm": {
                "provider": "openai-compatible",
                "base_url": "http://localhost:1234/v1",
                "api_key_env": "RC_TEST_KEY",
                "api_key": "inline-test-key",
                "primary_model": "fake-model",
                "fallback_models": [],
            },
            "security": {"hitl_required_stages": [5, 9, 20]},
            "experiment": {
                "mode": "sandbox",
                "time_budget_sec": 30,
                "max_iterations": 1,
                "metric_key": "val_loss",
                "metric_direction": "minimize",
                "sandbox": {
                    "python_path": sys.executable,
                    "gpu_required": False,
                    "max_memory_mb": 1024,
                },
            },
        }
        sandbox_config = RCConfig.from_dict(
            sandbox_data,
            project_root=tmp_path,
            check_paths=False,
        )
        llm = FakeLLMClient(
            "```json\n"
            '{"method_change_summary": {"redesign_goal": "runtime cleanup", '
            '"changed_conditions": [], "advantage_targets": ["quality"], '
            '"substantive_method_change": false, "expected_effect": "none"}}\n'
            "```\n"
            "```filename:main.py\n"
            "def main():\n    print('val_loss: 0.8')\n\nif __name__ == '__main__':\n    main()\n"
            "```"
        )

        def _unexpected_sandbox(*args: object, **kwargs: object):
            raise AssertionError("sandbox should not run when method gate skips the iteration")

        monkeypatch.setattr(
            "researchclaw.experiment.factory.create_sandbox",
            _unexpected_sandbox,
        )

        rc_executor._execute_iterative_refine(
            stage_dir,
            run_dir,
            sandbox_config,
            adapters,
            llm=llm,
        )

        payload = json.loads(
            (stage_dir / "refinement_log.json").read_text(encoding="utf-8")
        )
        assert payload["stop_reason"] == "cached_results_complete"
        assert payload["iterations"][0]["cached_completion"] is True
        assert payload["iterations"][0]["validation_summary"] == "cached_complete"
        assert not llm.calls
        assert (stage_dir / "method_diagnosis.json").exists()


class TestExportPublishCodePackage:
    def test_export_packages_experiment_final(
        self,
        tmp_path: Path,
        run_dir: Path,
        rc_config: RCConfig,
        adapters: AdapterBundle,
    ) -> None:
        _write_prior_artifact(
            run_dir, 19, "paper_revised.md", "# Test Paper\n\nSome content..."
        )
        _write_prior_artifact(
            run_dir,
            13,
            "experiment_final.py",
            'import numpy\nprint("val_loss: 0.1")\n',
        )
        stage_dir = tmp_path / "run" / "stage-22"
        stage_dir.mkdir(parents=True, exist_ok=True)

        rc_executor._execute_export_publish(
            stage_dir, run_dir, rc_config, adapters, llm=None
        )

        assert (stage_dir / "code" / "experiment.py").exists()
        assert (stage_dir / "code" / "README.md").exists()
        req_text = (stage_dir / "code" / "requirements.txt").read_text(encoding="utf-8")
        assert "numpy" in req_text

    def test_export_falls_back_to_experiment_py(
        self,
        tmp_path: Path,
        run_dir: Path,
        rc_config: RCConfig,
        adapters: AdapterBundle,
    ) -> None:
        _write_prior_artifact(
            run_dir, 19, "paper_revised.md", "# Test Paper\n\nSome content..."
        )
        _write_prior_artifact(
            run_dir,
            10,
            "experiment.py",
            'import numpy\nprint("val_loss: 0.1")\n',
        )
        stage_dir = tmp_path / "run" / "stage-22"
        stage_dir.mkdir(parents=True, exist_ok=True)

        rc_executor._execute_export_publish(
            stage_dir, run_dir, rc_config, adapters, llm=None
        )

        code_text = (stage_dir / "code" / "experiment.py").read_text(encoding="utf-8")
        assert "val_loss: 0.1" in code_text

    def test_export_no_experiment_skips_code_dir(
        self,
        tmp_path: Path,
        run_dir: Path,
        rc_config: RCConfig,
        adapters: AdapterBundle,
    ) -> None:
        _write_prior_artifact(
            run_dir, 19, "paper_revised.md", "# Test Paper\n\nSome content..."
        )
        stage_dir = tmp_path / "run" / "stage-22"
        stage_dir.mkdir(parents=True, exist_ok=True)

        result = rc_executor._execute_export_publish(
            stage_dir,
            run_dir,
            rc_config,
            adapters,
            llm=None,
        )

        assert not (stage_dir / "code").exists()
        assert "code/" not in result.artifacts

    def test_export_detects_multiple_dependencies(
        self,
        tmp_path: Path,
        run_dir: Path,
        rc_config: RCConfig,
        adapters: AdapterBundle,
    ) -> None:
        _write_prior_artifact(
            run_dir, 19, "paper_revised.md", "# Test Paper\n\nSome content..."
        )
        _write_prior_artifact(
            run_dir,
            13,
            "experiment_final.py",
            (
                "import numpy\n"
                "import torch\n"
                "from sklearn.metrics import accuracy_score\n"
                "print(accuracy_score([1], [1]))\n"
            ),
        )
        stage_dir = tmp_path / "run" / "stage-22"
        stage_dir.mkdir(parents=True, exist_ok=True)

        rc_executor._execute_export_publish(
            stage_dir, run_dir, rc_config, adapters, llm=None
        )

        requirements = (stage_dir / "code" / "requirements.txt").read_text(
            encoding="utf-8"
        )
        assert "numpy" in requirements
        assert "torch" in requirements
        assert "scikit-learn" in requirements

    def test_export_code_readme_contains_title(
        self,
        tmp_path: Path,
        run_dir: Path,
        rc_config: RCConfig,
        adapters: AdapterBundle,
    ) -> None:
        _write_prior_artifact(
            run_dir, 19, "paper_revised.md", "# My Great Paper\n\nSome content..."
        )
        _write_prior_artifact(
            run_dir,
            13,
            "experiment_final.py",
            'print("val_loss: 0.1")\n',
        )
        stage_dir = tmp_path / "run" / "stage-22"
        stage_dir.mkdir(parents=True, exist_ok=True)

        rc_executor._execute_export_publish(
            stage_dir, run_dir, rc_config, adapters, llm=None
        )

        readme = (stage_dir / "code" / "README.md").read_text(encoding="utf-8")
        assert "My Great Paper" in readme

    def test_export_publish_context_overflow_uses_revised_paper(
        self,
        tmp_path: Path,
        run_dir: Path,
        rc_config: RCConfig,
        adapters: AdapterBundle,
    ) -> None:
        revised = "# My Great Paper\n\nSome content..."
        _write_prior_artifact(run_dir, 19, "paper_revised.md", revised)
        stage_dir = tmp_path / "run" / "stage-22"
        stage_dir.mkdir(parents=True, exist_ok=True)

        class ExportOverflowLLM:
            def chat(self, messages, **kwargs):
                _ = messages, kwargs
                raise RuntimeError("Context-overflow message returned instead of Python code.")

        result = rc_executor._execute_export_publish(
            stage_dir, run_dir, rc_config, adapters, llm=ExportOverflowLLM()
        )

        assert result.status == StageStatus.DONE
        final_text = (stage_dir / "paper_final.md").read_text(encoding="utf-8")
        assert "My Great Paper" in final_text
        assert "Context-overflow" not in final_text


def test_contracts_stage13_includes_experiment_final() -> None:
    assert "experiment_final/" in CONTRACTS[Stage.ITERATIVE_REFINE].output_files


def test_contracts_stage22_includes_code_dir() -> None:
    assert "code/" in CONTRACTS[Stage.EXPORT_PUBLISH].output_files


# ── P1-1: Topic keyword extraction tests ──


class TestExtractTopicKeywords:
    def test_basic_extraction(self) -> None:
        keywords = rc_executor._extract_topic_keywords(
            "Agent-based Reinforcement Learning for Automated Scientific Discovery"
        )
        assert "agent-based" in keywords
        assert "reinforcement" in keywords
        assert "learning" in keywords
        assert "automated" in keywords
        assert "scientific" in keywords
        assert "discovery" in keywords
        # Stop words excluded
        # Stop words excluded
        assert "for" not in keywords

    def test_includes_domain_keywords(self) -> None:
        keywords = rc_executor._extract_topic_keywords(
            "Neural network pruning", domains=("ml", "optimization")
        )
        assert "neural" in keywords
        assert "network" in keywords
        assert "pruning" in keywords
        assert "ml" in keywords
        assert "optimization" in keywords

    def test_deduplication(self) -> None:
        keywords = rc_executor._extract_topic_keywords(
            "Learning to learn meta-learning", domains=("learning",)
        )
        assert keywords.count("learning") == 1

    def test_empty_topic(self) -> None:
        keywords = rc_executor._extract_topic_keywords("")
        assert keywords == []


# ── P1-2: Topic constraint block test ──


class TestTopicConstraintBlock:
    def test_contains_topic(self) -> None:
        block = rc_executor._topic_constraint_block("Transformer attention for time series")
        assert "Transformer attention for time series" in block

    def test_contains_prohibition(self) -> None:
        block = rc_executor._topic_constraint_block("anything")
        assert "PROHIBITED" in block
        assert "environment" in block.lower()
        assert "infrastructure" in block.lower()

    def test_hard_constraint_markers(self) -> None:
        block = rc_executor._topic_constraint_block("test")
        assert "HARD TOPIC CONSTRAINT" in block
        assert "END CONSTRAINT" in block


# ── Multi-perspective debate tests ──


class TestParseDecision:
    def test_unrecognized_text_is_invalid(self) -> None:
        assert rc_executor._parse_decision("Some random text") is None

    def test_proceed_explicit(self) -> None:
        text = "## Decision\nPROCEED\n## Justification\nGood results."
        assert rc_executor._parse_decision(text) == "proceed"

    def test_pivot_detected(self) -> None:
        text = "## Decision\nPIVOT\n## Justification\nHypotheses flawed."
        assert rc_executor._parse_decision(text) == "pivot"

    def test_refine_detected(self) -> None:
        text = "## Decision\nREFINE\n## Justification\nNeed more tuning."
        assert rc_executor._parse_decision(text) == "refine"

    def test_pivot_case_insensitive(self) -> None:
        text = "## Decision\npivot\n## Justification\nBad approach."
        assert rc_executor._parse_decision(text) == "pivot"

    def test_pivot_takes_priority_over_proceed(self) -> None:
        text = "## Decision\nPIVOT\nWe should not PROCEED."
        assert rc_executor._parse_decision(text) == "pivot"

    def test_decision_in_body_not_heading(self) -> None:
        text = "The results suggest we should PIVOT to a new approach."
        assert rc_executor._parse_decision(text) == "pivot"

    def test_usage_limit_text_is_invalid(self) -> None:
        text = "⚠️ You have hit your ChatGPT usage limit (plus plan). Try again in ~142 min."
        assert rc_executor._parse_decision(text) is None


class TestChatWithPrompt:
    def test_rejects_usage_limit_payload(self) -> None:
        fake_llm = FakeLLMClient(
            "⚠️ You have hit your ChatGPT usage limit (plus plan). Try again in ~142 min."
        )

        with pytest.raises(RuntimeError, match="quota"):
            _chat_with_prompt(fake_llm, "system", "user")


class TestResearchDecisionStructured:
    def test_decision_produces_structured_json(
        self, tmp_path: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        stage_dir = run_dir / "stage-15"
        stage_dir.mkdir(parents=True)
        _write_prior_artifact(run_dir, 14, "analysis.md", "# Analysis\nResults ok.")
        fake_llm = FakeLLMClient("## Decision\nPROCEED\n## Justification\nGood.")
        result = rc_executor._execute_research_decision(
            stage_dir, run_dir, rc_config, adapters, llm=fake_llm
        )
        assert result.decision == "proceed"
        assert "decision_structured.json" in result.artifacts
        import json
        data = json.loads((stage_dir / "decision_structured.json").read_text())
        assert data["decision"] == "proceed"

    def test_pivot_decision_from_llm(
        self, tmp_path: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        stage_dir = run_dir / "stage-15"
        stage_dir.mkdir(parents=True)
        _write_prior_artifact(run_dir, 14, "analysis.md", "# Analysis\nBad results.")
        fake_llm = FakeLLMClient("## Decision\nPIVOT\n## Justification\nFlawed.")
        result = rc_executor._execute_research_decision(
            stage_dir, run_dir, rc_config, adapters, llm=fake_llm
        )
        assert result.decision == "pivot"

    def test_usage_limit_response_fails_stage(
        self, tmp_path: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        stage_dir = run_dir / "stage-15"
        stage_dir.mkdir(parents=True)
        _write_prior_artifact(run_dir, 14, "analysis.md", "# Analysis\nResults ok.")
        fake_llm = FakeLLMClient(
            "⚠️ You have hit your ChatGPT usage limit (plus plan). Try again in ~142 min."
        )

        result = rc_executor._execute_research_decision(
            stage_dir, run_dir, rc_config, adapters, llm=fake_llm
        )

        assert result.status == StageStatus.FAILED
        assert result.decision == "hold"
        assert "quota" in (result.error or "").lower()

    def test_no_llm_defaults_to_proceed(
        self, tmp_path: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        stage_dir = run_dir / "stage-15"
        stage_dir.mkdir(parents=True)
        result = rc_executor._execute_research_decision(
            stage_dir, run_dir, rc_config, adapters, llm=None
        )
        assert result.decision == "proceed"

    def test_decision_generates_claims_from_results_artifacts(
        self, tmp_path: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        stage_dir = run_dir / "stage-15"
        stage_dir.mkdir(parents=True)
        _write_prior_artifact(run_dir, 2, "problem_anchor.md", "# Problem Anchor\nAnchor")
        _write_prior_artifact(run_dir, 8, "hypotheses.md", "## Hypothesis\nMethod A should outperform baseline B.")
        _write_prior_artifact(run_dir, 9, "claims_evidence_matrix.md", "# Claims-Evidence Matrix\n## C1\n- Claim: Method A beats baseline B.")
        _write_prior_artifact(run_dir, 14, "analysis.md", "# Analysis\nMethod A improves accuracy over baseline B.")
        _write_prior_artifact(run_dir, 14, "experiment_summary.json", json.dumps({"metrics_summary": {"accuracy": {"mean": 0.8, "count": 5}}}))
        llm = SequenceLLMClient(
            [
                "# Claims From Results\n\n## Supported Claims\n- Method A beats baseline B.\n\n## Partially Supported Claims\n- None.\n\n## Unsupported or Rejected Claims\n- None.\n\n## Missing Evidence\n- More robustness tests.\n\n## Paper Positioning Guidance\n- Keep claims narrow.\n",
                "## Decision\nPROCEED\n## Justification\nSupported claims exist.\n## Evidence\nReal metrics.\n## Next Actions\nWrite the paper.\n",
            ]
        )
        result = rc_executor._execute_research_decision(
            stage_dir, run_dir, rc_config, adapters, llm=llm
        )
        assert result.decision == "proceed"
        assert "claims_from_results.md" in result.artifacts
        assert (stage_dir / "claims_from_results.md").exists()
        claims_payload = json.loads((stage_dir / "claims_from_results.json").read_text())
        assert "Method A beats baseline B." in claims_payload["supported_claims"]
        assert len(llm.calls) == 2

    def test_decision_prompts_prioritize_authoritative_experiment_snapshot(
        self, tmp_path: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        stage_dir = run_dir / "stage-15"
        stage_dir.mkdir(parents=True)
        _write_prior_artifact(
            run_dir,
            14,
            "analysis.md",
            "# Analysis\nStale prose says falcon_qb_activation_rank loses.",
        )
        _write_prior_artifact(
            run_dir,
            14,
            "experiment_summary.json",
            json.dumps(
                {
                    "condition_summaries": {
                        "falcon_qb_activation_rank": {
                            "metrics": {"primary_metric_mean": 0.189296}
                        },
                        "cheap_proxy_controller": {
                            "metrics": {"primary_metric_mean": 0.192978}
                        },
                    }
                }
            ),
        )
        llm = SequenceLLMClient(
            [
                "## Supported Claims\n- Falcon beats cheap proxy.\n\n"
                "## Partially Supported Claims\n- None.\n\n"
                "## Unsupported or Rejected Claims\n- None.\n\n"
                "## Missing Evidence\n- None.\n\n"
                "## Paper Positioning Guidance\n- Keep it narrow.\n",
                "## Decision\nPROCEED\n## Justification\nFresh summary wins.\n",
            ]
        )

        rc_executor._execute_research_decision(
            stage_dir, run_dir, rc_config, adapters, llm=llm
        )

        claims_prompt = llm.calls[0][0]["content"]
        decision_prompt = llm.calls[1][0]["content"]
        assert "Authoritative Structured Experiment Snapshot" in claims_prompt
        assert "falcon_qb_activation_rank: primary_metric_mean=0.189296" in claims_prompt
        assert "Authoritative Structured Experiment Snapshot" in decision_prompt
        assert "If prose analysis conflicts with this snapshot, trust this snapshot." in decision_prompt


class TestProblemAnchorAndClaimMatrix:
    def test_problem_decompose_writes_problem_anchor(
        self, tmp_path: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        stage_dir = run_dir / "stage-02"
        stage_dir.mkdir(parents=True)
        _write_prior_artifact(run_dir, 1, "goal.md", "# Goal\nFind a better algorithm.")

        result = rc_executor._execute_problem_decompose(
            stage_dir, run_dir, rc_config, adapters, llm=None
        )

        assert result.status == StageStatus.DONE
        assert "problem_anchor.md" in result.artifacts
        anchor_text = (stage_dir / "problem_anchor.md").read_text(encoding="utf-8")
        assert "Core Question" in anchor_text
        assert "Dominant Contribution" in anchor_text

    def test_experiment_design_writes_claims_evidence_matrix(
        self, tmp_path: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        stage_dir = run_dir / "stage-09"
        stage_dir.mkdir(parents=True)
        _write_prior_artifact(run_dir, 1, "goal.md", "# Goal\nBetter method.")
        _write_prior_artifact(run_dir, 2, "problem_anchor.md", "# Problem Anchor\nFocus on baseline weakness.")
        _write_prior_artifact(
            run_dir,
            8,
            "hypotheses.md",
            "## Hypothesis 1\nA structured latent update should improve accuracy over the baseline.\n",
        )
        llm = FakeLLMClient(
            "objectives:\n  - compare methods\n"
            "datasets:\n  - benchmark_a\n"
            "baselines:\n  - baseline_b\n"
            "proposed_methods:\n  - latent_update_net\n"
            "ablations:\n  - no_latent_update\n"
            "metrics:\n  - accuracy\n"
            "risks:\n  - overfitting\n"
            "compute_budget:\n  max_gpu: 1\n  max_hours: 2\n"
        )

        result = rc_executor._execute_experiment_design(
            stage_dir, run_dir, rc_config, adapters, llm=llm
        )

        assert result.status == StageStatus.DONE
        assert "claims_evidence_matrix.md" in result.artifacts
        matrix_text = (stage_dir / "claims_evidence_matrix.md").read_text(encoding="utf-8")
        assert "Claims-Evidence Matrix" in matrix_text
        assert "latent_update_net" in matrix_text
        matrix_payload = json.loads((stage_dir / "claims_evidence_matrix.json").read_text())
        assert matrix_payload["claims"][0]["proposed_methods"] == ["latent_update_net"]
        adequacy_report = json.loads((stage_dir / "experiment_adequacy_report.json").read_text())
        assert adequacy_report["verdict"] in {"ready_for_gate", "borderline_review_needed", "weak_design"}
        assert "experiment_adequacy_report.md" in result.artifacts
        assert result.control_hints["adequacy_verdict"] == adequacy_report["verdict"]


class TestAutoReviewLoopLite:
    def test_peer_review_writes_review_loop_artifacts(
        self, run_dir: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        _write_prior_artifact(run_dir, 17, "paper_draft.md", "# Draft\n\nA full paper draft.")
        _write_prior_artifact(run_dir, 15, "claims_from_results.md", "# Claims From Results\n- Narrow claim.")
        _write_prior_artifact(
            run_dir,
            17,
            "draft_quality.json",
            json.dumps({"overall_warnings": ["Results section is thin"]}),
        )
        stage_dir = run_dir / "stage-18"
        stage_dir.mkdir(parents=True, exist_ok=True)
        llm = FakeLLMClient(
            "## Scorecard\n"
            "- novelty: 7/10\n"
            "- technical_soundness: 6/10\n"
            "- empirical_adequacy: 5/10\n"
            "- writing_clarity: 7/10\n"
            "- claim_calibration: 6/10\n"
            "- overall_score: 6/10\n\n"
            "## Top Findings\n"
            "- Must fix unsupported comparison claim in abstract.\n\n"
            "## Reviewer A\n"
            "- Strengths: Clear setup.\n"
            "- Weaknesses: Missing baseline fairness discussion.\n"
            "- Actionable revisions: Expand baseline analysis.\n"
        )

        result = rc_executor._execute_peer_review(
            stage_dir, run_dir, rc_config, adapters, llm=llm
        )

        assert result.status == StageStatus.DONE
        assert "review_state.json" in result.artifacts
        assert (stage_dir / "auto_review.md").exists()
        assert (stage_dir / "findings.md").exists()
        assert (run_dir / "REVIEW_STATE.json").exists()
        assert (run_dir / "score_history.md").exists()
        assert (stage_dir / "paper_score.json").exists()
        state = json.loads((stage_dir / "review_state.json").read_text(encoding="utf-8"))
        assert state["overall_score"] == 6.0
        assert state["target_score"] == 8.0
        assert state["venue_target_score"] == 8.0
        assert "Acceptance bar" in state["venue_rubric"]
        assert state["review_outcome"] == "revise_again"
        assert state["open_findings"] >= 1

    def test_paper_revision_uses_review_loop_context_and_updates_state(
        self, run_dir: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        _write_prior_artifact(run_dir, 17, "paper_draft.md", "# Draft\n\nOriginal text.")
        _write_prior_artifact(run_dir, 18, "reviews.md", "# Reviews\n- Fix claim calibration.")
        _write_prior_artifact(run_dir, 18, "auto_review.md", "# Auto Review\n- Overall score: 6/10")
        _write_prior_artifact(run_dir, 18, "findings.md", "# Findings\n- [ ] Fix claim calibration.")
        _write_prior_artifact(
            run_dir,
            18,
            "review_state.json",
            json.dumps({"iteration": 1, "status": "reviewed_pending_revision", "overall_score": 6.0}),
        )
        stage_dir = run_dir / "stage-19"
        stage_dir.mkdir(parents=True, exist_ok=True)

        result = rc_executor._execute_paper_revision(
            stage_dir, run_dir, rc_config, adapters, llm=None
        )

        assert result.status == StageStatus.DONE
        assert (stage_dir / "revision_response.md").exists()
        updated_state = json.loads((stage_dir / "review_state.json").read_text(encoding="utf-8"))
        assert updated_state["status"] == "revised_pending_re_review"
        assert (run_dir / "REVIEW_STATE.json").exists()

    def test_paper_revision_context_overflow_retries_with_compact_prompt(
        self, run_dir: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        _write_prior_artifact(run_dir, 17, "paper_draft.md", "# Draft\n\n" + ("A" * 50000))
        _write_prior_artifact(run_dir, 18, "reviews.md", "# Reviews\n- Tighten results.")
        _write_prior_artifact(
            run_dir,
            18,
            "review_state.json",
            json.dumps({"iteration": 1, "status": "reviewed_pending_revision", "overall_score": 6.0}),
        )
        stage_dir = run_dir / "stage-19"
        stage_dir.mkdir(parents=True, exist_ok=True)

        class RevisionOverflowOnceLLM:
            def __init__(self):
                self.user_prompts: list[str] = []

            def chat(self, messages, **kwargs):
                _ = kwargs
                user = next(m["content"] for m in messages if m.get("role") == "user")
                self.user_prompts.append(user)
                if "... [paper draft compacted:" not in user:
                    raise RuntimeError("Context-overflow message returned instead of Python code.")
                from researchclaw.llm.client import LLMResponse
                return LLMResponse(content="# Revised\n\nTightened revision.", model="fake")

        llm = RevisionOverflowOnceLLM()

        result = rc_executor._execute_paper_revision(
            stage_dir, run_dir, rc_config, adapters, llm=llm
        )

        assert result.status == StageStatus.DONE
        assert any("... [paper draft compacted:" in p for p in llm.user_prompts)
        revised = (stage_dir / "paper_revised.md").read_text(encoding="utf-8")
        assert "Tightened revision" in revised
        assert "Context-overflow" not in revised

    def test_paper_revision_preserves_original_if_compact_overflows(
        self, run_dir: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        original = "# Draft\n\nOriginal text."
        _write_prior_artifact(run_dir, 17, "paper_draft.md", original)
        _write_prior_artifact(run_dir, 18, "reviews.md", "# Reviews\n- Tighten results.")
        _write_prior_artifact(
            run_dir,
            18,
            "review_state.json",
            json.dumps({"iteration": 1, "status": "reviewed_pending_revision", "overall_score": 6.0}),
        )
        stage_dir = run_dir / "stage-19"
        stage_dir.mkdir(parents=True, exist_ok=True)

        class AlwaysRevisionOverflowLLM:
            def chat(self, messages, **kwargs):
                _ = messages, kwargs
                raise RuntimeError("Context-overflow message returned instead of Python code.")

        result = rc_executor._execute_paper_revision(
            stage_dir, run_dir, rc_config, adapters, llm=AlwaysRevisionOverflowLLM()
        )

        assert result.status == StageStatus.DONE
        assert (stage_dir / "paper_revised.md").read_text(encoding="utf-8") == original
        assert (stage_dir / "revision_notes_internal.md").exists()

    def test_peer_review_prefers_latest_revised_paper(
        self, run_dir: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        _write_prior_artifact(run_dir, 17, "paper_draft.md", "# Draft\n\nOld draft content.")
        _write_prior_artifact(run_dir, 19, "paper_revised.md", "# Revised\n\nNew revised content.")
        stage_dir = run_dir / "stage-18"
        stage_dir.mkdir(parents=True, exist_ok=True)
        llm = FakeLLMClient(
            "## Scorecard\n"
            "- novelty: 7/10\n"
            "- technical_soundness: 7/10\n"
            "- empirical_adequacy: 7/10\n"
            "- writing_clarity: 7/10\n"
            "- claim_calibration: 7/10\n"
            "- overall_score: 7/10\n"
        )

        result = rc_executor._execute_peer_review(
            stage_dir, run_dir, rc_config, adapters, llm=llm
        )

        assert result.status == StageStatus.DONE
        prompt = "\n".join(msg.get("content", "") for msg in llm.calls[0])
        assert "New revised content." in prompt
        assert "Old draft content." not in prompt

    def test_quality_gate_requests_review_revise_when_score_below_target(
        self, run_dir: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        _write_prior_artifact(run_dir, 19, "paper_revised.md", "# Revised\n\nBody.")
        _write_prior_artifact(
            run_dir,
            18,
            "review_state.json",
            json.dumps(
                {
                    "iteration": 1,
                    "overall_score": 5.8,
                    "target_score": 6.5,
                    "max_review_rounds": 4,
                    "open_findings": 2,
                    "review_outcome": "revise_again",
                }
            ),
        )
        stage_dir = run_dir / "stage-20"
        stage_dir.mkdir(parents=True, exist_ok=True)

        result = rc_executor._execute_quality_gate(
            stage_dir, run_dir, rc_config, adapters, llm=None
        )

        assert result.status == StageStatus.DONE
        assert result.decision == "review_revise"
        assert (stage_dir / "review_loop_gate.json").exists()

    def test_quality_gate_routes_to_experiment_refine_for_empirical_gap(
        self, run_dir: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        _write_prior_artifact(run_dir, 19, "paper_revised.md", "# Revised\n\nBody.")
        _write_prior_artifact(
            run_dir,
            18,
            "review_state.json",
            json.dumps(
                {
                    "iteration": 1,
                    "overall_score": 5.9,
                    "target_score": 8.0,
                    "max_review_rounds": 4,
                    "open_findings": 3,
                    "review_outcome": "revise_again",
                    "editorial_action": "supplement_experiments",
                }
            ),
        )
        stage_dir = run_dir / "stage-20"
        stage_dir.mkdir(parents=True, exist_ok=True)

        result = rc_executor._execute_quality_gate(
            stage_dir, run_dir, rc_config, adapters, llm=None
        )

        assert result.status == StageStatus.DONE
        assert result.decision == "editorial_experiment_refine"

    def test_quality_gate_context_overflow_retries_with_compact_prompt(
        self, run_dir: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        _write_prior_artifact(run_dir, 19, "paper_revised.md", "# Revised\n\n" + ("A" * 50000))
        _write_prior_artifact(
            run_dir,
            14,
            "experiment_summary.json",
            json.dumps({
                "metrics_summary": {"primary_metric": {"mean": 0.5, "min": 0.5, "max": 0.5}},
                "condition_summaries": {"method": {"primary_metric_mean": 0.5}},
            }),
        )
        stage_dir = run_dir / "stage-20"
        stage_dir.mkdir(parents=True, exist_ok=True)

        class QualityOverflowOnceLLM:
            def __init__(self):
                self.user_prompts: list[str] = []

            def chat(self, messages, **kwargs):
                _ = kwargs
                user = next(m["content"] for m in messages if m.get("role") == "user")
                self.user_prompts.append(user)
                if "... [paper for evaluation compacted:" not in user:
                    raise RuntimeError("Context-overflow message returned instead of Python code.")
                from researchclaw.llm.client import LLMResponse
                return LLMResponse(
                    content=json.dumps({
                        "score_1_to_10": 9,
                        "verdict": "proceed",
                        "strengths": ["compact review succeeded"],
                        "weaknesses": [],
                    }),
                    model="fake",
                )

        llm = QualityOverflowOnceLLM()

        result = rc_executor._execute_quality_gate(
            stage_dir, run_dir, rc_config, adapters, llm=llm
        )

        assert result.status == StageStatus.DONE
        assert any("... [paper for evaluation compacted:" in p for p in llm.user_prompts)
        report = json.loads((stage_dir / "quality_report.json").read_text(encoding="utf-8"))
        assert report["score_1_to_10"] == 9

    def test_quality_gate_compact_overflow_uses_default_report(
        self, run_dir: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        _write_prior_artifact(run_dir, 19, "paper_revised.md", "# Revised\n\n" + ("A" * 50000))
        _write_prior_artifact(
            run_dir,
            18,
            "review_state.json",
            json.dumps({
                "iteration": 1,
                "overall_score": 5.0,
                "target_score": 8.0,
                "max_review_rounds": 4,
                "open_findings": 3,
                "review_outcome": "revise_again",
                "editorial_action": "rework_innovation",
            }),
        )
        stage_dir = run_dir / "stage-20"
        stage_dir.mkdir(parents=True, exist_ok=True)

        class AlwaysQualityOverflowLLM:
            def chat(self, messages, **kwargs):
                _ = messages, kwargs
                raise RuntimeError("Context-overflow message returned instead of Python code.")

        result = rc_executor._execute_quality_gate(
            stage_dir, run_dir, rc_config, adapters, llm=AlwaysQualityOverflowLLM()
        )

        assert result.status == StageStatus.DONE
        assert result.decision == "degraded"
        report = json.loads((stage_dir / "quality_report.json").read_text(encoding="utf-8"))
        assert report["_assessment_unavailable"] is True
        assert any("compact retry" in w for w in report.get("weaknesses", []))

    def test_quality_gate_quota_error_uses_default_report(
        self, run_dir: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        _write_prior_artifact(run_dir, 19, "paper_revised.md", "# Revised\n\nBody.")
        stage_dir = run_dir / "stage-20"
        stage_dir.mkdir(parents=True, exist_ok=True)

        class QualityQuotaLLM:
            def chat(self, messages, **kwargs):
                _ = messages, kwargs
                raise RuntimeError("Upstream quota message returned instead of Python code.")

        result = rc_executor._execute_quality_gate(
            stage_dir, run_dir, rc_config, adapters, llm=QualityQuotaLLM()
        )

        assert result.status == StageStatus.DONE
        report = json.loads((stage_dir / "quality_report.json").read_text(encoding="utf-8"))
        assert any("quota" in w.lower() for w in report.get("weaknesses", []))

    def test_knowledge_archive_context_overflow_writes_deterministic_archive(
        self, run_dir: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        _write_prior_artifact(run_dir, 19, "paper_revised.md", "# Revised\n\n" + ("A" * 50000))
        stage_dir = run_dir / "stage-21"
        stage_dir.mkdir(parents=True, exist_ok=True)

        class ArchiveOverflowLLM:
            def chat(self, messages, **kwargs):
                _ = messages, kwargs
                raise RuntimeError("Context-overflow message returned instead of Python code.")

        result = rc_executor._execute_knowledge_archive(
            stage_dir, run_dir, rc_config, adapters, llm=ArchiveOverflowLLM()
        )

        assert result.status == StageStatus.DONE
        archive = (stage_dir / "archive.md").read_text(encoding="utf-8")
        assert "deterministic" not in archive.lower()
        assert "LLM context overflow" in archive


class TestPhaseThreeCompactArtifacts:
    def test_literature_collect_uses_note_seed_and_writes_digest(
        self, tmp_path: Path, adapters: AdapterBundle, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import researchclaw.literature.search as lit_search
        import researchclaw.data as rc_data

        monkeypatch.setattr(lit_search, "search_papers_multi_query", lambda *args, **kwargs: [])
        monkeypatch.setattr(rc_data, "load_seminal_papers", lambda topic: [])

        note_dir = tmp_path / "notes"
        note_dir.mkdir(parents=True)
        (note_dir / "baseline_note.md").write_text(
            "# Seed Note\nThis note describes a structured prior and a baseline failure mode.",
            encoding="utf-8",
        )
        kb_root = tmp_path / "kb"
        for name in ("questions", "literature", "experiments", "findings", "decisions", "reviews"):
            (kb_root / name).mkdir(parents=True, exist_ok=True)
        config = RCConfig.from_dict(
            {
                "project": {"name": "demo", "mode": "docs-first"},
                "research": {
                    "topic": "structured priors for planning",
                    "domains": ["ml"],
                    "note_seed_paths": [str(note_dir)],
                    "max_seed_docs": 6,
                },
                "runtime": {"timezone": "UTC"},
                "notifications": {"channel": "console"},
                "knowledge_base": {"backend": "markdown", "root": str(kb_root)},
                "openclaw_bridge": {},
                "llm": {"provider": "acp", "acp": {"agent": "codex"}},
                "experiment": {"mode": "simulated"},
                "web_search": {"enabled": False},
            },
            project_root=tmp_path,
            check_paths=False,
        )
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _write_prior_artifact(run_dir, 3, "queries.json", json.dumps({"queries": ["structured prior"], "year_min": 2020}))
        stage_dir = run_dir / "stage-04"
        stage_dir.mkdir(parents=True, exist_ok=True)

        result = rc_executor._execute_literature_collect(
            stage_dir, run_dir, config, adapters, llm=None
        )

        assert result.status == StageStatus.DONE
        candidates = [json.loads(line) for line in (stage_dir / "candidates.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        assert any(row.get("source") == "local_note" for row in candidates)
        assert (stage_dir / "baseline_digest.md").exists()
        assert (stage_dir / "local_seed_manifest.json").exists()

    def test_literature_collect_prioritizes_zotero_and_obsidian_before_local_seed(
        self, tmp_path: Path, adapters: AdapterBundle, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import researchclaw.literature.search as lit_search
        import researchclaw.data as rc_data

        monkeypatch.setattr(lit_search, "search_papers_multi_query", lambda *args, **kwargs: [])
        monkeypatch.setattr(rc_data, "load_seminal_papers", lambda topic: [])

        zotero_path = tmp_path / "zotero.json"
        zotero_path.write_text(
            json.dumps(
                [
                    {
                        "key": "ABCD1234",
                        "title": "Curated Zotero Paper",
                        "abstractNote": "A curated baseline paper from Zotero.",
                        "date": "2024",
                    }
                ]
            ),
            encoding="utf-8",
        )
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir(parents=True)
        (vault_dir / "obsidian_note.md").write_text(
            "# Obsidian Note\nThis note captures a paper idea and baseline comparison.",
            encoding="utf-8",
        )
        note_dir = tmp_path / "notes"
        note_dir.mkdir(parents=True)
        (note_dir / "seed_note.md").write_text(
            "# Local Seed\nThis is the lower-priority local note seed.",
            encoding="utf-8",
        )
        kb_root = tmp_path / "kb"
        for name in ("questions", "literature", "experiments", "findings", "decisions", "reviews"):
            (kb_root / name).mkdir(parents=True, exist_ok=True)
        config = RCConfig.from_dict(
            {
                "project": {"name": "demo", "mode": "docs-first"},
                "research": {
                    "topic": "structured priors for planning",
                    "domains": ["ml"],
                    "zotero_library_path": str(zotero_path),
                    "note_seed_paths": [str(note_dir)],
                    "max_seed_docs": 6,
                },
                "runtime": {"timezone": "UTC"},
                "notifications": {"channel": "console"},
                "knowledge_base": {
                    "backend": "markdown",
                    "root": str(kb_root),
                    "obsidian_vault": str(vault_dir),
                },
                "openclaw_bridge": {},
                "llm": {"provider": "acp", "acp": {"agent": "codex"}},
                "experiment": {"mode": "simulated"},
                "web_search": {"enabled": False},
            },
            project_root=tmp_path,
            check_paths=False,
        )
        run_dir = tmp_path / "run-priority"
        run_dir.mkdir()
        _write_prior_artifact(
            run_dir,
            3,
            "queries.json",
            json.dumps({"queries": ["structured prior"], "year_min": 2020}),
        )
        stage_dir = run_dir / "stage-04"
        stage_dir.mkdir(parents=True, exist_ok=True)

        result = rc_executor._execute_literature_collect(
            stage_dir, run_dir, config, adapters, llm=None
        )

        assert result.status == StageStatus.DONE
        candidates = [
            json.loads(line)
            for line in (stage_dir / "candidates.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        ordered_sources = [row.get("source") for row in candidates[:3]]
        assert ordered_sources == ["zotero_json", "obsidian_note", "local_note"]
        manifest = json.loads((stage_dir / "local_seed_manifest.json").read_text(encoding="utf-8"))
        assert manifest["priority_order"] == ["zotero", "obsidian", "local_seed"]
        assert manifest["source_mix"]["zotero_json"] == 1

    def test_literature_screen_writes_shortlist_digest(
        self, run_dir: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        _write_prior_artifact(
            run_dir,
            4,
            "candidates.jsonl",
            "\n".join(
                json.dumps(
                    {
                        "title": f"Paper {idx}",
                        "abstract": "Relevant ml abstract with test topic overlap",
                        "source": "local_note",
                    }
                )
                for idx in range(20)
            ),
        )
        stage_dir = run_dir / "stage-05"
        stage_dir.mkdir(parents=True, exist_ok=True)

        result = rc_executor._execute_literature_screen(
            stage_dir, run_dir, rc_config, adapters, llm=None
        )

        assert result.status == StageStatus.DONE
        assert (stage_dir / "literature_shortlist.md").exists()
        digest = (stage_dir / "literature_shortlist.md").read_text(encoding="utf-8")
        assert "Literature Shortlist" in digest
        assert "Paper 0" in digest

    def test_result_analysis_writes_experiment_log(
        self, run_dir: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        runs_dir = run_dir / "stage-12" / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        (runs_dir / "run-1.json").write_text(
            json.dumps(
                {
                    "run_id": "run-1",
                    "status": "completed",
                    "metrics": {"primary_metric": 0.81, "baseline/primary_metric": 0.74},
                    "stdout": "primary_metric: 0.81\nbaseline/primary_metric: 0.74\n",
                }
            ),
            encoding="utf-8",
        )
        stage_dir = run_dir / "stage-14"
        stage_dir.mkdir(parents=True, exist_ok=True)

        result = rc_executor._execute_result_analysis(
            stage_dir, run_dir, rc_config, adapters, llm=None
        )

        assert result.status == StageStatus.DONE
        assert "experiment_log.md" in result.artifacts
        log_text = (stage_dir / "experiment_log.md").read_text(encoding="utf-8")
        assert "Experiment Log" in log_text
        assert "Best run id" in log_text


class TestMultiPerspectiveGenerate:
    def test_generates_all_perspectives(self, tmp_path: Path) -> None:
        roles = {
            "role_a": {"system": "You are A.", "user": "Do A for {topic}."},
            "role_b": {"system": "You are B.", "user": "Do B for {topic}."},
        }
        fake_llm = FakeLLMClient("perspective output")
        perspectives_dir = tmp_path / "perspectives"
        result = rc_executor._multi_perspective_generate(
            fake_llm, roles, {"topic": "test"}, perspectives_dir
        )
        assert set(result.keys()) == {"role_a", "role_b"}
        assert (perspectives_dir / "role_a.md").exists()
        assert (perspectives_dir / "role_b.md").exists()
        assert len(fake_llm.calls) == 2

    def test_saves_perspective_content(self, tmp_path: Path) -> None:
        roles = {"critic": {"system": "Be critical.", "user": "Criticize {topic}."}}
        fake_llm = FakeLLMClient("critical analysis here")
        perspectives_dir = tmp_path / "perspectives"
        rc_executor._multi_perspective_generate(
            fake_llm, roles, {"topic": "ml"}, perspectives_dir
        )
        content = (perspectives_dir / "critic.md").read_text()
        assert content == "critical analysis here"

    def test_renders_variables_in_prompts(self, tmp_path: Path) -> None:
        roles = {"r1": {"system": "Sys for {topic}.", "user": "User for {topic}."}}
        fake_llm = FakeLLMClient("ok")
        rc_executor._multi_perspective_generate(
            fake_llm, roles, {"topic": "RL"}, tmp_path / "p"
        )
        call = fake_llm.calls[0]
        assert "RL" in call[0]["content"]


class TestSynthesizePerspectives:
    def test_combines_perspectives(self) -> None:
        fake_llm = FakeLLMClient("synthesized result")
        pm = rc_executor.PromptManager()
        perspectives = {"innovator": "idea A", "contrarian": "idea B"}
        result = rc_executor._synthesize_perspectives(
            fake_llm, perspectives, "hypothesis_synthesize", pm
        )
        assert result == "synthesized result"
        # Check the user prompt contained both perspectives
        call_content = fake_llm.calls[0][0]["content"]
        assert "innovator" in call_content
        assert "contrarian" in call_content


class TestHypothesisGenDebate:
    def test_hypothesis_gen_with_llm_creates_perspectives(
        self, tmp_path: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        stage_dir = run_dir / "stage-08"
        stage_dir.mkdir(parents=True)
        _write_prior_artifact(run_dir, 7, "synthesis.md", "# Synthesis\nGap found.")
        fake_llm = FakeLLMClient("## H1\nTest hypothesis")
        result = rc_executor._execute_hypothesis_gen(
            stage_dir, run_dir, rc_config, adapters, llm=fake_llm
        )
        assert result.status == StageStatus.DONE
        assert "hypotheses.md" in result.artifacts
        perspectives_dir = stage_dir / "perspectives"
        assert perspectives_dir.exists()
        # Should have 3 perspective files (innovator, pragmatist, contrarian)
        perspective_files = list(perspectives_dir.glob("*.md"))
        assert len(perspective_files) == 3

    def test_hypothesis_gen_without_llm_no_perspectives(
        self, tmp_path: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        stage_dir = run_dir / "stage-08"
        stage_dir.mkdir(parents=True)
        _write_prior_artifact(run_dir, 7, "synthesis.md", "# Synthesis\nGap found.")
        result = rc_executor._execute_hypothesis_gen(
            stage_dir, run_dir, rc_config, adapters, llm=None
        )
        assert result.status == StageStatus.DONE
        assert "hypotheses.md" in result.artifacts
        # No perspectives directory when no LLM
        assert not (stage_dir / "perspectives").exists()


class TestResultAnalysisDebate:
    def test_result_analysis_with_llm_creates_perspectives(
        self, tmp_path: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        stage_dir = run_dir / "stage-14"
        stage_dir.mkdir(parents=True)
        _write_prior_artifact(run_dir, 1, "goal.md", "# Goal\nTest")
        _write_prior_artifact(run_dir, 8, "hypotheses.md", "# H1\nTest")
        fake_llm = FakeLLMClient("## Analysis\nResults look good.")
        result = rc_executor._execute_result_analysis(
            stage_dir, run_dir, rc_config, adapters, llm=fake_llm
        )
        assert result.status == StageStatus.DONE
        assert "analysis.md" in result.artifacts
        perspectives_dir = stage_dir / "perspectives"
        assert perspectives_dir.exists()
        # Should have 3 perspective files (optimist, skeptic, methodologist)
        perspective_files = list(perspectives_dir.glob("*.md"))
        assert len(perspective_files) == 3

    def test_result_analysis_without_llm_no_perspectives(
        self, tmp_path: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        stage_dir = run_dir / "stage-14"
        stage_dir.mkdir(parents=True)
        result = rc_executor._execute_result_analysis(
            stage_dir, run_dir, rc_config, adapters, llm=None
        )
        assert result.status == StageStatus.DONE
        assert "analysis.md" in result.artifacts
        assert not (stage_dir / "perspectives").exists()

    def test_result_analysis_prepends_authoritative_snapshot(
        self, tmp_path: Path, rc_config: RCConfig, adapters: AdapterBundle, monkeypatch
    ) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        stage_dir = run_dir / "stage-14"
        stage_dir.mkdir(parents=True)
        monkeypatch.setattr(
            rc_analysis,
            "_collect_experiment_results",
            lambda *args, **kwargs: {
                "metrics_summary": {},
                "runs": [],
                "best_run": {
                    "metrics": {
                        "falcon_qb_activation_rank/primary_metric": 0.189296,
                        "cheap_proxy_controller/primary_metric": 0.192978,
                    }
                },
                "latex_table": "",
                "structured_results": {},
            },
        )

        rc_executor._execute_result_analysis(
            stage_dir, run_dir, rc_config, adapters, llm=None
        )

        analysis = (stage_dir / "analysis.md").read_text()
        assert "## Authoritative Structured Experiment Snapshot" in analysis
        assert "falcon_qb_activation_rank: primary_metric=0.189296" in analysis
        assert "cheap_proxy_controller: primary_metric=0.192978" in analysis


class TestAuthoritativeExperimentSnapshot:
    def test_builds_ranked_snapshot_from_condition_summaries(self) -> None:
        snapshot = rc_analysis._build_authoritative_experiment_snapshot(
            {
                "condition_summaries": {
                    "cheap_proxy_controller": {
                        "metrics": {"primary_metric_mean": 0.192978}
                    },
                    "falcon_qb_activation_rank": {
                        "metrics": {"primary_metric_mean": 0.189296}
                    },
                }
            },
            metric_key="primary_metric",
            metric_direction="minimize",
        )

        assert "Authoritative Structured Experiment Snapshot" in snapshot
        assert snapshot.index("falcon_qb_activation_rank") < snapshot.index("cheap_proxy_controller")


class TestParseMetricsFromStdout:
    """Tests for _parse_metrics_from_stdout() helper."""

    def test_parses_simple_name_value(self) -> None:
        from researchclaw.pipeline.executor import _parse_metrics_from_stdout

        stdout = "loss: 0.0042\naccuracy: 0.95"
        metrics = _parse_metrics_from_stdout(stdout)
        assert metrics["loss"] == pytest.approx(0.0042)
        assert metrics["accuracy"] == pytest.approx(0.95)

    def test_parses_compound_names(self) -> None:
        from researchclaw.pipeline.executor import _parse_metrics_from_stdout

        stdout = "UCB (Stochastic) cumulative_regret: 361.9233\nEXP3 (Adversarial) total_rewards: 13368.4811"
        metrics = _parse_metrics_from_stdout(stdout)
        assert "UCB (Stochastic) cumulative_regret" in metrics
        assert metrics["UCB (Stochastic) cumulative_regret"] == pytest.approx(361.9233)

    def test_ignores_non_numeric_lines(self) -> None:
        from researchclaw.pipeline.executor import _parse_metrics_from_stdout

        stdout = "Running experiment...\nloss: 0.5\nDone."
        metrics = _parse_metrics_from_stdout(stdout)
        assert len(metrics) == 1
        assert metrics["loss"] == pytest.approx(0.5)

    def test_empty_stdout_returns_empty_dict(self) -> None:
        from researchclaw.pipeline.executor import _parse_metrics_from_stdout

        assert _parse_metrics_from_stdout("") == {}

    def test_handles_negative_values(self) -> None:
        from researchclaw.pipeline.executor import _parse_metrics_from_stdout

        stdout = "UCB (Adversarial) cumulative_regret: -3877.5323"
        metrics = _parse_metrics_from_stdout(stdout)
        assert metrics["UCB (Adversarial) cumulative_regret"] == pytest.approx(-3877.5323)

    def test_filters_log_lines(self) -> None:
        from researchclaw.pipeline.executor import _parse_metrics_from_stdout

        stdout = (
            "Running experiments for support set size: 1\n"
            "Loading model weights: 42\n"
            "Training epoch: 5\n"
            "loss: 0.123\n"
            "accuracy: 0.95\n"
        )
        metrics = _parse_metrics_from_stdout(stdout)
        assert "loss" in metrics
        assert "accuracy" in metrics
        assert len(metrics) == 2  # log lines should be excluded

    def test_filters_long_name_lines(self) -> None:
        from researchclaw.pipeline.executor import _parse_metrics_from_stdout

        stdout = "this is a very long status message that should not be a metric: 42\n"
        metrics = _parse_metrics_from_stdout(stdout)
        assert len(metrics) == 0


class TestDetectRuntimeIssues:
    """Tests for _detect_runtime_issues() helper."""

    def _make_sandbox_result(
        self,
        metrics: dict | None = None,
        stdout: str = "",
        stderr: str = "",
    ):
        from types import SimpleNamespace

        return SimpleNamespace(
            metrics=metrics or {},
            stdout=stdout,
            stderr=stderr,
            returncode=0,
            elapsed_sec=1.0,
            timed_out=False,
        )

    def test_no_issues_returns_empty_string(self) -> None:
        r = self._make_sandbox_result(metrics={"loss": 0.5}, stdout="loss: 0.5")
        assert rc_executor._detect_runtime_issues(r) == ""

    def test_detects_nan_in_metrics(self) -> None:
        r = self._make_sandbox_result(metrics={"loss": float("nan")})
        result = rc_executor._detect_runtime_issues(r)
        assert "NaN" in result
        assert "loss" in result

    def test_detects_inf_in_metrics(self) -> None:
        r = self._make_sandbox_result(metrics={"loss": float("inf")})
        result = rc_executor._detect_runtime_issues(r)
        assert "Inf" in result

    def test_detects_nan_in_stdout(self) -> None:
        r = self._make_sandbox_result(stdout="accuracy: nan\nloss: 0.5")
        result = rc_executor._detect_runtime_issues(r)
        assert "NaN" in result or "nan" in result

    def test_detects_runtime_warning_in_stderr(self) -> None:
        stderr = (
            "optimizers.py:76: RuntimeWarning: invalid value encountered in divide\n"
            "  directions = np.vstack((directions[1:], new_direction / norm))\n"
        )
        r = self._make_sandbox_result(stderr=stderr)
        result = rc_executor._detect_runtime_issues(r)
        assert "RuntimeWarning" in result
        assert "invalid value" in result

    def test_detects_division_error_in_stderr(self) -> None:
        stderr = "ZeroDivisionError: division by zero\n"
        r = self._make_sandbox_result(stderr=stderr)
        result = rc_executor._detect_runtime_issues(r)
        assert "Error" in result

    def test_ignores_benign_stderr(self) -> None:
        # Non-warning stderr should be ignored
        r = self._make_sandbox_result(stderr="Loading module...\nDone.\n")
        assert rc_executor._detect_runtime_issues(r) == ""

    def test_ignores_hf_hub_unauthenticated_warning(self) -> None:
        stderr = (
            "Warning: You are sending unauthenticated requests to the HF Hub. "
            "Please set a HF_TOKEN to enable higher rate limits and faster downloads.\n"
        )
        r = self._make_sandbox_result(stderr=stderr)
        assert rc_executor._detect_runtime_issues(r) == ""

    def test_combined_nan_and_stderr(self) -> None:
        r = self._make_sandbox_result(
            metrics={"accuracy": float("nan")},
            stderr="RuntimeWarning: invalid value\n",
        )
        result = rc_executor._detect_runtime_issues(r)
        assert "NaN" in result
        assert "RuntimeWarning" in result

    def test_detects_dummy_metric_identical_values(self) -> None:
        stdout = (
            "UCB (Stochastic) convergence_rate: 1.0000\n"
            "UCB (Adversarial) convergence_rate: 1.0000\n"
            "Thompson (Stochastic) convergence_rate: 1.0000\n"
            "Thompson (Adversarial) convergence_rate: 1.0000\n"
        )
        r = self._make_sandbox_result(stdout=stdout)
        result = rc_executor._detect_runtime_issues(r)
        assert "DUMMY" in result
        assert "convergence_rate" in result

    def test_no_dummy_metric_when_values_differ(self) -> None:
        stdout = (
            "UCB (Stochastic) regret: 78.5\n"
            "Thompson (Stochastic) regret: 121.0\n"
            "EpsilonGreedy (Stochastic) regret: 42.1\n"
        )
        r = self._make_sandbox_result(stdout=stdout)
        result = rc_executor._detect_runtime_issues(r)
        assert "DUMMY" not in result


class TestRemoveBibtexEntries:
    """Tests for _remove_bibtex_entries() helper."""

    def test_removes_specified_keys(self) -> None:
        bib = (
            '@article{smith2024,\n  title={Good Paper},\n  author={Smith},\n}\n\n'
            '@article{venus2024,\n  title={Venus Exploration},\n  author={NASA},\n}\n'
        )
        result = rc_executor._remove_bibtex_entries(bib, {"venus2024"})
        assert "smith2024" in result
        assert "venus2024" not in result

    def test_keeps_all_when_no_match(self) -> None:
        bib = '@article{smith2024,\n  title={Paper},\n}\n'
        result = rc_executor._remove_bibtex_entries(bib, {"other_key"})
        assert "smith2024" in result

    def test_empty_bib(self) -> None:
        assert rc_executor._remove_bibtex_entries("", {"key"}) == ""


class TestRemoveCitationsFromText:
    """Tests for _remove_citations_from_text() helper."""

    def test_removes_latex_cite(self) -> None:
        text = r"As shown in \cite{venus2024}, the results are..."
        result = rc_executor._remove_citations_from_text(text, {"venus2024"})
        assert "venus2024" not in result
        assert "results are" in result

    def test_removes_markdown_cite(self) -> None:
        text = "Prior work [venus2024] explored this topic."
        result = rc_executor._remove_citations_from_text(text, {"venus2024"})
        assert "venus2024" not in result

    def test_cleans_multi_cite_comma(self) -> None:
        text = r"\cite{good2024,venus2024}"
        result = rc_executor._remove_citations_from_text(text, {"venus2024"})
        assert r"\cite{good2024}" in result


class TestCollectRawExperimentMetrics:
    """Tests for _collect_raw_experiment_metrics() helper."""

    def test_returns_empty_when_no_runs(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        block, has_parsed = rc_executor._collect_raw_experiment_metrics(run_dir)
        assert block == ""
        assert not has_parsed

    def test_extracts_metrics_from_stdout(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        runs_dir = run_dir / "stage-12" / "runs"
        runs_dir.mkdir(parents=True)
        payload = {
            "metrics": {},
            "stdout": "UCB regret: 361.92\nThompson regret: 576.24\n",
        }
        (runs_dir / "run-1.json").write_text(json.dumps(payload))
        result, has_parsed = rc_executor._collect_raw_experiment_metrics(run_dir)
        assert "361.92" in result
        assert "576.24" in result
        assert "1 run(s)" in result
        assert not has_parsed

    def test_extracts_from_metrics_dict(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        runs_dir = run_dir / "stage-12" / "runs"
        runs_dir.mkdir(parents=True)
        payload = {"metrics": {"loss": 0.042, "accuracy": 0.95}, "stdout": ""}
        (runs_dir / "run-1.json").write_text(json.dumps(payload))
        result, has_parsed = rc_executor._collect_raw_experiment_metrics(run_dir)
        assert "loss" in result
        assert "0.042" in result
        assert has_parsed

    def test_deduplicates_metrics(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        runs_dir = run_dir / "stage-12" / "runs"
        runs_dir.mkdir(parents=True)
        payload = {
            "metrics": {"loss": 0.5},
            "stdout": "loss: 0.5\nloss: 0.5\n",
        }
        (runs_dir / "run-1.json").write_text(json.dumps(payload))
        result, _ = rc_executor._collect_raw_experiment_metrics(run_dir)
        # "loss: 0.5" should appear only once (deduplicated)
        assert result.count("loss: 0.5") == 1


class TestCollectExperimentEvidence:
    """Tests for _collect_experiment_evidence() helper."""

    def test_returns_empty_when_no_artifacts(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        assert rc_executor._collect_experiment_evidence(run_dir) == ""

    def test_includes_main_py_code(self, run_dir: Path) -> None:
        exp_dir = run_dir / "stage-10" / "experiment"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "main.py").write_text("print('hello')", encoding="utf-8")
        result = rc_executor._collect_experiment_evidence(run_dir)
        assert "main.py" in result
        assert "hello" in result

    def test_includes_run_metrics(self, run_dir: Path) -> None:
        runs_dir = run_dir / "stage-12" / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        (runs_dir / "run-1.json").write_text(
            json.dumps({"metrics": {"loss": 0.5}, "elapsed_sec": 3.2}),
            encoding="utf-8",
        )
        result = rc_executor._collect_experiment_evidence(run_dir)
        assert "loss" in result
        assert "0.5" in result

    def test_includes_stderr_excerpt(self, run_dir: Path) -> None:
        runs_dir = run_dir / "stage-12" / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        (runs_dir / "run-1.json").write_text(
            json.dumps({
                "metrics": {"loss": 0.5},
                "stderr": "RuntimeWarning: divide by zero",
            }),
            encoding="utf-8",
        )
        result = rc_executor._collect_experiment_evidence(run_dir)
        assert "divide by zero" in result

    def test_includes_refinement_summary(self, run_dir: Path) -> None:
        refine_dir = run_dir / "stage-13"
        refine_dir.mkdir(parents=True, exist_ok=True)
        (refine_dir / "refinement_log.json").write_text(
            json.dumps({
                "iterations": [{"iteration": 1}, {"iteration": 2}],
                "converged": True,
                "stop_reason": "no_improvement_for_2_iterations",
                "best_metric": 0.3,
            }),
            encoding="utf-8",
        )
        result = rc_executor._collect_experiment_evidence(run_dir)
        assert "iterations_executed" in result
        assert "2" in result

    def test_includes_actual_trial_count(self, run_dir: Path) -> None:
        runs_dir = run_dir / "stage-12" / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        (runs_dir / "run-1.json").write_text(
            json.dumps({"metrics": {"loss": 0.5}}), encoding="utf-8"
        )
        result = rc_executor._collect_experiment_evidence(run_dir)
        assert "1 time(s)" in result
        assert "CRITICAL" in result


class TestWritePaperSections:
    """Tests for _write_paper_sections() multi-call writing."""

    def test_produces_three_part_draft(self) -> None:
        call_count = {"n": 0}
        parts = [
            "# Test Title\n\n## Abstract\nTest abstract.\n\n## Introduction\nTest intro.\n\n## Related Work\nTest related.",
            "## Method\nTest method.\n\n## Experiments\nTest experiments.",
            "## Results\nTest results.\n\n## Discussion\nTest discussion.\n\n## Limitations\nTest limits.\n\n## Conclusion\nTest conclusion.",
        ]

        class MultiCallLLM:
            def __init__(self):
                self.calls: list = []

            def chat(self, messages, **kwargs):
                self.calls.append(messages)
                from researchclaw.llm.client import LLMResponse
                idx = len(self.calls) - 1
                return LLMResponse(content=parts[min(idx, 2)], model="fake")

        llm = MultiCallLLM()
        from researchclaw.prompts import PromptManager
        pm = PromptManager()

        draft = rc_executor._write_paper_sections(
            llm=llm,
            pm=pm,
            preamble="Test preamble",
            topic_constraint="",
            exp_metrics_instruction="",
            citation_instruction="",
            outline="Test outline",
        )

        assert llm.calls is not None
        assert len(llm.calls) == 3
        assert "## Abstract" in draft
        assert "## Method" in draft
        assert "## Results" in draft
        assert "## Conclusion" in draft

    def test_each_call_receives_prior_context(self) -> None:
        class ContextTrackingLLM:
            def __init__(self):
                self.user_prompts: list[str] = []

            def chat(self, messages, **kwargs):
                for m in messages:
                    if m.get("role") == "user":
                        self.user_prompts.append(m["content"])
                from researchclaw.llm.client import LLMResponse
                return LLMResponse(content="## Section\nContent here.", model="fake")

        llm = ContextTrackingLLM()
        from researchclaw.prompts import PromptManager
        pm = PromptManager()

        rc_executor._write_paper_sections(
            llm=llm,
            pm=pm,
            preamble="Preamble",
            topic_constraint="",
            exp_metrics_instruction="",
            citation_instruction="",
            outline="Outline",
        )

        assert len(llm.user_prompts) == 3
        # Call 2 and 3 should contain "sections written so far"
        assert "sections written so far" in llm.user_prompts[1]
        assert "completing a paper" in llm.user_prompts[2]

    def test_part2_context_overflow_retries_with_compact_prompt(self) -> None:
        class OverflowOnceLLM:
            def __init__(self):
                self.user_prompts: list[str] = []
                self.full_part2_failures = 0

            def chat(self, messages, **kwargs):
                _ = kwargs
                user = next(m["content"] for m in messages if m.get("role") == "user")
                self.user_prompts.append(user)
                if "Now write the next sections" in user and "... [preamble compacted:" not in user:
                    self.full_part2_failures += 1
                    raise RuntimeError("Context-overflow message returned instead of Python code.")
                from researchclaw.llm.client import LLMResponse
                if "Now write the next sections" in user:
                    return LLMResponse(
                        content="## Method\nCompact method.\n\n## Experiments\nCompact experiments.",
                        model="fake",
                    )
                if "Now write the final sections" in user:
                    return LLMResponse(
                        content="## Results\nResults.\n\n## Discussion\nDiscussion.\n\n"
                        "## Limitations\nLimits.\n\n## Conclusion\nConclusion.",
                        model="fake",
                    )
                return LLMResponse(
                    content="## Title\nT\n\n## Abstract\nA\n\n## Introduction\nI\n\n## Related Work\nR",
                    model="fake",
                )

        llm = OverflowOnceLLM()
        from researchclaw.prompts import PromptManager
        pm = PromptManager()

        draft = rc_executor._write_paper_sections(
            llm=llm,
            pm=pm,
            preamble="Preamble\n" + ("A" * 20000),
            topic_constraint="",
            exp_metrics_instruction="Metrics\n" + ("B" * 30000),
            citation_instruction="Citations\n" + ("C" * 18000),
            outline="Outline\n" + ("D" * 12000),
        )

        assert llm.full_part2_failures == 2
        assert any("... [preamble compacted:" in p for p in llm.user_prompts)
        assert "## Method" in draft
        assert "Compact method" in draft
        assert "PLACEHOLDER" not in draft

    def test_part2_context_overflow_failure_raises_instead_of_placeholder(self) -> None:
        class AlwaysOverflowLLM:
            def chat(self, messages, **kwargs):
                _ = messages, kwargs
                raise RuntimeError("Context-overflow message returned instead of Python code.")

        from researchclaw.prompts import PromptManager
        pm = PromptManager()

        with pytest.raises(RuntimeError, match="failed after compact retry"):
            rc_executor._write_paper_sections(
                llm=AlwaysOverflowLLM(),
                pm=pm,
                preamble="Preamble",
                topic_constraint="",
                exp_metrics_instruction="Metrics",
                citation_instruction="Citations",
                outline="Outline",
            )


class TestLoadHardwareProfile:
    """Tests for _load_hardware_profile()."""

    @pytest.fixture()
    def run_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "run"
        d.mkdir()
        return d

    def test_loads_valid_profile(self, run_dir: Path) -> None:
        stage = run_dir / "stage-01"
        stage.mkdir()
        profile = {"has_gpu": True, "gpu_type": "mps", "tier": "limited"}
        (stage / "hardware_profile.json").write_text(
            json.dumps(profile), encoding="utf-8"
        )
        result = rc_executor._load_hardware_profile(run_dir)
        assert result is not None
        assert result["gpu_type"] == "mps"

    def test_returns_none_when_missing(self, run_dir: Path) -> None:
        assert rc_executor._load_hardware_profile(run_dir) is None

    def test_returns_none_on_invalid_json(self, run_dir: Path) -> None:
        stage = run_dir / "stage-01"
        stage.mkdir()
        (stage / "hardware_profile.json").write_text("not json", encoding="utf-8")
        assert rc_executor._load_hardware_profile(run_dir) is None


class TestExpandSearchQueries:
    """Tests for _expand_search_queries()."""

    def test_adds_broader_queries(self) -> None:
        queries = ["gradient descent optimization algorithms"]
        topic = "Comparing gradient descent optimization algorithms on benchmark functions"
        result = rc_executor._expand_search_queries(queries, topic)
        assert len(result) > len(queries)

    def test_deduplicates(self) -> None:
        queries = ["gradient descent survey"]
        topic = "gradient descent optimization"
        result = rc_executor._expand_search_queries(queries, topic)
        lowered = [q.lower().strip() for q in result]
        assert len(lowered) == len(set(lowered))

    def test_preserves_original_queries(self) -> None:
        queries = ["query A", "query B"]
        topic = "some research topic about machine learning methods"
        result = rc_executor._expand_search_queries(queries, topic)
        assert result[0] == "query A"
        assert result[1] == "query B"

    def test_adds_survey_benchmark_variants(self) -> None:
        queries = ["deep learning"]
        topic = "deep learning for image classification with limited data"
        result = rc_executor._expand_search_queries(queries, topic)
        has_survey = any("survey" in q.lower() for q in result)
        has_benchmark = any("benchmark" in q.lower() for q in result)
        assert has_survey
        assert has_benchmark


# ── R4-1: Experiment Budget Guard Tests ──────────────────────────────


class TestComputeBudgetBlock:
    """Test compute_budget prompt block injection (R4-1a)."""

    def test_compute_budget_block_exists_in_prompt_manager(self) -> None:
        from researchclaw.prompts import PromptManager

        pm = PromptManager()
        block = pm.block("compute_budget")
        assert "time_budget_sec" in block or "Compute Budget" in block

    def test_compute_budget_injected_into_code_generation(
        self, tmp_path: Path, run_dir: Path, adapters: AdapterBundle
    ) -> None:
        import sys

        data = {
            "project": {"name": "rc-test", "mode": "docs-first"},
            "research": {
                "topic": "optimizer comparison",
                "domains": ["ml"],
                "daily_paper_count": 2,
                "quality_threshold": 8.2,
            },
            "runtime": {"timezone": "UTC"},
            "notifications": {
                "channel": "local",
                "on_stage_start": True,
                "on_stage_fail": False,
                "on_gate_required": True,
            },
            "knowledge_base": {"backend": "markdown", "root": str(tmp_path / "kb")},
            "openclaw_bridge": {"use_memory": True, "use_message": True},
            "llm": {
                "provider": "openai-compatible",
                "base_url": "http://localhost:1234/v1",
                "api_key_env": "RC_TEST_KEY",
                "api_key": "inline-test-key",
                "primary_model": "fake-model",
                "fallback_models": [],
            },
            "security": {"hitl_required_stages": [5, 9, 20]},
            "experiment": {
                "mode": "sandbox",
                "time_budget_sec": 60,
                "metric_key": "best_loss",
                "metric_direction": "minimize",
                "sandbox": {
                    "python_path": sys.executable,
                    "gpu_required": False,
                    "max_memory_mb": 1024,
                },
            },
        }
        cfg = RCConfig.from_dict(data, project_root=tmp_path, check_paths=False)

        # Write exp_plan prior artifact
        _write_prior_artifact(run_dir, 10, "exp_plan.yaml", "objectives: test")

        # Capture what the LLM receives
        llm = FakeLLMClient(
            "```filename:main.py\nimport numpy as np\nprint('best_loss: 0.1')\n```"
        )
        stage_dir = run_dir / "stage-11"
        stage_dir.mkdir(parents=True, exist_ok=True)

        rc_executor._execute_code_generation(
            stage_dir, run_dir, cfg, adapters, llm=llm
        )

        # The LLM should have received compute budget info in some call
        # (may be first call in legacy mode, or second call with CodeAgent)
        assert len(llm.calls) >= 1
        all_user_msgs = " ".join(
            call[-1]["content"] for call in llm.calls if call
        )
        assert "60" in all_user_msgs or "Compute Budget" in all_user_msgs


class TestPartialTimeoutStatus:
    """Test partial status for timed-out experiments with data (R4-1c)."""

    def test_timed_out_with_metrics_sets_partial_status(
        self, tmp_path: Path, run_dir: Path, adapters: AdapterBundle, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import sys
        from researchclaw.pipeline.stage_impls import _execution as execution_impl

        data = {
            "project": {"name": "rc-test", "mode": "docs-first"},
            "research": {
                "topic": "test topic",
                "domains": ["ml"],
                "daily_paper_count": 2,
                "quality_threshold": 8.2,
            },
            "runtime": {"timezone": "UTC"},
            "notifications": {
                "channel": "local",
                "on_stage_start": True,
                "on_stage_fail": False,
                "on_gate_required": True,
            },
            "knowledge_base": {"backend": "markdown", "root": str(tmp_path / "kb")},
            "openclaw_bridge": {"use_memory": True, "use_message": True},
            "llm": {
                "provider": "openai-compatible",
                "base_url": "http://localhost:1234/v1",
                "api_key_env": "RC_TEST_KEY",
                "api_key": "inline-test-key",
                "primary_model": "fake-model",
                "fallback_models": [],
            },
            "security": {"hitl_required_stages": [5, 9, 20]},
            "experiment": {
                "mode": "sandbox",
                "time_budget_sec": 2,
                "metric_key": "best_loss",
                "metric_direction": "minimize",
                "sandbox": {
                    "python_path": sys.executable,
                    "gpu_required": False,
                    "max_memory_mb": 1024,
                },
            },
        }
        cfg = RCConfig.from_dict(data, project_root=tmp_path, check_paths=False)
        monkeypatch.setattr(
            execution_impl,
            "_query_stage12_gpu_inventory",
            lambda: [
                {
                    "index": 4,
                    "utilization": 0,
                    "memory_used_mb": 128,
                    "memory_total_mb": 16384,
                    "compute_apps": [],
                }
            ],
        )

        # Write experiment code that prints some metrics then sleeps
        exp_dir = run_dir / "stage-11" / "experiment"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "main.py").write_text(
            "import time, sys\n"
            "print('best_loss: 0.5', flush=True)\n"
            "sys.stdout.flush()\n"
            "time.sleep(10)\n",
            encoding="utf-8",
        )

        stage_dir = run_dir / "stage-12"
        stage_dir.mkdir(parents=True, exist_ok=True)

        rc_executor._execute_experiment_run(
            stage_dir, run_dir, cfg, adapters
        )

        run_file = stage_dir / "runs" / "run-1.json"
        assert run_file.exists()
        payload = json.loads(run_file.read_text(encoding="utf-8"))
        # Should be "partial" since metrics were captured before timeout
        assert payload["timed_out"] is True
        # Status should be "partial" if metrics captured, "failed" if not
        if payload["metrics"]:
            assert payload["status"] == "partial"
        else:
            # Subprocess stdout may not flush before kill on some platforms
            assert payload["status"] == "failed"
        observer = json.loads((stage_dir / "runtime_observer.json").read_text(encoding="utf-8"))
        assert observer["runtime_outcome"]["status"] in {"partial", "failed"}
        assert observer["preflight"]["ok"] is True
        assert observer["gpu_availability"]["status"] == "ready"
        assert observer["runtime_watchdog"]["status"] in {"timed_out", "healthy"}

    def test_stage12_preflight_failure_writes_runtime_observer(
        self, tmp_path: Path, run_dir: Path, adapters: AdapterBundle, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import sys
        from researchclaw.pipeline.stage_impls import _execution as execution_impl

        data = {
            "project": {"name": "rc-test", "mode": "docs-first"},
            "research": {"topic": "test topic", "domains": ["ml"]},
            "runtime": {"timezone": "UTC"},
            "notifications": {"channel": "local"},
            "knowledge_base": {"backend": "markdown", "root": str(tmp_path / "kb")},
            "openclaw_bridge": {"use_memory": False, "use_message": False},
            "llm": {
                "provider": "openai-compatible",
                "base_url": "http://localhost:1234/v1",
                "api_key_env": "RC_TEST_KEY",
                "api_key": "inline-test-key",
                "primary_model": "fake-model",
            },
            "experiment": {
                "mode": "sandbox",
                "time_budget_sec": 60,
                "metric_key": "best_loss",
                "metric_direction": "minimize",
                "sandbox": {
                    "python_path": sys.executable,
                    "gpu_required": False,
                },
            },
        }
        cfg = RCConfig.from_dict(data, project_root=tmp_path, check_paths=False)
        monkeypatch.setattr(
            execution_impl,
            "_query_stage12_gpu_inventory",
            lambda: [
                {
                    "index": 4,
                    "utilization": 0,
                    "memory_used_mb": 256,
                    "memory_total_mb": 16384,
                    "compute_apps": [],
                },
                {
                    "index": 5,
                    "utilization": 92,
                    "memory_used_mb": 12000,
                    "memory_total_mb": 16384,
                    "compute_apps": [{"pid": 123, "process_name": "python"}],
                },
            ],
        )

        exp_dir = run_dir / "stage-10" / "experiment"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "main.py").write_text(
            "from datasets import load_dataset\nload_dataset('json', data_files='dummy.jsonl')\nprint('hello')\n",
            encoding="utf-8",
        )
        stage11_dir = run_dir / "stage-11"
        stage11_dir.mkdir(parents=True, exist_ok=True)
        (stage11_dir / "schedule.json").write_text(
            json.dumps({"execution_strategy": "single_gpu_serial", "gpu_wait_policy": "wait_for_idle_gpu_0_6", "total_gpu_budget": 1}),
            encoding="utf-8",
        )

        stage_dir = run_dir / "stage-12"
        stage_dir.mkdir(parents=True, exist_ok=True)
        result = rc_executor._execute_experiment_run(stage_dir, run_dir, cfg, adapters)

        assert result.status == StageStatus.FAILED
        observer = json.loads((stage_dir / "runtime_observer.json").read_text(encoding="utf-8"))
        assert observer["status"] == "failed"
        assert observer["preflight"]["ok"] is False
        assert observer["preflight"]["errors"]
        assert observer["runtime_outcome"]["failure_type"] in {"dataset_prep", "config_mismatch"}
        assert observer["dataset_readiness"]["status"] == "blocked"
        assert observer["dataset_readiness"]["uses_huggingface_datasets"] is True
        assert observer["gpu_availability"]["status"] == "ready"
        assert observer["gpu_availability"]["idle_gpu_ids"] == [4]
        assert observer["runtime_watchdog"]["status"] == "failed"


class TestTimeoutAwareRefine:
    """Test timeout-aware prompt injection in iterative refine (R4-1b)."""

    def _prepare_timed_out_run(self, run_dir: Path) -> None:
        """Create a prior run that timed out with no metrics."""
        runs_dir = run_dir / "stage-12" / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        (runs_dir / "run-1.json").write_text(
            json.dumps({
                "run_id": "run-1",
                "task_id": "sandbox-main",
                "status": "failed",
                "metrics": {},
                "timed_out": True,
                "elapsed_sec": 120.0,
            }),
            encoding="utf-8",
        )
        # Write experiment code
        exp_dir = run_dir / "stage-11" / "experiment"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "main.py").write_text(
            "print('best_loss: 0.1')\n",
            encoding="utf-8",
        )

    def test_timeout_refine_injects_scale_reduction_prompt(
        self, tmp_path: Path, run_dir: Path, adapters: AdapterBundle
    ) -> None:
        self._prepare_timed_out_run(run_dir)
        stage_dir = run_dir / "stage-13"
        stage_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "project": {"name": "rc-test", "mode": "docs-first"},
            "research": {
                "topic": "test topic",
                "domains": ["ml"],
                "daily_paper_count": 2,
                "quality_threshold": 8.2,
            },
            "runtime": {"timezone": "UTC"},
            "notifications": {
                "channel": "local",
                "on_stage_start": True,
                "on_stage_fail": False,
                "on_gate_required": True,
            },
            "knowledge_base": {"backend": "markdown", "root": str(tmp_path / "kb")},
            "openclaw_bridge": {"use_memory": True, "use_message": True},
            "llm": {
                "provider": "openai-compatible",
                "base_url": "http://localhost:1234/v1",
                "api_key_env": "RC_TEST_KEY",
                "api_key": "inline-test-key",
                "primary_model": "fake-model",
                "fallback_models": [],
            },
            "security": {"hitl_required_stages": [5, 9, 20]},
            "experiment": {
                "mode": "sandbox",
                "time_budget_sec": 120,
                "max_iterations": 1,
                "metric_key": "best_loss",
                "metric_direction": "minimize",
            },
        }
        cfg = RCConfig.from_dict(data, project_root=tmp_path, check_paths=False)

        llm = FakeLLMClient(
            "```python\nimport numpy as np\nprint('best_loss: 0.1')\n```"
        )

        rc_executor._execute_iterative_refine(
            stage_dir, run_dir, cfg, adapters, llm=llm
        )

        # The LLM should have received the timeout-aware prompt
        assert len(llm.calls) >= 1
        user_msg = llm.calls[0][-1]["content"]
        assert "TIMED OUT" in user_msg
        assert "120" in user_msg

    def test_refine_uses_structured_diagnostic_bundle(
        self, tmp_path: Path, run_dir: Path, adapters: AdapterBundle
    ) -> None:
        self._prepare_timed_out_run(run_dir)
        stage12_dir = run_dir / "stage-12"
        (stage12_dir / "runtime_observer.json").write_text(
            json.dumps(
                {
                    "status": "failed",
                    "resource_plan": {
                        "execution_strategy": "single_gpu_serial",
                        "gpu_wait_policy": "wait_for_idle_gpu_0_6",
                    },
                    "preflight": {"ok": True, "errors": [], "warnings": []},
                    "runtime_outcome": {
                        "status": "failed",
                        "failure_type": "dataset_prep",
                        "retryable": True,
                        "timed_out": True,
                    },
                }
            ),
            encoding="utf-8",
        )
        _write_prior_artifact(
            run_dir,
            11,
            "exp_plan.yaml",
            "conditions:\n  - baseline\n  - proposed\n",
        )
        stage_dir = run_dir / "stage-13"
        stage_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "project": {"name": "rc-test", "mode": "docs-first"},
            "research": {"topic": "test topic", "domains": ["ml"]},
            "runtime": {"timezone": "UTC"},
            "notifications": {"channel": "local"},
            "knowledge_base": {"backend": "markdown", "root": str(tmp_path / "kb")},
            "openclaw_bridge": {"use_memory": False, "use_message": False},
            "llm": {
                "provider": "openai-compatible",
                "base_url": "http://localhost:1234/v1",
                "api_key_env": "RC_TEST_KEY",
                "api_key": "inline-test-key",
                "primary_model": "fake-model",
            },
            "experiment": {
                "mode": "sandbox",
                "time_budget_sec": 120,
                "max_iterations": 1,
                "metric_key": "best_loss",
                "metric_direction": "minimize",
            },
        }
        cfg = RCConfig.from_dict(data, project_root=tmp_path, check_paths=False)
        llm = FakeLLMClient("```python\nprint('best_loss: 0.1')\n```")

        result = rc_executor._execute_iterative_refine(
            stage_dir, run_dir, cfg, adapters, llm=llm
        )

        bundle = json.loads(
            (stage_dir / "refine_diagnostic_bundle.json").read_text(encoding="utf-8")
        )
        assert bundle["aggregates"]["dominant_failure_types"] == ["dataset_prep"]
        assert bundle["aggregates"]["dataset_observer_status"] == ""
        assert bundle["aggregates"]["gpu_observer_status"] == ""
        assert bundle["aggregates"]["watchdog_status"] == ""
        assert bundle["runtime_observer"]["runtime_outcome"]["retryable"] is True
        assert "refine_diagnostic_bundle.json" in result.artifacts
        assert "Dominant failure types: dataset_prep" in llm.calls[0][-1]["content"]


# ── R4-2: Data Integrity Enforcement Tests ───────────────────────────


class TestDataIntegrityBlock:
    """Test paper draft blocked when no metrics exist (R4-2a)."""

    def test_paper_draft_blocked_with_no_metrics(
        self, tmp_path: Path, run_dir: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        # Write prior artifacts with NO metrics
        _write_prior_artifact(run_dir, 16, "outline.md", "# Outline\n## Abstract\n")
        # No experiment_summary.json, no run files with metrics
        runs_dir = run_dir / "stage-12" / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        (runs_dir / "run-1.json").write_text(
            json.dumps({"run_id": "run-1", "status": "failed", "metrics": {}, "timed_out": True}),
            encoding="utf-8",
        )

        stage_dir = run_dir / "stage-17"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = FakeLLMClient("should not be called")
        result = rc_executor._execute_paper_draft(
            stage_dir, run_dir, rc_config, adapters, llm=llm
        )

        assert result.status == StageStatus.FAILED
        draft = (stage_dir / "paper_draft.md").read_text(encoding="utf-8")
        assert "Blocked" in draft or "BLOCKED" in draft or "no metrics" in draft.lower()
        # LLM should NOT have been called
        assert len(llm.calls) == 0

    def test_paper_draft_proceeds_with_metrics(
        self, tmp_path: Path, run_dir: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        _write_prior_artifact(run_dir, 16, "outline.md", "# Outline\n## Abstract\n")
        # Write experiment data with real metrics
        runs_dir = run_dir / "stage-12" / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        (runs_dir / "run-1.json").write_text(
            json.dumps({
                "run_id": "run-1",
                "status": "completed",
                "metrics": {"best_loss": 0.123},
                "stdout": "best_loss: 0.123\n",
            }),
            encoding="utf-8",
        )

        stage_dir = run_dir / "stage-17"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = FakeLLMClient("# Paper Title\n## Abstract\nSome abstract text.")
        result = rc_executor._execute_paper_draft(
            stage_dir, run_dir, rc_config, adapters, llm=llm
        )

        # Should proceed (LLM was called)
        assert len(llm.calls) >= 1
        # The prompt should contain anti-fabrication instructions
        all_prompts = " ".join(
            msg["content"] for call in llm.calls for msg in call
        )
        assert "Data Integrity" in all_prompts or "ONLY report numbers" in all_prompts


# ── R4-3: Conference-Grade Title Guidelines Tests ────────────────────


class TestTitleGuidelines:
    """Test title_guidelines and abstract_structure blocks (R4-3)."""

    def test_title_guidelines_block_exists(self) -> None:
        from researchclaw.prompts import PromptManager

        pm = PromptManager()
        block = pm.block("title_guidelines")
        assert "novelty" in block.lower() or "TITLE RULES" in block
        assert "14 words" in block or "15 words" in block or "concrete" in block.lower()

    def test_abstract_structure_block_exists(self) -> None:
        from researchclaw.prompts import PromptManager

        pm = PromptManager()
        block = pm.block("abstract_structure")
        assert "5-sentence" in block or "problem" in block.lower()

    def test_title_guidelines_injected_into_paper_draft(
        self, tmp_path: Path, run_dir: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        _write_prior_artifact(run_dir, 16, "outline.md", "# Outline\n")
        runs_dir = run_dir / "stage-12" / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        (runs_dir / "run-1.json").write_text(
            json.dumps({"run_id": "run-1", "status": "completed",
                        "metrics": {"best_loss": 0.1}, "stdout": "best_loss: 0.1\n"}),
            encoding="utf-8",
        )

        stage_dir = run_dir / "stage-17"
        stage_dir.mkdir(parents=True, exist_ok=True)

        llm = FakeLLMClient("# Paper Title\n## Abstract\nText.")
        rc_executor._execute_paper_draft(
            stage_dir, run_dir, rc_config, adapters, llm=llm
        )

        all_prompts = " ".join(
            msg["content"] for call in llm.calls for msg in call
        )
        assert "Title" in all_prompts or "TITLE" in all_prompts

    def test_paper_outline_prompt_includes_claims_from_results(
        self, run_dir: Path, rc_config: RCConfig, adapters: AdapterBundle
    ) -> None:
        _write_prior_artifact(run_dir, 2, "problem_anchor.md", "# Problem Anchor\nAnchor text.")
        _write_prior_artifact(run_dir, 14, "analysis.md", "# Analysis\nResults look solid.")
        _write_prior_artifact(run_dir, 15, "decision.md", "## Decision\nPROCEED")
        _write_prior_artifact(run_dir, 15, "claims_from_results.md", "# Claims From Results\n- Supported claim text.")
        _write_prior_artifact(run_dir, 9, "claims_evidence_matrix.md", "# Claims-Evidence Matrix\n- Matrix row.")
        stage_dir = run_dir / "stage-16"
        stage_dir.mkdir(parents=True, exist_ok=True)
        llm = FakeLLMClient("# Outline\n")

        rc_executor._execute_paper_outline(
            stage_dir, run_dir, rc_config, adapters, llm=llm
        )

        all_prompts = " ".join(msg["content"] for call in llm.calls for msg in call)
        assert "Supported claim text." in all_prompts


# ── R4-4: Conference-Grade Writing Quality Tests ─────────────────────


class TestConferenceWritingQuality:
    """Test enhanced writing prompts and writing_guide.py (R4-4)."""

    def test_writing_guide_format_all(self) -> None:
        from researchclaw.writing_guide import format_writing_tips

        result = format_writing_tips()
        assert "Conference Writing Best Practices" in result
        assert "Title" in result
        assert "Common Rejections" in result

    def test_writing_guide_format_subset(self) -> None:
        from researchclaw.writing_guide import format_writing_tips

        result = format_writing_tips(["title", "abstract"])
        assert "Title" in result
        assert "Abstract" in result
        assert "Common Rejections" not in result

    def test_paper_draft_system_includes_principles(self) -> None:
        from researchclaw.prompts import PromptManager

        pm = PromptManager()
        sp = pm.for_stage(
            "paper_draft",
            preamble="test",
            topic_constraint="test",
            exp_metrics_instruction="test",
            citation_instruction="test",
            outline="test",
        )
        # System prompt should mention key principles
        assert "NOVELTY" in sp.system or "novelty" in sp.system.lower()
        assert "fabricate" in sp.system.lower() or "real experimental" in sp.system.lower()


# ── R5-1 & R5-2: Bug Fixes Tests ────────────────────────────────────


class TestRefineTimeoutAndIterationCap:
    """Test R5-1 (no 120s cap) and R5-2 (iteration cap raised to 10)."""

    def test_refine_timeout_uses_full_budget(self) -> None:
        """R5-1: Refine sandbox should NOT cap at 120s."""
        import ast
        import inspect

        source = inspect.getsource(rc_executor._execute_iterative_refine)
        tree = ast.parse(source)
        source_text = inspect.getsource(rc_executor._execute_iterative_refine)
        # Should NOT contain min(..., 120)
        assert "min(config.experiment.time_budget_sec, 120)" not in source_text

    def test_iteration_cap_is_10(self) -> None:
        """R5-2: Max iterations should be capped at 10, not 3."""
        import inspect

        source = inspect.getsource(rc_executor._execute_iterative_refine)
        assert "min(requested_iterations, 10)" in source
        assert "min(requested_iterations, 3)" not in source

    def test_refine_respects_high_iteration_count(
        self, tmp_path: Path, run_dir: Path, adapters: AdapterBundle
    ) -> None:
        """R5-2: Setting max_iterations=7 should actually allow 7 iterations."""
        # Write prior run artifacts
        runs_dir = run_dir / "stage-12" / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        (runs_dir / "run-1.json").write_text(
            json.dumps({"run_id": "run-1", "status": "completed",
                        "metrics": {"best_loss": 0.5}}),
            encoding="utf-8",
        )
        exp_dir = run_dir / "stage-11" / "experiment"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "main.py").write_text("print('best_loss: 0.5')\n", encoding="utf-8")

        stage_dir = run_dir / "stage-13"
        stage_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "project": {"name": "rc-test", "mode": "docs-first"},
            "research": {"topic": "test", "domains": ["ml"],
                         "daily_paper_count": 2, "quality_threshold": 8.2},
            "runtime": {"timezone": "UTC"},
            "notifications": {"channel": "local", "on_stage_start": True,
                              "on_stage_fail": False, "on_gate_required": True},
            "knowledge_base": {"backend": "markdown", "root": str(tmp_path / "kb")},
            "openclaw_bridge": {"use_memory": True, "use_message": True},
            "llm": {"provider": "openai-compatible", "base_url": "http://localhost:1234/v1",
                    "api_key_env": "RC_TEST_KEY", "api_key": "inline-test-key",
                    "primary_model": "fake-model", "fallback_models": []},
            "security": {"hitl_required_stages": [5, 9, 20]},
            "experiment": {
                "mode": "sandbox",
                "time_budget_sec": 300,
                "max_iterations": 7,
                "metric_key": "best_loss",
                "metric_direction": "minimize",
            },
        }
        cfg = RCConfig.from_dict(data, project_root=tmp_path, check_paths=False)

        # LLM always returns same code — will trigger no_improvement early stop
        llm = FakeLLMClient("```python\nprint('best_loss: 0.5')\n```")

        rc_executor._execute_iterative_refine(
            stage_dir, run_dir, cfg, adapters, llm=llm
        )

        log = json.loads((stage_dir / "refinement_log.json").read_text(encoding="utf-8"))
        # Should have been allowed more than 3 iterations (capped at 7)
        assert log["max_iterations_executed"] == 7
        # But may have stopped early due to no_improvement_for_2_iterations
        assert len(log["iterations"]) >= 2


# ── R5-3: NaN/Divergence Fast-Fail Tests ────────────────────────────


class TestNaNDivergenceDetection:
    """Test NaN/Inf filtering and divergence detection (R5-3)."""

    def test_parse_metrics_filters_nan(self) -> None:
        from researchclaw.experiment.sandbox import parse_metrics

        stdout = "best_loss: 0.5\nbad_metric: nan\ngood_metric: 1.23\n"
        metrics = parse_metrics(stdout)
        assert "best_loss" in metrics
        assert "good_metric" in metrics
        assert "bad_metric" not in metrics  # NaN should be filtered

    def test_parse_metrics_filters_inf(self) -> None:
        from researchclaw.experiment.sandbox import parse_metrics

        stdout = "metric_a: inf\nmetric_b: -inf\nmetric_c: 0.42\n"
        metrics = parse_metrics(stdout)
        assert "metric_c" in metrics
        assert "metric_a" not in metrics
        assert "metric_b" not in metrics

    def test_detect_nan_divergence_finds_nan(self) -> None:
        from researchclaw.experiment.sandbox import detect_nan_divergence

        result = detect_nan_divergence("loss: nan\nstep 5 done", "")
        assert result is not None
        assert "NaN" in result or "nan" in result.lower()

    def test_detect_nan_divergence_finds_diverging_loss(self) -> None:
        from researchclaw.experiment.sandbox import detect_nan_divergence

        result = detect_nan_divergence("best_loss: 999.5\n", "")
        assert result is not None
        assert "loss" in result.lower() or "999" in result

    def test_detect_nan_divergence_returns_none_for_clean(self) -> None:
        from researchclaw.experiment.sandbox import detect_nan_divergence

        result = detect_nan_divergence("best_loss: 0.123\naccuracy: 0.95\n", "")
        assert result is None

    def test_runtime_issues_detects_diverging_loss(self) -> None:
        from types import SimpleNamespace

        fake_result = SimpleNamespace(
            metrics={"best_loss": 500.0},
            stdout="best_loss: 500.0\n",
            stderr="",
        )
        issues = rc_executor._detect_runtime_issues(fake_result)
        assert "DIVERGING" in issues or "diverging" in issues.lower()

    def test_compute_budget_includes_nan_guard(self) -> None:
        from researchclaw.prompts import PromptManager

        pm = PromptManager()
        block = pm.block("compute_budget")
        assert "NaN" in block or "nan" in block.lower() or "divergence" in block.lower()


# ── R5-4: Experiment Harness Template Tests ──────────────────────────


class TestExperimentHarness:
    """Test the immutable experiment harness (R5-4)."""

    def test_harness_should_stop(self) -> None:
        from researchclaw.experiment.harness_template import ExperimentHarness

        h = ExperimentHarness(time_budget=1)
        assert not h.should_stop()
        import time
        time.sleep(0.9)
        assert not h.should_stop()

    def test_harness_report_metric(self, capsys: pytest.CaptureFixture[str]) -> None:
        from researchclaw.experiment.harness_template import ExperimentHarness

        h = ExperimentHarness(time_budget=60)
        h.report_metric("best_loss", 0.123)
        captured = capsys.readouterr()
        assert "best_loss: 0.123" in captured.out
        assert h._metrics["best_loss"] == 0.123

    def test_harness_rejects_nan(self, capsys: pytest.CaptureFixture[str]) -> None:
        from researchclaw.experiment.harness_template import ExperimentHarness

        h = ExperimentHarness(time_budget=60)
        h.report_metric("bad", float("nan"))
        captured = capsys.readouterr()
        assert "bad" not in h._metrics
        assert "non-finite" in captured.err.lower() or "WARNING" in captured.err

    def test_harness_rejects_inf(self, capsys: pytest.CaptureFixture[str]) -> None:
        from researchclaw.experiment.harness_template import ExperimentHarness

        h = ExperimentHarness(time_budget=60)
        h.report_metric("bad", float("inf"))
        assert "bad" not in h._metrics

    def test_harness_finalize(self, tmp_path: Path) -> None:
        import os
        from researchclaw.experiment.harness_template import ExperimentHarness

        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            h = ExperimentHarness(time_budget=60)
            h.report_metric("accuracy", 0.95)
            h.report_metric("loss", 0.05)
            h.log_result({"condition": "A", "value": 1.0})
            partial = json.loads((tmp_path / "partial_results.json").read_text(encoding="utf-8"))
            assert partial["status"] == "partial"
            assert partial["completed_seed_count"] == 1
            h.finalize()

            results = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
            assert results["status"] == "completed"
            assert results["metrics"]["accuracy"] == 0.95
            assert results["metrics"]["loss"] == 0.05
            assert len(results["results"]) == 1
        finally:
            os.chdir(old_cwd)

    def test_harness_progress(self) -> None:
        from researchclaw.experiment.harness_template import ExperimentHarness

        h = ExperimentHarness(time_budget=1000)
        assert h.progress < 0.01  # Just started
        assert 0.0 <= h.progress <= 1.0

    def test_harness_injected_into_sandbox(self, tmp_path: Path) -> None:
        import sys
        from researchclaw.config import SandboxConfig
        from researchclaw.experiment.sandbox import ExperimentSandbox

        config = SandboxConfig(python_path=sys.executable)
        sandbox = ExperimentSandbox(config, tmp_path / "sandbox")

        # Create a project dir
        project = tmp_path / "project"
        project.mkdir()
        (project / "main.py").write_text("print('test: 1.0')\n", encoding="utf-8")

        sandbox.run_project(project, timeout_sec=5)

        # Check that harness was injected (BUG-DA8-06: dir is now _project_{N})
        project_dirs = list((tmp_path / "sandbox").glob("_project_*"))
        assert project_dirs, "No _project_N directory found"
        harness_path = project_dirs[0] / "experiment_harness.py"
        assert harness_path.exists()
        content = harness_path.read_text(encoding="utf-8")
        assert "ExperimentHarness" in content

    def test_harness_not_overwritten_by_project(self, tmp_path: Path) -> None:
        import sys
        from researchclaw.config import SandboxConfig
        from researchclaw.experiment.sandbox import ExperimentSandbox

        config = SandboxConfig(python_path=sys.executable)
        sandbox = ExperimentSandbox(config, tmp_path / "sandbox")

        # Create a project with a fake experiment_harness.py
        project = tmp_path / "project"
        project.mkdir()
        (project / "main.py").write_text("print('test: 1.0')\n", encoding="utf-8")
        (project / "experiment_harness.py").write_text("# FAKE HARNESS", encoding="utf-8")

        sandbox.run_project(project, timeout_sec=5)

        # The real harness should be there, not the fake one (BUG-DA8-06)
        project_dirs = list((tmp_path / "sandbox").glob("_project_*"))
        assert project_dirs
        harness_path = project_dirs[0] / "experiment_harness.py"
        content = harness_path.read_text(encoding="utf-8")
        assert "ExperimentHarness" in content
        assert "FAKE HARNESS" not in content

    def test_prompt_mentions_harness(self) -> None:
        from researchclaw.prompts import PromptManager

        pm = PromptManager()
        block = pm.block("compute_budget")
        assert "experiment_harness" in block or "ExperimentHarness" in block


# ── R5-5: Stdout Truncation Tests ────────────────────────────────────


class TestStdoutTruncation:
    """Test stdout/stderr truncation in refine run summaries (R5-5)."""

    def test_long_stdout_truncated_in_refine(
        self, tmp_path: Path, run_dir: Path, adapters: AdapterBundle
    ) -> None:
        # Create a run with very long stdout
        runs_dir = run_dir / "stage-12" / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        long_stdout = "\n".join(f"step {i}: loss={0.5 - i * 0.001:.6f}" for i in range(200))
        (runs_dir / "run-1.json").write_text(
            json.dumps({
                "run_id": "run-1",
                "status": "completed",
                "metrics": {"best_loss": 0.3},
                "stdout": long_stdout,
            }),
            encoding="utf-8",
        )

        exp_dir = run_dir / "stage-11" / "experiment"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "main.py").write_text("print('best_loss: 0.3')\n", encoding="utf-8")

        stage_dir = run_dir / "stage-13"
        stage_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "project": {"name": "rc-test", "mode": "docs-first"},
            "research": {"topic": "test", "domains": ["ml"],
                         "daily_paper_count": 2, "quality_threshold": 8.2},
            "runtime": {"timezone": "UTC"},
            "notifications": {"channel": "local", "on_stage_start": True,
                              "on_stage_fail": False, "on_gate_required": True},
            "knowledge_base": {"backend": "markdown", "root": str(tmp_path / "kb")},
            "openclaw_bridge": {"use_memory": True, "use_message": True},
            "llm": {"provider": "openai-compatible", "base_url": "http://localhost:1234/v1",
                    "api_key_env": "RC_TEST_KEY", "api_key": "inline-test-key",
                    "primary_model": "fake-model", "fallback_models": []},
            "security": {"hitl_required_stages": [5, 9, 20]},
            "experiment": {
                "mode": "sandbox",
                "time_budget_sec": 30,
                "max_iterations": 1,
                "metric_key": "best_loss",
                "metric_direction": "minimize",
            },
        }
        cfg = RCConfig.from_dict(data, project_root=tmp_path, check_paths=False)

        llm = FakeLLMClient("```python\nprint('best_loss: 0.3')\n```")
        rc_executor._execute_iterative_refine(
            stage_dir, run_dir, cfg, adapters, llm=llm
        )

        # The LLM should have received truncated stdout, not all 200 lines
        assert len(llm.calls) >= 1
        user_msg = llm.calls[0][-1]["content"]
        # Should contain truncation indicator
        assert "truncated" in user_msg or len(user_msg) < len(long_stdout)


# ===================================================================
# R6 Tests — Post-E2E Failure Analysis Fixes
# ===================================================================


class TestNoImproveStreakFix:
    """R6-1: no_improve_streak should only count iterations with real metrics."""

    def test_empty_metrics_dont_increment_streak(
        self, tmp_path: Path, run_dir: Path, adapters: AdapterBundle
    ) -> None:
        """When metrics are empty (None), the streak should NOT increment."""
        runs_dir = run_dir / "stage-12" / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        (runs_dir / "run-1.json").write_text(
            json.dumps({
                "run_id": "run-1",
                "status": "failed",
                "metrics": {},
                "stdout": "FAIL: NaN/divergence detected",
            }),
            encoding="utf-8",
        )
        exp_dir = run_dir / "stage-11" / "experiment"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "main.py").write_text("print('hello')\n", encoding="utf-8")

        stage_dir = run_dir / "stage-13"
        stage_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "project": {"name": "rc-test", "mode": "docs-first"},
            "research": {"topic": "test", "domains": ["ml"],
                         "daily_paper_count": 2, "quality_threshold": 8.2},
            "runtime": {"timezone": "UTC"},
            "notifications": {"channel": "local", "on_stage_start": True,
                              "on_stage_fail": False, "on_gate_required": True},
            "knowledge_base": {"backend": "markdown", "root": str(tmp_path / "kb")},
            "openclaw_bridge": {"use_memory": True, "use_message": True},
            "llm": {"provider": "openai-compatible", "base_url": "http://localhost:1234/v1",
                    "api_key_env": "RC_TEST_KEY", "api_key": "inline-test-key",
                    "primary_model": "fake-model", "fallback_models": []},
            "security": {"hitl_required_stages": [5, 9, 20]},
            "experiment": {
                "mode": "sandbox",
                "time_budget_sec": 30,
                "max_iterations": 4,
                "metric_key": "primary_metric",
                "metric_direction": "minimize",
            },
        }
        cfg = RCConfig.from_dict(data, project_root=tmp_path, check_paths=False)

        # LLM returns code that won't produce metrics in simulated mode
        llm = FakeLLMClient("```python\nprint('no metrics here')\n```")
        result = rc_executor._execute_iterative_refine(
            stage_dir, run_dir, cfg, adapters, llm=llm
        )

        # Should abort after 3 consecutive no-metrics iterations
        log_path = stage_dir / "refinement_log.json"
        log_data = json.loads(log_path.read_text())
        # consecutive_no_metrics triggers early abort after 3 iterations
        assert len(log_data["iterations"]) == 3
        assert log_data.get("stop_reason") == "consecutive_no_metrics"


class TestStdoutFailureDetection:
    """R6-2: Detect stdout failure signals even when exit code is 0."""

    def test_fail_signal_in_stdout_marks_failed(self, tmp_path: Path) -> None:
        """Exit code 0 + 'FAIL:' in stdout + no metrics → status='failed'."""
        from researchclaw.pipeline.executor import _execute_experiment_run

        # Create necessary structure
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "stage-10").mkdir()
        exp_dir = run_dir / "stage-10" / "experiment"
        exp_dir.mkdir()
        # Simple code that prints FAIL but exits 0
        (exp_dir / "main.py").write_text(
            "print('FAIL: NaN/divergence detected')\n", encoding="utf-8"
        )
        (run_dir / "stage-11").mkdir()
        (run_dir / "stage-11" / "schedule.json").write_text("{}", encoding="utf-8")

        stage_dir = run_dir / "stage-12"
        stage_dir.mkdir()

        data = {
            "project": {"name": "rc-test", "mode": "docs-first"},
            "research": {"topic": "test", "domains": ["ml"],
                         "daily_paper_count": 2, "quality_threshold": 8.2},
            "runtime": {"timezone": "UTC"},
            "notifications": {"channel": "local", "on_stage_start": True,
                              "on_stage_fail": False, "on_gate_required": True},
            "knowledge_base": {"backend": "markdown", "root": str(tmp_path / "kb")},
            "openclaw_bridge": {"use_memory": True, "use_message": True},
            "llm": {"provider": "openai-compatible", "base_url": "http://localhost:1234/v1",
                    "api_key_env": "RC_TEST_KEY", "api_key": "inline-test-key",
                    "primary_model": "fake-model", "fallback_models": []},
            "security": {"hitl_required_stages": [5, 9, 20]},
            "experiment": {
                "mode": "sandbox",
                "time_budget_sec": 30,
                "max_iterations": 1,
                "metric_key": "primary_metric",
                "metric_direction": "minimize",
                "sandbox": {
                    "python_path": sys.executable,
                    "gpu_required": False,
                    "max_memory_mb": 512,
                    "allowed_imports": ["json"],
                },
            },
        }
        cfg = RCConfig.from_dict(data, project_root=tmp_path, check_paths=False)
        adapters = AdapterBundle()

        result = _execute_experiment_run(
            stage_dir, run_dir, cfg, adapters
        )

        # Check the run payload
        runs_dir = stage_dir / "runs"
        run_file = runs_dir / "run-1.json"
        assert run_file.exists()
        payload = json.loads(run_file.read_text())
        assert payload["status"] == "failed"

    def test_clean_exit_no_fail_signal_marks_completed(self, tmp_path: Path) -> None:
        """Exit code 0 + valid metrics + no FAIL signal → status='completed'."""
        from researchclaw.pipeline.executor import _execute_experiment_run

        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "stage-10").mkdir()
        exp_dir = run_dir / "stage-10" / "experiment"
        exp_dir.mkdir()
        (exp_dir / "main.py").write_text(
            "print('primary_metric: 0.95')\n", encoding="utf-8"
        )
        (run_dir / "stage-11").mkdir()
        (run_dir / "stage-11" / "schedule.json").write_text("{}", encoding="utf-8")

        stage_dir = run_dir / "stage-12"
        stage_dir.mkdir()

        data = {
            "project": {"name": "rc-test", "mode": "docs-first"},
            "research": {"topic": "test", "domains": ["ml"],
                         "daily_paper_count": 2, "quality_threshold": 8.2},
            "runtime": {"timezone": "UTC"},
            "notifications": {"channel": "local", "on_stage_start": True,
                              "on_stage_fail": False, "on_gate_required": True},
            "knowledge_base": {"backend": "markdown", "root": str(tmp_path / "kb")},
            "openclaw_bridge": {"use_memory": True, "use_message": True},
            "llm": {"provider": "openai-compatible", "base_url": "http://localhost:1234/v1",
                    "api_key_env": "RC_TEST_KEY", "api_key": "inline-test-key",
                    "primary_model": "fake-model", "fallback_models": []},
            "security": {"hitl_required_stages": [5, 9, 20]},
            "experiment": {
                "mode": "sandbox",
                "time_budget_sec": 30,
                "max_iterations": 1,
                "metric_key": "primary_metric",
                "metric_direction": "minimize",
                "sandbox": {
                    "python_path": sys.executable,
                    "gpu_required": False,
                    "max_memory_mb": 512,
                    "allowed_imports": ["json"],
                },
            },
        }
        cfg = RCConfig.from_dict(data, project_root=tmp_path, check_paths=False)
        adapters = AdapterBundle()

        result = _execute_experiment_run(
            stage_dir, run_dir, cfg, adapters
        )

        runs_dir = stage_dir / "runs"
        payload = json.loads((runs_dir / "run-1.json").read_text())
        assert payload["status"] == "completed"


class TestMetricValUndefined:
    """R6-3: metric_val should be initialized to None before conditional block."""

    def test_metric_val_initialized_before_use(self) -> None:
        """Verify the code pattern: metric_val = None before if block."""
        import inspect
        source = inspect.getsource(rc_executor._execute_iterative_refine)
        # Find that metric_val = None appears before the sandbox block
        init_pos = source.find("metric_val = None")
        sandbox_pos = source.find("if validation.ok and config.experiment.mode")
        assert init_pos != -1, "metric_val = None not found"
        assert sandbox_pos != -1, "sandbox block not found"
        assert init_pos < sandbox_pos, "metric_val = None should come before sandbox block"


class TestConsecutiveEmptyMetrics:
    """R6-4: Pipeline should detect consecutive empty-metrics REFINE cycles."""

    def test_detects_consecutive_empty(self, tmp_path: Path) -> None:
        """Two cycles with empty metrics should return True."""
        from researchclaw.pipeline.runner import _consecutive_empty_metrics

        run_dir = tmp_path / "run"
        # Current cycle (stage-14)
        s14 = run_dir / "stage-14"
        s14.mkdir(parents=True)
        (s14 / "experiment_summary.json").write_text(json.dumps({
            "metrics_summary": {},
            "best_run": {"metrics": {}},
        }))
        # Previous cycle (stage-14_v1)
        s14v1 = run_dir / "stage-14_v1"
        s14v1.mkdir(parents=True)
        (s14v1 / "experiment_summary.json").write_text(json.dumps({
            "metrics_summary": {},
            "best_run": {"metrics": {}},
        }))

        assert _consecutive_empty_metrics(run_dir, pivot_count=1) is True

    def test_not_empty_when_metrics_exist(self, tmp_path: Path) -> None:
        """If any cycle has real metrics, return False."""
        from researchclaw.pipeline.runner import _consecutive_empty_metrics

        run_dir = tmp_path / "run"
        s14 = run_dir / "stage-14"
        s14.mkdir(parents=True)
        (s14 / "experiment_summary.json").write_text(json.dumps({
            "metrics_summary": {},
            "best_run": {"metrics": {"loss": 0.5}},
        }))
        s14v1 = run_dir / "stage-14_v1"
        s14v1.mkdir(parents=True)
        (s14v1 / "experiment_summary.json").write_text(json.dumps({
            "metrics_summary": {},
            "best_run": {"metrics": {}},
        }))

        assert _consecutive_empty_metrics(run_dir, pivot_count=1) is False

    def test_false_when_no_previous_cycle(self, tmp_path: Path) -> None:
        """First cycle (no v1) should return False."""
        from researchclaw.pipeline.runner import _consecutive_empty_metrics

        run_dir = tmp_path / "run"
        s14 = run_dir / "stage-14"
        s14.mkdir(parents=True)
        (s14 / "experiment_summary.json").write_text(json.dumps({
            "metrics_summary": {},
            "best_run": {"metrics": {}},
        }))

        # No stage-14_v1 exists
        assert _consecutive_empty_metrics(run_dir, pivot_count=1) is False

    def test_low_yield_refine_is_not_applied_to_new_falcon_activation_target(
        self, tmp_path: Path
    ) -> None:
        from researchclaw.pipeline.runner import _recent_low_yield_refine

        run_dir = tmp_path / "run"
        for dirname, metric in [
            ("stage-14_v3", 0.1900),
            ("stage-14_v4", 0.1901),
            ("stage-14", 0.1902),
        ]:
            stage_dir = run_dir / dirname
            stage_dir.mkdir(parents=True)
            (stage_dir / "experiment_summary.json").write_text(
                json.dumps(
                    {
                        "metric_key": "primary_metric",
                        "metrics_summary": {"primary_metric": {"mean": metric}},
                    }
                ),
                encoding="utf-8",
            )
        stage15_dir = run_dir / "stage-15"
        stage15_dir.mkdir(parents=True)
        (stage15_dir / "decision_structured.json").write_text(
            json.dumps({"decision": "refine"}),
            encoding="utf-8",
        )
        (stage15_dir / "phase2_handoff.md").write_text(
            (
                "**REFINE**\n\n"
                "New target override: use `falcon_qb_activation_rank` as the "
                "primary practical method and run strict H1 matched-budget "
                "factorization experiments."
            ),
            encoding="utf-8",
        )

        assert _recent_low_yield_refine(run_dir) == (False, "")


# ===================================================================
# R7 Tests — Experiment-Paper Quality Alignment
# ===================================================================


class TestMultiConditionEnforcement:
    """R7-1: Code generation prompt must enforce multi-condition experiments."""

    def test_code_generation_prompt_has_multi_condition_block(self) -> None:
        """The code_generation prompt should contain multi-condition instructions."""
        from researchclaw.prompts import PromptManager
        pm = PromptManager()
        sp = pm.for_stage(
            "code_generation",
            topic="test topic",
            metric="primary_metric",
            pkg_hint="",
            exp_plan="conditions:\n  - echo_chamber\n  - bridge_building\n  - random",
        )
        assert "MULTI-CONDITION REQUIREMENT" in sp.user
        assert "condition=" in sp.user
        assert "SUMMARY" in sp.user

    def test_multi_condition_labels_required(self) -> None:
        """Prompt must mention per-condition labeled output format."""
        from researchclaw.prompts import PromptManager
        pm = PromptManager()
        sp = pm.for_stage(
            "code_generation",
            topic="test",
            metric="loss",
            pkg_hint="",
            exp_plan="treatments: [A, B, C]",
        )
        assert "condition=<name>" in sp.user


class TestEvidenceBoundedWriting:
    """R7-2: Paper draft prompt must enforce evidence-bounded claims."""

    def test_paper_draft_has_evidence_bounding_rules(self) -> None:
        """System prompt should contain evidence-bounding rules."""
        from researchclaw.prompts import PromptManager
        pm = PromptManager()
        sp = pm.for_stage(
            "paper_draft",
            preamble="test preamble",
            topic_constraint="",
            exp_metrics_instruction="",
            citation_instruction="",
            outline="# Outline",
        )
        assert "EVIDENCE-BOUNDING RULES" in sp.system
        assert "title" in sp.system.lower()
        assert "causal claim" in sp.system.lower() or "causal claims" in sp.system.lower()

    def test_hedging_language_guidance(self) -> None:
        """Should suggest hedged alternatives like 'Toward...' for partial data."""
        from researchclaw.prompts import PromptManager
        pm = PromptManager()
        sp = pm.for_stage(
            "paper_draft",
            preamble="",
            topic_constraint="",
            exp_metrics_instruction="",
            citation_instruction="",
            outline="",
        )
        assert "Toward" in sp.system or "Investigating" in sp.system


class TestConditionCoverageDetection:
    """R7-3: REFINE should detect condition coverage gaps."""

    def test_coverage_hint_injected_when_no_labels(
        self, tmp_path: Path, run_dir: Path, adapters: AdapterBundle
    ) -> None:
        """If stdout has no 'condition=' labels, a coverage hint should be injected."""
        runs_dir = run_dir / "stage-12" / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        (runs_dir / "run-1.json").write_text(
            json.dumps({
                "run_id": "run-1",
                "status": "completed",
                "metrics": {"primary_metric": 0.5},
                "stdout": "primary_metric: 0.5\nprimary_metric: 0.3\n",
            }),
            encoding="utf-8",
        )

        exp_plan_dir = run_dir / "stage-09"
        exp_plan_dir.mkdir(parents=True, exist_ok=True)
        (exp_plan_dir / "exp_plan.yaml").write_text(
            "conditions:\n  - echo_chamber\n  - bridge_building\n  - random\n",
            encoding="utf-8",
        )

        exp_dir = run_dir / "stage-11" / "experiment"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "main.py").write_text("print('primary_metric: 0.5')\n", encoding="utf-8")

        stage_dir = run_dir / "stage-13"
        stage_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "project": {"name": "rc-test", "mode": "docs-first"},
            "research": {"topic": "test", "domains": ["ml"],
                         "daily_paper_count": 2, "quality_threshold": 8.2},
            "runtime": {"timezone": "UTC"},
            "notifications": {"channel": "local", "on_stage_start": True,
                              "on_stage_fail": False, "on_gate_required": True},
            "knowledge_base": {"backend": "markdown", "root": str(tmp_path / "kb")},
            "openclaw_bridge": {"use_memory": True, "use_message": True},
            "llm": {"provider": "openai-compatible", "base_url": "http://localhost:1234/v1",
                    "api_key_env": "RC_TEST_KEY", "api_key": "inline-test-key",
                    "primary_model": "fake-model", "fallback_models": []},
            "security": {"hitl_required_stages": [5, 9, 20]},
            "experiment": {
                "mode": "sandbox",
                "time_budget_sec": 30,
                "max_iterations": 1,
                "metric_key": "primary_metric",
                "metric_direction": "minimize",
            },
        }
        cfg = RCConfig.from_dict(data, project_root=tmp_path, check_paths=False)

        llm = FakeLLMClient("```python\nprint('primary_metric: 0.3')\n```")
        rc_executor._execute_iterative_refine(
            stage_dir, run_dir, cfg, adapters, llm=llm
        )

        assert len(llm.calls) >= 1
        user_msg = llm.calls[0][-1]["content"]
        assert "CONDITION COVERAGE GAP" in user_msg

    def test_no_hint_when_labels_present(
        self, tmp_path: Path, run_dir: Path, adapters: AdapterBundle
    ) -> None:
        """If stdout already has 'condition=' labels, no hint should be injected."""
        runs_dir = run_dir / "stage-12" / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        (runs_dir / "run-1.json").write_text(
            json.dumps({
                "run_id": "run-1",
                "status": "completed",
                "metrics": {"primary_metric": 0.5},
                "stdout": "condition=echo primary_metric: 0.5\ncondition=bridge primary_metric: 0.3\n",
            }),
            encoding="utf-8",
        )

        exp_plan_dir = run_dir / "stage-09"
        exp_plan_dir.mkdir(parents=True, exist_ok=True)
        (exp_plan_dir / "exp_plan.yaml").write_text(
            "conditions:\n  - echo\n  - bridge\n",
            encoding="utf-8",
        )

        exp_dir = run_dir / "stage-11" / "experiment"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "main.py").write_text("print('primary_metric: 0.5')\n", encoding="utf-8")

        stage_dir = run_dir / "stage-13"
        stage_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "project": {"name": "rc-test", "mode": "docs-first"},
            "research": {"topic": "test", "domains": ["ml"],
                         "daily_paper_count": 2, "quality_threshold": 8.2},
            "runtime": {"timezone": "UTC"},
            "notifications": {"channel": "local", "on_stage_start": True,
                              "on_stage_fail": False, "on_gate_required": True},
            "knowledge_base": {"backend": "markdown", "root": str(tmp_path / "kb")},
            "openclaw_bridge": {"use_memory": True, "use_message": True},
            "llm": {"provider": "openai-compatible", "base_url": "http://localhost:1234/v1",
                    "api_key_env": "RC_TEST_KEY", "api_key": "inline-test-key",
                    "primary_model": "fake-model", "fallback_models": []},
            "security": {"hitl_required_stages": [5, 9, 20]},
            "experiment": {
                "mode": "sandbox",
                "time_budget_sec": 30,
                "max_iterations": 1,
                "metric_key": "primary_metric",
                "metric_direction": "minimize",
            },
        }
        cfg = RCConfig.from_dict(data, project_root=tmp_path, check_paths=False)

        llm = FakeLLMClient("```python\nprint('primary_metric: 0.3')\n```")
        rc_executor._execute_iterative_refine(
            stage_dir, run_dir, cfg, adapters, llm=llm
        )

        assert len(llm.calls) >= 1
        user_msg = llm.calls[0][-1]["content"]
        assert "CONDITION COVERAGE GAP" not in user_msg


# ===================================================================
# R8 Tests — AutoBench Round 1 Fixes
# ===================================================================


class TestBreadthFirstPrompt:
    """R8-1: Code generation prompt should require breadth-first condition ordering."""

    def test_breadth_first_in_code_generation(self) -> None:
        from researchclaw.prompts import PromptManager
        pm = PromptManager()
        sp = pm.for_stage(
            "code_generation",
            topic="test",
            metric="primary_metric",
            pkg_hint="",
            exp_plan="conditions: [A, B, C]",
        )
        assert "BREADTH-FIRST" in sp.user
        assert "ONE representative" in sp.user


class TestRefineFilePreservation:
    """R8-2: Refine should preserve supporting files when LLM only returns main.py."""

    def test_supporting_files_preserved_in_refine(
        self, tmp_path: Path, run_dir: Path, adapters: AdapterBundle
    ) -> None:
        """When LLM returns only main.py, other project files should be preserved."""
        runs_dir = run_dir / "stage-12" / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        (runs_dir / "run-1.json").write_text(
            json.dumps({
                "run_id": "run-1",
                "status": "completed",
                "metrics": {"primary_metric": 0.5},
                "stdout": "primary_metric: 0.5",
            }),
            encoding="utf-8",
        )

        # Multi-file experiment project
        exp_dir = run_dir / "stage-11" / "experiment"
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "main.py").write_text("from helpers import foo\nprint('primary_metric: 0.5')\n")
        (exp_dir / "helpers.py").write_text("def foo(): return 42\n")
        (exp_dir / "utils.py").write_text("def bar(): return 99\n")

        stage_dir = run_dir / "stage-13"
        stage_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "project": {"name": "rc-test", "mode": "docs-first"},
            "research": {"topic": "test", "domains": ["ml"],
                         "daily_paper_count": 2, "quality_threshold": 8.2},
            "runtime": {"timezone": "UTC"},
            "notifications": {"channel": "local", "on_stage_start": True,
                              "on_stage_fail": False, "on_gate_required": True},
            "knowledge_base": {"backend": "markdown", "root": str(tmp_path / "kb")},
            "openclaw_bridge": {"use_memory": True, "use_message": True},
            "llm": {"provider": "openai-compatible", "base_url": "http://localhost:1234/v1",
                    "api_key_env": "RC_TEST_KEY", "api_key": "inline-test-key",
                    "primary_model": "fake-model", "fallback_models": []},
            "security": {"hitl_required_stages": [5, 9, 20]},
            "experiment": {
                "mode": "sandbox",
                "time_budget_sec": 30,
                "max_iterations": 1,
                "metric_key": "primary_metric",
                "metric_direction": "minimize",
            },
        }
        cfg = RCConfig.from_dict(data, project_root=tmp_path, check_paths=False)

        # LLM returns only main.py in multi-file format
        llm = FakeLLMClient("```filename:main.py\nfrom helpers import foo\nprint('primary_metric: 0.3')\n```")
        rc_executor._execute_iterative_refine(
            stage_dir, run_dir, cfg, adapters, llm=llm
        )

        # Check that experiment_v1 has ALL files, not just main.py
        v1_dir = stage_dir / "experiment_v1"
        assert v1_dir.exists()
        v1_files = {f.name for f in v1_dir.glob("*.py")}
        assert "main.py" in v1_files
        assert "helpers.py" in v1_files, "Supporting file helpers.py should be preserved"
        assert "utils.py" in v1_files, "Supporting file utils.py should be preserved"


# ===================================================================
# R9 Tests — AutoBench Round 2 Fixes
# ===================================================================


class TestCodeGenTopicNeutral:
    """R9-1: Code generation prompt should be topic-neutral, not optimization-biased."""

    def test_no_gradient_descent_bias(self) -> None:
        from researchclaw.prompts import PromptManager
        pm = PromptManager()
        sp = pm.for_stage(
            "code_generation",
            topic="multi-agent simulation",
            metric="primary_metric",
            pkg_hint="",
            exp_plan="conditions: [L1, L2, L3, L4]",
        )
        # Should NOT contain optimization-specific examples as recommended approaches
        assert "Adam" not in sp.user
        assert "SGD" not in sp.user
        assert "Rosenbrock" not in sp.user
        # "gradient descent" may appear as anti-pattern warning but not as example
        assert "e.g., gradient descent" not in sp.user

    def test_topic_relevant_guidance(self) -> None:
        from researchclaw.prompts import PromptManager
        pm = PromptManager()
        sp = pm.for_stage(
            "code_generation",
            topic="multi-agent simulation",
            metric="primary_metric",
            pkg_hint="",
            exp_plan="conditions: [L1, L2, L3, L4]",
        )
        # Should contain generic guidance that works for any topic
        assert "simulation" in sp.user.lower() or "appropriate" in sp.user.lower()
        assert "ACTUAL experiment" in sp.user or "relevant to the TOPIC" in sp.user


class TestRefineTopicAlignment:
    """R9-2: Refine prompt should include topic-code alignment check."""

    def test_topic_alignment_in_refine_prompt(self) -> None:
        from researchclaw.prompts import PromptManager
        pm = PromptManager()
        sp = pm.sub_prompt(
            "iterative_improve",
            metric_key="primary_metric",
            metric_direction="maximize",
            files_context="# main.py\nprint('hello')",
            run_summaries="{}",
            condition_coverage_hint="",
            topic="multi-agent diversity scaling",
            exp_plan_anchor="",
        )
        assert "EXPERIMENT PLAN ANCHOR" in sp.user
        assert "multi-agent diversity scaling" in sp.user
        assert "NEVER rename" in sp.user


# =====================================================================
# _validate_draft_quality tests
# =====================================================================


def _make_prose(word_count: int) -> str:  # noqa: E302
    """Generate flowing prose text of approximately *word_count* words."""
    sentence = (
        "This is a flowing academic prose sentence "
        "that demonstrates our research findings. "
    )
    words_per = len(sentence.split())
    return sentence * (word_count // words_per + 1)


def _make_bullets(word_count: int) -> str:
    """Generate bullet-point text of approximately *word_count* words."""
    line = "- This is a bullet point about a research finding\n"
    words_per = len(line.split())
    return line * (word_count // words_per + 1)


def _make_comparative_prose(word_count: int) -> str:
    """Generate related-work style prose with comparative language."""
    sentence = (
        "Unlike prior work that focuses on simple baselines, "
        "our approach differs by incorporating novel techniques. "
        "In contrast to existing methods, we address key limitations. "
        "However, while previous approaches rely on heuristics, "
        "our method provides theoretical guarantees. "
    )
    words_per = len(sentence.split())
    return sentence * (word_count // words_per + 1)


def _make_results_prose(word_count: int) -> str:
    """Generate results prose with statistical measures."""
    sentence = (
        "Our method achieves 85.3 ± 1.2 accuracy averaged over 5 seeds. "
        "The baseline comparison yields a p-value of 0.003, confirming "
        "statistical significance with 95% confidence interval. "
    )
    words_per = len(sentence.split())
    return sentence * (word_count // words_per + 1)


def _build_draft(**section_overrides: str) -> str:
    """Build a paper draft with default prose sections."""
    defaults = {
        "Abstract": _make_prose(200),
        "Introduction": _make_prose(900),
        "Related Work": _make_comparative_prose(700),
        "Method": _make_prose(1200),
        "Experiments": _make_prose(1000),
        "Results": _make_results_prose(700),
        "Discussion": _make_prose(500),
        "Limitations": _make_prose(250),
        "Conclusion": _make_prose(250),
    }
    defaults.update(section_overrides)
    parts = ["# My Research Title\n"]
    for heading, body in defaults.items():
        parts.append(f"# {heading}\n{body}\n")
    return "\n".join(parts)


class TestValidateDraftQuality:
    """Tests for _validate_draft_quality()."""

    def test_short_section_triggers_warning(self) -> None:
        """Short Method section triggers expand warning."""
        draft = _build_draft(Method=_make_prose(200))
        result = rc_executor._validate_draft_quality(draft)
        assert any("Method" in w for w in result["overall_warnings"])
        assert any("EXPAND" in d or "Expand" in d
                    for d in result["revision_directives"])

    def test_bullet_density_triggers_warning(self) -> None:
        """Bullet-heavy Method section triggers rewrite warning."""
        draft = _build_draft(Method=_make_bullets(1200))
        result = rc_executor._validate_draft_quality(draft)
        assert any(
            "bullet" in w.lower() or "density" in w.lower()
            for w in result["overall_warnings"]
        )
        assert any("REWRITE" in d for d in result["revision_directives"])

    def test_clean_draft_no_warnings(self) -> None:
        """Balanced prose draft produces zero warnings."""
        draft = _build_draft()
        result = rc_executor._validate_draft_quality(draft)
        assert len(result["overall_warnings"]) == 0
        assert len(result["revision_directives"]) == 0

    def test_balance_warning(self) -> None:
        """Large imbalance between sections triggers balance warning."""
        draft = _build_draft(
            Introduction=_make_prose(1500),
            Results=_make_prose(100),
        )
        result = rc_executor._validate_draft_quality(draft)
        bal = [w for w in result["overall_warnings"]
               if "imbalance" in w.lower()]
        assert len(bal) >= 1, (
            f"Expected balance warning, got: {result['overall_warnings']}"
        )

    def test_writes_json_to_stage_dir(self, tmp_path: Path) -> None:
        """Quality report is written as draft_quality.json."""
        draft = _build_draft(Method=_make_prose(200))
        rc_executor._validate_draft_quality(draft, stage_dir=tmp_path)
        assert (tmp_path / "draft_quality.json").exists()
        data = json.loads(
            (tmp_path / "draft_quality.json").read_text()
        )
        assert "section_analysis" in data
        assert "overall_warnings" in data
        assert "revision_directives" in data
