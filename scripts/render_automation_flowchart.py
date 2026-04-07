from __future__ import annotations

from pathlib import Path
import textwrap

from PIL import Image, ImageColor, ImageDraw, ImageFont


W = 3840
H = 2160
BG = "#f3f6f8"
TEXT = "#10222f"
MUTED = "#425d6f"
LINE = "#6f8798"
ARROW = "#2f5f7c"
ACCENT = "#bb5a34"
SIDEBAR = "#e8eff4"
WHITE = "#ffffff"
SHADOW = (190, 204, 214, 105)

MAIN_LEFT = 150
MAIN_TOP = 220
MAIN_W = 2840
BOX_W = 620
BOX_H = 220
COL_GAP = 90
ROW_GAP = 120
SIDEBAR_X = 3090
SIDEBAR_W = 600


def load_font(size: int, bold: bool = False):
    candidates = (
        ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"]
        if bold
        else ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"]
    )
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


TITLE = load_font(58, bold=True)
SUB = load_font(26)
BOX_TITLE = load_font(28, bold=True)
BOX_TEXT = load_font(22)
SMALL = load_font(19)
SIDETITLE = load_font(26, bold=True)
SIDEBODY = load_font(21)


BOXES = [
    ("1. Problem Anchor", "Freeze problem, scope, baseline gaps, and contribution boundaries."),
    ("2. Literature Intake", "Read local PDF and note seeds first, then expand with academic search."),
    ("3. Knowledge Synthesis", "Extract gaps and turn them into testable innovation directions."),
    ("4. Claim-Evidence Design", "Bind every core claim to metrics, baselines, and ablations."),
    ("5. Method & Experiments", "Generate code, run experiments, refine failures, and collect evidence."),
    ("6. Result Calibration", "Summarize results and decide which claims survive the evidence."),
    ("7. Paper, Score & Revise", "Draft the paper, score it, fix findings, and re-review when needed."),
    ("8. Final Gate & Export", "Pass quality checks, verify citations, archive outputs, and export deliverables."),
]


SIDEBAR_CARDS = [
    (
        "Phase 1",
        [
            "problem_anchor.md",
            "claims_evidence_matrix.md",
            "claims_from_results.md",
            "Purpose: stop inflated claims before writing.",
        ],
    ),
    (
        "Phase 2",
        [
            "reviews.md + auto_review.md",
            "paper_score.json + score_history.md",
            "Below target or findings open -> rerun 18-20",
            "Default target: 6.0/10, max 4 rounds",
        ],
    ),
    (
        "Phase 3",
        [
            "baseline_digest.md",
            "literature_shortlist.md",
            "experiment_log.md",
            "Purpose: reuse compact context and save tokens.",
        ],
    ),
]


def rounded(draw: ImageDraw.ImageDraw, xy, fill, outline, width=3, radius=30):
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle((x0 + 8, y0 + 10, x1 + 8, y1 + 10), radius=radius, fill=SHADOW)
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def wrap(draw: ImageDraw.ImageDraw, text: str, font, x: int, y: int, width: int, fill: str, gap: int = 6):
    avg = max(font.size // 2, 9)
    lines = textwrap.wrap(text, width=max(16, width // avg))
    cy = y
    for line in lines:
        draw.text((x, cy), line, font=font, fill=fill)
        bbox = draw.textbbox((x, cy), line, font=font)
        cy = bbox[3] + gap
    return cy


def arrow(draw: ImageDraw.ImageDraw, a, b, color=ARROW, width=6):
    draw.line((a, b), fill=color, width=width)
    x0, y0 = a
    x1, y1 = b
    if abs(x1 - x0) >= abs(y1 - y0):
        if x1 >= x0:
            pts = [(x1, y1), (x1 - 24, y1 - 12), (x1 - 24, y1 + 12)]
        else:
            pts = [(x1, y1), (x1 + 24, y1 - 12), (x1 + 24, y1 + 12)]
    else:
        if y1 >= y0:
            pts = [(x1, y1), (x1 - 12, y1 - 24), (x1 + 12, y1 - 24)]
        else:
            pts = [(x1, y1), (x1 - 12, y1 + 24), (x1 + 12, y1 + 24)]
    draw.polygon(pts, fill=color)


def poly_arrow(draw: ImageDraw.ImageDraw, points, color=ARROW, width=6):
    for i in range(len(points) - 1):
        draw.line((points[i], points[i + 1]), fill=color, width=width)
    arrow(draw, points[-2], points[-1], color=color, width=width)


def main():
    repo = Path(__file__).resolve().parents[1]
    out = repo / "docs" / "automation_pipeline_flow_4k.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    img = Image.new("RGBA", (W, H), BG)
    draw = ImageDraw.Draw(img)

    top_rgb = ImageColor.getrgb("#f7fafb")
    bottom_rgb = ImageColor.getrgb("#e9eff3")
    for y in range(H):
        t = y / max(H - 1, 1)
        color = tuple(int(top_rgb[i] * (1 - t) + bottom_rgb[i] * t) for i in range(3))
        draw.line((0, y, W, y), fill=color, width=1)

    draw.text((MAIN_LEFT, 60), "AutoResearchClaw Simplified Automation Flow", font=TITLE, fill=TEXT)
    draw.text(
        (MAIN_LEFT, 132),
        "Main path only: 8 blocks for problem framing, literature intake, experiments, scoring, revision, and export.",
        font=SUB,
        fill=MUTED,
    )

    sidebar = (SIDEBAR_X, 80, SIDEBAR_X + SIDEBAR_W, H - 100)
    rounded(draw, sidebar, fill=SIDEBAR, outline="#9ab0bf", width=3, radius=34)
    draw.text((SIDEBAR_X + 28, 108), "Enhancement Layer", font=SIDETITLE, fill=TEXT)
    draw.text((SIDEBAR_X + 28, 148), "What changed beyond the original pipeline", font=SMALL, fill=MUTED)

    positions = []
    for idx, (title, body) in enumerate(BOXES):
        row = idx // 4
        col = idx % 4
        x0 = MAIN_LEFT + col * (BOX_W + COL_GAP)
        y0 = MAIN_TOP + row * (BOX_H + ROW_GAP)
        xy = (x0, y0, x0 + BOX_W, y0 + BOX_H)
        positions.append(xy)

        outline = ACCENT if idx in {0, 1, 3, 5, 6} else LINE
        rounded(draw, xy, fill=WHITE, outline=outline, width=4 if outline == ACCENT else 3)
        draw.text((x0 + 28, y0 + 28), title, font=BOX_TITLE, fill=TEXT)
        wrap(draw, body, BOX_TEXT, x0 + 28, y0 + 82, BOX_W - 56, MUTED)

    for row in range(2):
        base = row * 4
        for i in range(3):
            left = positions[base + i]
            right = positions[base + i + 1]
            arrow(draw, (left[2], (left[1] + left[3]) // 2), (right[0], (right[1] + right[3]) // 2))

    poly_arrow(
        draw,
        [
            ((positions[3][0] + positions[3][2]) // 2, positions[3][3]),
            ((positions[3][0] + positions[3][2]) // 2, positions[3][3] + 54),
            ((positions[4][0] + positions[4][2]) // 2, positions[3][3] + 54),
            ((positions[4][0] + positions[4][2]) // 2, positions[4][1]),
        ],
    )

    loop_label_x = positions[6][0] + 70
    loop_y = positions[6][3] + 34
    poly_arrow(
        draw,
        [
            (positions[6][0] + 80, positions[6][3]),
            (positions[6][0] + 80, loop_y),
            (positions[6][0] - 120, loop_y),
            (positions[6][0] - 120, positions[6][1] + 110),
            (positions[6][0], positions[6][1] + 110),
        ],
        color=ACCENT,
    )
    label = "Score below target or findings open -> revise and re-review"
    lb = draw.textbbox((loop_label_x, loop_y - 18), label, font=SMALL)
    draw.rounded_rectangle((lb[0] - 14, lb[1] - 8, lb[2] + 14, lb[3] + 8), radius=18, fill="#fff4ef", outline=ACCENT, width=2)
    draw.text((loop_label_x, loop_y - 18), label, font=SMALL, fill=ACCENT)

    card_y = 205
    for heading, lines in SIDEBAR_CARDS:
        card = (SIDEBAR_X + 22, card_y, SIDEBAR_X + SIDEBAR_W - 22, card_y + 260)
        rounded(draw, card, fill=WHITE, outline="#95acbc", width=2, radius=24)
        draw.text((card[0] + 22, card[1] + 18), heading, font=SIDETITLE, fill=TEXT)
        cy = card[1] + 64
        for line in lines:
            cy = wrap(draw, f"- {line}", SIDEBODY, card[0] + 22, cy, SIDEBAR_W - 88, MUTED, gap=5) + 2
        card_y += 290

    footer = "Scoring loop inspired by ARIS-style auto-review-loop: score, fix, and rerun a bounded number of review rounds."
    draw.text((MAIN_LEFT, H - 88), footer, font=SMALL, fill=MUTED)

    img.convert("RGB").save(out, format="PNG", optimize=True)
    print(out)


if __name__ == "__main__":
    main()
