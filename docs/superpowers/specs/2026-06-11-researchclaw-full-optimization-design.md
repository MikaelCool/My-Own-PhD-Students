# ResearchClaw Full Optimization Design

## Goal

Upgrade ResearchClaw from a feature-rich autonomous research pipeline into a benchmarked, traceable, reproducible, and learnable Research OS.

## Scope

This design implements the full optimization direction as infrastructure and integration points:

- Reproducible engineering baseline with CI and complete dev test dependencies.
- Structured observability for every run event.
- Research lineage ledger for datasets, code, metrics, artifacts, selection rules, and simulation boundaries.
- ResearchClawBench primitives for stage-level and workflow-level evaluation.
- Adaptive orchestration policy for single-agent, centralized, and parallel multi-agent execution.
- Post-training trajectory records suitable for future DSPy, bandit, Agent Lightning, or RL pipelines.
- Skill matching that uses expected gain, token cost, conflicts, and control category instead of only keyword overlap.

Large stage-file refactors are intentionally deferred behind typed interfaces. The first optimization release must stay compatible with the existing 23-stage runner.

## Architecture

### Observability

Add a small stdlib-only tracing package that creates stable trace/span identifiers and normalizes event payloads. It records model version, prompt version, token counts, cost, latency, artifact hashes, decision reasons, and rollback reasons. Existing `run_index.json` supervisor events will include this context when available.

### Provenance

Add a research lineage ledger that stores immutable evidence records:

- dataset records: name, version, split, hash, source, leakage status;
- code records: commit, command, environment image, dependency hash;
- metric records: name, value, direction, source artifact;
- artifact records: path, sha256, role, simulated flag;
- decision records: selected branch, rejected branches, rule, human reviewer.

The ledger validates common failure modes: untagged simulated artifacts, missing metric direction, missing selection rule, and non-hashed artifact paths.

### Benchmarking

Add `researchclaw.bench` as a lightweight benchmark kernel. It defines benchmark tasks, stage results, objective metrics, and aggregate reports. This does not vendor external benchmarks; it gives ResearchClaw a stable adapter surface for ScienceAgentBench, RE-Bench, MLAgentBench, PostTrainBench, and internal cases.

### Orchestration

Add an adaptive policy module. Sequential/high-coupling tasks use centralized execution. Parallel literature screening, candidate experiments, and peer review can use multi-agent fanout with explicit branch budgets and stop rules. High-risk decisions force human review.

### Post-Training Data

Add trajectory records with `state`, `action`, `artifact_refs`, `reward`, `cost`, `next_state`, and `terminal` fields. This is the boundary for future RL or prompt optimization. The project will not train policies until objective rewards are reliable.

### Skill Matching

Extend the existing matcher to account for:

- expected gain bands;
- token cost bands under low/medium/high budgets;
- conflict skills;
- required control category;
- precondition text matches.

The old API remains backward compatible.

## Data Flow

1. A pipeline stage starts and receives a trace context.
2. Each meaningful tool/model/decision event is normalized and appended to the run index.
3. Stage outputs register artifacts and metrics into the lineage ledger.
4. Benchmark adapters score stage outputs with objective metrics.
5. Orchestration policy records why it chose single-agent, centralized, or multi-agent execution.
6. The trajectory exporter emits process-level training data only after the above records exist.

## Error Handling

- Missing or corrupt tracing inputs fall back to generated IDs and empty metadata.
- Ledger validation returns structured issues instead of raising by default.
- Benchmark aggregation treats missing required metrics as failed results.
- Policy selection is deterministic and explainable.
- Skill matching keeps old behavior when new metadata is absent.

## Testing

Tests cover:

- trace context creation and event normalization;
- supervisor event trace propagation;
- lineage ledger validation;
- benchmark aggregation;
- adaptive orchestration decisions;
- post-training trajectory serialization;
- skill matcher gain/cost/conflict behavior;
- dependency baseline needed by existing tests.

## Release Strategy

The implementation will be pushed on a Codex branch and published as a draft pull request. The branch should not rewrite current pipeline stages. It should provide stable infrastructure for subsequent refactors.
