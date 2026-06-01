# Hard Problem Anchor: Tiny Reproducible Benchmark for Low-Rank Matrix Approximation

## Dominant Research Question

How can we design a **tiny, fully reproducible, structure-identifiable benchmark** for low-rank matrix approximation that does more than compare fixed-rank baselines, by exposing a precise baseline weakness and enabling one **theory-backed instance-aware approximation principle** that is provably better in a clearly defined regime?

This project is only valid if the benchmark serves one scientific purpose:

- isolate the structural conditions under which existing low-rank methods behave differently,
- make those conditions directly testable in a minimal protocol,
- support one method-level improvement with a proof obligation.

If the work drifts into benchmark tooling, larger experiment grids, or generic reproduction, it has failed.

## Precise Baseline Weakness Being Targeted

The target weakness is:

- existing baselines are usually compared under **coarse fixed-rank or fixed-budget protocols**,
- their theory relies on structure assumptions such as spectral decay, coherence, leverage concentration, or noise regime,
- but their experiments often do **not isolate those assumptions cleanly enough** to explain when one method should win or fail,
- so current comparisons blur together **error, budget choice, and matrix structure**, making both theory and empirical claims weaker than they appear.

The paper should therefore target one sharp claim:

> Fixed-rank evaluation is too coarse to fairly compare low-rank approximation methods across matrix regimes, and a tiny benchmark should be designed to identify the structural variables that determine when an instance-aware budget or rank rule is preferable.

## Main Contribution

### Main Contribution: Instance-Aware Approximation Principle

Propose one clean **instance-aware rank or budget selection principle** for low-rank approximation.

The contribution is not a new engineering stack and not a bag of heuristics. The contribution is a rule that:

- uses observable matrix statistics or efficiently estimable surrogates,
- selects rank, sketch size, or sampling budget adaptively,
- has a theorem comparing it to fixed-rank or fixed-budget baselines,
- is evaluated under a tiny protocol specifically designed to test the theorem's regime split.

The paper should read as:

> We identify that fixed-rank protocols hide structure dependence, build a tiny benchmark that exposes it, and show that an instance-aware approximation rule improves robustness or regret relative to fixed-budget baselines in the regimes predicted by theory.

## Supporting Innovations

### Supporting Innovation 1: Structure-Identifiable Tiny Benchmark

The benchmark is a supporting innovation, not the headline claim. Its role is to define the **minimal matrix family suite** needed to distinguish baseline mechanisms.

It must explicitly control a small set of variables such as:

- spectral decay,
- coherence or leverage concentration,
- tail energy or rank misspecification,
- noise level,
- access model if relevant.

Its research value comes from one formal design claim:

- if certain controlled families are omitted, the baseline methods become empirically indistinguishable even though their theory predicts different behavior.

### Supporting Innovation 2: Regime-Level Theory

Provide one theory result that explains a **failure boundary or advantage region**.

The preferred form is one of:

- an instance-dependent upper bound sharper than a coarse worst-case bound,
- a lower bound showing that fixed-budget methods must incur excess error in a target regime,
- a phase-transition style result predicting where baseline ordering changes.

This theory must use the same structural variables that the benchmark sweeps.

## Proof Obligations

At least one theorem-level result is required. The project does not qualify as a research contribution without it.

Minimum acceptable proof target:

- prove an oracle-comparison, regret, or excess-error guarantee for the instance-aware rule relative to fixed-rank or fixed-budget baselines.

Stronger supporting proof targets:

- formalize benchmark distinguishability or identifiability for a chosen comparison class,
- prove a regime-separation proposition or lower bound tied to coherence, decay, tail energy, or noise.

Unacceptable outcome:

- only informal intuition,
- only asymptotic storytelling disconnected from the benchmark variables,
- only empirical stability claims with no theorem.

## Experimental Obligations

The experiments must be tiny, sharp, and theory-testing.

Required:

- reproduce the key baseline comparison protocol fairly under matched rank budget, observation budget, pass budget, and seed policy,
- use controlled synthetic matrix families rather than ad hoc toy examples,
- compare at least `oracle rank` vs `fixed rank` vs `proposed adaptive rule`,
- report reconstruction error plus at least one stability-oriented metric such as regret to oracle, variance across seeds, or robustness under misspecification,
- include at least one regime sweep where the theoretical variable changes continuously and the predicted transition is visible.

The benchmark is successful only if each experiment has a clear necessity:

- one experiment validates the benchmark's ability to separate regimes,
- one validates the method advantage,
- one checks robustness under misspecification or noise.

## Explicit Non-Goals

The project must not claim contribution from any of the following:

- benchmark packaging, dashboards, orchestration, or code cleanup,
- larger-scale runs, more datasets, or more baselines without a sharper scientific claim,
- pure speed improvements, systems tricks, or implementation optimization,
- heuristic rank sweeps, tuning recipes, or hyperparameter search presented as algorithmic novelty,
- vague "more reproducible" positioning without a formal benchmark design reason,
- average-case wins without a clearly specified regime and fair budget control,
- any SOTA claim unless the comparison is genuinely fair and consistently supported.

## Baseline-Locking Requirement

This anchor is not complete until `baseline_briefing.md` is filled with three real papers and each paper is extracted along four axes:

- task setup,
- structure assumptions,
- theory type,
- experimental protocol.

Only after that step can the benchmark variables and theorem target be considered baseline-locked rather than generic.
