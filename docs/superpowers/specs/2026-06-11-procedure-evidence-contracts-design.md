# Procedure Evidence Contracts Design

## Goal

Upgrade ResearchClaw's research governance from prompt-only guidance into testable, machine-readable contracts for skills, claims, and evidence.

## Design

### Skill Procedure Contracts

Skills remain compatible with existing `SKILL.md`, YAML, and JSON loaders, but may now carry a `procedure_contract`. The contract defines explicit ordered steps, required inputs, expected outputs, verification checks, and failure modes. A skill is still injectable as prompt text, but the system can also validate whether it is executable as a procedure before selecting it for a high-risk stage.

### Structured Claim Evidence Matrix

The existing `claims_evidence_matrix.md` remains for human reading. The canonical source becomes a structured claim matrix containing claim nodes, evidence requirements, status, linked metrics, linked artifacts, and failure signals. Stage 9 writes JSON, YAML, and a Mermaid claim graph so reviewers can inspect claim dependencies and missing evidence visually.

### Evidence Ledger

The lineage ledger becomes the formal evidence ledger as well as the reproducibility ledger. It records positive evidence, negative results, failed experiments, and unsupported claims with source artifacts and affected claim IDs. Stage 15 writes `evidence_ledger.json` from claims and experiment results so paper-writing stages can distinguish "unsupported" from "failed" and "negative but informative".

## Error Handling

Invalid procedure contracts return deterministic `LineageIssue`-style validation records instead of raising during normal registry loading. Claim graphs escape special characters so graph rendering cannot corrupt the artifact. Ledger validation flags unsupported claims without claim IDs, failed experiments without failure modes, and result records without source artifacts.

## Testing

Tests cover red/green behavior for contract validation, JSON/YAML/Mermaid claim exports, ledger persistence of unsupported and failed evidence, and Stage 9/15 integration artifacts.
