# Procedure Evidence Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make skills, claims, and evidence auditable through structured contracts and ledgers.

**Architecture:** Extend existing `researchclaw.skills`, add focused `researchclaw.evidence` helpers, and extend `researchclaw.lineage`. Integrate new artifacts into Stage 9 and Stage 15 without changing existing Markdown outputs.

**Tech Stack:** Python dataclasses, JSON, YAML via PyYAML, Mermaid graph text, pytest.

---

### Task 1: Procedure Contract Schema

**Files:**
- Modify: `researchclaw/skills/schema.py`
- Modify: `researchclaw/skills/loader.py`
- Test: `tests/test_procedure_evidence_contracts.py`

- [ ] Add tests that a skill can load and validate ordered procedure steps.
- [ ] Add `ProcedureStep`, `ProcedureContract`, and validation helpers.
- [ ] Preserve backward compatibility for skills without contracts.

### Task 2: Structured Claim Matrix And Graph

**Files:**
- Create: `researchclaw/evidence/__init__.py`
- Create: `researchclaw/evidence/claims.py`
- Modify: `researchclaw/pipeline/stage_impls/_experiment_design.py`
- Test: `tests/test_procedure_evidence_contracts.py`

- [ ] Add tests for JSON/YAML dictionaries and Mermaid graph output.
- [ ] Move claim-matrix construction into a reusable evidence helper.
- [ ] Have Stage 9 write `claims_evidence_matrix.yaml` and `claim_graph.mmd`.

### Task 3: Formal Evidence Ledger

**Files:**
- Modify: `researchclaw/lineage/ledger.py`
- Modify: `researchclaw/pipeline/stage_impls/_analysis.py`
- Test: `tests/test_procedure_evidence_contracts.py`

- [ ] Add tests for negative results, failed experiments, and unsupported claims.
- [ ] Extend `LineageLedger` with evidence event records and validation.
- [ ] Have Stage 15 write `evidence_ledger.json` from claims and experiment results.

### Task 4: Verification And Main Update

**Files:**
- Modify: `.github/workflows/ci.yml` only if clean checkout requires it.

- [ ] Run focused tests.
- [ ] Run CI-equivalent local pytest.
- [ ] Review git diff for unrelated changes.
- [ ] Commit locally.
- [ ] Update GitHub `main` directly after verification.
