"""Structured claims-evidence matrix and graph utilities."""

from __future__ import annotations

import re
from typing import Any

from researchclaw.pipeline._helpers import _normalize_named_list, _utcnow_iso


def _extract_claims(text: str, *, max_items: int = 3) -> list[str]:
    claims: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^[-*#\s]*", "", line)
        line = re.sub(r"^(H\d+|C\d+)[:.)]\s*", "", line, flags=re.IGNORECASE)
        if len(line) >= 24:
            claims.append(line.rstrip("."))
        if len(claims) >= max_items:
            break
    return claims


def _graph_label(text: str, *, limit: int = 72) -> str:
    label = re.sub(r"\s+", " ", text).strip()
    label = label.replace('"', "'").replace("[", "(").replace("]", ")")
    if len(label) > limit:
        label = label[: limit - 3].rstrip() + "..."
    return label


def build_claim_graph_mermaid(payload: dict[str, Any]) -> str:
    """Build a Mermaid graph that links claims to required evidence."""
    lines = ["graph TD"]
    for claim in payload.get("claims", []):
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("claim_id") or "claim")
        claim_label = _graph_label(str(claim.get("claim") or claim_id))
        lines.append(f'  {claim_id}["{claim_id}: {claim_label}"]')
        for idx, evidence in enumerate(claim.get("required_evidence", []) or [], start=1):
            evidence_id = f"E_{claim_id}_{idx}"
            evidence_label = _graph_label(str(evidence))
            lines.append(f'  {evidence_id}["{evidence_label}"]')
            lines.append(f"  {claim_id} --> {evidence_id}")
        failure_signal = str(claim.get("failure_signal") or "").strip()
        if failure_signal:
            failure_id = f"F_{claim_id}"
            lines.append(f'  {failure_id}{{"{_graph_label(failure_signal)}"}}')
            lines.append(f"  {failure_id} -. downgrades .-> {claim_id}")
    return "\n".join(lines) + "\n"


def build_claims_evidence_matrix(
    topic: str,
    hypotheses: str,
    plan: dict[str, Any],
    metric_key: str,
) -> tuple[str, dict[str, Any], str]:
    """Return Markdown, structured payload, and Mermaid graph for claim evidence."""
    claims = _extract_claims(hypotheses, max_items=3)
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
        claim_id = f"C{idx}"
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
            "claim_id": claim_id,
            "claim": claim,
            "status": "planned",
            "proposed_methods": targeted_methods,
            "baselines": baselines[: min(3, len(baselines))],
            "ablations": supporting_ablations,
            "datasets": datasets[: min(4, len(datasets))],
            "metrics": metrics[: min(3, len(metrics))],
            "required_evidence": required_evidence,
            "linked_artifacts": [],
            "linked_metrics": [],
            "failure_signal": (
                "Claim must be downgraded or removed if the proposed method fails "
                "to beat or match strong baselines under the planned metrics/regimes."
            ),
        }
        rows.append(row)

        md_lines.extend(
            [
                f"## {claim_id}",
                f"- Claim: {claim}",
                f"- Status: {row['status']}",
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
        md_lines.extend([f"- Failure signal: {row['failure_signal']}", ""])

    if objectives:
        md_lines.extend(["## Must-Run Order", *(f"- {objective}" for objective in objectives), ""])

    payload = {
        "schema_version": 1,
        "topic": topic,
        "generated": _utcnow_iso(),
        "claims": rows,
        "must_run_order": objectives,
    }
    return "\n".join(md_lines).rstrip() + "\n", payload, build_claim_graph_mermaid(payload)
