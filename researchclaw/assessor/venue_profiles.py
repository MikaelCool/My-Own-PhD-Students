"""Venue-aware editorial profiles for paper scoring and review."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VenueProfile:
    key: str
    label: str
    editorial_stance: str
    target_review_score: float
    novelty_floor: float
    experiment_floor: float
    hard_requirements: tuple[str, ...]
    rubric_focus: tuple[str, ...] = ()
    dimension_floors: tuple[tuple[str, float], ...] = ()

    @property
    def dimension_floor_map(self) -> dict[str, float]:
        return dict(self.dimension_floors)


_PROFILES: dict[str, VenueProfile] = {
    "ccf-a": VenueProfile(
        key="ccf-a",
        label="CCF-A",
        editorial_stance=(
            "Act as the editor-in-chief of a top CCF-A venue. Be rigorous, fair, "
            "blunt about weaknesses, and reject inflated novelty or weak evidence."
        ),
        target_review_score=8.0,
        novelty_floor=7.5,
        experiment_floor=7.0,
        hard_requirements=(
            "At least 2-3 defensible innovation points, not engineering polish.",
            "Fair baseline reproduction and strong ablations.",
            "Claims calibrated to actual evidence and statistical support.",
        ),
        rubric_focus=(
            "Novelty must be theory-bearing or algorithmically substantive, not workflow polish.",
            "Empirical claims must survive strong baselines, ablations, and robustness checks.",
            "Overclaiming is penalized heavily; unsupported gains should trigger rollback.",
        ),
        dimension_floors=(
            ("novelty", 7.5),
            ("technical_soundness", 7.0),
            ("empirical_adequacy", 7.0),
            ("writing_clarity", 6.5),
            ("claim_calibration", 7.0),
        ),
    ),
    "neurips": VenueProfile(
        key="neurips",
        label="NeurIPS",
        editorial_stance="Act like a NeurIPS area chair who prioritizes novelty, rigor, and clarity.",
        target_review_score=7.8,
        novelty_floor=7.2,
        experiment_floor=7.0,
        hard_requirements=(
            "Clear novelty over strong baselines.",
            "Methodological rigor and reproducibility details.",
            "Results supported by sound statistics and ablations.",
        ),
        rubric_focus=(
            "Weight novelty, rigor, and reproducibility jointly; weak empirical backing is costly.",
            "Penalize papers that report wins without calibrated uncertainty or fair comparisons.",
            "Reward concise, evidence-matched claims over hype.",
        ),
        dimension_floors=(
            ("novelty", 7.2),
            ("technical_soundness", 7.0),
            ("empirical_adequacy", 7.0),
            ("writing_clarity", 6.6),
            ("claim_calibration", 7.0),
        ),
    ),
    "icml": VenueProfile(
        key="icml",
        label="ICML",
        editorial_stance="Act like an ICML senior program committee member focused on scientific rigor.",
        target_review_score=7.8,
        novelty_floor=7.0,
        experiment_floor=7.0,
        hard_requirements=(
            "Contribution must be algorithmically meaningful.",
            "Experimental evidence must be broad and fair.",
            "Theory claims must align with actual derivations or proofs.",
        ),
        rubric_focus=(
            "Scientific rigor and algorithmic contribution outweigh style alone.",
            "Theory language should be conservative unless proofs or derivations are actually present.",
            "Fair experiments and ablations are mandatory for acceptance-level scores.",
        ),
        dimension_floors=(
            ("novelty", 7.0),
            ("technical_soundness", 7.1),
            ("empirical_adequacy", 7.0),
            ("writing_clarity", 6.5),
            ("claim_calibration", 6.9),
        ),
    ),
    "acl": VenueProfile(
        key="acl",
        label="ACL",
        editorial_stance="Act like an ACL senior area chair focused on empirical soundness and clarity.",
        target_review_score=7.6,
        novelty_floor=6.8,
        experiment_floor=7.0,
        hard_requirements=(
            "Novelty must be concrete and well-positioned in prior work.",
            "Datasets, baselines, and metrics must be reported transparently.",
            "Error analysis and limitations should be honest and specific.",
        ),
        rubric_focus=(
            "Transparent datasets, baselines, and reporting matter as much as the headline idea.",
            "Reward explicit limitations and error analysis instead of generic impact claims.",
            "Reject novelty inflation when positioning against prior work is weak.",
        ),
        dimension_floors=(
            ("novelty", 6.8),
            ("technical_soundness", 6.9),
            ("empirical_adequacy", 7.0),
            ("writing_clarity", 6.8),
            ("claim_calibration", 6.9),
        ),
    ),
    "cvpr": VenueProfile(
        key="cvpr",
        label="CVPR",
        editorial_stance="Act like a CVPR area chair focused on visual evidence and strong empirical validation.",
        target_review_score=7.8,
        novelty_floor=7.0,
        experiment_floor=7.2,
        hard_requirements=(
            "Innovation must exceed implementation polish.",
            "Baselines, visual evidence, and ablations must be convincing.",
            "Claims should match actual quantitative and qualitative results.",
        ),
        rubric_focus=(
            "Visual and quantitative evidence should jointly support the contribution.",
            "Implementation polish does not substitute for a substantive method gain.",
            "Ablations and qualitative analysis should explain why the method works.",
        ),
        dimension_floors=(
            ("novelty", 7.0),
            ("technical_soundness", 7.0),
            ("empirical_adequacy", 7.2),
            ("writing_clarity", 6.5),
            ("claim_calibration", 6.9),
        ),
    ),
}


def normalize_venue_name(name: str) -> str:
    raw = (name or "CCF-A").strip().lower()
    raw = raw.replace("_", "-").replace(" ", "-")
    if raw in {"ccfa", "ccf-a-class", "ccf-a-venue"}:
        return "ccf-a"
    return raw


def get_venue_profile(name: str) -> VenueProfile:
    key = normalize_venue_name(name)
    return _PROFILES.get(key, _PROFILES["ccf-a"])


def format_venue_rubric(profile: VenueProfile) -> str:
    lines = [f"- Acceptance bar: >= {profile.target_review_score:.1f}/10 overall."]
    for dimension, floor in profile.dimension_floors:
        lines.append(f"- {dimension}: floor {floor:.1f}/10")
    for item in profile.rubric_focus:
        lines.append(f"- {item}")
    return "\n".join(lines)


def resolve_review_target(configured_target: float, profile: VenueProfile) -> float:
    """Return the effective score-loop target for a venue.

    The configured target may raise the bar further, but it should not lower
    the venue's own acceptance standard.
    """
    if configured_target <= 0:
        return round(profile.target_review_score, 2)
    return round(max(configured_target, profile.target_review_score), 2)
