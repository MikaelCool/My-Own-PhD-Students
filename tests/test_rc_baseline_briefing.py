from pathlib import Path

from researchclaw.config import RCConfig, validate_config
from researchclaw.pipeline._helpers import _build_context_preamble


def _config_data(tmp_path: Path, baseline_path: Path) -> dict[str, object]:
    kb_root = tmp_path / "docs" / "kb"
    for name in (
        "questions",
        "literature",
        "experiments",
        "findings",
        "decisions",
        "reviews",
    ):
        (kb_root / name).mkdir(parents=True, exist_ok=True)

    return {
        "project": {"name": "demo", "mode": "docs-first"},
        "research": {
            "topic": "Test topic",
            "domains": ["ml"],
            "baseline_brief": str(baseline_path),
        },
        "runtime": {"timezone": "America/New_York"},
        "notifications": {"channel": "console"},
        "knowledge_base": {"backend": "markdown", "root": "docs/kb"},
        "openclaw_bridge": {},
        "llm": {
            "provider": "acp",
            "base_url": "",
            "api_key_env": "",
            "acp": {"agent": "codex"},
        },
        "experiment": {"mode": "simulated"},
    }


def test_validate_config_checks_baseline_brief_path(tmp_path: Path):
    missing = tmp_path / "missing_baseline.md"
    result = validate_config(
        _config_data(tmp_path, missing),
        project_root=tmp_path,
        check_paths=True,
    )

    assert result.ok is False
    assert f"Missing path: {missing}" in result.errors


def test_context_preamble_includes_baseline_briefing(tmp_path: Path):
    baseline = tmp_path / "baseline.md"
    baseline.write_text("# Baseline\n- key idea: structured prior\n", encoding="utf-8")
    config = RCConfig.from_dict(
        _config_data(tmp_path, baseline),
        project_root=tmp_path,
        check_paths=False,
    )

    preamble = _build_context_preamble(config, tmp_path / "artifacts" / "run")

    assert "Baseline Briefing" in preamble
    assert "structured prior" in preamble


def test_context_preamble_includes_baseline_digest_and_experiment_log(tmp_path: Path):
    baseline = tmp_path / "baseline.md"
    baseline.write_text("# Baseline\n- key idea: structured prior\n", encoding="utf-8")
    config = RCConfig.from_dict(
        _config_data(tmp_path, baseline),
        project_root=tmp_path,
        check_paths=False,
    )
    run_dir = tmp_path / "artifacts" / "run"
    (run_dir / "stage-04").mkdir(parents=True, exist_ok=True)
    (run_dir / "stage-14").mkdir(parents=True, exist_ok=True)
    (run_dir / "stage-04" / "baseline_digest.md").write_text(
        "# Baseline Digest\nseed notes summary",
        encoding="utf-8",
    )
    (run_dir / "stage-14" / "experiment_log.md").write_text(
        "# Experiment Log\nbest metric: 0.81",
        encoding="utf-8",
    )

    preamble = _build_context_preamble(
        config,
        run_dir,
        include_experiment_data=True,
    )

    assert "Baseline Digest" in preamble
    assert "seed notes summary" in preamble
    assert "Experiment Log" in preamble
    assert "best metric" in preamble
