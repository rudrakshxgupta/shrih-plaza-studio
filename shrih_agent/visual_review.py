"""Visual reviewer: inspects a rendered post the way a human art director would.

It checks the rendered PNG and the HTML it came from. Any defect is written to
memory/mistake_memory.json so the design agent is told about it next time.
"""

import html as htmllib
import re
from pathlib import Path
from typing import Any

from . import decisions as owner_decisions
from . import design_history
from . import mistake_memory
from .agents import FORBIDDEN_PATTERNS
from .design_agent import BRAND_LOGO_FILES, CANVAS, SIGNAGE_RISK_PREFIXES

# Brand names seen on the 3D renders that are NOT approved. The owner confirmed
# the twelve signed brands are final, so none of these may appear in a post.
UNAPPROVED_BRAND_NAMES = [
    "bigg bazzar", "bigg bazaar", "jio bazar", "jioo bazar", "burger king", "burger kingg", "subway",
    "parle", "amul", "nestle", "itc", "pepsi", "smart bazar", "reliance", "reli mart", "monolee",
    "fortune", "pearss", "amazonee", "lacostee", "biryani", "ratna sagaar",
]

BLACK = 10
MIN_BAR_HEIGHT = 250
MIN_BAR_WIDTH = 30


def _black_bars(image) -> list[tuple[int, int]]:
    """Runs of adjacent columns that each hold a tall unbroken run of pure black."""
    gray = image.convert("L")
    width, height = gray.size
    pixels = gray.load()
    tall_columns: list[int] = []
    for x in range(width):
        longest = run = 0
        for y in range(height):
            if pixels[x, y] < BLACK:
                run += 1
                longest = max(longest, run)
            else:
                run = 0
        if longest >= MIN_BAR_HEIGHT:
            tall_columns.append(x)
    bars: list[tuple[int, int]] = []
    start = previous = None
    for x in tall_columns:
        if start is None:
            start = previous = x
        elif x == previous + 1:
            previous = x
        else:
            if previous - start + 1 >= MIN_BAR_WIDTH:
                bars.append((start, previous))
            start = previous = x
    if start is not None and previous - start + 1 >= MIN_BAR_WIDTH:
        bars.append((start, previous))
    return bars


class VisualReviewerAgent:
    def run(self, design: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
        issues: list[str] = []
        checks: dict[str, bool] = {}

        if design.get("status") != "built" or not design.get("png"):
            return {"agent": "visual_reviewer", "approved": False, "score": 0,
                    "issues": [design.get("reason") or design.get("render", {}).get("error") or "Design was not built."],
                    "checks": {}}

        png = Path(design["png"])
        html = Path(design["html"]).read_text(encoding="utf-8")
        visible_text = re.sub(r"<[^>]+>", " ", re.sub(r"<img[^>]*>", "", html))
        visible_text = re.sub(r"\s+", " ", visible_text).lower()

        from PIL import Image

        image = Image.open(png).convert("RGB")
        checks["size_1080x1350"] = image.size == CANVAS
        if not checks["size_1080x1350"]:
            issues.append(f"Exported size is {image.size}, expected {CANVAS}.")

        bars = _black_bars(image)
        checks["no_black_bars"] = not bars
        if bars:
            issues.append(f"Black bars in the photo at x={bars}. The crop went outside the source image.")
            mistake_memory.append_mistake(
                "design_defect", f"Rendered post had black bars at x={bars}.",
                "Never crop wider than the source image: scale to cover the frame, then crop inside it.",
                "visual_reviewer_auto")

        alts = [htmllib.unescape(a) for a in re.findall(r'alt="([^"]*)"', html)]
        approved_names = {name.lower() for _, name in BRAND_LOGO_FILES}
        brand_alts = [a for a in alts if a.lower() not in approved_names and "logo" not in a.lower() and "render" not in a.lower()]
        checks["only_approved_brand_logos"] = not brand_alts
        if brand_alts:
            issues.append(f"Image not on the approved list: {brand_alts}.")

        found = [name for name in UNAPPROVED_BRAND_NAMES if re.search(rf"\b{re.escape(name)}\b", visible_text)]
        checks["no_unapproved_brand_text"] = not found
        if found:
            issues.append(f"Unapproved brand names in text: {found}.")
            mistake_memory.append_mistake("fake_amenity", f"Unapproved brand text on a post: {found}.",
                                          "Only the 12 owner-approved brands may appear. Never name any other brand.", "visual_reviewer_auto")

        source = Path(design.get("source_image", "")).name
        checks["safe_source_render"] = not source.startswith(SIGNAGE_RISK_PREFIXES)
        if not checks["safe_source_render"]:
            issues.append(f"{source} shows shop signs for unapproved brands.")
            mistake_memory.append_mistake("fake_amenity", f"Used {source}, which shows unapproved shop signs.",
                                          "Do not use elevation renders as post images. Use the aerial with the north building masked or cropped.", "visual_reviewer_auto")

        forbidden = [p for p in FORBIDDEN_PATTERNS if re.search(p, visible_text)]
        for claim in project.get("forbidden_claims", []):
            if str(claim).lower() in visible_text:
                forbidden.append(str(claim))
        checks["no_forbidden_claims"] = not forbidden
        if forbidden:
            issues.append(f"Forbidden wording on the post: {forbidden}.")

        phone = re.sub(r"\D", "", project.get("contact", {}).get("phone", ""))
        checks["correct_phone"] = bool(phone) and phone in re.sub(r"\D", "", visible_text)
        if not checks["correct_phone"]:
            issues.append("Owner-confirmed phone number is missing.")

        checks["artists_impression_note"] = "artist's impression" in visible_text or "artist&#39;s impression" in visible_text
        if not checks["artists_impression_note"]:
            issues.append("Missing the \"Artist's impression\" note while construction is not finished.")

        checks["logo_present"] = any("logo" in a.lower() for a in alts)
        if not checks["logo_present"]:
            issues.append("Shrih Plaza logo is missing.")

        sizes = [int(s) for s in re.findall(r"font-size:(\d+)px", html)]
        checks["min_font_size_14"] = not sizes or min(sizes) >= 14
        if not checks["min_font_size_14"]:
            issues.append(f"Text as small as {min(sizes)}px will not read on a phone.")

        metrics = design.get("layout_metrics") or {}
        checks["headline_fits"] = bool(metrics.get("headline_fits", True))
        if not checks["headline_fits"]:
            issues.append("The headline does not fit in three lines; it would be cut off. Shorten the hook.")
            mistake_memory.append_mistake("design_defect", "Headline was too long and got cut off.",
                                          "Keep the hook to about 6 words so the headline fits in three lines.", "visual_reviewer_auto")
        checks["text_does_not_collide"] = bool(metrics.get("text_block_ok", True))
        if not checks["text_does_not_collide"]:
            issues.append("Headline and support text run into the photo area or each other.")

        sig = design_history.signature(str(design.get("layout")), Path(design.get("source_image", "")).name.split(".")[0],
                                       f"{design.get('layout')}-template")
        copied = design_history.repeats(sig)
        checks["new_design_not_a_repeat"] = not copied
        if copied:
            issues.append(f"Same layout and photo or type as approved design {copied[0]}. An approved design is a quality bar, "
                          "not a template: make a completely new design, not new text on the old one.")

        combo = (design.get("layout"), design.get("palette"))
        checks["not_a_denied_combination"] = combo not in owner_decisions.rejected_combos()
        if not checks["not_a_denied_combination"]:
            issues.append(f"The owner denied the {combo[0]} layout in {combo[1]} colours before.")

        approved = all(checks.values())
        return {"agent": "visual_reviewer", "approved": approved, "score": 10 if approved else 0,
                "issues": issues, "checks": checks}
