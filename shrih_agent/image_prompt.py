"""Builds the actual text sent to the image-editing model and the
architecture-verification model, from the brand kit, the architecture policy,
and everything the system has learned from past mistakes.
"""

from typing import Any

from . import mistake_memory
from .io import read_text
from .paths import BRAND_KIT_DIR, POLICIES_DIR

ARCHITECTURE_POLICY_PATH = POLICIES_DIR / "architecture_preservation_policy.md"
AI_BRAND_PROMPT_PATH = BRAND_KIT_DIR / "ai-brand-prompt.md"

CHECKLIST_ITEMS = [
    ("building_outline_matches", "Building outline matches"),
    ("floor_count_matches", "Floor count matches"),
    ("window_grid_matches", "Window grid matches"),
    ("balcony_positions_match", "Balcony positions match"),
    ("entrance_shape_matches", "Entrance shape matches"),
    ("elevation_materials_match", "Elevation materials/design match"),
    ("no_fake_amenities_added", "No fake amenities added"),
    ("no_misleading_completion_state", "No misleading completion state"),
]

_CHECKLIST_KEY_TO_CATEGORY = {
    "building_outline_matches": "building_outline",
    "floor_count_matches": "floor_count",
    "window_grid_matches": "window_grid",
    "balcony_positions_match": "balcony",
    "entrance_shape_matches": "entrance",
    "elevation_materials_match": "facade_material",
    "no_fake_amenities_added": "fake_amenity",
    "no_misleading_completion_state": "misleading_completion",
}


def category_for_checklist_key(key: str) -> str:
    return _CHECKLIST_KEY_TO_CATEGORY.get(key, "other")

_ALLOWED_EDITS = [
    "Upscale", "Denoise", "Sharpen", "Improve brightness and contrast",
    "Improve color balance", "Replace dull sky", "Add realistic daylight or evening ambience",
    "Clean temporary clutter",
    "Add realistic people, cars, greenery, or approved seasonal/festival decor "
    "(e.g. a Krishna Janmashtami display) only if they do not block or alter important architecture",
]

_FORBIDDEN_EDITS = [
    "Change building height", "Change floor count", "Change facade/elevation design",
    "Change balcony shapes", "Change windows", "Change entrance design",
    "Change structural proportions", "Add unapproved amenities",
    "Add signs, shops, or branding that are not approved",
    "Make the project look completed if the source image is a construction/proposed render, "
    "in a way that would mislead buyers",
]


def build_image_edit_prompt(
    image_brief: dict[str, Any],
    brand: dict[str, Any] | None = None,
    extra_corrective_instructions: list[str] | None = None,
) -> str:
    brand = brand or {}
    scene_direction = str(image_brief.get("scene_direction", "")).strip()
    lighting = str(image_brief.get("lighting", "")).strip()
    seasonal_elements = [str(item).strip() for item in image_brief.get("seasonal_elements", []) if str(item).strip()]
    framing = str(image_brief.get("framing", "")).strip()

    lines = [
        "Edit this real estate elevation photo for premium social media marketing. "
        "This is a REAL, existing building -- SHRIH PLAZA. Do not invent a different building.",
        "",
        "Allowed edits:",
        *[f"- {item}" for item in _ALLOWED_EDITS],
        "",
        "Strictly forbidden edits:",
        *[f"- {item}" for item in _FORBIDDEN_EDITS],
    ]

    if scene_direction:
        lines += ["", f"Scene direction: {scene_direction}"]
    if lighting:
        lines += [f"Lighting: {lighting}"]
    if framing:
        lines += [f"Framing/angle: {framing}"]
    if seasonal_elements:
        lines += [f"Approved seasonal/festival elements to add (do not obscure the building): {', '.join(seasonal_elements)}"]

    visual_style = brand.get("visual_style")
    if visual_style:
        lines += ["", "Brand visual style: " + "; ".join(visual_style)]

    avoid = mistake_memory.avoid_instructions()
    if avoid:
        lines += [
            "",
            "Do NOT repeat these specific mistakes from past generations of this same building:",
            *[f"- {item}" for item in avoid],
        ]

    if extra_corrective_instructions:
        lines += [
            "",
            "This is a corrective retry. Specifically fix:",
            *[f"- {item}" for item in extra_corrective_instructions],
        ]

    lines += [
        "",
        "Output should look premium, realistic, and truthful to the real building.",
    ]
    return "\n".join(lines)


def build_architecture_checklist_prompt(policy_text: str | None = None) -> str:
    policy_text = policy_text if policy_text is not None else _read_policy_text()
    checklist_json_keys = ", ".join(f'"{key}"' for key, _ in CHECKLIST_ITEMS)
    return "\n".join([
        "You are the architecture-preservation guard for a real estate brand. "
        "Compare the ORIGINAL reference photo of the building against the CANDIDATE edited photo.",
        "",
        "Policy the candidate must follow:",
        policy_text,
        "",
        "For each checklist item below, decide true (matches the original, or the change is only an "
        "allowed lighting/sky/ambience/seasonal-decor edit) or false (the building's actual structure "
        "changed in a way the policy forbids).",
        f"Checklist keys: {checklist_json_keys}",
        "",
        "Return ONLY this JSON shape, no markdown fences:",
        '{"approved": <true only if every checklist value is true>, '
        '"checklist": {"<key>": <true|false>, ...}, "issues": ["<short description of each false item>"]}',
    ])


def _read_policy_text() -> str:
    if ARCHITECTURE_POLICY_PATH.exists():
        return read_text(ARCHITECTURE_POLICY_PATH)
    return "Never change building height, floor count, facade, windows, balconies, entrance, or proportions."
