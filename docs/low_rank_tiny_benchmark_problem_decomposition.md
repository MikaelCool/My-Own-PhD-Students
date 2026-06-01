# Problem Decomposition: A Tiny Reproducible Benchmark for Low-Rank Matrix Approximation

## 1. Research Thesis

The paper should not be framed as "we built a small benchmark for low-rank approximation." That contribution is too weak. The defensible thesis is:

> Existing low-rank approximation methods are usually compared under coarse fixed-rank protocols that blur the role of matrix structure. We define a tiny but structure-identifiable benchmark, use it to expose regime-level failures in existing methods, and introduce an instance-aware approximation principle with theory that explains when and why it improves over fixed-budget baselines.

This thesis only works if the paper closes a three-part loop:

1. **Theory**: identify a structural variable or descriptor that existing worst-case analyses do not resolve well.
2. **Algorithm**: use that descriptor to drive a new rank/budget selection rule or approximation mechanism.
3. **Experiment**: build the smallest reproducible protocol that can separate regimes predicted by the theory.

If any one of these three parts is missing, the work collapses:

- no theory: becomes a benchmark/tool paper,
- no algorithm: becomes an empirical diagnosis note,
- no targeted experiment: becomes an untestable theory story.

## 2. Workstream Decomposition

### 2.1 Theory Workstream

Main objective: formalize which matrix structure variables should define the benchmark and prove at least one regime-separating claim.

Core outputs:

- a definition of **benchmark identifiability** or **regime distinguishability**,
- an instance descriptor based on a small set of variables such as spectral decay, stable rank, leverage concentration, coherence, and noise level,
- at least one theorem/proposition showing that two classes of methods are not equivalent on this descriptor space,
- a guarantee for the proposed adaptive rule that is better than naive fixed-rank evaluation in some identifiable regime.

### 2.2 Algorithm Workstream

Main objective: propose one clean method-level innovation, not a bag of heuristics.

Core outputs:

- an instance-aware rank or sketch-budget selection rule,
- optionally a structure-aware sampling or regularization mechanism if needed to support the claim,
- a mathematically stated decision criterion that can be analyzed independently of implementation details.

The algorithm should be simple enough that its advantage is attributable to the principle, not to hyperparameter search.

### 2.3 Experiment Workstream

Main objective: construct the smallest protocol that directly tests the theory.

Core outputs:

- a minimal synthetic matrix suite with controlled structure variables,
- a fairness protocol fixing rank budget, observation budget, pass budget, and seed policy,
- plots that track regime transitions rather than only average error tables,
- deterministic or seed-controlled scripts that can be rerun cheaply end-to-end.

The benchmark is a scientific instrument here, not the paper's main novelty by itself.

## 3. Baseline Gap Map to Fill Before Committing

The current `baseline_briefing.md` is still empty, so the immediate bottleneck is not idea generation but structured baseline extraction. Before finalizing the project scope, each of the three baseline papers must be mapped along the following dimensions:

| Dimension | Questions to extract |
|---|---|
| Task setup | Full matrix vs sampled entries vs sketch access? Fixed-rank approximation vs adaptive budget? Frobenius vs spectral objective? |
| Structural assumptions | Coherence? Stable rank? Spectral decay? Spikiness? Noise model? Sampling distribution? |
| Theory type | Worst-case upper bound? Relative error? Instance-dependent guarantee? Lower bound? |
| Experimental protocol | Which synthetic families were used? Which structural variables were explicitly controlled? Which budgets were fixed? |
| Unresolved weakness | Where does the theory fail to predict empirical behavior? Where does the experiment fail to isolate assumptions? |

Until this map is filled, the right target is not "choose the best idea" but "remove ambiguity about what has and has not already been solved."

## 4. Core Innovation Axes

The paper should center on **three tightly coupled theory-bearing innovations**. They play different roles:

- Innovation 1 defines the scientific object of study.
- Innovation 2 contributes the main algorithmic novelty.
- Innovation 3 provides the regime-level theory that makes the first two worth publishing.

### 4.1 Innovation 1: Structure-Identifiable Tiny Benchmark

**Role in paper**
This is the problem-definition innovation. It turns the benchmark from infrastructure into a minimal scientific protocol.

**Exact weakness in the baseline**

- Baselines are likely compared under fixed-rank or fixed-budget settings that do not isolate the structural assumptions used in their own theory.
- Existing synthetic experiments often vary one nuisance parameter at a time without proving that the chosen matrix families are sufficient to distinguish competing algorithmic mechanisms.
- As a result, empirical wins are hard to attribute: they may reflect an implicit bias of the test distribution rather than a genuine algorithmic advantage.

**Proposed mechanism**

Define a **minimal matrix family suite** indexed by a low-dimensional structure tuple:

\[
\theta = (\text{decay}, \text{coherence}, \text{tail energy}, \text{noise level}, \text{access model}).
\]

The benchmark should include only matrix families that are necessary to separate hypotheses such as:

- fast vs slow spectral decay,
- diffuse vs concentrated leverage scores,
- clean low-rank signal vs low-rank-plus-noise,
- well-specified vs misspecified target rank.

The key move is to formalize benchmark adequacy as a distinguishability property:

- a benchmark is **structure-identifiable** for a method class if different mechanisms that imply different error behavior on some admissible regime are actually separable by at least one matrix family in the suite.

**Expected theoretical claim**

At minimum, prove a proposition of the following form:

> For a chosen pair of baseline method classes, any benchmark suite that omits either a coherence-controlled family or a decay-controlled family cannot distinguish the predicted ordering of the methods across all admissible matrices in the target regime.

This is weaker than a full characterization, but strong enough to justify why the tiny benchmark is not arbitrary. A stronger version would define a finite set of families that is sufficient for distinguishing a target comparison class.

**Minimal experiment needed to validate it**

- Two baseline methods with theoretically different sensitivity to one structural factor.
- One controlled family for spectral decay and one for leverage concentration.
- A fixed budget protocol with 20-50 seeds and deterministic generation.
- A regime sweep showing at least one ordering reversal or sharp performance separation that disappears when one family is removed from the suite.

This experiment should answer a single question: does the benchmark isolate a theoretically meaningful difference that a generic toy setup would miss?

**Main failure mode**

- The distinguishability notion stays informal and never becomes a real theorem or proposition.
- The chosen matrix families look hand-picked after the fact to favor the proposed method.
- The benchmark is still only a convenience layer with no evidence that its components are necessary.

### 4.2 Innovation 2: Instance-Aware Rank/Budget Selection Principle

**Role in paper**
This is the main algorithmic contribution. It should be the piece that a reviewer can point to as the method-level novelty.

**Exact weakness in the baseline**

- Fixed-rank comparison assumes the user knows the correct target rank or truncation budget in advance.
- Many baseline papers likely report oracle-tuned performance, which obscures robustness under rank misspecification.
- Existing guarantees often say what happens once \(k\) is given, but not how \(k\) or sketch size should be selected from observable statistics.

**Proposed mechanism**

Introduce an **instance-aware selection rule** that chooses truncation rank \(k\), sketch size \(s\), or sampling intensity from estimated structural statistics. A clean version is:

1. estimate a small set of observable descriptors such as local spectral gaps, cumulative tail energy surrogate, or stable-rank proxy,
2. choose the smallest budget achieving a certified surrogate risk target,
3. apply a standard or lightly modified low-rank approximation routine using that budget.

The novelty is not inventing a new decomposition algorithm from scratch. The novelty is a principled decision rule that converts structure estimates into a budget with theory.

If needed, this can be paired with a mild structural regularizer or rescaling rule, but only if that extra mechanism is analytically essential.

**Expected theoretical claim**

The desired statement is an oracle-comparison result, for example:

> The selected rank \(\hat{k}\) attains reconstruction error within a controlled factor of the oracle rank \(k^\star\) while using a budget that adapts to the instance-dependent tail profile.

Or, in a more benchmark-aligned form:

> Under matrices with bounded descriptor class \(\Theta\), the proposed rule achieves smaller worst-case regret under rank misspecification than any fixed-rank rule chosen independently of the instance.

The theory does not need to dominate every baseline everywhere. It needs to show a clean and defensible advantage in a clearly defined regime.

**Minimal experiment needed to validate it**

- Compare three policies:
  - oracle rank baseline,
  - fixed-rank baseline,
  - proposed adaptive rule.
- Sweep over:
  - decay rate,
  - target rank misspecification,
  - noise level.
- Report:
  - reconstruction error,
  - budget used,
  - regret relative to oracle,
  - variance across seeds.

The most important plot is not raw accuracy. It is a regret or stability curve showing that the adaptive rule degrades more gracefully when the fixed-rank assumption is wrong.

**Main failure mode**

- The rule requires hidden information that is effectively oracle access.
- The selected descriptors are too noisy or too expensive to estimate to be part of a "tiny" protocol.
- The method wins only after substantial tuning, making the claimed principle look like a heuristic wrapper rather than algorithmic novelty.

### 4.3 Innovation 3: Instance-Dependent Regime Theory for Baseline Failure Boundaries

**Role in paper**
This is the theory anchor. It explains not only why the new method works, but why baseline behavior changes across the benchmark.

**Exact weakness in the baseline**

- Baseline analyses are likely dominated by worst-case error bounds that are too coarse to explain differences between matrices with the same nominal rank.
- Existing theory may mention coherence or stable rank, but not in a way that predicts phase transitions in realistic small synthetic families.
- Baseline experiments probably show empirical behavior across structured matrices without a matching theoretical account of the transitions.

**Proposed mechanism**

Derive an **instance-dependent upper/lower bound pair** or a **phase-transition characterization** that uses the same structure variables encoded by the benchmark. The clean target is to show how approximation quality depends jointly on:

- spectral tail profile,
- leverage concentration or coherence,
- noise contamination,
- rank misspecification.

The theory can support either:

- the proposed adaptive rule directly, or
- a separation result between the proposed method and one or two baseline classes.

This is the strongest place to introduce lower bounds or impossibility statements if they can be proved on small matrix families.

**Expected theoretical claim**

At least one of the following should be true:

- an upper bound sharper than the relevant baseline worst-case bound in a defined descriptor regime,
- a lower bound showing that fixed-budget or non-adaptive methods must incur excess error once coherence or tail energy crosses a threshold,
- a phase-transition theorem that predicts where baseline ordering reverses.

The best version is a theory statement whose variables are directly sweepable in the tiny benchmark.

**Minimal experiment needed to validate it**

- A one- or two-dimensional sweep over the theory variables, such as:
  - coherence vs decay,
  - noise vs rank misspecification.
- Error curves with confidence intervals, not just point estimates.
- One figure explicitly overlaying theoretical regime boundaries or predicted transition points against empirical behavior.

This experiment should not be large. It should be sharp enough to test whether the theorem has explanatory power.

**Main failure mode**

- The bound is technically correct but too loose to predict any visible transition.
- The theory variables are not observable or not matched by the benchmark construction.
- The empirical curves do not align with the claimed regime split, forcing the paper into a disconnected "theory + experiments" narrative.

## 5. How the Three Innovations Fit Together

The intended paper logic is:

1. Fixed-rank low-rank approximation comparisons are under-specified because they ignore structure-sensitive regime differences.
2. A tiny benchmark can be principled if it is designed to be structure-identifiable rather than merely convenient.
3. Once the regimes are made explicit, one can design an instance-aware budget selection rule that is robust to misspecification.
4. Instance-dependent theory explains both why baselines fail in some regimes and why the proposed adaptive rule helps.
5. The tiny protocol validates the theory with cheap but decisive experiments.

This ordering matters. If the paper starts from "we built a benchmark," it will sound like infrastructure. If it starts from "existing comparisons hide a regime-selection problem," the benchmark becomes necessary rather than auxiliary.

## 6. Minimal Paper Blueprint

### 6.1 Problem Statement

Define a low-rank approximation evaluation problem where the object of comparison is not only reconstruction at fixed rank, but the **policy that maps instance structure to an approximation budget** under a controlled access model.

### 6.2 Method Section

Should contain only:

- benchmark structure descriptor,
- adaptive rank/budget rule,
- approximation routine and any essential regularization,
- complexity discussion.

Do not bloat this section with infrastructure details.

### 6.3 Theory Section

Should contain:

- definition of structure-identifiable benchmark or equivalent criterion,
- one proposition justifying the matrix family design,
- one main theorem for the adaptive rule,
- optionally one lower bound or failure-boundary theorem.

### 6.4 Experiment Section

Should contain:

- benchmark generation protocol,
- fairness constraints,
- ablations only if they serve the theory,
- one regime-transition figure,
- one rank-misspecification robustness figure,
- one compact reproducibility table.

## 7. Genuine Algorithmic Novelty vs Engineering Support

This separation needs to be explicit from day one to avoid inflating the contribution.

### 7.1 Genuine Research Contributions

- Formal benchmark design principle based on distinguishability or identifiability.
- Instance-aware rank or sketch-budget selection rule with theorem.
- Instance-dependent error or lower-bound analysis tied to benchmark variables.
- Regime-level empirical validation directly testing the theory.

### 7.2 Engineering Support Only

These are necessary, but they are not paper contributions:

- deterministic matrix generator implementation,
- seed handling and exact rerun scripts,
- plotting code and result packaging,
- benchmark CLI or config files,
- containerization, caching, parallel execution,
- baseline reimplementation cleanup,
- additional dashboards or convenience wrappers.

These should appear in the artifact or appendix, not in the main contribution list.

## 8. Minimal Experimental Protocol

The benchmark should remain tiny. A plausible minimum protocol is:

- **Matrix families**:
  - decay-controlled low-coherence family,
  - decay-controlled high-coherence family,
  - noisy low-rank-plus-tail family,
  - rank-misspecified family with adjustable tail energy.
- **Budgets**:
  - same target rank or same selection budget,
  - same sketch/sample budget where applicable,
  - same pass/access model.
- **Metrics**:
  - Frobenius reconstruction error,
  - spectral error if relevant,
  - regret to oracle rank,
  - seed variance,
  - compute-normalized cost only if methods differ materially in cost.
- **Plots**:
  - error vs rank misspecification,
  - error vs coherence/decay sweep,
  - budget selected by adaptive rule vs oracle budget.

If the protocol grows beyond what a reviewer can understand in a few minutes, it is no longer serving the "tiny" thesis.

## 9. Priority Order for Immediate Next Steps

The next actions should be executed in this order:

1. Fill `baseline_briefing.md` with three real baseline papers.
2. For each baseline, extract:
   - exact access model,
   - objective norm,
   - structural assumptions,
   - whether rank is fixed or selected,
   - synthetic regimes used in experiments,
   - fairness conditions in comparison.
3. Identify one unresolved structural variable that is present across baselines but not cleanly handled.
4. Choose the adaptive rule only after step 3, not before.
5. Build the benchmark around the theory variable, not around convenience.

## 10. Kill Criteria

Stop or pivot if any of the following becomes true:

- the benchmark cannot be justified beyond convenience,
- the adaptive rule depends on oracle information,
- the theory cannot say anything stronger than a loose worst-case bound,
- baseline comparisons require too many incompatible access models to make a fair tiny protocol,
- empirical gains only appear after tuning that baselines do not receive,
- a baseline paper already contains the same benchmark-design principle plus adaptive rule plus regime theory combination.

## 11. Deliverables for the Next Iteration

To move this from framing to research execution, the next iteration should produce four concrete artifacts:

1. a completed `baseline_briefing.md`,
2. a one-page theorem target sheet listing the exact conjectured claims,
3. a benchmark specification sheet defining the minimal matrix families and fairness protocol,
4. a method note stating the adaptive rule in equations before any implementation work begins.

Without these four artifacts, implementation would be premature and likely drift into engineering.
