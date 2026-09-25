"""Design history: every poster's composition signature, so no design is ever reused.

Owner rule (2026-09-26): an approved design is a quality bar, not a template.
The next post must be a completely new design; changing only the text on an
approved design does not count. A signature records the parts that make a
design look the same: layout family, photo, hero crop, and type treatment.
"""

from datetime import datetime
from typing import Any

from .io import read_json, write_json
from .paths import MEMORY_DIR

HISTORY_PATH = MEMORY_DIR / "design_history.json"
RULE = ("An approved design is a quality bar, never a template. Every new post must be a completely new design: "
        "new layout family, new photo or crop, new type treatment. Changing only the text is not a new design.")


def load_history() -> list[dict[str, Any]]:
    if not HISTORY_PATH.exists():
        return []
    return list(read_json(HISTORY_PATH).get("designs", []))


def signature(layout: str, photo: str, type_treatment: str) -> dict[str, str]:
    return {"layout": layout, "photo": photo, "type_treatment": type_treatment}


def record(post_id: str, sig: dict[str, str], status: str) -> None:
    designs = [d for d in load_history() if d.get("post_id") != post_id]
    designs.append({"post_id": post_id, **sig, "status": status, "created": datetime.now().isoformat(timespec="seconds")})
    write_json(HISTORY_PATH, {"rule": RULE, "designs": designs})


def repeats(sig: dict[str, str], exclude_post: str = "") -> list[str]:
    """Past designs this one would copy. Same layout family plus the same photo, or plus the same
    type treatment, reads as the same poster with new text."""
    hits = []
    for d in load_history():
        if d.get("post_id") == exclude_post:
            continue
        same_layout = d.get("layout") == sig["layout"]
        if same_layout and (d.get("photo") == sig["photo"] or d.get("type_treatment") == sig["type_treatment"]):
            hits.append(d["post_id"])
    return hits
