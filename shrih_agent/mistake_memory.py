"""Structured record of past architecture-preservation failures.

Every time a generated image changes something it must not (an extra floor, a
different window grid, a hallucinated balcony), that failure is logged here.
Every future image-edit prompt pulls the accumulated avoid-instructions from
this file, so the same mistake is explicitly forbidden again rather than
silently risking a repeat. This is what makes the system "learn" -- there is
no model fine-tuning here, just an ever-growing list of do-not-repeat clauses
fed back into every subsequent prompt.
"""

from datetime import datetime
from typing import Any

from .io import read_json, write_json
from .paths import MEMORY_DIR

MISTAKE_MEMORY_PATH = MEMORY_DIR / "mistake_memory.json"

CATEGORIES = {
    "floor_count",
    "window_grid",
    "balcony",
    "entrance",
    "facade_material",
    "building_outline",
    "fake_amenity",
    "misleading_completion",
    "design_defect",
    "other",
}


def load_mistakes() -> dict[str, Any]:
    if not MISTAKE_MEMORY_PATH.exists():
        return {"mistakes": []}
    return read_json(MISTAKE_MEMORY_PATH)


def append_mistake(category: str, description: str, avoid_instruction: str, source: str) -> dict[str, Any]:
    category = category if category in CATEGORIES else "other"
    data = load_mistakes()
    data.setdefault("mistakes", []).append({
        "id": f"mistake_{len(data['mistakes']) + 1:04d}",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "category": category,
        "description": description,
        "avoid_instruction": avoid_instruction,
        "source": source,
    })
    write_json(MISTAKE_MEMORY_PATH, data)
    return data


def avoid_instructions() -> list[str]:
    data = load_mistakes()
    seen: set[str] = set()
    instructions: list[str] = []
    for mistake in data.get("mistakes", []):
        instruction = str(mistake.get("avoid_instruction", "")).strip()
        if instruction and instruction not in seen:
            seen.add(instruction)
            instructions.append(instruction)
    return instructions
