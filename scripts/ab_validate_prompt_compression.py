#!/usr/bin/env python3
"""A/B validation for prompt compression quality.

Runs a real Stage 9 old-vs-new prompt comparison via Codex CLI and a
deterministic Stage 10 information-preservation audit.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from researchclaw.config import RCConfig
from researchclaw.pipeline._helpers import (
    _build_context_preamble,
    _build_experiment_plan_summary,
    _compact_markdown_context,
    _compress_instruction_block,
    _extract_yaml_block,
    _get_evolution_overlay,
    _load_baseline_briefing,
    _read_prior_artifact,
)
from researchclaw.pipeline.research_governor import (
    build_phase_charter,
    build_stage_skill_overlay,
)
from researchclaw.prompts import PromptManager, RenderedPrompt


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _load_config(repo_root: Path) -> RCConfig:
    return RCConfig.load(repo_root / "config.arc.yaml", check_paths=False)


def _load_prompt_manager(config: RCConfig) -> PromptManager:
    custom = config.prompts.custom_file or None
    return PromptManager(custom)


def _shared_stage9_dataset_guidance(
    config: RCConfig,
    hypotheses: str,
) -> str:
    pm = _load_prompt_manager(config)
    block = ""
    try:
        block = pm.block("dataset_guidance")
    except Exception:
        block = ""
    try:
        from researchclaw.data import detect_frameworks, load_framework_docs

        fw_ids = detect_frameworks(config.research.topic, hypotheses)
        if fw_ids:
            docs = load_framework_docs(fw_ids, max_chars=1500)
            if docs:
                block += docs
    except Exception:
        pass
    return block


def _build_old_stage9_prompt(config: RCConfig, run_dir: Path) -> RenderedPrompt:
    pm = _load_prompt_manager(config)
    hypotheses = _read_prior_artifact(run_dir, "hypotheses.md") or ""
    synthesis = _read_prior_artifact(run_dir, "synthesis.md") or ""
    problem_anchor = _read_prior_artifact(run_dir, "problem_anchor.md") or ""

    preamble = _build_context_preamble(
        config,
        run_dir,
        compact=False,
        include_goal=True,
        include_problem_anchor=True,
        include_hypotheses=True,
    )
    overlay = (
        _get_evolution_overlay(run_dir, "experiment_design")
        + "\n"
        + build_phase_charter("experiment_design")
        + "\n"
        + build_stage_skill_overlay(
            config,
            stage_name="experiment_design",
            context="\n\n".join((hypotheses[:1800], synthesis[:1800], problem_anchor[:1200])),
            max_chars=2400,
        )
    )
    baseline_briefing = _load_baseline_briefing(config, max_chars=12000)
    return pm.for_stage(
        "experiment_design",
        evolution_overlay=overlay,
        preamble=preamble,
        hypotheses=hypotheses,
        baseline_briefing=baseline_briefing,
        dataset_guidance=_shared_stage9_dataset_guidance(config, hypotheses),
        time_budget_sec=config.experiment.time_budget_sec,
        metric_key=config.experiment.metric_key,
        metric_direction=config.experiment.metric_direction,
        hardware_profile="-",
        per_condition_budget_sec=max(1, int(config.experiment.time_budget_sec * 0.7 / 6)),
        available_tier1_datasets="-",
    )


def _build_new_stage9_prompt(config: RCConfig, run_dir: Path) -> RenderedPrompt:
    pm = _load_prompt_manager(config)
    hypotheses = _read_prior_artifact(run_dir, "hypotheses.md") or ""
    synthesis = _read_prior_artifact(run_dir, "synthesis.md") or ""
    problem_anchor = _read_prior_artifact(run_dir, "problem_anchor.md") or ""

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
    overlay = (
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
    compact_hypotheses = (
        "Source artifact: `stage-08/hypotheses.md`\n"
        "- Read the source artifact on disk if exact wording is needed.\n"
        + _compact_markdown_context(hypotheses, max_chars=2200, max_items=12)
    ).strip()
    baseline_briefing = _compact_markdown_context(
        _load_baseline_briefing(config, max_chars=12000),
        max_chars=1800,
        max_items=10,
    )
    return pm.for_stage(
        "experiment_design",
        evolution_overlay=overlay,
        preamble=preamble,
        hypotheses=compact_hypotheses or hypotheses,
        baseline_briefing=baseline_briefing,
        dataset_guidance=_shared_stage9_dataset_guidance(config, hypotheses),
        time_budget_sec=config.experiment.time_budget_sec,
        metric_key=config.experiment.metric_key,
        metric_direction=config.experiment.metric_direction,
        hardware_profile="-",
        per_condition_budget_sec=max(1, int(config.experiment.time_budget_sec * 0.7 / 6)),
        available_tier1_datasets="-",
    )


def _build_old_stage10_prompt(config: RCConfig, run_dir: Path) -> RenderedPrompt:
    pm = _load_prompt_manager(config)
    exp_plan = _read_prior_artifact(run_dir, "exp_plan.yaml") or ""
    metric = config.experiment.metric_key
    prompt_instruction_bundle = _compress_instruction_block(
        "\n".join(
            part for part in (
                pm.block("pkg_hint_sandbox") if "pkg_hint_sandbox" in pm._blocks else "",
                (
                    "\n## Compute Budget Constraint\n"
                    f"- Total execution time limit: {config.experiment.time_budget_sec} seconds\n"
                    "- Design experiments that complete within this budget\n"
                ),
            )
            if part
        ),
        max_chars=20000,
    )
    return pm.for_stage(
        "code_generation",
        evolution_overlay=_get_evolution_overlay(run_dir, "code_generation"),
        topic=config.research.topic,
        metric=metric,
        pkg_hint=prompt_instruction_bundle,
        exp_plan=exp_plan,
        metric_direction_hint="",
    )


def _build_new_stage10_prompt(config: RCConfig, run_dir: Path) -> RenderedPrompt:
    pm = _load_prompt_manager(config)
    exp_plan = _read_prior_artifact(run_dir, "exp_plan.yaml") or ""
    metric = config.experiment.metric_key
    compact_plan = _build_experiment_plan_summary(exp_plan, run_dir=run_dir, max_chars=4700)
    prompt_instruction_bundle = _compress_instruction_block(
        "\n".join(
            part for part in (
                pm.block("pkg_hint_sandbox") if "pkg_hint_sandbox" in pm._blocks else "",
                (
                    "\n## Compute Budget Constraint\n"
                    f"- Total execution time limit: {config.experiment.time_budget_sec} seconds\n"
                    "- Design experiments that complete within this budget\n"
                ),
            )
            if part
        ),
        max_chars=5200,
    )
    return pm.for_stage(
        "code_generation",
        evolution_overlay=_get_evolution_overlay(run_dir, "code_generation"),
        topic=config.research.topic,
        metric=metric,
        pkg_hint=prompt_instruction_bundle,
        exp_plan=compact_plan or exp_plan,
        metric_direction_hint="",
    )


def _flatten_prompt(sp: RenderedPrompt) -> str:
    return f"[System]\n{sp.system}\n\n{sp.user}".strip() + "\n"


def _run_codex_prompt(
    *,
    repo_root: Path,
    prompt_text: str,
    work_dir: Path,
    timeout_sec: int,
    resume_if_present: bool = True,
) -> dict[str, Any]:
    output_path = work_dir / "last_message.txt"
    meta_path = work_dir / "runner.json"
    if resume_if_present and output_path.exists():
        content = output_path.read_text(encoding="utf-8").strip()
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if isinstance(meta, dict):
                    meta["content"] = content
                    return meta
            except Exception:
                pass
        return {
            "returncode": 0,
            "elapsed_sec": None,
            "stdout_tail": "",
            "stderr_tail": "",
            "content": content,
            "resumed": True,
        }
    t0 = time.time()
    try:
        proc = subprocess.run(
            [
                "codex",
                "exec",
                "-C",
                str(repo_root),
                "--full-auto",
                "--skip-git-repo-check",
                "--output-last-message",
                str(output_path),
            ],
            input=prompt_text,
            text=True,
            capture_output=True,
            timeout=timeout_sec,
        )
        elapsed = time.time() - t0
        content = output_path.read_text(encoding="utf-8").strip() if output_path.exists() else ""
        payload = {
            "returncode": proc.returncode,
            "elapsed_sec": round(elapsed, 2),
            "stdout_tail": (proc.stdout or "")[-4000:],
            "stderr_tail": (proc.stderr or "")[-4000:],
            "content": content,
            "resumed": False,
        }
    except subprocess.TimeoutExpired as exc:
        elapsed = time.time() - t0
        content = output_path.read_text(encoding="utf-8").strip() if output_path.exists() else ""
        payload = {
            "returncode": -1,
            "elapsed_sec": round(elapsed, 2),
            "stdout_tail": ((exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else ""),
            "stderr_tail": ((exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else ""),
            "content": content,
            "timed_out": True,
            "resumed": False,
        }
    meta_path.write_text(json.dumps({k: v for k, v in payload.items() if k != "content"}, indent=2), encoding="utf-8")
    return payload


def _parse_yaml_payload(text: str) -> dict[str, Any] | None:
    raw_yaml = _extract_yaml_block(text)
    candidates = [raw_yaml, text]
    for candidate in candidates:
        if not candidate.strip():
            continue
        try:
            parsed = yaml.safe_load(candidate)
        except yaml.YAMLError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
    return None


def _contains_any(value: Any, patterns: list[str]) -> bool:
    text = json.dumps(value, ensure_ascii=False).lower()
    return any(pattern in text for pattern in patterns)


def _score_stage9_plan(plan: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(plan, dict):
        return {
            "score": 0,
            "breakdown": {"parseable_yaml": 0},
            "issues": ["response is not parseable YAML"],
        }

    score = 0
    breakdown: dict[str, int] = {}
    issues: list[str] = []

    required = [
        "objectives",
        "datasets",
        "baselines",
        "proposed_methods",
        "ablations",
        "metrics",
        "risks",
        "compute_budget",
        "story_background",
        "target_sota_context",
        "baseline_failure_modes",
        "must_run_experiments",
        "nice_to_have_experiments",
        "stop_conditions",
    ]
    missing = [key for key in required if key not in plan]
    parse_score = 20 if not missing else max(0, 20 - 2 * len(missing))
    score += parse_score
    breakdown["schema"] = parse_score
    if missing:
        issues.append("missing keys: " + ", ".join(missing))

    richness = 0
    count_specs = {
        "baselines": (3, 6),
        "proposed_methods": (2, 5),
        "ablations": (2, 4),
        "datasets": (1, 2),
        "metrics": (2, 3),
        "must_run_experiments": (2, 4),
        "nice_to_have_experiments": (1, 2),
    }
    for key, (threshold, pts) in count_specs.items():
        items = plan.get(key)
        if isinstance(items, list) and len(items) >= threshold:
            richness += pts
        else:
            issues.append(f"{key} below threshold {threshold}")
    score += richness
    breakdown["richness"] = richness

    fairness = 0
    if _contains_any(plan.get("must_run_experiments"), ["reproduce", "replicate", "baseline"]):
        fairness += 6
    else:
        issues.append("must_run_experiments does not clearly require baseline reproduction")
    if _contains_any(plan.get("ablations"), ["ablation", "remove", "without", "component"]):
        fairness += 4
    else:
        issues.append("ablations are weakly specified")
    if _contains_any(plan.get("metrics"), ["std", "variance", "confidence", "significance", "seed", "throughput", "memory", "latency"]):
        fairness += 5
    else:
        issues.append("metrics lack statistical/efficiency signals")
    score += fairness
    breakdown["fairness"] = fairness

    story = 0
    if str(plan.get("story_background", "")).strip():
        story += 8
    else:
        issues.append("story_background is empty")
    if str(plan.get("target_sota_context", "")).strip():
        story += 4
    else:
        issues.append("target_sota_context is empty")
    failure_modes = plan.get("baseline_failure_modes")
    if isinstance(failure_modes, list) and failure_modes:
        story += 4
    else:
        issues.append("baseline_failure_modes is empty")
    score += story
    breakdown["story"] = story

    control = 0
    stop_conditions = plan.get("stop_conditions")
    if isinstance(stop_conditions, list) and stop_conditions:
        control += 8
    else:
        issues.append("stop_conditions is empty")
    risks = plan.get("risks")
    if isinstance(risks, list) and len(risks) >= 2:
        control += 6
    else:
        issues.append("risks are underspecified")
    score += control
    breakdown["control"] = control

    return {
        "score": score,
        "breakdown": breakdown,
        "issues": issues,
    }


def _compact_plan_item_strings(plan: dict[str, Any], key: str) -> list[str]:
    value = plan.get(key)
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("name") or item.get("id") or item.get("title")
                if text:
                    out.append(str(text))
            elif str(item).strip():
                out.append(str(item).strip())
        return out
    if isinstance(value, dict):
        return [str(k).strip() for k in value.keys() if str(k).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _audit_stage10_information_preservation(exp_plan_text: str, compact_summary: str) -> dict[str, Any]:
    try:
        plan = yaml.safe_load(exp_plan_text)
    except yaml.YAMLError:
        plan = None
    if not isinstance(plan, dict):
        return {
            "ok": False,
            "issues": ["exp_plan.yaml is not parseable"],
            "coverage": {},
        }

    summary_lower = compact_summary.lower()
    coverage: dict[str, dict[str, Any]] = {}
    issues: list[str] = []
    for key in (
        "datasets",
        "baselines",
        "proposed_methods",
        "ablations",
        "metrics",
        "must_run_experiments",
        "nice_to_have_experiments",
        "stop_conditions",
    ):
        items = _compact_plan_item_strings(plan, key)
        missing = [item for item in items if item.lower() not in summary_lower]
        coverage[key] = {
            "total": len(items),
            "covered": len(items) - len(missing),
            "missing": missing,
        }
        if missing:
            issues.append(f"{key} missing from compact summary: {missing[:5]}")

    return {
        "ok": not issues,
        "issues": issues,
        "coverage": coverage,
    }


def _judge_pairwise(
    *,
    repo_root: Path,
    old_yaml: str,
    new_yaml: str,
    work_dir: Path,
    timeout_sec: int,
) -> dict[str, Any]:
    judge_prompt = f"""
[System]
You are a strict research-planning evaluator. Compare two experiment plans and output JSON only.

Rubric:
- baseline_fairness: Does it reproduce strong baselines before extending claims?
- experiment_depth: Does it include robust must-run experiments, ablations, failure cases, and useful metrics?
- story_quality: Is there a concrete, believable problem story with target regime and failure modes?
- resource_realism: Is the plan aligned with a constrained real GPU budget instead of fantasy scope?
- paperability: Is it suitable as a strong foundation for later analysis and paper writing?

Return JSON:
{{
  "winner": "old|new|tie",
  "old": {{"total": 0-10, "strengths": ["..."], "weaknesses": ["..."]}},
  "new": {{"total": 0-10, "strengths": ["..."], "weaknesses": ["..."]}},
  "decision_rationale": "..."
}}

Plan OLD:
```yaml
{old_yaml[:12000]}
```

Plan NEW:
```yaml
{new_yaml[:12000]}
```
""".strip() + "\n"
    result = _run_codex_prompt(
        repo_root=repo_root,
        prompt_text=judge_prompt,
        work_dir=work_dir,
        timeout_sec=timeout_sec,
    )
    try:
        payload = json.loads(result["content"])
    except Exception:
        payload = {
            "parse_error": True,
            "raw": result["content"][:4000],
        }
    return {"runner": result, "payload": payload}


def _markdown_report(payload: dict[str, Any]) -> str:
    ab = payload["stage9_ab"]
    judge = payload["stage9_judge"]["payload"]
    lines = [
        "# Prompt Compression A/B Validation",
        "",
        "## Summary",
        f"- Stage 9 old prompt chars: {ab['old']['prompt_chars']}",
        f"- Stage 9 new prompt chars: {ab['new']['prompt_chars']}",
        f"- Stage 9 old score: {ab['old']['rule_score']['score']}",
        f"- Stage 9 new score: {ab['new']['rule_score']['score']}",
        f"- Stage 10 old prompt chars: {payload['stage10']['old_prompt_chars']}",
        f"- Stage 10 new prompt chars: {payload['stage10']['new_prompt_chars']}",
        f"- Stage 10 preservation ok: {payload['stage10']['preservation']['ok']}",
        "",
        "## Pairwise Judge",
        f"- Winner: {judge.get('winner', 'unknown')}",
        f"- Rationale: {judge.get('decision_rationale', 'n/a')}",
        "",
        "## Old Prompt",
        f"- Elapsed: {ab['old']['runner']['elapsed_sec']}s",
        f"- Return code: {ab['old']['runner']['returncode']}",
        f"- Issues: {', '.join(ab['old']['rule_score']['issues'][:8]) if ab['old']['rule_score']['issues'] else 'none'}",
        "",
        "## New Prompt",
        f"- Elapsed: {ab['new']['runner']['elapsed_sec']}s",
        f"- Return code: {ab['new']['runner']['returncode']}",
        f"- Issues: {', '.join(ab['new']['rule_score']['issues'][:8]) if ab['new']['rule_score']['issues'] else 'none'}",
        "",
        "## Stage 10 Preservation",
    ]
    issues = payload["stage10"]["preservation"]["issues"]
    if issues:
        lines.extend(f"- {issue}" for issue in issues[:20])
    else:
        lines.append("- All tracked high-signal plan items were preserved in the compact summary.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, help="Artifact run dir to use as context")
    parser.add_argument("--timeout-sec", type=int, default=900)
    parser.add_argument(
        "--output-dir",
        default="",
        help="Directory for evaluation artifacts (default: .researchclaw/evals/<timestamp>)",
    )
    args = parser.parse_args()

    repo_root = REPO_ROOT
    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.exists():
        raise SystemExit(f"run dir not found: {run_dir}")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else (repo_root / ".researchclaw" / "evals" / f"prompt-ab-{stamp}")
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    config = _load_config(repo_root)

    old_stage9 = _build_old_stage9_prompt(config, run_dir)
    new_stage9 = _build_new_stage9_prompt(config, run_dir)
    old_prompt_text = _flatten_prompt(old_stage9)
    new_prompt_text = _flatten_prompt(new_stage9)

    old_dir = output_dir / "stage9_old"
    new_dir = output_dir / "stage9_new"
    judge_dir = output_dir / "stage9_judge"
    old_dir.mkdir(exist_ok=True)
    new_dir.mkdir(exist_ok=True)
    judge_dir.mkdir(exist_ok=True)

    old_runner = _run_codex_prompt(
        repo_root=repo_root,
        prompt_text=old_prompt_text,
        work_dir=old_dir,
        timeout_sec=args.timeout_sec,
    )
    new_runner = _run_codex_prompt(
        repo_root=repo_root,
        prompt_text=new_prompt_text,
        work_dir=new_dir,
        timeout_sec=args.timeout_sec,
    )

    old_plan = _parse_yaml_payload(old_runner["content"])
    new_plan = _parse_yaml_payload(new_runner["content"])
    old_score = _score_stage9_plan(old_plan)
    new_score = _score_stage9_plan(new_plan)

    old_yaml_text = yaml.safe_dump(old_plan, allow_unicode=True, sort_keys=False) if isinstance(old_plan, dict) else old_runner["content"]
    new_yaml_text = yaml.safe_dump(new_plan, allow_unicode=True, sort_keys=False) if isinstance(new_plan, dict) else new_runner["content"]
    judge = _judge_pairwise(
        repo_root=repo_root,
        old_yaml=old_yaml_text,
        new_yaml=new_yaml_text,
        work_dir=judge_dir,
        timeout_sec=min(args.timeout_sec, 600),
    )

    old_stage10 = _build_old_stage10_prompt(config, run_dir)
    new_stage10 = _build_new_stage10_prompt(config, run_dir)
    exp_plan_text = _read_prior_artifact(run_dir, "exp_plan.yaml") or ""
    compact_plan = _build_experiment_plan_summary(exp_plan_text, run_dir=run_dir, max_chars=4700)
    preservation = _audit_stage10_information_preservation(exp_plan_text, compact_plan)

    report = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "run_dir": str(run_dir),
        "stage9_ab": {
            "old": {
                "prompt_chars": len(old_prompt_text),
                "runner": old_runner,
                "rule_score": old_score,
            },
            "new": {
                "prompt_chars": len(new_prompt_text),
                "runner": new_runner,
                "rule_score": new_score,
            },
        },
        "stage9_judge": judge,
        "stage10": {
            "old_prompt_chars": len(_flatten_prompt(old_stage10)),
            "new_prompt_chars": len(_flatten_prompt(new_stage10)),
            "compact_plan_chars": len(compact_plan),
            "preservation": preservation,
        },
    }

    _json_dump(output_dir / "report.json", report)
    (output_dir / "report.md").write_text(_markdown_report(report), encoding="utf-8")
    (output_dir / "stage9_old" / "prompt.txt").write_text(old_prompt_text, encoding="utf-8")
    (output_dir / "stage9_new" / "prompt.txt").write_text(new_prompt_text, encoding="utf-8")
    print(output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
