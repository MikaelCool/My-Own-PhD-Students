from __future__ import annotations

from collections import deque
from pathlib import Path

from experiment_config import ExperimentConfig
from methods import CONDITION_CLASS_REGISTRY, ProbeControlCondition


EXPECTED_STAGE13_CONDITIONS = [
    "lora_fixed",
    "qlora_fixed",
    "cheap_proxy_controller",
    "exact_svd_oracle_controller",
    "probe_control",
    "falcon_qb_weight_init",
    "falcon_qb_activation_rank",
    "falcon_qb_init_plus_cheap_proxy",
]


def test_experiment_config_defaults_to_eight_conditions_and_three_seeds() -> None:
    config = ExperimentConfig()

    assert config.screening_seeds == [0, 1, 2]
    assert config.main_seeds == [0, 1, 2]
    assert getattr(config, "active_condition_names", []) == EXPECTED_STAGE13_CONDITIONS
    assert [spec["name"] for spec in config.condition_specs] == EXPECTED_STAGE13_CONDITIONS
    assert len(config.condition_specs) == 8


def test_stage13_registry_exposes_falcon_qb_condition_classes() -> None:
    config = ExperimentConfig()
    for condition_name in (
        "falcon_qb_weight_init",
        "falcon_qb_activation_rank",
        "falcon_qb_init_plus_cheap_proxy",
    ):
        class_name = config.condition_name_to_spec[condition_name]["class_name"]
        assert class_name in CONDITION_CLASS_REGISTRY


def test_main_uses_experiment_config_module_and_no_subprocess() -> None:
    source = Path("main.py").read_text(encoding="utf-8")

    assert 'import_module("experiment_config")' in source
    assert 'import_module("config")' not in source
    assert "subprocess" not in source


def test_main_summary_compares_stage13_planned_pairs() -> None:
    source = Path("main.py").read_text(encoding="utf-8")

    assert '("cheap_proxy_controller", "probe_control")' in source
    assert '("exact_svd_oracle_controller", "probe_control")' in source
    assert '("cheap_proxy_controller", "falcon_qb_activation_rank")' in source
    assert '("falcon_qb_weight_init", "falcon_qb_init_plus_cheap_proxy")' in source
    assert '("probe_control", "persistence_selective")' not in source
    assert '("persistence_selective", "state_consistent_rank_morphing")' not in source


class _DummyAdapter:
    def __init__(self, module_name: str, rank: int) -> None:
        self.module_name = module_name
        self.rank = rank


class _DummyModel:
    def __init__(self, adapters: list[tuple[str, _DummyAdapter]]) -> None:
        self._adapters = adapters

    def iter_dynamic_adapters(self) -> list[tuple[str, _DummyAdapter]]:
        return list(self._adapters)


def test_probe_control_emits_phase_aware_proxy_and_persistence_fields(monkeypatch) -> None:
    config = ExperimentConfig()
    spec = next(spec for spec in config.condition_specs if spec["name"] == "probe_control")
    condition = ProbeControlCondition(spec, config, tokenizer=None)

    layer_a = _DummyAdapter("layer_a", 8)
    layer_b = _DummyAdapter("layer_b", 8)
    model = _DummyModel([("layer_a", layer_a), ("layer_b", layer_b)])

    monkeypatch.setattr(
        condition,
        "_collect_probe_features",
        lambda _model, _step_idx, exact_oracle_scope="sampled": {
            "layer_a": {
                "adapter": layer_a,
                "current_rank": 8,
                "effective_rank": 12,
                "tail_energy": 0.24,
                "spectral_entropy": 0.82,
                "spectral_gap": 1.05,
                "drift": 0.18,
                "current_basis": [[1.0, 0.0], [0.0, 1.0]],
                "probe": {"exact_effective_rank": 12, "exact_tail_energy": 0.18},
                "retained_energy_at_current_rank": 0.70,
                "exact_retained_energy_at_current_rank": 0.74,
            },
            "layer_b": {
                "adapter": layer_b,
                "current_rank": 8,
                "effective_rank": 6,
                "tail_energy": 0.05,
                "spectral_entropy": 0.28,
                "spectral_gap": 1.90,
                "drift": 0.03,
                "current_basis": [[1.0, 0.0], [0.0, 1.0]],
                "probe": {"exact_effective_rank": 6, "exact_tail_energy": 0.04},
                "retained_energy_at_current_rank": 0.97,
                "exact_retained_energy_at_current_rank": 0.96,
            },
        },
    )
    monkeypatch.setattr(
        condition,
        "_proxy_feature_vector",
        lambda adapter: (
            {"grad_norm": 3.0, "update_fro_norm": 2.0, "ema_update_norm": 2.5}
            if adapter.module_name == "layer_a"
            else {"grad_norm": 0.2, "update_fro_norm": 0.1, "ema_update_norm": 0.1}
        ),
    )
    monkeypatch.setattr(
        condition,
        "_get_persistence_window",
        lambda layer_name: deque(
            maxlen=condition.persistence_window_size,
            iterable=[[[1.0, 0.0], [0.0, 1.0]]] if layer_name == "layer_a" else [],
        ),
    )
    monkeypatch.setattr(
        condition,
        "_apply_state_consistent_resize",
        lambda adapter, optimizer, new_rank, probe_basis: {
            "module_name": adapter.module_name,
            "old_rank": adapter.rank,
            "new_rank": new_rank,
            "copied_rank": min(adapter.rank, new_rank),
            "changed": new_rank != adapter.rank,
            "projected": new_rank != adapter.rank,
        },
    )
    monkeypatch.setattr(
        condition.probe_engine,
        "compute_persistence_alignment",
        lambda current_basis, basis_window: 0.92 if basis_window else 0.18,
    )

    step_idx = int(config.probe_interval * 5)
    result = condition.maybe_update_rank(model, optimizer=None, step_idx=step_idx)
    decisions = result["per_layer_decisions"]

    assert decisions["layer_a"]["phase"] == "late_persistence_weighted"
    assert "proxy_expand_score" in decisions["layer_a"]
    assert "proxy_compress_score" in decisions["layer_a"]
    assert "persistence" in decisions["layer_a"]
    assert "score_margin" in decisions["layer_a"]
    assert "phase_blend_weight" in decisions["layer_a"]


def test_probe_control_can_follow_reference_average_rank_schedule(monkeypatch) -> None:
    config = ExperimentConfig()
    spec = next(spec for spec in config.condition_specs if spec["name"] == "probe_control")
    condition = ProbeControlCondition(spec, config, tokenizer=None)
    condition.set_reference_run(
        {
            "seed": 0,
            "trigger_history": [
                {
                    "step_idx": int(config.probe_interval),
                    "triggered": True,
                    "average_new_rank": 10.0,
                    "num_layers_changed": 2,
                }
            ],
            "rank_history": [
                {
                    "step_idx": int(config.probe_interval),
                    "ranks": {"layer_a": 10, "layer_b": 10},
                }
            ],
        }
    )

    layer_a = _DummyAdapter("layer_a", 8)
    layer_b = _DummyAdapter("layer_b", 8)
    model = _DummyModel([("layer_a", layer_a), ("layer_b", layer_b)])

    monkeypatch.setattr(
        condition,
        "_collect_probe_features",
        lambda _model, _step_idx, exact_oracle_scope="sampled": {
            "layer_a": {
                "adapter": layer_a,
                "current_rank": layer_a.rank,
                "effective_rank": 12,
                "tail_energy": 0.24,
                "spectral_entropy": 0.82,
                "spectral_gap": 1.05,
                "drift": 0.18,
                "current_basis": [[1.0, 0.0], [0.0, 1.0]],
                "probe": {"exact_effective_rank": 12, "exact_tail_energy": 0.18},
                "retained_energy_at_current_rank": 0.70,
                "exact_retained_energy_at_current_rank": 0.74,
            },
            "layer_b": {
                "adapter": layer_b,
                "current_rank": layer_b.rank,
                "effective_rank": 9,
                "tail_energy": 0.12,
                "spectral_entropy": 0.55,
                "spectral_gap": 1.20,
                "drift": 0.10,
                "current_basis": [[1.0, 0.0], [0.0, 1.0]],
                "probe": {"exact_effective_rank": 10, "exact_tail_energy": 0.10},
                "retained_energy_at_current_rank": 0.82,
                "exact_retained_energy_at_current_rank": 0.84,
            },
        },
    )
    monkeypatch.setattr(
        condition,
        "_proxy_feature_vector",
        lambda adapter: (
            {"grad_norm": 3.0, "update_fro_norm": 2.0, "ema_update_norm": 2.5}
            if adapter.module_name == "layer_a"
            else {"grad_norm": 1.2, "update_fro_norm": 0.9, "ema_update_norm": 1.0}
        ),
    )
    monkeypatch.setattr(
        condition,
        "_get_persistence_window",
        lambda _layer_name: deque(maxlen=condition.persistence_window_size),
    )
    monkeypatch.setattr(
        condition.probe_engine,
        "compute_persistence_alignment",
        lambda current_basis, basis_window: 0.0,
    )

    def _resize(adapter: _DummyAdapter, optimizer, new_rank: int, probe_basis) -> dict[str, object]:
        old_rank = adapter.rank
        adapter.rank = int(new_rank)
        return {
            "module_name": adapter.module_name,
            "old_rank": old_rank,
            "new_rank": int(new_rank),
            "copied_rank": min(old_rank, int(new_rank)),
            "changed": int(new_rank) != old_rank,
            "projected": int(new_rank) != old_rank,
        }

    monkeypatch.setattr(condition, "_apply_state_consistent_resize", _resize)

    result = condition.maybe_update_rank(model, optimizer=None, step_idx=int(config.probe_interval))

    assert result["average_new_rank"] > 8.0
