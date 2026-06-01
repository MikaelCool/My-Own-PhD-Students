"""Stage 9: Experiment design."""

from __future__ import annotations

import json
import hashlib
import logging
import re
from pathlib import Path
from typing import Any

import yaml

from researchclaw.adapters import AdapterBundle
from researchclaw.config import RCConfig
from researchclaw.llm.client import LLMClient
from researchclaw.pipeline._domain import _detect_domain
from researchclaw.pipeline._helpers import (
    StageResult,
    _build_context_preamble,
    _chat_with_prompt,
    _compact_markdown_context,
    _extract_hypothesis_claims,
    _extract_yaml_block,
    _get_evolution_overlay,
    _load_baseline_briefing,
    _load_hardware_profile,
    _normalize_named_list,
    _read_prior_artifact,
    _safe_json_loads,
    _utcnow_iso,
)
from researchclaw.pipeline.research_governor import build_phase_charter, build_stage_skill_overlay
from researchclaw.pipeline.stages import Stage, StageStatus
from researchclaw.prompts import PromptManager

logger = logging.getLogger(__name__)


def _benchmark_network_policy(config: RCConfig) -> str:
    """Return the effective dataset/network policy for benchmark selection."""
    if config.experiment.mode == "docker":
        return config.experiment.docker.network_policy
    if config.experiment.mode == "sandbox":
        return "none"
    return "full"


def _build_claims_evidence_matrix(
    topic: str,
    hypotheses: str,
    plan: dict[str, Any],
    metric_key: str,
) -> tuple[str, dict[str, Any]]:
    claims = _extract_hypothesis_claims(hypotheses, max_items=3)
    baselines = _normalize_named_list(plan.get("baselines"))
    proposed = _normalize_named_list(plan.get("proposed_methods"))
    ablations = _normalize_named_list(plan.get("ablations"))
    datasets = _normalize_named_list(plan.get("datasets"))
    metrics = _normalize_named_list(plan.get("metrics")) or [metric_key]
    objectives = _normalize_named_list(plan.get("objectives"))

    if not claims:
        claims = [
            f"The proposed method for {topic} addresses the central baseline weakness more effectively than strong references."
        ]

    rows: list[dict[str, Any]] = []
    md_lines = [
        "# Claims-Evidence Matrix",
        "",
        "This matrix binds each research claim to the minimum evidence required before it can appear as a strong paper claim.",
        "",
    ]

    for idx, claim in enumerate(claims, start=1):
        targeted_methods = proposed[idx - 1 : idx] or proposed[:1]
        supporting_ablations = ablations[idx - 1 : idx] or ablations[:1]
        required_evidence = [
            "baseline reproduction on the original setting",
            "main comparison on the primary metric",
            "statistical significance or uncertainty estimate",
            "at least one failure-case or robustness check",
        ]
        if supporting_ablations:
            required_evidence.append("component isolation through ablation")

        row = {
            "claim_id": f"C{idx}",
            "claim": claim,
            "proposed_methods": targeted_methods,
            "baselines": baselines[: min(3, len(baselines))],
            "ablations": supporting_ablations,
            "datasets": datasets[: min(4, len(datasets))],
            "metrics": metrics[: min(3, len(metrics))],
            "required_evidence": required_evidence,
            "failure_signal": (
                "Claim must be downgraded or removed if the proposed method fails "
                "to beat or match strong baselines under the planned metrics/regimes."
            ),
        }
        rows.append(row)

        md_lines.extend(
            [
                f"## {row['claim_id']}",
                f"- Claim: {claim}",
                f"- Proposed condition(s): {', '.join(targeted_methods) if targeted_methods else 'TBD'}",
                f"- Baselines / controls: {', '.join(row['baselines']) if row['baselines'] else 'TBD'}",
                f"- Ablations: {', '.join(supporting_ablations) if supporting_ablations else 'At least one component-isolation ablation required'}",
                f"- Datasets / regimes: {', '.join(row['datasets']) if row['datasets'] else 'Use the reproduced baseline setting first, then extended regimes'}",
                f"- Metrics: {', '.join(row['metrics'])}",
                "- Required evidence:",
            ]
        )
        for evidence in required_evidence:
            md_lines.append(f"  - {evidence}")
        md_lines.extend(
            [
                f"- Failure signal: {row['failure_signal']}",
                "",
            ]
        )

    if objectives:
        md_lines.extend(
            [
                "## Must-Run Order",
                *(f"- {objective}" for objective in objectives),
                "",
            ]
        )

    payload = {
        "topic": topic,
        "generated": _utcnow_iso(),
        "claims": rows,
        "must_run_order": objectives,
    }
    return "\n".join(md_lines).rstrip() + "\n", payload


def _build_story_background(topic: str, plan: dict[str, Any]) -> str:
    story = str(plan.get("story_background", "")).strip()
    sota_context = str(plan.get("target_sota_context", "")).strip()
    failure_modes = plan.get("baseline_failure_modes", [])
    must_run = plan.get("must_run_experiments", []) or plan.get("objectives", [])
    baselines = _normalize_named_list(plan.get("baselines"))
    proposed = _normalize_named_list(plan.get("proposed_methods"))
    datasets = _normalize_named_list(plan.get("datasets"))

    lines = [
        "# Story Background",
        "",
        f"- Topic: {topic}",
        f"- Target deployment / evaluation context: {sota_context or 'To be validated against strong baselines in a concrete workload, not generic score chasing.'}",
        "",
        "## Why This Problem Matters",
        story or (
            "This study needs a concrete pressure point where existing strong baselines are already competitive but still leave a specific gap. "
            "The paper story should be anchored to that gap rather than generic performance improvement."
        ),
        "",
        "## Baseline Pressure Test",
        "- Strong baselines to beat fairly: " + (", ".join(baselines[:6]) if baselines else "TBD"),
        "- Proposed method family: " + (", ".join(proposed[:4]) if proposed else "TBD"),
        "- Core datasets / regimes: " + (", ".join(datasets[:6]) if datasets else "TBD"),
        "",
        "## Failure Modes That Make The Story Interesting",
    ]
    if isinstance(failure_modes, list) and failure_modes:
        lines.extend(f"- {str(item)}" for item in failure_modes[:8])
    else:
        lines.append("- Baseline is strong overall but fails under a specific resource / robustness / adaptation constraint.")
        lines.append("- The proposed method must explain why its gain appears specifically in that pressure regime.")
    lines.extend(
        [
            "",
            "## Must-Run Experiments Before Claiming Success",
        ]
    )
    if isinstance(must_run, list) and must_run:
        lines.extend(f"- {str(item)}" for item in must_run[:10])
    else:
        lines.append("- Reproduce the strongest baseline setting first.")
        lines.append("- Run at least one robustness / failure-case regime, not just a main table.")
    return "\n".join(lines).rstrip() + "\n"


def _build_experiment_coverage_md(plan: dict[str, Any]) -> str:
    sections = {
        "Baselines": _normalize_named_list(plan.get("baselines")),
        "Proposed Methods": _normalize_named_list(plan.get("proposed_methods")),
        "Ablations": _normalize_named_list(plan.get("ablations")),
        "Datasets": _normalize_named_list(plan.get("datasets")),
        "Metrics": _normalize_named_list(plan.get("metrics")),
        "Must-Run Experiments": _normalize_named_list(plan.get("must_run_experiments"))
        or _normalize_named_list(plan.get("objectives")),
        "Nice-To-Have Experiments": _normalize_named_list(plan.get("nice_to_have_experiments")),
    }
    lines = ["# Experiment Coverage Checklist", ""]
    for name, items in sections.items():
        lines.append(f"## {name}")
        if items:
            lines.extend(f"- {item}" for item in items[:16])
        else:
            lines.append("- None specified.")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _build_baseline_coverage_checklist(run_dir: Path, plan: dict[str, Any]) -> str:
    shortlist_rows: list[dict[str, Any]] = []
    shortlist_text = _read_prior_artifact(run_dir, "shortlist.jsonl") or ""
    for raw_line in shortlist_text.splitlines():
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            shortlist_rows.append(payload)
    baseline_names = _normalize_named_list(plan.get("baselines"))
    lines = [
        "# Baseline Coverage Checklist",
        "",
        "This checklist exists to prevent thin experiments that only run a small main table.",
        "",
        "## Required Coverage",
        "- Reproduce the strongest baseline setting before claiming any gain.",
        "- Include at least one efficiency view (time, throughput, memory, or parameters).",
        "- Include at least one robustness or failure-case regime.",
        "- Include component-isolation ablations for every major claimed mechanism.",
        "",
        "## Planned Baselines",
    ]
    if baseline_names:
        lines.extend(f"- {name}" for name in baseline_names[:12])
    else:
        lines.append("- None explicitly named yet.")
    lines.extend(["", "## Literature Anchors"])
    if isinstance(shortlist_rows, list) and shortlist_rows:
        for row in shortlist_rows[:12]:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title", "Untitled"))
            reason = str(row.get("keep_reason", "")).strip()
            lines.append(f"- {title}")
            if reason:
                lines.append(f"  reason: {reason[:180]}")
    else:
        lines.append("- No shortlist available.")
    return "\n".join(lines).rstrip() + "\n"


def _build_experiment_adequacy_report(
    *,
    run_dir: Path,
    config: RCConfig,
    plan: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    baselines = _normalize_named_list(plan.get("baselines"), max_items=32)
    proposed = _normalize_named_list(plan.get("proposed_methods"), max_items=32)
    ablations = _normalize_named_list(plan.get("ablations"), max_items=32)
    datasets = _normalize_named_list(plan.get("datasets"), max_items=32)
    metrics = _normalize_named_list(plan.get("metrics"), max_items=32)
    must_run = _normalize_named_list(plan.get("must_run_experiments"), max_items=32) or _normalize_named_list(plan.get("objectives"), max_items=32)

    shortlist_count = 0
    shortlist_text = _read_prior_artifact(run_dir, "shortlist.jsonl") or ""
    for raw in shortlist_text.splitlines():
        if raw.strip():
            shortlist_count += 1
    cards_dir = _read_prior_artifact(run_dir, "cards/") or ""
    knowledge_card_count = 0
    if cards_dir and Path(cards_dir).is_dir():
        try:
            knowledge_card_count = sum(1 for p in Path(cards_dir).rglob("*") if p.is_file())
        except OSError:
            knowledge_card_count = 0

    checks = [
        {
            "name": "baseline_coverage",
            "score": 2 if len(baselines) >= 3 else (1 if len(baselines) >= 2 else 0),
            "max_score": 2,
            "detail": f"{len(baselines)} baselines planned",
        },
        {
            "name": "proposed_method_coverage",
            "score": 2 if len(proposed) >= 2 else (1 if len(proposed) >= 1 else 0),
            "max_score": 2,
            "detail": f"{len(proposed)} proposed method conditions planned",
        },
        {
            "name": "ablation_coverage",
            "score": 2 if len(ablations) >= 2 else (1 if len(ablations) >= 1 else 0),
            "max_score": 2,
            "detail": f"{len(ablations)} ablations planned",
        },
        {
            "name": "dataset_coverage",
            "score": 2 if len(datasets) >= 2 else (1 if len(datasets) >= 1 else 0),
            "max_score": 2,
            "detail": f"{len(datasets)} datasets / regimes planned",
        },
        {
            "name": "metric_alignment",
            "score": 2 if config.experiment.metric_key in metrics else (1 if metrics else 0),
            "max_score": 2,
            "detail": f"metrics={metrics[:6]}",
        },
        {
            "name": "must_run_coverage",
            "score": 2 if len(must_run) >= 3 else (1 if len(must_run) >= 1 else 0),
            "max_score": 2,
            "detail": f"{len(must_run)} must-run / objective items",
        },
        {
            "name": "literature_grounding",
            "score": 2 if shortlist_count >= 8 or knowledge_card_count >= 8 else (1 if shortlist_count >= 4 or knowledge_card_count >= 4 else 0),
            "max_score": 2,
            "detail": f"shortlist={shortlist_count}, knowledge_cards={knowledge_card_count}",
        },
    ]

    total_score = sum(int(item["score"]) for item in checks)
    max_score = sum(int(item["max_score"]) for item in checks)
    if total_score >= 10:
        verdict = "ready_for_gate"
    elif total_score >= 7:
        verdict = "borderline_review_needed"
    else:
        verdict = "weak_design"

    missing = [item["name"] for item in checks if int(item["score"]) == 0]
    lines = [
        "# Experiment Adequacy Report",
        "",
        f"- Verdict: {verdict}",
        f"- Score: {total_score}/{max_score}",
        f"- Primary metric must align with config metric `{config.experiment.metric_key}`.",
        "",
        "## Checks",
    ]
    for item in checks:
        lines.append(
            f"- {item['name']}: {item['score']}/{item['max_score']} — {item['detail']}"
        )
    lines.extend(
        [
            "",
            "## Immediate Attention",
        ]
    )
    if missing:
        lines.extend(f"- {name}" for name in missing)
    else:
        lines.append("- No zero-score adequacy gaps detected.")
    payload = {
        "generated": _utcnow_iso(),
        "verdict": verdict,
        "score": total_score,
        "max_score": max_score,
        "checks": checks,
        "missing": missing,
        "plan_counts": {
            "baselines": len(baselines),
            "proposed_methods": len(proposed),
            "ablations": len(ablations),
            "datasets": len(datasets),
            "metrics": len(metrics),
            "must_run": len(must_run),
        },
        "literature_grounding": {
            "shortlist_count": shortlist_count,
            "knowledge_card_count": knowledge_card_count,
        },
    }
    return "\n".join(lines).rstrip() + "\n", payload


def _execute_experiment_design(
    stage_dir: Path,
    run_dir: Path,
    config: RCConfig,
    adapters: AdapterBundle,
    *,
    llm: LLMClient | None = None,
    prompts: PromptManager | None = None,
) -> StageResult:
    hypotheses = _read_prior_artifact(run_dir, "hypotheses.md") or ""
    compact_hypotheses = (
        "Source artifact: `stage-08/hypotheses.md`\n"
        "- Read the source artifact on disk if exact wording is needed.\n"
        + _compact_markdown_context(hypotheses, max_chars=2200, max_items=12)
    ).strip()
    problem_anchor = _read_prior_artifact(run_dir, "problem_anchor.md") or ""
    synthesis = _read_prior_artifact(run_dir, "synthesis.md") or ""
    preamble = _build_context_preamble(
        config,
        run_dir,
        compact=True,
        include_goal=True,
        include_problem_anchor=True,
        include_hypotheses=False,
        include_baseline_digest=False,
        include_baseline_briefing=False,
    )
    plan: dict[str, Any] | None = None

    # ── Domain detection ──────────────────────────────────────────────────
    # Detect the research domain early so we can adapt experiment design
    # and code generation. For ML domains, existing behavior is unchanged.
    _domain_profile = None
    try:
        from researchclaw.domains.detector import detect_domain as _detect_domain_adv
        _domain_profile = _detect_domain_adv(
            topic=config.research.topic,
            hypotheses=hypotheses,
        )
        logger.info(
            "Domain detected: %s (%s)",
            _domain_profile.display_name,
            _domain_profile.domain_id,
        )
        # Persist domain profile for Stage 10
        import json as _json_dd
        (stage_dir / "domain_profile.json").write_text(
            _json_dd.dumps({
                "domain_id": _domain_profile.domain_id,
                "display_name": _domain_profile.display_name,
                "experiment_paradigm": _domain_profile.experiment_paradigm,
                "core_libraries": _domain_profile.core_libraries,
                "gpu_required": _domain_profile.gpu_required,
            }, indent=2),
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001
        logger.debug("Domain detection unavailable", exc_info=True)
    if llm is not None:
        _pm = prompts or PromptManager()
        # Pass dataset_guidance block for experiment design
        try:
            _dg_block = _pm.block("dataset_guidance")
        except (KeyError, Exception):  # noqa: BLE001
            _dg_block = ""
        # I-08: Inject RL step guidance for RL topics
        _rl_kws = ("reinforcement learning", "ppo", "sac", "td3", "ddpg",
                    "dqn", "mujoco", "continuous control", "actor-critic",
                    "policy gradient", "exploration bonus")
        _is_rl_topic = any(kw in config.research.topic.lower() for kw in _rl_kws)
        if _is_rl_topic:
            try:
                _dg_block += _pm.block("rl_step_guidance")
            except Exception:  # noqa: BLE001
                pass
            # Improvement G: For RL with short budget, constrain to classic control
            if config.experiment.time_budget_sec <= 3600:
                _dg_block += (
                    "\n\n## RL TIME CONSTRAINT (MANDATORY):\n"
                    f"Your time budget is {config.experiment.time_budget_sec}s (≤ 3600s).\n"
                    "You MUST use ONLY classic control environments: "
                    "CartPole-v1, Pendulum-v1, MountainCar-v0, Acrobot-v1, LunarLander-v3.\n"
                    "Do NOT use MuJoCo (HalfCheetah, Hopper, Walker2d, Ant, Humanoid) — "
                    "they require >5000s for meaningful training.\n"
                )
            if config.experiment.time_budget_sec <= 1800:
                _dg_block += (
                    "Time budget ≤ 1800s: use ONLY CartPole-v1 or Pendulum-v1 "
                    "(the simplest environments).\n"
                )
        # F-01: Inject framework docs for experiment design
        try:
            from researchclaw.data import detect_frameworks, load_framework_docs
            _fw_ids = detect_frameworks(config.research.topic, hypotheses)
            if _fw_ids:
                _fw_docs = load_framework_docs(_fw_ids, max_chars=1500)
                if _fw_docs:
                    _dg_block += _fw_docs
        except Exception:  # noqa: BLE001
            pass
        # Improvement A: Compute hardware profile + per-condition budget
        _hw_profile_str = (
            "- GPU: NVIDIA RTX 6000 Ada (49140 MB VRAM)\n"
            "- GPU count: 1\n"
            "- CPU: shared server"
        )
        _per_condition_sec = int(config.experiment.time_budget_sec * 0.7 / 6)
        _tier1 = "CIFAR-10, CIFAR-100, MNIST, FashionMNIST, STL-10, SVHN"

        _overlay = (
            _get_evolution_overlay(run_dir, "experiment_design")
            + "\n"
            + build_phase_charter("experiment_design")
            + "\n"
            + build_stage_skill_overlay(
                config,
                stage_name="experiment_design",
                context="\n\n".join((hypotheses[:900], synthesis[:900], problem_anchor[:700])),
                max_chars=900,
            )
        )
        baseline_briefing = _compact_markdown_context(
            _load_baseline_briefing(config, max_chars=12000),
            max_chars=1800,
            max_items=10,
        )
        sp = _pm.for_stage(
            "experiment_design",
            evolution_overlay=_overlay,
            preamble=preamble,
            hypotheses=compact_hypotheses or hypotheses,
            baseline_briefing=baseline_briefing,
            dataset_guidance=_dg_block,
            time_budget_sec=config.experiment.time_budget_sec,
            metric_key=config.experiment.metric_key,
            metric_direction=config.experiment.metric_direction,
            hardware_profile=_hw_profile_str,
            per_condition_budget_sec=_per_condition_sec,
            available_tier1_datasets=_tier1,
        )
        resp = _chat_with_prompt(
            llm,
            sp.system,
            sp.user,
            json_mode=sp.json_mode,
            max_tokens=sp.max_tokens,
        )
        raw_yaml = _extract_yaml_block(resp.content)
        try:
            parsed = yaml.safe_load(raw_yaml)
        except yaml.YAMLError:
            parsed = None
        # Fallback: reasoning models sometimes emit the YAML without fences
        # or wrapped in prose. Try parsing the whole response as YAML.
        if not isinstance(parsed, dict):
            try:
                parsed = yaml.safe_load(resp.content)
            except yaml.YAMLError:
                pass
        # Last fallback: try to find any YAML-like dict in the response
        if not isinstance(parsed, dict):
            import re as _re_yaml

            # Look for lines starting with known keys
            _yaml_lines = []
            _capturing = False
            for line in resp.content.splitlines():
                if _re_yaml.match(
                    r"^(baselines|proposed_methods|ablations|datasets|"
                    r"metrics|objectives|risks|compute_budget)\s*:",
                    line,
                ):
                    _capturing = True
                if _capturing:
                    if line.strip() == "" or line.startswith("```"):
                        continue
                    if line.startswith("#") or line.startswith("**"):
                        continue
                    _yaml_lines.append(line)
            if _yaml_lines:
                try:
                    parsed = yaml.safe_load("\n".join(_yaml_lines))
                except yaml.YAMLError:
                    pass
        if isinstance(parsed, dict):
            plan = parsed
        else:
            logger.warning(
                "Stage 09: LLM response could not be parsed as YAML "
                "(len=%d, first 200 chars: %s). Content extraction method "
                "returned: %s",
                len(resp.content),
                resp.content[:200],
                raw_yaml[:200] if raw_yaml else "<empty>",
            )
            # BUG-12: Retry with a stricter, shorter prompt
            if llm is not None:
                logger.info("Stage 09: Retrying with strict YAML-only prompt...")
                _retry_prompt = (
                    "Output ONLY valid YAML. No prose, no markdown fences, no explanation.\n"
                    f"Topic: {config.research.topic}\n"
                    "Required keys: baselines, proposed_methods, ablations, "
                    "datasets, metrics, objectives, risks, compute_budget.\n"
                    "Each key maps to a list of strings."
                )
                _retry_resp = _chat_with_prompt(
                    llm,
                    "You output ONLY valid YAML. Nothing else.",
                    _retry_prompt,
                    max_tokens=4096,
                )
                try:
                    _retry_parsed = yaml.safe_load(_retry_resp.content)
                    if isinstance(_retry_parsed, dict):
                        plan = _retry_parsed
                        logger.info("Stage 09: Strict YAML retry succeeded.")
                except yaml.YAMLError:
                    pass

    # BUG-12: Fallback 4 — extract method/baseline names from Stage 8 hypotheses
    if plan is None:
        _hyp_text = _read_prior_artifact(run_dir, "hypotheses.md") or ""
        if _hyp_text:
            import re as _re_hyp
            # Extract method-like names from hypothesis text
            _method_candidates = _re_hyp.findall(
                r"(?:proposed|our|novel|new)\s+(?:method|approach|algorithm|framework|model)[:\s]+[\"']?([A-Za-z][\w-]+)",
                _hyp_text, _re_hyp.IGNORECASE,
            )
            _baseline_candidates = _re_hyp.findall(
                r"(?:baseline|compare|existing|standard|traditional)\s+(?:method|approach|model)?[:\s]+[\"']?([A-Za-z][\w-]+)",
                _hyp_text, _re_hyp.IGNORECASE,
            )
            if _method_candidates or _baseline_candidates:
                logger.info(
                    "Stage 09: Extracted names from hypotheses: methods=%s, baselines=%s",
                    _method_candidates[:3], _baseline_candidates[:3],
                )
                plan = {
                    "topic": config.research.topic,
                    "generated": _utcnow_iso(),
                    "objectives": ["Evaluate hypotheses with controlled experiments"],
                    "datasets": ["primary_dataset"],
                    "baselines": _baseline_candidates[:3] or ["baseline_1", "baseline_2"],
                    "proposed_methods": _method_candidates[:3] or ["proposed_method"],
                    "ablations": ["without_key_component", "simplified_version"],
                    "metrics": [config.experiment.metric_key, "secondary_metric"],
                    "risks": ["validity threats", "confounding variables"],
                    "compute_budget": {"max_gpu": 1, "max_hours": 4},
                }

    if plan is None:
        # BUG-12: Use domain-aware names instead of fully generic placeholders
        _topic_prefix = config.research.topic.split()[0] if config.research.topic else "method"
        logger.warning(
            "Stage 09: LLM failed to produce valid experiment plan YAML. "
            "Using topic-derived fallback."
        )
        plan = {
            "topic": config.research.topic,
            "generated": _utcnow_iso(),
            "objectives": ["Evaluate hypotheses with controlled experiments"],
            "datasets": ["primary_dataset", "secondary_dataset"],
            "baselines": [f"{_topic_prefix}_baseline_1", f"{_topic_prefix}_baseline_2"],
            "proposed_methods": [f"{_topic_prefix}_proposed", f"{_topic_prefix}_variant"],
            "ablations": ["without_key_component", "simplified_version"],
            "metrics": [config.experiment.metric_key, "secondary_metric"],
            "risks": ["validity threats", "confounding variables"],
            "compute_budget": {"max_gpu": 1, "max_hours": 4},
        }
    # ── BA: BenchmarkAgent — intelligent dataset/baseline selection ──────
    _benchmark_plan = None
    # BUG-40: Skip BenchmarkAgent for non-ML domains — it has no relevant
    # benchmarks for physics/chemistry/mathematics/etc. and would inject
    # wrong datasets (e.g., CIFAR-10 for PDE topics).
    _ba_domain_id, _, _ = _detect_domain(
        config.research.topic,
        tuple(config.research.domains) if config.research.domains else (),
    )
    _ba_domain_ok = _ba_domain_id == "ml"
    if not _ba_domain_ok:
        logger.info(
            "BenchmarkAgent skipped: domain '%s' is not ML (topic: %s)",
            _ba_domain_id, config.research.topic[:80],
        )
    if (
        _ba_domain_ok
        and config.experiment.benchmark_agent.enabled
        and config.experiment.mode in ("sandbox", "docker")
        and llm is not None
    ):
        try:
            from researchclaw.agents.benchmark_agent import BenchmarkOrchestrator
            from researchclaw.agents.benchmark_agent.orchestrator import (
                BenchmarkAgentConfig as _BACfg,
            )

            _ba_cfg_raw = config.experiment.benchmark_agent
            _ba_cfg = _BACfg(
                enabled=_ba_cfg_raw.enabled,
                enable_hf_search=_ba_cfg_raw.enable_hf_search,
                max_hf_results=_ba_cfg_raw.max_hf_results,
                enable_web_search=_ba_cfg_raw.enable_web_search,
                max_web_results=_ba_cfg_raw.max_web_results,
                web_search_min_local=_ba_cfg_raw.web_search_min_local,
                tier_limit=_ba_cfg_raw.tier_limit,
                min_benchmarks=_ba_cfg_raw.min_benchmarks,
                min_baselines=_ba_cfg_raw.min_baselines,
                prefer_cached=_ba_cfg_raw.prefer_cached,
                max_iterations=_ba_cfg_raw.max_iterations,
            )

            _hw = _load_hardware_profile(run_dir)
            _ba = BenchmarkOrchestrator(
                llm,
                config=_ba_cfg,
                gpu_memory_mb=(
                    _hw.get("gpu_memory_mb", 49000) if _hw else 49000
                ),
                time_budget_sec=config.experiment.time_budget_sec,
                network_policy=_benchmark_network_policy(config),
                stage_dir=stage_dir / "benchmark_agent",
            )
            _benchmark_plan = _ba.orchestrate({
                "topic": config.research.topic,
                "hypothesis": hypotheses,
                "experiment_plan": plan.get("objectives", "") if isinstance(plan, dict) else "",
            })

            # Inject BenchmarkAgent selections into experiment plan
            if isinstance(plan, dict) and _benchmark_plan.selected_benchmarks:
                plan["datasets"] = [
                    b.get("name", "Unknown") for b in _benchmark_plan.selected_benchmarks
                ]
                # Normalize existing baselines to list of strings
                # BUG-35: LLM may emit baselines as dict, list of dicts,
                # or list of strings — normalize all to list[str].
                _baselines_from_plan = plan.get("baselines", [])
                if isinstance(_baselines_from_plan, dict):
                    _baselines_from_plan = list(_baselines_from_plan.keys())
                elif isinstance(_baselines_from_plan, list):
                    _baselines_from_plan = [
                        item["name"] if isinstance(item, dict) else str(item)
                        for item in _baselines_from_plan
                    ]
                else:
                    _baselines_from_plan = []
                plan["baselines"] = [
                    bl.get("name", "Unknown") for bl in _benchmark_plan.selected_baselines
                ] + _baselines_from_plan
                # Deduplicate baselines
                plan["baselines"] = list(dict.fromkeys(plan["baselines"]))

            logger.info(
                "BenchmarkAgent: %d benchmarks, %d baselines selected (%d LLM calls, %.1fs)",
                len(_benchmark_plan.selected_benchmarks),
                len(_benchmark_plan.selected_baselines),
                _benchmark_plan.total_llm_calls,
                _benchmark_plan.elapsed_sec,
            )
        except Exception as _ba_exc:
            logger.warning("BenchmarkAgent failed (non-fatal): %s", _ba_exc)

    # Save benchmark plan for code_generation stage
    if _benchmark_plan is not None:
        try:
            (stage_dir / "benchmark_plan.json").write_text(
                json.dumps(_benchmark_plan.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001
            pass

    plan.setdefault("topic", config.research.topic)

    # BUG-R41-09: Enforce condition count limit based on time budget.
    # Too many conditions (30+) guarantee timeouts and wasted compute.
    _time_budget = getattr(
        getattr(config, "experiment", None), "time_budget_sec", 3600
    )
    _max_conditions = 8
    if _time_budget > 3600:
        _max_conditions = 12
    if _time_budget > 12 * 3600:
        _max_conditions = 20
    if _time_budget > 24 * 3600:
        _max_conditions = 28
    if _time_budget > 72 * 3600:
        _max_conditions = 32

    _baselines = plan.get("baselines", [])
    if isinstance(_baselines, dict):
        _baselines = list(_baselines.values())
    _proposed = plan.get("proposed_methods", [])
    if isinstance(_proposed, dict):
        _proposed = list(_proposed.values())
    _ablations = plan.get("ablations", [])
    if isinstance(_ablations, dict):
        _ablations = list(_ablations.values())
    _total = len(_baselines) + len(_proposed) + len(_ablations)

    if _total > _max_conditions:
        logger.warning(
            "Stage 9: Plan has %d conditions (limit %d for %ds budget). "
            "Trimming to fit.",
            _total, _max_conditions, _time_budget,
        )
        # Preserve a defensible mix instead of collapsing coverage too aggressively.
        _proposed_count = min(len(_proposed), max(2, _max_conditions // 3))
        _remaining = max(0, _max_conditions - _proposed_count)
        _baseline_budget = min(len(_baselines), max(3, _remaining // 2))
        _ablation_budget = max(1, _remaining - _baseline_budget)
        if len(_proposed) > _proposed_count:
            plan["proposed_methods"] = _proposed[:_proposed_count]
            logger.info(
                "Stage 9: Trimmed proposed methods %d → %d",
                len(_proposed), _proposed_count,
            )

        if len(_baselines) > _baseline_budget:
            plan["baselines"] = _baselines[:_baseline_budget]
            logger.info(
                "Stage 9: Trimmed baselines %d → %d",
                len(_baselines), _baseline_budget,
            )
        if len(_ablations) > _ablation_budget:
            plan["ablations"] = _ablations[:_ablation_budget]
            logger.info(
                "Stage 9: Trimmed ablations %d → %d",
                len(_ablations), _ablation_budget,
            )

    (stage_dir / "exp_plan.yaml").write_text(
        yaml.dump(plan, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    _plan_yaml = yaml.dump(plan, default_flow_style=False, allow_unicode=True)
    (stage_dir / "exp_plan.meta.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sha256": hashlib.sha256(_plan_yaml.encode("utf-8")).hexdigest(),
                "generated": _utcnow_iso(),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    claims_matrix_md, claims_matrix_payload = _build_claims_evidence_matrix(
        config.research.topic,
        hypotheses,
        plan,
        config.experiment.metric_key,
    )
    (stage_dir / "claims_evidence_matrix.md").write_text(
        claims_matrix_md,
        encoding="utf-8",
    )
    (stage_dir / "claims_evidence_matrix.json").write_text(
        json.dumps(claims_matrix_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (stage_dir / "story_background.md").write_text(
        _build_story_background(config.research.topic, plan),
        encoding="utf-8",
    )
    (stage_dir / "experiment_coverage.md").write_text(
        _build_experiment_coverage_md(plan),
        encoding="utf-8",
    )
    (stage_dir / "baseline_coverage_checklist.md").write_text(
        _build_baseline_coverage_checklist(run_dir, plan),
        encoding="utf-8",
    )
    adequacy_md, adequacy_payload = _build_experiment_adequacy_report(
        run_dir=run_dir,
        config=config,
        plan=plan,
    )
    (stage_dir / "experiment_adequacy_report.md").write_text(
        adequacy_md,
        encoding="utf-8",
    )
    (stage_dir / "experiment_adequacy_report.json").write_text(
        json.dumps(adequacy_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return StageResult(
        stage=Stage.EXPERIMENT_DESIGN,
        status=StageStatus.DONE,
        artifacts=(
            "exp_plan.yaml",
            "exp_plan.meta.json",
            "claims_evidence_matrix.md",
            "claims_evidence_matrix.json",
            "story_background.md",
            "experiment_coverage.md",
            "baseline_coverage_checklist.md",
            "experiment_adequacy_report.md",
            "experiment_adequacy_report.json",
        ),
        evidence_refs=(
            "stage-09/exp_plan.yaml",
            "stage-09/claims_evidence_matrix.md",
            "stage-09/claims_evidence_matrix.json",
            "stage-09/story_background.md",
            "stage-09/experiment_coverage.md",
            "stage-09/baseline_coverage_checklist.md",
            "stage-09/experiment_adequacy_report.md",
            "stage-09/experiment_adequacy_report.json",
        ),
        control_hints={
            "adequacy_verdict": adequacy_payload["verdict"],
            "adequacy_score": adequacy_payload["score"],
            "adequacy_max_score": adequacy_payload["max_score"],
        },
    )
