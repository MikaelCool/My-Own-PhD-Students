# Hard Problem Anchor: Spectrum-Aware Selective Low-Rank Control for LoRA Training

Sources: `stage-01/goal.md`, `stage-02/problem_tree.md`

## Dominant Research Question

Can a theory-backed, training-time **spectrum-aware selective controller** for LoRA updates improve the **quality / peak-VRAM / efficiency** Pareto frontier in real 7B-9B fine-tuning, compared with fixed-rank LoRA and existing adaptive-rank baselines, by deciding **whether to impose low-rank constraint, when to impose it, and how strongly to impose it** from online spectrum signals?

## Precise Baseline Weakness Being Targeted

- `ASVD` and `SVD-LLM` show that truncation quality depends on spectrum and layer heterogeneity, but they are fundamentally **frozen-model or post-training compression** methods, not training-time LoRA controllers.
- `LoRA-Squeeze` and `HyperAdaLoRA` show that optimal LoRA rank is **not static**, but their control logic does not directly use online estimates of the current `ΔW_l^t = B_l^t A_l^t` spectrum to decide selective intervention.
- Existing baselines therefore leave a concrete gap: they do not answer whether **online, layer-wise, state-aware selective low-rank control inside the real LoRA training loop** can reduce **active training memory** rather than merely shrink the final adapter.

## Main Contribution

Design a **selective spectrum-aware controller** for LoRA training.
The controller observes lightweight spectral summaries of each layer update and outputs:

- whether to trigger low-rank projection,
- the target rank or retained energy,
- the intervention frequency or strength.

The paper wins only if this controller improves **training-time active-state efficiency**, not just deployment size.

## Supporting Innovation 1

### Error-Controlled Online Spectrum Probe

Use a lightweight `QB + RSVD` probe to estimate only controller-relevant quantities, such as:

- effective rank,
- tail energy,
- spectral gap or slope,
- short-horizon spectrum drift.

This is not a standalone contribution unless it is accurate enough, cheap enough, and analyzable as a control signal.

## Supporting Innovation 2

### State-Consistent Rank Morphing

When rank changes, remap not only `(A, B)` but also optimizer state so that the method does not collapse into periodic implicit reinitialization.
This support matters only because unstable morphing would erase any claimed controller benefit.

## Proof Obligations

1. Show that the online probe estimates controller-relevant spectrum statistics with bounded error or bounded trigger mismatch relative to an exact-spectrum oracle.
2. Show that selective control driven by approximate spectra is not just another heuristic schedule, but has a bounded decision gap, regret surrogate, or other defensible approximation to an oracle controller.
3. Show that rank morphing with optimizer-state mapping induces bounded update distortion or local stability loss, rather than uncontrolled optimization shocks.
4. If claiming deployment-side benefit, show that training-time control induces a measurably more compressible final spectrum instead of duplicating post-hoc compression.

## Experimental Obligations

1. Run all main results in a **real LoRA training loop** on **7B/8B/9B** models, within the stated 120-hour budget and at most 2 free GPUs.
2. Report **peak VRAM**, **throughput/step time**, **time-to-target quality**, **task quality**, and **final adapter compressibility** separately.
3. Include fair baselines at minimum: standard LoRA, fixed-rank truncation or `LoRA-Squeeze`-style in-training compression, `AdaLoRA` or `HyperAdaLoRA`-style adaptive-rank control, and train-then-compress baselines.
4. Prove the method changes **active training memory**; checkpoint shrinkage alone does not count as success.
5. Show at least one mechanism study: probe accuracy vs exact SVD, layer-wise trigger patterns, and same-average-rank comparison against a non-selective schedule.

## Explicit Non-Goals

- Not another generic rank schedule paper.
- Not a checkpoint-size-only compression paper.
- Not a pure kernel, offload, checkpointing, or mixed-precision systems paper.
- Not an RL story unless simple rules and lightweight learners already fail.
- Not a toy simulation without real 7B-9B fine-tuning evidence.

## Go/No-Go Rule

If the MVP cannot show either:

- lower `peak VRAM` or better `time-to-target` at similar quality, or
- clearly better quality/compressibility at comparable training-time cost,

then the topic should be narrowed to analysis of LoRA update spectra rather than pursued as a main method paper.
