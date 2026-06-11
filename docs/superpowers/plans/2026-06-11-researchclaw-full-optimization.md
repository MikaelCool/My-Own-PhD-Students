# ResearchClaw Full Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the full optimization foundation for benchmarked, traceable, reproducible, and learnable autonomous research.

**Architecture:** Add stdlib-only infrastructure modules that integrate with the current pipeline without rewriting the 23-stage runner. Keep compatibility with existing tests and expose typed interfaces for future deeper refactors.

**Tech Stack:** Python 3.11+, dataclasses, JSON, pytest, GitHub Actions.

---

### Task 1: Engineering Baseline

**Files:**
- Modify: `pyproject.toml`
- Create: `.github/workflows/ci.yml`

- [ ] Add missing dev dependencies: `pytest-asyncio`, `fastapi`, `uvicorn`, and `httpx`.
- [ ] Register the `asyncio` marker.
- [ ] Add CI for Python 3.11 and 3.12 with editable dev install and `pytest -q`.

### Task 2: Observability

**Files:**
- Create: `researchclaw/observability/__init__.py`
- Create: `researchclaw/observability/tracing.py`
- Modify: `researchclaw/pipeline/control_state.py`
- Test: `tests/test_research_foundation.py`

- [ ] Add `TraceContext` with `trace_id`, `span_id`, `parent_span_id`, `run_id`, `stage`, and metadata.
- [ ] Add event normalization with token, cost, latency, model, prompt, artifact hash, decision, and rollback fields.
- [ ] Propagate trace metadata through `append_supervisor_event`.

### Task 3: Research Lineage

**Files:**
- Create: `researchclaw/lineage/__init__.py`
- Create: `researchclaw/lineage/ledger.py`
- Test: `tests/test_research_foundation.py`

- [ ] Add typed records for datasets, code, metrics, artifacts, and decisions.
- [ ] Add SHA-256 helpers and JSON export/import.
- [ ] Add validation for untagged simulation data, missing metric direction, and missing selection rules.

### Task 4: ResearchClawBench

**Files:**
- Create: `researchclaw/bench/__init__.py`
- Create: `researchclaw/bench/core.py`
- Test: `tests/test_research_foundation.py`

- [ ] Add benchmark task, metric, result, and report dataclasses.
- [ ] Add objective aggregation and pass/fail handling.
- [ ] Add a JSON report format for dashboards and regression tracking.

### Task 5: Adaptive Orchestration

**Files:**
- Create: `researchclaw/policy/__init__.py`
- Create: `researchclaw/policy/orchestration.py`
- Test: `tests/test_research_foundation.py`

- [ ] Add deterministic policy inputs for coupling, parallelism, risk, uncertainty, and budget.
- [ ] Return centralized, single-agent, or parallel multi-agent decisions with reasons.
- [ ] Force human review on high-risk scientific decisions.

### Task 6: Post-Training Trajectories

**Files:**
- Create: `researchclaw/post_training/__init__.py`
- Create: `researchclaw/post_training/trajectory.py`
- Test: `tests/test_research_foundation.py`

- [ ] Add process-level transition records.
- [ ] Add trajectory reward summaries.
- [ ] Add JSONL export compatible with offline optimization pipelines.

### Task 7: Skill Matcher Upgrade

**Files:**
- Modify: `researchclaw/skills/matcher.py`
- Test: `tests/test_research_foundation.py`

- [ ] Keep the current matcher API backward compatible.
- [ ] Add optional active skill conflicts, token budget band, and control category filters.
- [ ] Score expected gain and token cost when metadata exists.

### Task 8: Verification and Publish

**Files:**
- All modified files.

- [ ] Run targeted tests for the new optimization foundation.
- [ ] Run full `pytest -q`.
- [ ] Inspect `git diff`.
- [ ] Commit on `codex/full-researchclaw-optimization`.
- [ ] Push to GitHub and open a draft PR.
